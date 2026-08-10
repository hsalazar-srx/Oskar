"""
Integration tests — _queue_bom_changes_outbox (Slice E, ADR-012 D6).

D6 supersession rule: ADD -> 1 AddComponent outbox row. DELETE -> 1
UpdateComponent "close" row. CHANGE -> 2 rows (close + add), with the add
row's depends_on set to the close row's id (Slice E0's dispatch-ordering
mechanism) so the add is gated behind the close's completion.

Wired into transition()'s dc_approve branch, beside
_queue_routing_operations_outbox — verified end-to-end via the full
submit -> ... -> dc_approve workflow, same pattern as
test_concurrency_gate.py (BOM lines with no drift, so the concurrency gate's
hash-equal fast path lets dc_approve through cleanly to reach the outbox
queue step).

NOTE (I2-18 workaround): run tests one at a time.
"""
from __future__ import annotations

from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from src.adapters.erp.base import BOMNotFound, ERPAdapter
from src.services.ecn.models import (
    BOMChangeRequest,
    ECNCreateRequest,
    ECNStatusTransitionRequest,
)
from src.services.ecn.service import ECNService

pytestmark = pytest.mark.asyncio

_ACTOR = "hsalazar"
_FACILITY = "L"
_PARENT_ITEM = "LFQOUT0001"

_PAYLOAD: dict[str, Any] = {
    "data": {
        "head": {"PRNO": _PARENT_ITEM, "STRT": "001", "FACI": "L", "ITDS": "Queue outbox test assy"},
        "records": [
            {"MSEQ": 10, "MTNO": "LF200010", "ITDS": "Resistor", "OPNO": 10,
             "CNQT": 4.0, "PEUN": "EA", "FDAT": 20240101, "TDAT": 99999999, "ITTY": "3", "STAT": "20"},
        ],
    }
}


class _StubERPAdapter(ERPAdapter):
    async def get_bom(self, item_number, facility, *, structure_type="001", bom_type="M", effective_on=None):
        if item_number != _PARENT_ITEM:
            raise BOMNotFound(item_number)
        import copy
        return copy.deepcopy(_PAYLOAD)

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
    async def update_routing_operation(self, *a, **kw): raise NotImplementedError
    async def add_routing_operation(self, *a, **kw): raise NotImplementedError
    async def add_item_alias(self, *a, **kw): raise NotImplementedError


async def _advance(db_session, ecn_id, trigger, *, actor=_ACTOR, actor_role="OR", erp=None, **kw):
    svc = ECNService(db_session)
    req = ECNStatusTransitionRequest(trigger=trigger, actor_role=actor_role, **kw)
    return await svc.transition(ecn_id, req, actor_username=actor, erp=erp)


async def _make_ecn_with_bom_change(
    db_session: AsyncSession, req: BOMChangeRequest, erp: ERPAdapter,
) -> tuple[str, str]:
    svc = ECNService(db_session)
    ecn_req = ECNCreateRequest(
        facility=_FACILITY, title="Queue BOM outbox test ECN",
        is_new_item=False, routing_changes=False, operation_changes=False,
        new_parts=False, change_parts=True, bom_changes=True,
        lead_time_changes=False, change_to_documents=False,
        requires_customer_approval=False, regulatory_impact=False,
    )
    ecn = await svc.create(ecn_req, _ACTOR)
    item = await svc.create_item(ecn.id, line_number=10, item_number=_PARENT_ITEM)
    change = await svc.create_bom_change(ecn.id, item.id, req)

    await _advance(db_session, ecn.id, "submit", erp=erp)
    await _advance(db_session, ecn.id, "approve_engineering", actor="eng_user", actor_role="SE")
    await _advance(db_session, ecn.id, "approve_role", actor="eng_user", actor_role="EM", role_id="EM")
    await _advance(db_session, ecn.id, "approve_role", actor="qm_user", actor_role="QM", role_id="QM")
    await _advance(db_session, ecn.id, "complete_management_review", actor="qm_user", actor_role="QM")

    return ecn.id, change.id


