"""
OSKAR — per-item ECN history (Slice F, I2-12; Stargile ECNChangesBrowse parity).

Against real Postgres, because the whole feature is one UNION ALL query —
mocking the SQL would test nothing that matters.

Rows are seeded with raw INSERTs rather than via ECNService.create(). That is
deliberate: I2-18 records that the db_session fixture hangs on the SECOND
consecutive ECNService.create() in one file on this dev machine, so a file
needing several ECNs cannot use the service layer yet. Raw seeding also keeps
these tests focused on the query rather than on workflow rules.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
import sqlalchemy as sa

from src.services.bom.item_history import (
    CHANGE_BOM_COMPONENT,
    CHANGE_BOM_PARENT,
    CHANGE_ITEM,
    CHANGE_MPN,
    get_item_ecn_history,
)

pytestmark = pytest.mark.asyncio

_ITEM = "LFHIST00001"
_OTHER_PARENT = "LFHIST00099"
_COMPONENT = "LFHIST00050"


def _ts(day: str) -> datetime:
    """'2026-01-01' -> a real tz-aware datetime.

    asyncpg binds parameters by type, not by string coercion — a date string
    is rejected outright rather than parsed.
    """
    return datetime.fromisoformat(day).replace(tzinfo=timezone.utc)


async def _mk_ecn(session, number: str, *, created_at: str, title="Test ECN") -> str:
    ecn_id = str(uuid.uuid4())
    await session.execute(
        sa.text("""
            INSERT INTO ecn_instances
                (id, ecn_number, facility, title, originator_username, status, created_at)
            VALUES (:id, :num, 'L', :title, 'hsalazar', 30, :created_at)
        """),
        {"id": ecn_id, "num": number, "title": title, "created_at": _ts(created_at)},
    )
    return ecn_id


async def _mk_item(session, ecn_id: str, item_number: str, *, line=1, name="Widget") -> str:
    # effectivity_type is NOT NULL with no default and a CHECK limiting it to
    # DATE | ECN | IMMEDIATE (DATE additionally requires effectivity_from).
    # IMMEDIATE is the one that needs no companion column.
    item_id = str(uuid.uuid4())
    await session.execute(
        sa.text("""
            INSERT INTO ecn_items
                (id, ecn_id, line_number, item_number, item_name, effectivity_type)
            VALUES (:id, :ecn_id, :line, :itno, :name, 'IMMEDIATE')
        """),
        {"id": item_id, "ecn_id": ecn_id, "line": line, "itno": item_number, "name": name},
    )
    return item_id


async def _mk_bom_change(
    session, ecn_id, *, parent: str, component: str, change_type="ADD", item_id=None
):
    await session.execute(
        sa.text("""
            INSERT INTO ecn_bom_changes
                (id, ecn_id, ecn_item_id, parent_item_number, change_type,
                 component_number, bom_type)
            VALUES (:id, :ecn_id, :item_id, :parent, :ct, :component, 'M')
        """),
        {
            "id": str(uuid.uuid4()), "ecn_id": ecn_id, "item_id": item_id,
            "parent": parent, "ct": change_type, "component": component,
        },
    )


async def _mk_mpn(session, item_id: str, mpn: str, *, manufacturer="YAGEO", default=False):
    await session.execute(
        sa.text("""
            INSERT INTO ecn_mpns (id, ecn_item_id, mpn, manufacturer, is_default)
            VALUES (:id, :item_id, :mpn, :mfr, :dflt)
        """),
        {
            "id": str(uuid.uuid4()), "item_id": item_id, "mpn": mpn,
            "mfr": manufacturer, "dflt": default,
        },
    )


class TestEmptyHistory:
    async def test_unknown_item_returns_empty_not_error(self, db_session):
        """A part nobody has changed is a legitimate answer, not a 404."""
        entries, total = await get_item_ecn_history(db_session, "LFNOSUCH999")
        assert entries == []
        assert total == 0


class TestItemMasterChanges:
    async def test_item_master_change_appears(self, db_session):
        ecn_id = await _mk_ecn(db_session, "ECN-H001", created_at="2026-01-01")
        await _mk_item(db_session, ecn_id, _ITEM)

        entries, total = await get_item_ecn_history(db_session, _ITEM)

        assert total == 1
        assert entries[0].change_type == CHANGE_ITEM
        assert entries[0].ecn_number == "ECN-H001"
        assert entries[0].related_item is None

    async def test_carries_ecn_header_context(self, db_session):
        """Actionable without a second lookup — that is the point of joining
        the ECN header in rather than returning bare ids."""
        ecn_id = await _mk_ecn(
            db_session, "ECN-H002", created_at="2026-01-02", title="Change the widget"
        )
        await _mk_item(db_session, ecn_id, _ITEM)

        entries, _ = await get_item_ecn_history(db_session, _ITEM)

        e = entries[0]
        assert e.ecn_title == "Change the widget"
        assert e.originator_username == "hsalazar"
        assert e.facility == "L"
        assert e.ecn_status == 30


class TestBOMRelationships:
    async def test_item_as_bom_parent(self, db_session):
        ecn_id = await _mk_ecn(db_session, "ECN-H003", created_at="2026-01-03")
        await _mk_bom_change(db_session, ecn_id, parent=_ITEM, component=_COMPONENT)

        entries, _ = await get_item_ecn_history(db_session, _ITEM)

        assert entries[0].change_type == CHANGE_BOM_PARENT
        assert entries[0].related_item == _COMPONENT
        assert _COMPONENT in entries[0].detail

    async def test_item_as_bom_component(self, db_session):
        """The case a user checking only the item's own records would miss —
        someone else's BOM changed, and this item is why."""
        ecn_id = await _mk_ecn(db_session, "ECN-H004", created_at="2026-01-04")
        await _mk_bom_change(
            db_session, ecn_id, parent=_OTHER_PARENT, component=_ITEM, change_type="DELETE"
        )

        entries, _ = await get_item_ecn_history(db_session, _ITEM)

        assert entries[0].change_type == CHANGE_BOM_COMPONENT
        assert entries[0].related_item == _OTHER_PARENT
        assert "DELETE" in entries[0].detail

    async def test_both_directions_are_reported_separately(self, db_session):
        """An item can be a parent in one ECN and a component in another —
        both must show, and be distinguishable."""
        ecn_a = await _mk_ecn(db_session, "ECN-H005", created_at="2026-01-05")
        await _mk_bom_change(db_session, ecn_a, parent=_ITEM, component=_COMPONENT)
        ecn_b = await _mk_ecn(db_session, "ECN-H006", created_at="2026-01-06")
        await _mk_bom_change(db_session, ecn_b, parent=_OTHER_PARENT, component=_ITEM)

        entries, total = await get_item_ecn_history(db_session, _ITEM)

        assert total == 2
        assert {e.change_type for e in entries} == {CHANGE_BOM_PARENT, CHANGE_BOM_COMPONENT}


