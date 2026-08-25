"""
Integration tests — BOM snapshot capture at submit/resubmit (Slice E, ADR-012
D2/D6/R8).

At the submit and resubmit(restart) triggers, workflow.py's transition()
captures one bom_snapshots row (reason='ecn_submit') per DISTINCT parent
item referenced by the ECN's ecn_bom_changes rows, via Slice D's
insert_snapshot(). This is the baseline the dc_approve concurrency gate
(test_concurrency_gate.py, next scope item) diffs the live BOM against.

Resilience (deliberate, per the plan): if the ERP call fails (adapter
raises, e.g. BOMNotFound or a connection error), snapshot capture for that
item is skipped with a logged warning — submit must NOT be blocked by an
ERP outage. An ECN with no ecn_bom_changes rows captures nothing (no-op,
not an error) — the vast majority of ECNs (routing-only, MPN-only, etc.)
have no BOM changes at all.

Uses tests/helpers/fake_erp.py's FakeERPAdapter, which raises BOMNotFound
for any item_number with no matching fixture — this doubles as the "ERP
call fails" case without needing a custom raising stub.

NOTE (I2-18 workaround, confirmed by the coordinator 2026-08-07): a
pre-existing bug in tests/integration/conftest.py's db_session fixture
teardown (RuntimeError: Event loop is closed, Windows/Python 3.14 Proactor-
loop race) means a SECOND consecutive test in the same pytest invocation
that calls ECNService.create() can hang forever on a lock. Every test class
below is self-contained (creates its own ECN) but MUST be run one test at a
time (`pytest tests/services/bom/test_snapshot_at_submit.py::Class::test`),
not as a whole-file invocation, until I2-18 is fixed.
"""
from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.ecn.models import (
    BOMChangeRequest,
    ECNCreateRequest,
    ECNStatusTransitionRequest,
)
from src.services.ecn.service import ECNService
from tests.helpers.fake_erp import FakeERPAdapter

pytestmark = pytest.mark.asyncio

_ACTOR = "hsalazar"
_FACILITY = "L"

# FakeERPAdapter serves this fixture (tests/fixtures/bom/single_level.json,
# see tests/helpers/fake_erp.py's _BOM_FIXTURES map) for LF100001.
_FIXTURE_ITEM = "LF100001"
_NO_FIXTURE_ITEM = "LFNOFIXTURE9999"


async def _make_ecn_with_bom_change(
    db_session: AsyncSession, *, parent_item_number: str, component_number: str = "LF200099",
) -> tuple[str, str]:
    svc = ECNService(db_session)
    req = ECNCreateRequest(
        facility=_FACILITY, title="Snapshot-at-submit test ECN",
        is_new_item=False, routing_changes=False, operation_changes=False,
        new_parts=False, change_parts=True, bom_changes=True,
        lead_time_changes=False, change_to_documents=False,
        requires_customer_approval=False, regulatory_impact=False,
    )
    ecn = await svc.create(req, _ACTOR)
    item = await svc.create_item(ecn.id, line_number=10, item_number=parent_item_number)
    await svc.create_bom_change(
        ecn.id, item.id,
        BOMChangeRequest(change_type="ADD", component_number=component_number, quantity=1.0),
    )
    return ecn.id, item.id