class TestAddChangeType:
    async def test_add_queues_one_add_component_row(self, db_session: AsyncSession):
        erp = _StubERPAdapter()
        req = BOMChangeRequest(
            change_type="ADD", component_number="LF200099", quantity=2.0,
            unit_of_measure="EA", operation_number=20, from_date=20260901,
        )
        ecn_id, change_id = await _make_ecn_with_bom_change(db_session, req, erp)

        await _advance(db_session, ecn_id, "dc_approve", actor="dc_user", actor_role="DC", erp=erp)

        rows = await db_session.execute(
            sa.text(
                "SELECT mi_transaction, idempotency_key, depends_on, mi_params FROM movex_outbox "
                "WHERE ecn_id = :ecn_id"
            ),
            {"ecn_id": ecn_id},
        )
        outbox_rows = rows.mappings().all()
        assert len(outbox_rows) == 1
        assert outbox_rows[0]["mi_transaction"] == "PDS002MI.AddComponent"
        assert outbox_rows[0]["idempotency_key"] == f"PDS002MI.AddComponent:{ecn_id}:{change_id}"
        assert outbox_rows[0]["depends_on"] is None
        # R9 regression guard — facility must flow through into mi_params so
        # add_bom_component's now-parameterised facility field never falls
        # back to its 'D' default for a non-D-facility ECN.
        assert outbox_rows[0]["mi_params"]["facility"] == _FACILITY


class TestDeleteChangeType:
    async def test_delete_queues_one_update_component_close_row(self, db_session: AsyncSession):
        erp = _StubERPAdapter()
        req = BOMChangeRequest(
            change_type="DELETE", component_number="LF200010", operation_number=10,
            old_from_date=20240101,
        )
        ecn_id, change_id = await _make_ecn_with_bom_change(db_session, req, erp)

        await _advance(db_session, ecn_id, "dc_approve", actor="dc_user", actor_role="DC", erp=erp)

        rows = await db_session.execute(
            sa.text(
                "SELECT mi_transaction, idempotency_key, depends_on FROM movex_outbox "
                "WHERE ecn_id = :ecn_id"
            ),
            {"ecn_id": ecn_id},
        )
        outbox_rows = rows.mappings().all()
        assert len(outbox_rows) == 1
        assert outbox_rows[0]["mi_transaction"] == "PDS002MI.UpdateComponent"
        assert outbox_rows[0]["idempotency_key"] == f"PDS002MI.UpdateComponent:{ecn_id}:{change_id}:close"
        assert outbox_rows[0]["depends_on"] is None


class TestChangeChangeType:
    async def test_change_queues_close_and_add_with_dependency_link(self, db_session: AsyncSession):
        erp = _StubERPAdapter()
        req = BOMChangeRequest(
            change_type="CHANGE", component_number="LF200010", operation_number=10,
            quantity=6.0, from_date=20260901, old_from_date=20240101, old_quantity=4.0,
        )
        ecn_id, change_id = await _make_ecn_with_bom_change(db_session, req, erp)

        await _advance(db_session, ecn_id, "dc_approve", actor="dc_user", actor_role="DC", erp=erp)

        rows = await db_session.execute(
            sa.text(
                "SELECT id, mi_transaction, idempotency_key, depends_on FROM movex_outbox "
                "WHERE ecn_id = :ecn_id ORDER BY idempotency_key"
            ),
            {"ecn_id": ecn_id},
        )
        outbox_rows = rows.mappings().all()
        assert len(outbox_rows) == 2

        by_key = {r["idempotency_key"]: r for r in outbox_rows}
        close_key = f"PDS002MI.UpdateComponent:{ecn_id}:{change_id}:close"
        add_key = f"PDS002MI.AddComponent:{ecn_id}:{change_id}:add"
        assert close_key in by_key
        assert add_key in by_key

        close_row = by_key[close_key]
        add_row = by_key[add_key]
        assert close_row["mi_transaction"] == "PDS002MI.UpdateComponent"
        assert add_row["mi_transaction"] == "PDS002MI.AddComponent"
        assert close_row["depends_on"] is None
        assert str(add_row["depends_on"]) == str(close_row["id"])


class TestIdempotencyOnReplay:
    async def test_dc_approve_replay_does_not_duplicate_outbox_rows(self, db_session: AsyncSession):
        """ON CONFLICT DO NOTHING on idempotency_key — calling the queue
        method twice for the same bom_change must not create duplicate rows
        (matches _queue_alias_outbox/_queue_routing_operations_outbox's own
        idempotency guarantee)."""
        erp = _StubERPAdapter()
        req = BOMChangeRequest(
            change_type="ADD", component_number="LF200099", quantity=2.0,
            operation_number=20, from_date=20260901,
        )
        ecn_id, _change_id = await _make_ecn_with_bom_change(db_session, req, erp)

        svc = ECNService(db_session)
        first = await svc._queue_bom_changes_outbox(ecn_id)
        second = await svc._queue_bom_changes_outbox(ecn_id)

        assert len(first) == 1
        assert len(second) == 0  # ON CONFLICT DO NOTHING — no new rows

        rows = await db_session.execute(
            sa.text("SELECT COUNT(*) FROM movex_outbox WHERE ecn_id = :ecn_id"),
            {"ecn_id": ecn_id},
        )
        assert rows.scalar_one() == 1