class TestMPNChanges:
    async def test_mpn_change_appears(self, db_session):
        ecn_id = await _mk_ecn(db_session, "ECN-H007", created_at="2026-01-07")
        item_id = await _mk_item(db_session, ecn_id, _ITEM)
        await _mk_mpn(db_session, item_id, "RC0402FR-0710KL", default=True)

        entries, total = await get_item_ecn_history(db_session, _ITEM)

        # The item row itself also counts as history, so 2 entries
        assert total == 2
        mpn_entries = [e for e in entries if e.change_type == CHANGE_MPN]
        assert len(mpn_entries) == 1
        assert "RC0402FR-0710KL" in mpn_entries[0].detail
        assert "YAGEO" in mpn_entries[0].detail
        assert "[default]" in mpn_entries[0].detail

    async def test_non_default_mpn_not_marked_default(self, db_session):
        ecn_id = await _mk_ecn(db_session, "ECN-H008", created_at="2026-01-08")
        item_id = await _mk_item(db_session, ecn_id, _ITEM)
        await _mk_mpn(db_session, item_id, "ALT-MPN-1", default=False)

        entries, _ = await get_item_ecn_history(db_session, _ITEM)
        mpn_entry = next(e for e in entries if e.change_type == CHANGE_MPN)
        assert "[default]" not in mpn_entry.detail


