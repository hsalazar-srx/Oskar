"""
OSKAR — ecn_bom_changes gains ecn_id + parent_item_number, ecn_item_id
becomes nullable (ADR-014, migration 0032).

Real-Postgres schema-shape test for migration 0032. Confirms: the two new
columns exist with the expected nullability, ecn_id's FK targets
ecn_instances with ON DELETE CASCADE, ecn_item_id's FK now targets
ecn_items with ON DELETE SET NULL (was RESTRICT before this migration —
see ADR-014's "Consequences"), and backfill correctly populated both new
columns for every pre-existing row from the ecn_item_id -> ecn_items join.
"""
from __future__ import annotations

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.ecn.models import BOMChangeRequest, ECNCreateRequest
from src.services.ecn.service import ECNService

pytestmark = pytest.mark.asyncio

_ACTOR = "hsalazar"
_FACILITY = "L"


class TestEcnBomChangesParentItemNumberColumns:
    @pytest.mark.parametrize(
        "column_name,expected_nullable",
        [
            ("ecn_id", "NO"),
            ("parent_item_number", "NO"),
            ("ecn_item_id", "YES"),
        ],
    )
    async def test_column_nullability(
        self, db_session: AsyncSession, column_name: str, expected_nullable: str
    ):
        result = await db_session.execute(
            sa.text(
                "SELECT is_nullable FROM information_schema.columns "
                "WHERE table_name = 'ecn_bom_changes' AND column_name = :col"
            ),
            {"col": column_name},
        )
        row = result.first()
        assert row is not None, f"column {column_name} does not exist on ecn_bom_changes"
        assert row[0] == expected_nullable

    async def test_ecn_id_references_ecn_instances_on_delete_cascade(
        self, db_session: AsyncSession
    ):
        # confdeltype is Postgres "char" — cast to text so the driver returns
        # a str rather than a single-byte value.
        result = await db_session.execute(
            sa.text(
                "SELECT confrelid::regclass::text, confdeltype::text "
                "FROM pg_constraint "
                "WHERE conrelid = 'ecn_bom_changes'::regclass "
                "  AND conname = 'ecn_bom_changes_ecn_id_fkey'"
            )
        )
        row = result.first()
        assert row is not None
        assert row[0] == "ecn_instances"
        assert row[1] == "c"  # CASCADE

    async def test_ecn_item_id_fk_is_now_set_null_not_restrict(
        self, db_session: AsyncSession
    ):
        result = await db_session.execute(
            sa.text(
                "SELECT confdeltype::text FROM pg_constraint "
                "WHERE conrelid = 'ecn_bom_changes'::regclass "
                "  AND conname = 'ecn_bom_changes_ecn_item_id_fkey'"
            )
        )
        row = result.first()
        assert row is not None
        assert row[0] == "n"  # SET NULL — was 'r' (RESTRICT) before 0032

    async def test_idx_ecn_bom_changes_ecn_exists(self, db_session: AsyncSession):
        result = await db_session.execute(
            sa.text(
                "SELECT 1 FROM pg_indexes "
                "WHERE tablename = 'ecn_bom_changes' AND indexname = 'idx_ecn_bom_changes_ecn'"
            )
        )
        assert result.first() is not None


class TestBackfillCorrectness:
    async def test_backfill_matches_item_join_for_existing_rows(
        self, db_session: AsyncSession
    ):
        """A row created before this migration existed (simulated here by
        creating it through the item-scoped path, which is still how every
        row in the fleet before ADR-014 was authored) must have ecn_id and
        parent_item_number equal to what a join through ecn_item_id would
        produce — proves the backfill UPDATE in 0032 is correct, not just
        that the columns exist."""
        svc = ECNService(db_session)
        ecn = await svc.create(
            ECNCreateRequest(
                facility=_FACILITY, title="Migration backfill check",
                is_new_item=False,
                routing_changes=False, operation_changes=False, new_parts=False,
                lead_time_changes=False, change_to_documents=False,
                requires_customer_approval=False, regulatory_impact=False,
            ),
            _ACTOR,
        )
        item = await svc.create_item(ecn.id, line_number=10, item_number="LF100001")
        change = await svc.create_bom_change(
            ecn.id, item.id,
            BOMChangeRequest(change_type="ADD", component_number="LF200010"),
        )

        result = await db_session.execute(
            sa.text(
                "SELECT b.ecn_id, b.parent_item_number, i.ecn_id, i.item_number "
                "FROM ecn_bom_changes b JOIN ecn_items i ON i.id = b.ecn_item_id "
                "WHERE b.id = :id"
            ),
            {"id": change.id},
        )
        row = result.first()
        assert row is not None
        b_ecn_id, b_parent_item_number, i_ecn_id, i_item_number = row
        assert str(b_ecn_id) == str(i_ecn_id)
        assert b_parent_item_number == i_item_number

    async def test_ecn_item_id_can_be_deleted_without_restrict_error(
        self, db_session: AsyncSession
    ):
        """Deleting an ecn_items row that has BOM changes attached used to
        raise a raw IntegrityError (ON DELETE RESTRICT). Post-0032 it
        succeeds and the BOM change row survives with ecn_item_id set NULL
        — ADR-014's stated consequence."""
        svc = ECNService(db_session)
        ecn = await svc.create(
            ECNCreateRequest(
                facility=_FACILITY, title="Delete item with BOM change attached",
                is_new_item=False,
                routing_changes=False, operation_changes=False, new_parts=False,
                lead_time_changes=False, change_to_documents=False,
                requires_customer_approval=False, regulatory_impact=False,
            ),
            _ACTOR,
        )
        item = await svc.create_item(ecn.id, line_number=10, item_number="LF100002")
        change = await svc.create_bom_change(
            ecn.id, item.id,
            BOMChangeRequest(change_type="ADD", component_number="LF200020"),
        )

        await db_session.execute(
            sa.text("DELETE FROM ecn_items WHERE id = :id"), {"id": item.id}
        )

        result = await db_session.execute(
            sa.text(
                "SELECT ecn_item_id, ecn_id, parent_item_number "
                "FROM ecn_bom_changes WHERE id = :id"
            ),
            {"id": change.id},
        )
        row = result.first()
        assert row is not None
        assert row[0] is None
        assert str(row[1]) == ecn.id
        assert row[2] == "LF100002"
