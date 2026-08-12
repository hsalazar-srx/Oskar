"""
Integration tests — ECNBomChangesMixin.bulk_create_bom_changes against real
Postgres (Slice E, I2-6).

ECN-wide, multi-item — verified against the real Stargile UploadECNBoMs.java
source (2026-08-11): item_number is a per-row field, not a fixed scope, same
shape as bulk_create_routing_operations.
"""
from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.ecn.models import ECNCreateRequest, ECNNotFound, ECNValidationError
from src.services.ecn.service import ECNService
from src.workflow.machine import ECNStatus

pytestmark = pytest.mark.asyncio

_ACTOR = "hsalazar"
_FACILITY = "L"


async def _make_ecn_with_items(db_session: AsyncSession) -> tuple[str, str, str]:
    svc = ECNService(db_session)
    req = ECNCreateRequest(
        facility=_FACILITY, title="Bulk BOM changes integration test",
        is_new_item=False, routing_changes=False, operation_changes=False,
        new_parts=False, change_parts=True, bom_changes=True,
        lead_time_changes=False, change_to_documents=False,
        requires_customer_approval=False, regulatory_impact=False,
    )
    ecn = await svc.create(req, _ACTOR)
    item1 = await svc.create_item(ecn.id, line_number=10, item_number="LFBULK0001")
    item2 = await svc.create_item(ecn.id, line_number=20, item_number="LFBULK0002")
    return ecn.id, item1.id, item2.id


class TestBulkCreateBomChanges:
    async def test_multi_item_insert(self, db_session: AsyncSession):
        """Rows spread across two different items in one upload — the
        multi-item shape verified against Stargile's real UploadECNBoMs.java."""
        svc = ECNService(db_session)
        ecn_id, _item1_id, _item2_id = await _make_ecn_with_items(db_session)
        rows = [
            {"item_number": "LFBULK0001", "component_number": "LF200010", "change_type": "ADD",
             "quantity": 4.0, "operation_number": 10, "from_date": 20260901},
            {"item_number": "LFBULK0002", "component_number": "LF200020", "change_type": "ADD",
             "quantity": 2.0, "operation_number": 20, "from_date": 20260901},
        ]
        changes = await svc.bulk_create_bom_changes(ecn_id, rows)
        assert len(changes) == 2
        assert {c.item_number for c in changes} == {"LFBULK0001", "LFBULK0002"}
        assert {c.component_number for c in changes} == {"LF200010", "LF200020"}

    async def test_sequence_number_notes_and_circuit_refs_are_persisted(
        self, db_session: AsyncSession
    ):
        """Regression: the bulk INSERT used to omit sequence_number, notes,
        and circuit_refs_new entirely, silently dropping them even when a
        caller supplied them — the single-row create_bom_change endpoint and
        BOMChangesPanel.tsx's manual form always supported all three."""
        svc = ECNService(db_session)
        ecn_id, _item1_id, _item2_id = await _make_ecn_with_items(db_session)
        rows = [
            {"item_number": "LFBULK0001", "component_number": "LF200010", "change_type": "ADD",
             "quantity": 4.0, "operation_number": 10, "sequence_number": 100,
             "from_date": 20260901, "notes": "Added per SI review",
             "circuit_refs_new": ["R1", "R7", "R12"]},
        ]
        changes = await svc.bulk_create_bom_changes(ecn_id, rows)
        assert len(changes) == 1
        assert changes[0].sequence_number == 100
        assert changes[0].notes == "Added per SI review"
        assert changes[0].circuit_refs_new == ["R1", "R7", "R12"]

    async def test_single_item_multi_row_insert(self, db_session: AsyncSession):
        svc = ECNService(db_session)
        ecn_id, _item1_id, _item2_id = await _make_ecn_with_items(db_session)
        rows = [
            {"item_number": "LFBULK0001", "component_number": "LF200010", "change_type": "ADD",
             "quantity": 4.0, "operation_number": 10, "from_date": 20260901},
            {"item_number": "LFBULK0001", "component_number": "LF200030", "change_type": "ADD",
             "quantity": 1.0, "operation_number": 30, "from_date": 20260901},
        ]
        changes = await svc.bulk_create_bom_changes(ecn_id, rows)
        assert len(changes) == 2
        assert all(c.item_number == "LFBULK0001" for c in changes)

    async def test_duplicate_key_in_batch_raises(self, db_session: AsyncSession):
        svc = ECNService(db_session)
        ecn_id, _item1_id, _item2_id = await _make_ecn_with_items(db_session)
        rows = [
            {"item_number": "LFBULK0001", "component_number": "LF200010", "change_type": "ADD",
             "operation_number": 10},
            {"item_number": "LFBULK0001", "component_number": "LF200010", "change_type": "ADD",
             "operation_number": 10},
        ]
        with pytest.raises(ECNValidationError, match="more than once"):
            await svc.bulk_create_bom_changes(ecn_id, rows)

    async def test_same_component_different_items_not_a_duplicate(self, db_session: AsyncSession):
        svc = ECNService(db_session)
        ecn_id, _item1_id, _item2_id = await _make_ecn_with_items(db_session)
        rows = [
            {"item_number": "LFBULK0001", "component_number": "LF200010", "change_type": "ADD",
             "operation_number": 10},
            {"item_number": "LFBULK0002", "component_number": "LF200010", "change_type": "ADD",
             "operation_number": 10},
        ]
        changes = await svc.bulk_create_bom_changes(ecn_id, rows)
        assert len(changes) == 2

    async def test_change_type_without_old_from_date_raises(self, db_session: AsyncSession):
        svc = ECNService(db_session)
        ecn_id, _item1_id, _item2_id = await _make_ecn_with_items(db_session)
        rows = [{"item_number": "LFBULK0001", "component_number": "LF200010",
                  "change_type": "CHANGE", "quantity": 6.0}]
        with pytest.raises(ECNValidationError, match="old_from_date"):
            await svc.bulk_create_bom_changes(ecn_id, rows)

    async def test_unresolved_item_number_raises(self, db_session: AsyncSession):
        """item_number not already on this ECN — bulk BOM-change upload does
        not create items, same as bulk routing."""
        svc = ECNService(db_session)
        ecn_id, _item1_id, _item2_id = await _make_ecn_with_items(db_session)
        rows = [{"item_number": "LFNOTONECN", "component_number": "LF200010", "change_type": "ADD"}]
        with pytest.raises(ECNValidationError, match="item_number"):
            await svc.bulk_create_bom_changes(ecn_id, rows)

    async def test_unknown_ecn_raises(self, db_session: AsyncSession):
        svc = ECNService(db_session)
        rows = [{"item_number": "LFBULK0001", "component_number": "LF200010", "change_type": "ADD"}]
        with pytest.raises(ECNNotFound):
            await svc.bulk_create_bom_changes("00000000-0000-0000-0000-000000000000", rows)

    async def test_blocked_at_dc_approved_without_dc_role(self, db_session: AsyncSession):
        svc = ECNService(db_session)
        ecn_id, _item1_id, _item2_id = await _make_ecn_with_items(db_session)
        import sqlalchemy as sa
        await db_session.execute(
            sa.text("UPDATE ecn_instances SET status = :status WHERE id = :id"),
            {"status": int(ECNStatus.DC_APPROVED), "id": ecn_id},
        )
        rows = [{"item_number": "LFBULK0001", "component_number": "LF200010", "change_type": "ADD"}]
        with pytest.raises(ECNValidationError, match="DC_APPROVED"):
            await svc.bulk_create_bom_changes(ecn_id, rows)
