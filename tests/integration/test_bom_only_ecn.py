"""
OSKAR — BOM-only ECNs: a BOM change with no item on the ECN (ADR-014).

The behaviour this ADR unlocks, against real Postgres. Before ADR-014,
ecn_bom_changes.ecn_item_id was NOT NULL REFERENCES ecn_items(id), so an ECN
that changes only a BOM had to carry a dummy item row purely to satisfy the
schema — a row that then told every downstream reviewer the item master was
changing when it was not.

Stargile never worked this way: ZECNBOMS rows are self-contained (own BMPRNO
parent, own BMZECNLN line number, no FK to the items table), and the check
requiring the parent to be an ECN item was written there and deliberately
commented out (RequestECNBoMDetailValidationHelper.java:334-339, 495-500).

The paths covered here are the ones where a NULL ecn_item_id could silently
break something rather than fail loudly — in particular the snapshot
stamp-back, which ADR-014 calls out by name: if it stayed keyed on
ecn_item_id, a BOM-only row would never receive a snapshot_id, and
_check_bom_concurrency treats a missing snapshot as "cannot verify, proceed"
— silently disabling the I2-6 concurrency gate for exactly this new case.
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
    ECNValidationError,
)
from src.services.ecn.service import ECNService

pytestmark = pytest.mark.asyncio

_ACTOR = "hsalazar"
_FACILITY = "L"
_PARENT_ITEM = "LFBOMONLY01"

_PAYLOAD: dict[str, Any] = {
    "data": {
        "head": {"PRNO": _PARENT_ITEM, "STRT": "001", "FACI": "L",
                 "ITDS": "BOM-only scenario assy"},
        "records": [
            {"MSEQ": 10, "MTNO": "LF200010", "ITDS": "Resistor", "OPNO": 10,
             "CNQT": 4.0, "PEUN": "EA", "FDAT": 20240101, "TDAT": 99999999,
             "ITTY": "3", "STAT": "20"},
        ],
    }
}


class _StubERPAdapter(ERPAdapter):
    async def get_bom(self, item_number, facility, *, structure_type="001",
                      bom_type="M", effective_on=None):
        if item_number != _PARENT_ITEM:
            raise BOMNotFound(item_number)
        import copy
        return copy.deepcopy(_PAYLOAD)

    async def get_item(self, item_number): return {"itno": item_number}
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


async def _make_bom_only_ecn(db_session: AsyncSession) -> tuple[str, str]:
    """An ECN carrying exactly one BOM change and NO items at all."""
    svc = ECNService(db_session)
    ecn = await svc.create(
        ECNCreateRequest(
            facility=_FACILITY, title="BOM-only ECN (ADR-014)",
            is_new_item=False, routing_changes=False, operation_changes=False,
            new_parts=False, change_parts=True, bom_changes=True,
            lead_time_changes=False, change_to_documents=False,
            requires_customer_approval=False, regulatory_impact=False,
        ),
        _ACTOR,
    )
    change = await svc.create_bom_change(
        ecn.id, None,
        BOMChangeRequest(
            change_type="ADD", component_number="LF200020",
            parent_item_number=_PARENT_ITEM,
            quantity=2.0, unit_of_measure="EA", operation_number=10,
            from_date=20260901,
        ),
    )
    return ecn.id, change.id


class TestCreateBomOnlyChange:
    async def test_creates_row_with_null_item_and_real_parent(self, db_session: AsyncSession):
        ecn_id, change_id = await _make_bom_only_ecn(db_session)

        row = await db_session.execute(
            sa.text(
                "SELECT ecn_id, parent_item_number, ecn_item_id "
                "FROM ecn_bom_changes WHERE id = :id"
            ),
            {"id": change_id},
        )
        r = row.first()
        assert r is not None
        assert str(r[0]) == ecn_id
        assert r[1] == _PARENT_ITEM
        assert r[2] is None, "BOM-only change must not be linked to an item row"

    async def test_ecn_has_no_items_at_all(self, db_session: AsyncSession):
        ecn_id, _ = await _make_bom_only_ecn(db_session)
        count = await db_session.execute(
            sa.text("SELECT COUNT(*) FROM ecn_items WHERE ecn_id = :e"), {"e": ecn_id},
        )
        assert count.scalar_one() == 0

    async def test_parent_item_number_required_when_no_item(self, db_session: AsyncSession):
        svc = ECNService(db_session)
        ecn = await svc.create(
            ECNCreateRequest(
                facility=_FACILITY, title="Missing parent", is_new_item=False,
                routing_changes=False, operation_changes=False, new_parts=False,
                lead_time_changes=False, change_to_documents=False,
                requires_customer_approval=False, regulatory_impact=False,
            ),
            _ACTOR,
        )
        with pytest.raises(ECNValidationError, match="parent_item_number"):
            await svc.create_bom_change(
                ecn.id, None,
                BOMChangeRequest(change_type="ADD", component_number="LF200020"),
            )

    async def test_appears_in_ecn_wide_aggregate_list(self, db_session: AsyncSession):
        """The BOM Changes tab reads list_all_bom_changes, which used to JOIN
        through ecn_items — a BOM-only row would have been invisible there."""
        ecn_id, change_id = await _make_bom_only_ecn(db_session)
        svc = ECNService(db_session)
        changes = await svc.list_all_bom_changes(ecn_id)
        assert [c.id for c in changes] == [change_id]
        assert changes[0].item_number == _PARENT_ITEM
        assert changes[0].ecn_item_id is None


class TestBomOnlyEcnSubmit:
    async def test_submit_succeeds_and_stamps_snapshot(self, db_session: AsyncSession):
        """ADR-014's named trap: the snapshot stamp-back must be keyed on
        (ecn_id, parent_item_number), not ecn_item_id. If it were still keyed
        on the item, this row would get no snapshot_id and the dc_approve
        concurrency gate would silently skip it."""
        ecn_id, change_id = await _make_bom_only_ecn(db_session)
        svc = ECNService(db_session)
        erp = _StubERPAdapter()

        await svc.transition(
            ecn_id,
            ECNStatusTransitionRequest(trigger="submit", actor_role="OR"),
            actor_username=_ACTOR, erp=erp,
        )

        row = await db_session.execute(
            sa.text("SELECT snapshot_id FROM ecn_bom_changes WHERE id = :id"),
            {"id": change_id},
        )
        assert row.scalar_one() is not None, (
            "BOM-only change did not receive a snapshot_id — the concurrency "
            "gate would silently skip it (ADR-014 trap)"
        )

    async def test_submit_blocked_when_ecn_has_no_content_at_all(
        self, db_session: AsyncSession
    ):
        """The other half of ADR-014's related finding: _guard_submit's
        docstring claimed '≥1 item' but checked nothing, so a completely
        empty ECN could be submitted and routed to a reviewer."""
        from src.services.ecn.models import ECNTransitionError

        svc = ECNService(db_session)
        ecn = await svc.create(
            ECNCreateRequest(
                facility=_FACILITY, title="Empty ECN", is_new_item=False,
                routing_changes=False, operation_changes=False, new_parts=False,
                lead_time_changes=False, change_to_documents=False,
                requires_customer_approval=False, regulatory_impact=False,
            ),
            _ACTOR,
        )
        with pytest.raises(ECNTransitionError, match="at least one item"):
            await svc.transition(
                ecn.id,
                ECNStatusTransitionRequest(trigger="submit", actor_role="OR"),
                actor_username=_ACTOR, erp=_StubERPAdapter(),
            )
