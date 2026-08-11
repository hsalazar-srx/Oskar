"""
Integration tests — ECNBomChangesMixin: create/list/update/delete
ecn_bom_changes rows against real Postgres (migration 0030).

Covers what tests/routers/test_ecn_bom_changes.py cannot (that suite mocks
ECNService entirely): the actual SQL, old_from_date validation, and the
DC_APPROVED-workflow-order edit lock with the DC-role bypass.
"""
from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.ecn.models import (
    BOMChangeRequest,
    ECNCreateRequest,
    ECNNotFound,
    ECNValidationError,
)
from src.services.ecn.service import ECNService
from src.workflow.machine import ECNStatus

pytestmark = pytest.mark.asyncio

_ACTOR = "hsalazar"
_FACILITY = "L"


async def _make_ecn_with_item(db_session: AsyncSession, **overrides) -> tuple[str, str]:
    svc = ECNService(db_session)
    req = ECNCreateRequest(
        facility=_FACILITY,
        title=overrides.get("title", "BOM changes integration test"),
        is_new_item=False,
        routing_changes=False, operation_changes=False, new_parts=False,
        lead_time_changes=False, change_to_documents=False,
        requires_customer_approval=False, regulatory_impact=False,
    )
    ecn = await svc.create(req, _ACTOR)
    item = await svc.create_item(
        ecn.id, line_number=10, item_number="LF100001",
    )
    return ecn.id, item.id


class TestCreateBomChange:
    async def test_create_add_change(self, db_session: AsyncSession):
        svc = ECNService(db_session)
        ecn_id, item_id = await _make_ecn_with_item(db_session)
        req = BOMChangeRequest(
            change_type="ADD", component_number="LF200010",
            quantity=4.0, unit_of_measure="EA", operation_number=10,
            from_date=20260901,
        )
        change = await svc.create_bom_change(ecn_id, item_id, req)
        assert change.change_type == "ADD"
        assert change.component_number == "LF200010"
        assert change.quantity == pytest.approx(4.0)
        assert change.old_from_date is None

    async def test_create_change_type_without_old_from_date_raises(self, db_session: AsyncSession):
        svc = ECNService(db_session)
        ecn_id, item_id = await _make_ecn_with_item(db_session)
        req = BOMChangeRequest(
            change_type="CHANGE", component_number="LF200010", quantity=6.0,
        )
        with pytest.raises(ECNValidationError, match="old_from_date"):
            await svc.create_bom_change(ecn_id, item_id, req)

    async def test_create_delete_type_without_old_from_date_raises(self, db_session: AsyncSession):
        svc = ECNService(db_session)
        ecn_id, item_id = await _make_ecn_with_item(db_session)
        req = BOMChangeRequest(change_type="DELETE", component_number="LF200010")
        with pytest.raises(ECNValidationError, match="old_from_date"):
            await svc.create_bom_change(ecn_id, item_id, req)

    async def test_create_change_type_with_old_from_date_succeeds(self, db_session: AsyncSession):
        svc = ECNService(db_session)
        ecn_id, item_id = await _make_ecn_with_item(db_session)
        req = BOMChangeRequest(
            change_type="CHANGE", component_number="LF200010", quantity=6.0,
            from_date=20260901, old_from_date=20240101, old_quantity=4.0,
        )
        change = await svc.create_bom_change(ecn_id, item_id, req)
        assert change.old_from_date == 20240101
        assert change.old_quantity == pytest.approx(4.0)

    async def test_create_unknown_item_raises(self, db_session: AsyncSession):
        svc = ECNService(db_session)
        ecn_id, _item_id = await _make_ecn_with_item(db_session)
        req = BOMChangeRequest(change_type="ADD", component_number="LF200010")
        with pytest.raises(ECNNotFound):
            await svc.create_bom_change(
                ecn_id, "00000000-0000-0000-0000-000000000000", req
            )

    async def test_create_with_circuit_refs(self, db_session: AsyncSession):
        svc = ECNService(db_session)
        ecn_id, item_id = await _make_ecn_with_item(db_session)
        req = BOMChangeRequest(
            change_type="ADD", component_number="LF200010",
            circuit_refs_new=["R1", "R7", "R12"],
        )
        change = await svc.create_bom_change(ecn_id, item_id, req)
        assert change.circuit_refs_new == ["R1", "R7", "R12"]


class TestListBomChanges:
    async def test_list_returns_all_changes_for_item(self, db_session: AsyncSession):
        svc = ECNService(db_session)
        ecn_id, item_id = await _make_ecn_with_item(db_session)
        await svc.create_bom_change(
            ecn_id, item_id, BOMChangeRequest(change_type="ADD", component_number="LF200010")
        )
        await svc.create_bom_change(
            ecn_id, item_id, BOMChangeRequest(change_type="ADD", component_number="LF200020")
        )
        changes = await svc.list_bom_changes(ecn_id, item_id)
        assert len(changes) == 2

    async def test_list_empty_for_item_with_no_changes(self, db_session: AsyncSession):
        svc = ECNService(db_session)
        ecn_id, item_id = await _make_ecn_with_item(db_session)
        changes = await svc.list_bom_changes(ecn_id, item_id)
        assert changes == []

    async def test_list_unknown_item_raises(self, db_session: AsyncSession):
        svc = ECNService(db_session)
        ecn_id, _item_id = await _make_ecn_with_item(db_session)
        with pytest.raises(ECNNotFound):
            await svc.list_bom_changes(ecn_id, "00000000-0000-0000-0000-000000000000")


