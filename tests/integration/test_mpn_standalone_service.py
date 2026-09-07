"""
OSKAR — standalone MPN changes at the service layer (ADR-016).

Migration 0034 made ecn_mpns self-contained (ecn_id + item_number on the row,
ecn_item_id nullable). This covers the service layer that has to stop reaching
its ECN through ecn_items.

Every read path used `JOIN ecn_items i ON i.id = m.ecn_item_id` — an INNER
join. With a NULL ecn_item_id those rows vanish from the result set silently:
no error, just an MPN that does not appear on the tab, is never queued to
Movex, and never reaches the MPN master. The two that matter most:

  * helpers.py:_count_ecn_content — feeds the submit guard. A standalone MPN
    not counted means an MPN-only ECN cannot be submitted at all.
  * workflow.py:_queue_alias_outbox — a standalone MPN not queued means the
    alias is never written to M3, and nothing reports a failure.

ADR-014 named this exact class of trap for BOM changes (its "one trap worth
naming" section, about the snapshot stamp-back silently disabling the
concurrency gate). Same shape here, so it gets the same treatment: tests that
assert the standalone row is actually picked up, not just that the query runs.
"""
from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.ecn.helpers import _count_ecn_content
from src.services.ecn.models import ECNCreateRequest, ECNNotFound
from src.services.ecn.service import ECNService

pytestmark = pytest.mark.asyncio

_ACTOR = "hsalazar"
_FACILITY = "L"


async def _make_ecn(db_session: AsyncSession) -> str:
    """An ECN with no items on it at all — the case ADR-016 unlocks."""
    svc = ECNService(db_session)
    ecn = await svc.create(
        ECNCreateRequest(
            facility=_FACILITY, title="Standalone MPN ECN (ADR-016)",
            is_new_item=False, routing_changes=False, operation_changes=False,
            new_parts=False, change_parts=True, bom_changes=False,
            lead_time_changes=False, change_to_documents=False,
            requires_customer_approval=False, regulatory_impact=False,
        ),
        _ACTOR,
    )
    return ecn.id


class TestCreateStandaloneMpn:
    async def test_create_without_an_item_id_succeeds(self, db_session: AsyncSession):
        """The whole point of ADR-016: an MPN change with no item row."""
        ecn_id = await _make_ecn(db_session)
        svc = ECNService(db_session)

        detail = await svc.create_mpn(
            ecn_id,
            item_id=None,
            item_number="LF200010",
            mpn="CRCW060310K0FKEA",
            manufacturer="Vishay",
        )

        assert detail.mpn == "CRCW060310K0FKEA"
        assert detail.item_number == "LF200010"
        assert detail.ecn_item_id is None

    async def test_item_scoped_create_still_works_and_links(self, db_session: AsyncSession):
        """The item-scoped path is kept, not replaced — ADR-014 kept both for
        BOM changes and the same reasoning applies. When an item IS given, the
        convenience link is populated and item_number derived from it."""
        ecn_id = await _make_ecn(db_session)
        svc = ECNService(db_session)
        item = await svc.create_item(ecn_id, line_number=1, item_number="LF100001")

        detail = await svc.create_mpn(
            ecn_id, item_id=item.id, mpn="MPN-LINKED",
        )

        assert detail.ecn_item_id == item.id
        assert detail.item_number == "LF100001"