class TestSnapshotCapturedAtSubmit:
    async def test_submit_captures_one_snapshot_for_bom_change_parent_item(
        self, db_session: AsyncSession
    ):
        ecn_id, _item_id = await _make_ecn_with_bom_change(
            db_session, parent_item_number=_FIXTURE_ITEM
        )
        svc = ECNService(db_session)
        erp = FakeERPAdapter()
        await svc.transition(
            ecn_id,
            ECNStatusTransitionRequest(trigger="submit", actor_role="OR"),
            actor_username=_ACTOR,
            erp=erp,
        )

        rows = await db_session.execute(
            sa.text(
                "SELECT item_number, facility, reason, ecn_id FROM bom_snapshots "
                "WHERE ecn_id = :ecn_id"
            ),
            {"ecn_id": ecn_id},
        )
        snapshots = rows.mappings().all()
        assert len(snapshots) == 1
        assert snapshots[0]["item_number"] == _FIXTURE_ITEM
        assert snapshots[0]["reason"] == "ecn_submit"

    async def test_bom_change_row_gets_snapshot_id_populated(self, db_session: AsyncSession):
        ecn_id, item_id = await _make_ecn_with_bom_change(
            db_session, parent_item_number=_FIXTURE_ITEM
        )
        svc = ECNService(db_session)
        erp = FakeERPAdapter()
        await svc.transition(
            ecn_id,
            ECNStatusTransitionRequest(trigger="submit", actor_role="OR"),
            actor_username=_ACTOR,
            erp=erp,
        )

        changes = await svc.list_bom_changes(ecn_id, item_id)
        assert len(changes) == 1
        assert changes[0].snapshot_id is not None

    async def test_no_bom_changes_captures_nothing(self, db_session: AsyncSession):
        """An ECN with zero ecn_bom_changes rows is the common case (routing-
        only, MPN-only, etc.) — must be a silent no-op, not an error.

        The ECN carries one item so it has content: since ADR-014 the submit
        guard requires an ECN to hold at least one item, routing operation,
        BOM change or MPN. That matches this test's own stated scenario (a
        routing-only ECN) — it previously submitted an ECN that was empty on
        every tab, which the guard's docstring had always claimed to reject.
        """
        svc = ECNService(db_session)
        req = ECNCreateRequest(
            facility=_FACILITY, title="No BOM changes ECN",
            is_new_item=False, routing_changes=True, operation_changes=False,
            new_parts=False, lead_time_changes=False, change_to_documents=False,
            requires_customer_approval=False, regulatory_impact=False,
        )
        ecn = await svc.create(req, _ACTOR)
        await svc.create_item(ecn.id, line_number=10, item_number="LFNOBOM001")
        erp = FakeERPAdapter()
        await svc.transition(
            ecn.id,
            ECNStatusTransitionRequest(trigger="submit", actor_role="OR"),
            actor_username=_ACTOR,
            erp=erp,
        )

        rows = await db_session.execute(
            sa.text("SELECT COUNT(*) FROM bom_snapshots WHERE ecn_id = :ecn_id"),
            {"ecn_id": ecn.id},
        )
        assert rows.scalar_one() == 0

    async def test_erp_failure_does_not_block_submit(self, db_session: AsyncSession):
        """FakeERPAdapter.get_bom raises BOMNotFound for any item without a
        fixture — this is the 'ERP call fails' resilience case: submit must
        still succeed, just with no snapshot captured for that item."""
        ecn_id, _item_id = await _make_ecn_with_bom_change(
            db_session, parent_item_number=_NO_FIXTURE_ITEM
        )
        svc = ECNService(db_session)
        erp = FakeERPAdapter()

        detail = await svc.transition(
            ecn_id,
            ECNStatusTransitionRequest(trigger="submit", actor_role="OR"),
            actor_username=_ACTOR,
            erp=erp,
        )
        # transition() returns (ECNDetail, outbox_ids) on the router-facing
        # path, but resubmit-style direct calls may return just ECNDetail —
        # either way, submit must not have raised.
        assert detail is not None

        rows = await db_session.execute(
            sa.text("SELECT COUNT(*) FROM bom_snapshots WHERE ecn_id = :ecn_id"),
            {"ecn_id": ecn_id},
        )
        assert rows.scalar_one() == 0

    async def test_no_erp_adapter_passed_skips_gracefully(self, db_session: AsyncSession):
        """erp=None (default) — e.g. the recursive system-triggered
        transition() self-call in workflow.py's zero-outbox auto-advance,
        which never passes erp — must not raise."""
        ecn_id, _item_id = await _make_ecn_with_bom_change(
            db_session, parent_item_number=_FIXTURE_ITEM
        )
        svc = ECNService(db_session)
        detail = await svc.transition(
            ecn_id,
            ECNStatusTransitionRequest(trigger="submit", actor_role="OR"),
            actor_username=_ACTOR,
        )
        assert detail is not None

        rows = await db_session.execute(
            sa.text("SELECT COUNT(*) FROM bom_snapshots WHERE ecn_id = :ecn_id"),
            {"ecn_id": ecn_id},
        )
        assert rows.scalar_one() == 0

    async def test_multiple_items_distinct_parents_capture_multiple_snapshots(
        self, db_session: AsyncSession
    ):
        svc = ECNService(db_session)
        req = ECNCreateRequest(
            facility=_FACILITY, title="Multi-item snapshot test ECN",
            is_new_item=False, routing_changes=False, operation_changes=False,
            new_parts=False, change_parts=True, bom_changes=True,
            lead_time_changes=False, change_to_documents=False,
            requires_customer_approval=False, regulatory_impact=False,
        )
        ecn = await svc.create(req, _ACTOR)
        item1 = await svc.create_item(ecn.id, line_number=10, item_number=_FIXTURE_ITEM)
        item2 = await svc.create_item(ecn.id, line_number=20, item_number=_NO_FIXTURE_ITEM)
        await svc.create_bom_change(
            ecn.id, item1.id,
            BOMChangeRequest(change_type="ADD", component_number="LF200099", quantity=1.0),
        )
        await svc.create_bom_change(
            ecn.id, item2.id,
            BOMChangeRequest(change_type="ADD", component_number="LF200098", quantity=1.0),
        )

        erp = FakeERPAdapter()
        await svc.transition(
            ecn.id,
            ECNStatusTransitionRequest(trigger="submit", actor_role="OR"),
            actor_username=_ACTOR,
            erp=erp,
        )

        # item1 has a real fixture -> snapshot captured. item2 has none ->
        # BOMNotFound -> skipped with warning, not blocking. Net: exactly 1
        # snapshot row, for item1 only.
        rows = await db_session.execute(
            sa.text(
                "SELECT item_number FROM bom_snapshots WHERE ecn_id = :ecn_id"
            ),
            {"ecn_id": ecn.id},
        )
        item_numbers = {r[0] for r in rows}
        assert item_numbers == {_FIXTURE_ITEM}

    async def test_two_bom_changes_same_parent_item_captures_one_snapshot(
        self, db_session: AsyncSession
    ):
        """DISTINCT parent items — two ecn_bom_changes rows on the same item
        must not produce two snapshot rows."""
        svc = ECNService(db_session)
        req = ECNCreateRequest(
            facility=_FACILITY, title="Same-parent dedup test ECN",
            is_new_item=False, routing_changes=False, operation_changes=False,
            new_parts=False, change_parts=True, bom_changes=True,
            lead_time_changes=False, change_to_documents=False,
            requires_customer_approval=False, regulatory_impact=False,
        )
        ecn = await svc.create(req, _ACTOR)
        item = await svc.create_item(ecn.id, line_number=10, item_number=_FIXTURE_ITEM)
        await svc.create_bom_change(
            ecn.id, item.id,
            BOMChangeRequest(change_type="ADD", component_number="LF200099", quantity=1.0),
        )
        await svc.create_bom_change(
            ecn.id, item.id,
            BOMChangeRequest(change_type="ADD", component_number="LF200098", quantity=2.0),
        )

        erp = FakeERPAdapter()
        await svc.transition(
            ecn.id,
            ECNStatusTransitionRequest(trigger="submit", actor_role="OR"),
            actor_username=_ACTOR,
            erp=erp,
        )

        rows = await db_session.execute(
            sa.text("SELECT COUNT(*) FROM bom_snapshots WHERE ecn_id = :ecn_id"),
            {"ecn_id": ecn.id},
        )
        assert rows.scalar_one() == 1
