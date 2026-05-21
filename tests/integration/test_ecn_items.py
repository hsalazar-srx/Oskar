"""
Integration tests — ECNItemsMixin: create_item, list_items, get_item,
update_item, delete_item, MPN CRUD, routing operations.
"""
from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.ecn.models import (
    ECNCreateRequest,
    ECNNotFound,
    ECNValidationError,
    RoutingOperationRequest,
)
from src.services.ecn.service import ECNService
from src.workflow.machine import ECNStatus

pytestmark = pytest.mark.asyncio

_ACTOR = "hsalazar"
_FACILITY = "L"


async def _make_ecn(db_session: AsyncSession, **overrides) -> str:
    """Helper: create a minimal ECN and return its id."""
    svc = ECNService(db_session)
    req = ECNCreateRequest(
        facility=_FACILITY,
        title=overrides.get("title", "Items integration test"),
        is_new_item=overrides.get("is_new_item", False),
        routing_changes=False, operation_changes=False, new_parts=False,
        lead_time_changes=False, change_to_documents=False,
        requires_customer_approval=False, regulatory_impact=False,
    )
    ecn = await svc.create(req, _ACTOR)
    return ecn.id


# ---------------------------------------------------------------------------
# create_item / get_item
# ---------------------------------------------------------------------------

class TestCreateItem:

    async def test_create_returns_item_detail(self, db_session: AsyncSession):
        svc = ECNService(db_session)
        ecn_id = await _make_ecn(db_session)
        item = await svc.create_item(
            ecn_id, line_number=10, item_number="LF-TEST-0001",
            item_name="Test resistor", is_new_item=True,
        )
        assert item.item_number == "LF-TEST-0001"
        assert item.is_new_item is True
        assert item.ecn_id == ecn_id

    async def test_create_item_unknown_ecn_raises(self, db_session: AsyncSession):
        svc = ECNService(db_session)
        with pytest.raises(ECNNotFound):
            await svc.create_item(
                "00000000-0000-0000-0000-000000000000",
                line_number=10, item_number="LF-TEST-9999",
            )

    async def test_get_item_returns_created(self, db_session: AsyncSession):
        svc = ECNService(db_session)
        ecn_id = await _make_ecn(db_session)
        item = await svc.create_item(
            ecn_id, line_number=10, item_number="LF-TEST-0002",
        )
        fetched = await svc.get_item(ecn_id, item.id)
        assert fetched.id == item.id

    async def test_get_item_not_found_raises(self, db_session: AsyncSession):
        svc = ECNService(db_session)
        ecn_id = await _make_ecn(db_session)
        with pytest.raises(ECNNotFound):
            await svc.get_item(ecn_id, "00000000-0000-0000-0000-000000000000")


# ---------------------------------------------------------------------------
# list_items
# ---------------------------------------------------------------------------

class TestListItems:

    async def test_list_empty_for_new_ecn(self, db_session: AsyncSession):
        svc = ECNService(db_session)
        ecn_id = await _make_ecn(db_session)
        items = await svc.list_items(ecn_id)
        assert items == []

    async def test_list_returns_created_items_ordered_by_line(self, db_session: AsyncSession):
        svc = ECNService(db_session)
        ecn_id = await _make_ecn(db_session)
        await svc.create_item(ecn_id, line_number=20, item_number="LF-B")
        await svc.create_item(ecn_id, line_number=10, item_number="LF-A")
        items = await svc.list_items(ecn_id)
        assert [i.line_number for i in items] == [10, 20]


# ---------------------------------------------------------------------------
# update_item
# ---------------------------------------------------------------------------

class TestUpdateItem:

    async def test_update_item_name(self, db_session: AsyncSession):
        svc = ECNService(db_session)
        ecn_id = await _make_ecn(db_session)
        item = await svc.create_item(ecn_id, line_number=10, item_number="LF-UPD")
        updated = await svc.update_item(ecn_id, item.id, item_name="New name")
        assert updated.item_name == "New name"

    async def test_update_procurement_and_product_group(self, db_session: AsyncSession):
        svc = ECNService(db_session)
        ecn_id = await _make_ecn(db_session)
        item = await svc.create_item(ecn_id, line_number=10, item_number="LF-GRP")
        updated = await svc.update_item(
            ecn_id, item.id,
            procurement_group="PCA", product_group="PCBA",
        )
        assert updated.procurement_group == "PCA"
        assert updated.product_group == "PCBA"


# ---------------------------------------------------------------------------
# delete_item
# ---------------------------------------------------------------------------

class TestDeleteItem:

    async def test_delete_removes_item(self, db_session: AsyncSession):
        svc = ECNService(db_session)
        ecn_id = await _make_ecn(db_session)
        item = await svc.create_item(ecn_id, line_number=10, item_number="LF-DEL")
        await svc.delete_item(ecn_id, item.id)
        items = await svc.list_items(ecn_id)
        assert all(i.id != item.id for i in items)

    async def test_delete_not_found_raises(self, db_session: AsyncSession):
        svc = ECNService(db_session)
        ecn_id = await _make_ecn(db_session)
        with pytest.raises(ECNNotFound):
            await svc.delete_item(ecn_id, "00000000-0000-0000-0000-000000000000")

    async def test_delete_non_draft_raises(self, db_session: AsyncSession):
        import sqlalchemy as sa
        svc = ECNService(db_session)
        ecn_id = await _make_ecn(db_session)
        item = await svc.create_item(ecn_id, line_number=10, item_number="LF-ND")
        # Force status to ENGINEERING_REVIEW (30) — first non-draft valid status
        await db_session.execute(
            sa.text("UPDATE ecn_instances SET status = 30 WHERE id = :id"),
            {"id": ecn_id},
        )
        with pytest.raises(ECNValidationError, match="DRAFT"):
            await svc.delete_item(ecn_id, item.id)