class TestAllFourSourcesTogether:
    async def test_every_change_type_appears_in_one_result(self, db_session):
        """The whole point of the view: four structurally different tables,
        shown together, because checking only one draws a wrong conclusion."""
        ecn_id = await _mk_ecn(db_session, "ECN-H009", created_at="2026-01-09")
        item_id = await _mk_item(db_session, ecn_id, _ITEM)
        await _mk_mpn(db_session, item_id, "MPN-X")
        await _mk_bom_change(
            db_session, ecn_id, parent=_ITEM, component=_COMPONENT, item_id=item_id
        )
        await _mk_bom_change(
            db_session, ecn_id, parent=_OTHER_PARENT, component=_ITEM, item_id=item_id
        )

        entries, total = await get_item_ecn_history(db_session, _ITEM)

        assert total == 4
        assert {e.change_type for e in entries} == {
            CHANGE_ITEM, CHANGE_MPN, CHANGE_BOM_PARENT, CHANGE_BOM_COMPONENT
        }

    async def test_one_ecn_yields_several_entries(self, db_session):
        """Separate facts stay separate rows — collapsing per ECN would hide
        exactly the detail this view exists to show."""
        ecn_id = await _mk_ecn(db_session, "ECN-H010", created_at="2026-01-10")
        item_id = await _mk_item(db_session, ecn_id, _ITEM)
        await _mk_bom_change(
            db_session, ecn_id, parent=_ITEM, component=_COMPONENT, item_id=item_id
        )

        entries, _ = await get_item_ecn_history(db_session, _ITEM)
        assert len({e.ecn_number for e in entries}) == 1
        assert len(entries) == 2


class TestOrderingAndPaging:
    async def test_newest_first(self, db_session):
        old = await _mk_ecn(db_session, "ECN-H011", created_at="2026-01-01")
        await _mk_item(db_session, old, _ITEM, line=1)
        new = await _mk_ecn(db_session, "ECN-H012", created_at="2026-06-01")
        await _mk_item(db_session, new, _ITEM, line=1)

        entries, _ = await get_item_ecn_history(db_session, _ITEM)

        assert entries[0].ecn_number == "ECN-H012"
        assert entries[1].ecn_number == "ECN-H011"

    async def test_limit_and_offset(self, db_session):
        for i, day in enumerate(["2026-02-01", "2026-02-02", "2026-02-03"], start=1):
            ecn_id = await _mk_ecn(db_session, f"ECN-H02{i}", created_at=day)
            await _mk_item(db_session, ecn_id, _ITEM)

        page1, total = await get_item_ecn_history(db_session, _ITEM, limit=2, offset=0)
        page2, _ = await get_item_ecn_history(db_session, _ITEM, limit=2, offset=2)

        assert total == 3
        assert len(page1) == 2
        assert len(page2) == 1
        # total counts everything, not just the page
        assert {e.ecn_number for e in page1} & {e.ecn_number for e in page2} == set()

    async def test_item_number_is_trimmed(self, db_session):
        ecn_id = await _mk_ecn(db_session, "ECN-H030", created_at="2026-03-01")
        await _mk_item(db_session, ecn_id, _ITEM)

        entries, total = await get_item_ecn_history(db_session, f"  {_ITEM}  ")
        assert total == 1
        assert entries[0].ecn_number == "ECN-H030"