class TestStandaloneMpnsAreVisible:
    """Each of these fails against an INNER JOIN through ecn_items."""

    async def test_list_all_mpns_includes_standalone_rows(self, db_session: AsyncSession):
        ecn_id = await _make_ecn(db_session)
        svc = ECNService(db_session)
        await svc.create_mpn(ecn_id, item_id=None, item_number="LF200010", mpn="STANDALONE-1")

        mpns = await svc.list_all_mpns(ecn_id)

        assert [m.mpn for m in mpns] == ["STANDALONE-1"]
        assert mpns[0].item_number == "LF200010"

    async def test_standalone_mpn_counts_as_ecn_content(self, db_session: AsyncSession):
        """Feeds the submit guard. If this returns 0, an MPN-only ECN cannot
        be submitted — the workflow reports "no content" for an ECN that
        visibly has an MPN on it."""
        ecn_id = await _make_ecn(db_session)
        svc = ECNService(db_session)
        await svc.create_mpn(ecn_id, item_id=None, item_number="LF200010", mpn="COUNTS-1")

        assert await _count_ecn_content(db_session, ecn_id) == 1

    async def test_mixed_linked_and_standalone_are_both_listed(
        self, db_session: AsyncSession
    ):
        ecn_id = await _make_ecn(db_session)
        svc = ECNService(db_session)
        item = await svc.create_item(ecn_id, line_number=1, item_number="LF100001")
        await svc.create_mpn(ecn_id, item_id=item.id, mpn="LINKED-1")
        await svc.create_mpn(ecn_id, item_id=None, item_number="LF200010", mpn="STANDALONE-1")

        mpns = await svc.list_all_mpns(ecn_id)

        assert {m.mpn for m in mpns} == {"LINKED-1", "STANDALONE-1"}


class TestUpdateAndDeleteOnStandaloneRows:
    """ADR-014 left ECN-scoped BOM changes with no PATCH/DELETE route at all —
    a row you could create and then never edit or remove. That gap is not
    repeated here; both must work on a NULL-item row."""

    async def test_update_a_standalone_mpn(self, db_session: AsyncSession):
        ecn_id = await _make_ecn(db_session)
        svc = ECNService(db_session)
        created = await svc.create_mpn(
            ecn_id, item_id=None, item_number="LF200010", mpn="EDIT-ME"
        )

        updated = await svc.update_mpn(ecn_id, created.id, manufacturer="Yageo")

        assert updated.manufacturer == "Yageo"

    async def test_delete_a_standalone_mpn(self, db_session: AsyncSession):
        ecn_id = await _make_ecn(db_session)
        svc = ECNService(db_session)
        created = await svc.create_mpn(
            ecn_id, item_id=None, item_number="LF200010", mpn="DELETE-ME"
        )

        await svc.delete_mpn(ecn_id, created.id)

        assert await svc.list_all_mpns(ecn_id) == []

    async def test_cannot_touch_an_mpn_belonging_to_another_ecn(
        self, db_session: AsyncSession
    ):
        """Ownership was previously proven via the item join. With ecn_id on
        the row it becomes a direct predicate — but it must still be checked,
        or one ECN could edit another's MPNs."""
        ecn_a = await _make_ecn(db_session)
        ecn_b = await _make_ecn(db_session)
        svc = ECNService(db_session)
        mpn_on_a = await svc.create_mpn(
            ecn_a, item_id=None, item_number="LF200010", mpn="BELONGS-TO-A"
        )

        with pytest.raises(ECNNotFound):
            await svc.update_mpn(ecn_b, mpn_on_a.id, manufacturer="Nope")


class TestDeletingAnItemLeavesItsMpns:
    async def test_item_delete_sets_the_link_null_and_keeps_the_mpn(
        self, db_session: AsyncSession
    ):
        """The FK moved from ON DELETE RESTRICT to SET NULL. Previously this
        raised a raw IntegrityError 500; now the MPN survives with its
        item_number intact, which is why item_number is denormalised onto the
        row rather than only reachable through the link."""
        ecn_id = await _make_ecn(db_session)
        svc = ECNService(db_session)
        item = await svc.create_item(ecn_id, line_number=1, item_number="LF100001")
        await svc.create_mpn(ecn_id, item_id=item.id, mpn="SURVIVOR")

        await svc.delete_item(ecn_id, item.id)

        mpns = await svc.list_all_mpns(ecn_id)
        assert len(mpns) == 1
        assert mpns[0].mpn == "SURVIVOR"
        assert mpns[0].ecn_item_id is None
        assert mpns[0].item_number == "LF100001"