# ---------------------------------------------------------------------------
# MPN CRUD
# ---------------------------------------------------------------------------

class TestMPNCRUD:

    async def test_create_mpn(self, db_session: AsyncSession):
        svc = ECNService(db_session)
        ecn_id = await _make_ecn(db_session)
        item = await svc.create_item(ecn_id, line_number=10, item_number="LF-MPN")
        mpn = await svc.create_mpn(
            ecn_id, item.id,
            mpn="RC0402FR-0710KL",
            manufacturer="Yageo",
            is_default=True,
        )
        assert mpn.mpn == "RC0402FR-0710KL"
        assert mpn.manufacturer == "Yageo"
        assert mpn.is_default is True

    async def test_create_mpn_unknown_item_raises(self, db_session: AsyncSession):
        svc = ECNService(db_session)
        ecn_id = await _make_ecn(db_session)
        with pytest.raises(ECNNotFound):
            await svc.create_mpn(
                ecn_id, "00000000-0000-0000-0000-000000000000",
                mpn="BAD", manufacturer="X",
            )

    async def test_mpn_visible_on_item_fetch(self, db_session: AsyncSession):
        svc = ECNService(db_session)
        ecn_id = await _make_ecn(db_session)
        item = await svc.create_item(ecn_id, line_number=10, item_number="LF-MPN2")
        await svc.create_mpn(ecn_id, item.id, mpn="GRM21BR61A106KE18L", manufacturer="Murata")
        fetched = await svc.get_item(ecn_id, item.id)
        assert len(fetched.mpns) == 1
        assert fetched.mpns[0].mpn == "GRM21BR61A106KE18L"

    async def test_update_mpn(self, db_session: AsyncSession):
        svc = ECNService(db_session)
        ecn_id = await _make_ecn(db_session)
        item = await svc.create_item(ecn_id, line_number=10, item_number="LF-MPN3")
        mpn = await svc.create_mpn(ecn_id, item.id, mpn="OLD-MPN", manufacturer="X")
        updated = await svc.update_mpn(ecn_id, mpn.id, mpn="NEW-MPN")
        assert updated.mpn == "NEW-MPN"

    async def test_delete_mpn(self, db_session: AsyncSession):
        svc = ECNService(db_session)
        ecn_id = await _make_ecn(db_session)
        item = await svc.create_item(ecn_id, line_number=10, item_number="LF-MPN4")
        mpn = await svc.create_mpn(ecn_id, item.id, mpn="DELETE-ME", manufacturer="X")
        await svc.delete_mpn(ecn_id, mpn.id)
        fetched = await svc.get_item(ecn_id, item.id)
        assert fetched.mpns == []


# ---------------------------------------------------------------------------
# Routing operations
# ---------------------------------------------------------------------------

class TestRoutingOperations:

    def _op_req(self, **overrides) -> RoutingOperationRequest:
        defaults = dict(
            operation_number=10,
            operation_description="SMT placement",
            work_centre="SMT01",
            run_time=120.0,
            setup_time=30.0,
            change_type="ADD",
        )
        return RoutingOperationRequest(**(defaults | overrides))

    async def test_create_routing_op(self, db_session: AsyncSession):
        svc = ECNService(db_session)
        ecn_id = await _make_ecn(db_session)
        item = await svc.create_item(ecn_id, line_number=10, item_number="LF-ROP")
        op = await svc.create_routing_operation(ecn_id, item.id, self._op_req())
        assert op.operation_number == 10
        assert op.work_centre == "SMT01"
        assert op.change_type == "ADD"

    async def test_list_routing_ops(self, db_session: AsyncSession):
        svc = ECNService(db_session)
        ecn_id = await _make_ecn(db_session)
        item = await svc.create_item(ecn_id, line_number=10, item_number="LF-ROP2")
        await svc.create_routing_operation(ecn_id, item.id, self._op_req(operation_number=10))
        await svc.create_routing_operation(ecn_id, item.id, self._op_req(operation_number=20))
        ops = await svc.list_routing_operations(ecn_id, item.id)
        assert [o.operation_number for o in ops] == [10, 20]

    async def test_duplicate_op_number_raises(self, db_session: AsyncSession):
        from src.services.ecn.models import ECNConflict
        svc = ECNService(db_session)
        ecn_id = await _make_ecn(db_session)
        item = await svc.create_item(ecn_id, line_number=10, item_number="LF-DUP")
        await svc.create_routing_operation(ecn_id, item.id, self._op_req(operation_number=10))
        with pytest.raises(ECNConflict):
            await svc.create_routing_operation(ecn_id, item.id, self._op_req(operation_number=10))

    async def test_update_routing_op(self, db_session: AsyncSession):
        svc = ECNService(db_session)
        ecn_id = await _make_ecn(db_session)
        item = await svc.create_item(ecn_id, line_number=10, item_number="LF-RUP")
        op = await svc.create_routing_operation(ecn_id, item.id, self._op_req())
        updated = await svc.update_routing_operation(
            ecn_id, item.id, op.id, work_centre="SMT02", run_time=90.0,
        )
        assert updated.work_centre == "SMT02"
        assert updated.run_time == 90.0

    async def test_delete_routing_op(self, db_session: AsyncSession):
        svc = ECNService(db_session)
        ecn_id = await _make_ecn(db_session)
        item = await svc.create_item(ecn_id, line_number=10, item_number="LF-RDEL")
        op = await svc.create_routing_operation(ecn_id, item.id, self._op_req())
        await svc.delete_routing_operation(ecn_id, item.id, op.id)
        ops = await svc.list_routing_operations(ecn_id, item.id)
        assert ops == []
