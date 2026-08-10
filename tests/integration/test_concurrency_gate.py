"""
Integration tests — BOM concurrency gate at dc_approve (Slice E, ADR-012,
I2-6, R8).

For ECNs with ecn_bom_changes rows, dc_approve re-fetches the live BOM via
the ERP adapter and diffs it against the snapshot captured at submit (Slice
D's diff_boms()). Hash-equal fast path (content_hash() match) skips the full
diff. A live change that lands on the SAME key
(component_number, operation_number) as one of this ECN's ecn_bom_changes
rows is a CONFLICT — raises ECNTransitionError (409) with the diff payload
attached, blocking the transition entirely (nothing is written to
ecn_instances or ecn_transition_history). A live change on a
NON-conflicting key proceeds (transition succeeds) with a warning recorded
in the transition history's notes.

Uses a small hand-rolled mock ERPAdapter (not tests/helpers/fake_erp.py's
FakeERPAdapter, which serves one fixed fixture file per item_number) because
this test needs the live BOM to return something DIFFERENT at dc_approve
time than what it returned at submit time — a mutable in-test stub is the
simplest way to express "the BOM changed between submit and dc_approve".

NOTE (I2-18 workaround): run tests in this file one at a time
(pytest tests/integration/test_concurrency_gate.py::Class::test), not as a
whole-file invocation — see test_snapshot_at_submit.py's module docstring
for the full explanation.
"""
from __future__ import annotations

import copy
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from src.adapters.erp.base import BOMNotFound, ERPAdapter
from src.services.ecn.models import (
    BOMChangeRequest,
    ECNCreateRequest,
    ECNStatusTransitionRequest,
    ECNTransitionError,
)
from src.services.ecn.service import ECNService
from src.workflow.machine import ECNStatus

pytestmark = pytest.mark.asyncio

_ACTOR = "hsalazar"
_FACILITY = "L"
_PARENT_ITEM = "LFCONC0001"

_BASE_PAYLOAD: dict[str, Any] = {
    "data": {
        "head": {"PRNO": _PARENT_ITEM, "STRT": "001", "FACI": "L", "ITDS": "Concurrency test assy"},
        "records": [
            {"MSEQ": 10, "MTNO": "LF200010", "ITDS": "Resistor 10K 0603", "OPNO": 10,
             "CNQT": 4.0, "PEUN": "EA", "FDAT": 20240101, "TDAT": 99999999, "ITTY": "3", "STAT": "20"},
            {"MSEQ": 20, "MTNO": "LF200011", "ITDS": "Capacitor 100nF 0603", "OPNO": 10,
             "CNQT": 8.0, "PEUN": "EA", "FDAT": 20240101, "TDAT": 99999999, "ITTY": "3", "STAT": "20"},
        ],
    }
}


class _MutableStubERPAdapter(ERPAdapter):
    """Minimal ERPAdapter stub whose get_bom() response can be mutated
    in-test between the submit call and the dc_approve call, to simulate a
    live Movex BOM change happening in the gap (R8's whole reason for
    existing)."""

    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload

    async def get_bom(self, item_number, facility, *, structure_type="001",
                       bom_type="M", effective_on=None):
        if item_number != _PARENT_ITEM:
            raise BOMNotFound(item_number)
        return copy.deepcopy(self.payload)

    # Unused abstract methods — not exercised by this test.
    async def get_item(self, item_number): raise NotImplementedError
    async def get_item_facility(self, item_number, facility): raise NotImplementedError
    async def get_bom_indented(self, item_number, facility, *, structure_type="001", max_depth=12): raise NotImplementedError
    async def get_where_used(self, component_number, facility, *, effective_on=None): raise NotImplementedError
    async def get_routing_operations(self, item_number, facility, structure_type="001"): raise NotImplementedError
    async def lookup_by_alias(self, popn, cuno=None): raise NotImplementedError
    async def get_next_itno_sequence(self, prefix): raise NotImplementedError
    async def search_items(self, query, limit=50): raise NotImplementedError
    async def get_ecn(self, ecn_id): raise NotImplementedError
    async def list_open_orders(self, item_numbers, facility): raise NotImplementedError
    async def health_check(self): return True
    async def create_product(self, *a, **kw): raise NotImplementedError
    async def add_bom_component(self, *a, **kw): raise NotImplementedError
    async def delete_bom_component(self, *a, **kw): raise NotImplementedError
    async def update_bom_component(self, *a, **kw): raise NotImplementedError
    async def update_routing_operation(self, *a, **kw): raise NotImplementedError
    async def add_routing_operation(self, *a, **kw): raise NotImplementedError
    async def add_item_alias(self, *a, **kw): raise NotImplementedError