class TestUpdateBomChange:
    async def test_update_quantity(self, db_session: AsyncSession):
        svc = ECNService(db_session)
        ecn_id, item_id = await _make_ecn_with_item(db_session)
        change = await svc.create_bom_change(
            ecn_id, item_id, BOMChangeRequest(change_type="ADD", component_number="LF200010", quantity=4.0)
        )
        updated = await svc.update_bom_change(ecn_id, item_id, change.id, quantity=8.0)
        assert updated.quantity == pytest.approx(8.0)

    async def test_update_not_found_raises(self, db_session: AsyncSession):
        svc = ECNService(db_session)
        ecn_id, item_id = await _make_ecn_with_item(db_session)
        with pytest.raises(ECNNotFound):
            await svc.update_bom_change(
                ecn_id, item_id, "00000000-0000-0000-0000-000000000000", quantity=1.0
            )


class TestDeleteBomChange:
    async def test_delete_removes_row(self, db_session: AsyncSession):
        svc = ECNService(db_session)
        ecn_id, item_id = await _make_ecn_with_item(db_session)
        change = await svc.create_bom_change(
            ecn_id, item_id, BOMChangeRequest(change_type="ADD", component_number="LF200010")
        )
        await svc.delete_bom_change(ecn_id, item_id, change.id)
        changes = await svc.list_bom_changes(ecn_id, item_id)
        assert changes == []

    async def test_delete_not_found_raises(self, db_session: AsyncSession):
        svc = ECNService(db_session)
        ecn_id, item_id = await _make_ecn_with_item(db_session)
        with pytest.raises(ECNNotFound):
            await svc.delete_bom_change(
                ecn_id, item_id, "00000000-0000-0000-0000-000000000000"
            )


class TestEditLockAtDcApproved:
    """DC_APPROVED-and-beyond (workflow order, not raw int) blocks edits
    unless actor_role='DC'."""

    async def test_edit_blocked_when_ecn_at_dc_approved(self, db_session: AsyncSession):
        svc = ECNService(db_session)
        ecn_id, item_id = await _make_ecn_with_item(db_session)
        change = await svc.create_bom_change(
            ecn_id, item_id, BOMChangeRequest(change_type="ADD", component_number="LF200010")
        )
        import sqlalchemy as sa
        await db_session.execute(
            sa.text("UPDATE ecn_instances SET status = :status WHERE id = :id"),
            {"status": int(ECNStatus.DC_APPROVED), "id": ecn_id},
        )
        with pytest.raises(ECNValidationError, match="DC_APPROVED"):
            await svc.update_bom_change(ecn_id, item_id, change.id, quantity=9.0)

    async def test_edit_allowed_at_dc_approved_with_dc_role(self, db_session: AsyncSession):
        svc = ECNService(db_session)
        ecn_id, item_id = await _make_ecn_with_item(db_session)
        change = await svc.create_bom_change(
            ecn_id, item_id, BOMChangeRequest(change_type="ADD", component_number="LF200010")
        )
        import sqlalchemy as sa
        await db_session.execute(
            sa.text("UPDATE ecn_instances SET status = :status WHERE id = :id"),
            {"status": int(ECNStatus.DC_APPROVED), "id": ecn_id},
        )
        updated = await svc.update_bom_change(
            ecn_id, item_id, change.id, actor_role="DC", quantity=9.0
        )
        assert updated.quantity == pytest.approx(9.0)

    async def test_edit_still_allowed_before_dc_approved(self, db_session: AsyncSession):
        """DRAFT is well before DC_APPROVED in workflow order — edits allowed
        with no actor_role at all (matches routing ops' DRAFT-open behaviour)."""
        svc = ECNService(db_session)
        ecn_id, item_id = await _make_ecn_with_item(db_session)
        change = await svc.create_bom_change(
            ecn_id, item_id, BOMChangeRequest(change_type="ADD", component_number="LF200010")
        )
        updated = await svc.update_bom_change(ecn_id, item_id, change.id, quantity=5.0)
        assert updated.quantity == pytest.approx(5.0)

    async def test_create_blocked_at_dc_approved_without_dc_role(self, db_session: AsyncSession):
        svc = ECNService(db_session)
        ecn_id, item_id = await _make_ecn_with_item(db_session)
        import sqlalchemy as sa
        await db_session.execute(
            sa.text("UPDATE ecn_instances SET status = :status WHERE id = :id"),
            {"status": int(ECNStatus.DC_APPROVED), "id": ecn_id},
        )
        with pytest.raises(ECNValidationError, match="DC_APPROVED"):
            await svc.create_bom_change(
                ecn_id, item_id, BOMChangeRequest(change_type="ADD", component_number="LF200099")
            )

    async def test_delete_blocked_at_approved_without_dc_role(self, db_session: AsyncSession):
        """APPROVED(50) is also post-DC_APPROVED in workflow order."""
        svc = ECNService(db_session)
        ecn_id, item_id = await _make_ecn_with_item(db_session)
        change = await svc.create_bom_change(
            ecn_id, item_id, BOMChangeRequest(change_type="ADD", component_number="LF200010")
        )
        import sqlalchemy as sa
        await db_session.execute(
            sa.text("UPDATE ecn_instances SET status = :status WHERE id = :id"),
            {"status": int(ECNStatus.APPROVED), "id": ecn_id},
        )
        with pytest.raises(ECNValidationError, match="DC_APPROVED"):
            await svc.delete_bom_change(ecn_id, item_id, change.id)