async def _advance(db_session, ecn_id, trigger, *, actor=_ACTOR, actor_role="OR", erp=None, **kw):
    svc = ECNService(db_session)
    req = ECNStatusTransitionRequest(trigger=trigger, actor_role=actor_role, **kw)
    return await svc.transition(ecn_id, req, actor_username=actor, erp=erp)


async def _make_ecn_ready_for_dc_approve(
    db_session: AsyncSession, erp: ERPAdapter, *, component_number: str = "LF200010",
    operation_number: int = 10,
) -> tuple[str, str]:
    """Create an ECN with one ecn_bom_changes row, and drive it through
    submit -> ... -> MANAGEMENT_REVIEW's approvals, right up to (but not
    including) dc_approve — the caller fires dc_approve itself so it can
    assert on the outcome."""
    svc = ECNService(db_session)
    req = ECNCreateRequest(
        facility=_FACILITY, title="Concurrency gate test ECN",
        is_new_item=False, routing_changes=False, operation_changes=False,
        new_parts=False, change_parts=True, bom_changes=True,
        lead_time_changes=False, change_to_documents=False,
        requires_customer_approval=False, regulatory_impact=False,
    )
    ecn = await svc.create(req, _ACTOR)
    item = await svc.create_item(ecn.id, line_number=10, item_number=_PARENT_ITEM)
    await svc.create_bom_change(
        ecn.id, item.id,
        BOMChangeRequest(
            change_type="CHANGE", component_number=component_number,
            operation_number=operation_number, quantity=6.0,
            from_date=20260901, old_from_date=20240101, old_quantity=4.0,
        ),
    )

    await _advance(db_session, ecn.id, "submit", erp=erp)
    await _advance(db_session, ecn.id, "approve_engineering", actor="eng_user", actor_role="SE")
    await _advance(db_session, ecn.id, "approve_role", actor="eng_user", actor_role="EM", role_id="EM")
    await _advance(db_session, ecn.id, "approve_role", actor="qm_user", actor_role="QM", role_id="QM")
    await _advance(db_session, ecn.id, "complete_management_review", actor="qm_user", actor_role="QM")

    return ecn.id, item.id


class TestHashEqualFastPath:
    async def test_unchanged_bom_proceeds_to_approved(self, db_session: AsyncSession):
        erp = _MutableStubERPAdapter(_BASE_PAYLOAD)
        ecn_id, _item_id = await _make_ecn_ready_for_dc_approve(db_session, erp)

        # BOM is IDENTICAL between submit and dc_approve — content_hash
        # fast path should skip the full diff and proceed cleanly.
        result = await _advance(
            db_session, ecn_id, "dc_approve", actor="dc_user", actor_role="DC", erp=erp,
        )
        detail = result[0] if isinstance(result, tuple) else result
        assert detail.status in (ECNStatus.APPROVED, ECNStatus.IMPLEMENTED)


class TestConflictingChangeBlocks:
    async def test_conflicting_key_change_raises_409(self, db_session: AsyncSession):
        """Live BOM's LF200010/OPNO 10 line quantity changed between submit
        and dc_approve — same (component_number, operation_number) key this
        ECN's ecn_bom_change is trying to CHANGE. Must block with 409."""
        erp = _MutableStubERPAdapter(_BASE_PAYLOAD)
        ecn_id, _item_id = await _make_ecn_ready_for_dc_approve(
            db_session, erp, component_number="LF200010", operation_number=10,
        )

        mutated = copy.deepcopy(_BASE_PAYLOAD)
        mutated["data"]["records"][0]["CNQT"] = 999.0  # LF200010 / OPNO 10 — conflicting key
        erp.payload = mutated

        with pytest.raises(ECNTransitionError) as exc_info:
            await _advance(db_session, ecn_id, "dc_approve", actor="dc_user", actor_role="DC", erp=erp)

        assert exc_info.value.payload is not None
        assert "changed" in exc_info.value.payload

    async def test_conflict_does_not_advance_ecn_status(self, db_session: AsyncSession):
        erp = _MutableStubERPAdapter(_BASE_PAYLOAD)
        ecn_id, _item_id = await _make_ecn_ready_for_dc_approve(
            db_session, erp, component_number="LF200010", operation_number=10,
        )
        mutated = copy.deepcopy(_BASE_PAYLOAD)
        mutated["data"]["records"][0]["CNQT"] = 999.0
        erp.payload = mutated

        with pytest.raises(ECNTransitionError):
            await _advance(db_session, ecn_id, "dc_approve", actor="dc_user", actor_role="DC", erp=erp)

        svc = ECNService(db_session)
        ecn = await svc.get(ecn_id)
        # complete_management_review already advanced the ECN to DC_APPROVED
        # before dc_approve was attempted (that's a separate, earlier
        # transition in the sequence) — the gate blocking dc_approve itself
        # means the ECN stays at DC_APPROVED, not advancing to APPROVED.
        assert ecn.status == ECNStatus.DC_APPROVED


class TestNonConflictingChangeProceeds:
    async def test_unrelated_line_change_proceeds_with_warning(self, db_session: AsyncSession):
        """Live BOM's LF200011/OPNO 10 line changed — a DIFFERENT key than
        this ECN's ecn_bom_change (LF200010/OPNO 10). Must NOT block; must
        record a warning in the transition history notes."""
        erp = _MutableStubERPAdapter(_BASE_PAYLOAD)
        ecn_id, _item_id = await _make_ecn_ready_for_dc_approve(
            db_session, erp, component_number="LF200010", operation_number=10,
        )
        mutated = copy.deepcopy(_BASE_PAYLOAD)
        mutated["data"]["records"][1]["CNQT"] = 12.0  # LF200011 — unrelated key
        erp.payload = mutated

        result = await _advance(
            db_session, ecn_id, "dc_approve", actor="dc_user", actor_role="DC", erp=erp,
        )
        detail = result[0] if isinstance(result, tuple) else result
        assert detail.status in (ECNStatus.APPROVED, ECNStatus.IMPLEMENTED)

        rows = await db_session.execute(
            sa.text(
                "SELECT notes FROM ecn_transition_history "
                "WHERE ecn_id = :ecn_id AND action = 'dc_approve' ORDER BY created_at DESC LIMIT 1"
            ),
            {"ecn_id": ecn_id},
        )
        notes = rows.scalar_one()
        assert notes is not None
        assert "BOM" in notes or "changed" in notes.lower()


class TestNoSnapshotDegradesGracefully:
    async def test_missing_snapshot_proceeds_with_warning_not_hard_block(self, db_session: AsyncSession):
        """If submit-time capture never happened (e.g. ERP was down at
        submit — test_snapshot_at_submit.py's resilience case), dc_approve
        must not hard-fail — 'cannot verify, proceed with warning', per the
        plan's explicit instruction."""
        # erp=None at submit -> no snapshot captured at all.
        svc = ECNService(db_session)
        req = ECNCreateRequest(
            facility=_FACILITY, title="No-snapshot concurrency test ECN",
            is_new_item=False, routing_changes=False, operation_changes=False,
            new_parts=False, change_parts=True, bom_changes=True,
            lead_time_changes=False, change_to_documents=False,
            requires_customer_approval=False, regulatory_impact=False,
        )
        ecn = await svc.create(req, _ACTOR)
        item = await svc.create_item(ecn.id, line_number=10, item_number=_PARENT_ITEM)
        await svc.create_bom_change(
            ecn.id, item.id,
            BOMChangeRequest(
                change_type="CHANGE", component_number="LF200010", operation_number=10,
                quantity=6.0, from_date=20260901, old_from_date=20240101, old_quantity=4.0,
            ),
        )
        await _advance(db_session, ecn.id, "submit", erp=None)
        await _advance(db_session, ecn.id, "approve_engineering", actor="eng_user", actor_role="SE")
        await _advance(db_session, ecn.id, "approve_role", actor="eng_user", actor_role="EM", role_id="EM")
        await _advance(db_session, ecn.id, "approve_role", actor="qm_user", actor_role="QM", role_id="QM")
        await _advance(db_session, ecn.id, "complete_management_review", actor="qm_user", actor_role="QM")

        erp = _MutableStubERPAdapter(_BASE_PAYLOAD)
        result = await _advance(
            db_session, ecn.id, "dc_approve", actor="dc_user", actor_role="DC", erp=erp,
        )
        detail = result[0] if isinstance(result, tuple) else result
        assert detail.status in (ECNStatus.APPROVED, ECNStatus.IMPLEMENTED)
