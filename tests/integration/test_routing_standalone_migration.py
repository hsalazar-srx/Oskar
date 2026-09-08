"""
OSKAR — ecn_routing_operations gains ecn_id + item_number, ecn_item_id becomes
nullable (ADR-016, migration 0035).

The second half of ADR-016, after 0034 did the same for ecn_mpns. Stargile's
ZECNROUT carries its own RTPRNO (product number) alongside RTOPNO/RTOPDS/
RTPLGR/RTPITI/RTSETI, with no pointer to an items table
(Repository/MetadataIds/MOVEX/Tables/ZECNROUT.table).

TWO THINGS DIFFER FROM 0034, both verified against the live schema rather than
assumed from 0034's shape:

1. uq_routing_item_opno is a TABLE CONSTRAINT (pg_constraint.contype='u'), not
   a bare index. `DROP INDEX` fails on it — it needs `DROP CONSTRAINT`. 0034's
   uq_ecn_mpn indexes were plain indexes, so that migration never hit this.

2. The FK is already ON DELETE CASCADE (0034's was RESTRICT). Moving it to SET
   NULL is a real behaviour change: deleting an item currently DELETES its
   routing operations, and after this it leaves them behind with item_number
   intact. TestDeletingAnItemKeepsItsRoutingOps covers that directly, because
   it is the kind of change that is easy to make by accident and hard to
   notice.

The unique-index trap from 0034 applies identically: a unique constraint keyed
on a nullable column stops enforcing anything for NULL rows, since Postgres
treats NULLs as distinct.
"""
from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio


class TestRoutingDecouplingColumns:
    @pytest.mark.parametrize(
        "column_name,expected_nullable",
        [
            ("ecn_id", "NO"),
            ("item_number", "NO"),
            ("ecn_item_id", "YES"),
        ],
    )
    async def test_column_nullability(
        self, db_session: AsyncSession, column_name: str, expected_nullable: str
    ):
        result = await db_session.execute(
            sa.text(
                "SELECT is_nullable FROM information_schema.columns "
                "WHERE table_name = 'ecn_routing_operations' AND column_name = :col"
            ),
            {"col": column_name},
        )
        row = result.first()
        assert row is not None, f"{column_name} does not exist on ecn_routing_operations"
        assert row[0] == expected_nullable

    async def test_ecn_id_references_ecn_instances_on_delete_cascade(
        self, db_session: AsyncSession
    ):
        result = await db_session.execute(
            sa.text(
                "SELECT confrelid::regclass::text, confdeltype::text FROM pg_constraint "
                "WHERE conrelid = 'ecn_routing_operations'::regclass "
                "  AND conname = 'ecn_routing_operations_ecn_id_fkey'"
            )
        )
        row = result.first()
        assert row is not None, "ecn_routing_operations_ecn_id_fkey does not exist"
        assert row[0] == "ecn_instances"
        assert row[1] == "c"  # CASCADE

    async def test_ecn_item_id_fk_moved_from_cascade_to_set_null(
        self, db_session: AsyncSession
    ):
        """Was ON DELETE CASCADE (migration 0009) — deleting an item silently
        destroyed its routing operations. As a convenience link it must SET
        NULL instead, so the operations survive on their item_number."""
        result = await db_session.execute(
            sa.text(
                "SELECT confdeltype::text FROM pg_constraint "
                "WHERE conrelid = 'ecn_routing_operations'::regclass "
                "  AND conname = 'ecn_routing_operations_ecn_item_id_fkey'"
            )
        )
        row = result.first()
        assert row is not None
        assert row[0] == "n"  # SET NULL — was 'c' (CASCADE) before 0035


class TestUniqueConstraintRebuilt:
    async def test_old_constraint_is_gone(self, db_session: AsyncSession):
        """It was a table constraint, not an index — if the migration used
        DROP INDEX it would have failed outright, but assert the end state
        rather than trusting that."""
        result = await db_session.execute(
            sa.text(
                "SELECT COUNT(*) FROM pg_constraint "
                "WHERE conrelid = 'ecn_routing_operations'::regclass "
                "  AND conname = 'uq_routing_item_opno'"
            )
        )
        assert result.scalar_one() == 0

    async def test_new_constraint_keys_on_ecn_and_item_number(
        self, db_session: AsyncSession
    ):
        result = await db_session.execute(
            sa.text(
                "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
                "WHERE conrelid = 'ecn_routing_operations'::regclass "
                "  AND conname = 'uq_routing_ecn_item_opno'"
            )
        )
        row = result.first()
        assert row is not None, "uq_routing_ecn_item_opno does not exist"
        definition = row[0]
        assert "ecn_id" in definition
        assert "item_number" in definition
        assert "operation_number" in definition
        assert "ecn_item_id" not in definition


class TestStandaloneRowsAreStillConstrained:
    """The 0034 trap, re-checked here: a uniqueness rule keyed on a nullable
    column enforces nothing for NULL rows. These fail if the constraint was
    not rebuilt."""

    async def _seed_ecn(self, db_session: AsyncSession) -> str:
        ecn_id = str(uuid.uuid4())
        await db_session.execute(
            sa.text(
                "INSERT INTO ecn_instances (id, ecn_number, title, originator_username) "
                "VALUES (:id, :num, 'Routing decoupling test', 'hsalazar')"
            ),
            {"id": ecn_id, "num": f"ECN-RT-{ecn_id[:8]}"},
        )
        return ecn_id

    async def _insert_op(
        self, db_session: AsyncSession, ecn_id: str, opno: int, *, item: str = "LF100001"
    ) -> None:
        await db_session.execute(
            sa.text(
                "INSERT INTO ecn_routing_operations "
                "(id, ecn_id, ecn_item_id, item_number, operation_number, "
                " operation_description, work_centre, run_time, change_type) "
                "VALUES (:id, :ecn_id, NULL, :item, :opno, 'Test op', 'WC01', 1.5, 'ADD')"
            ),
            {"id": str(uuid.uuid4()), "ecn_id": ecn_id, "item": item, "opno": opno},
        )

    async def test_duplicate_operation_number_on_same_item_is_rejected(
        self, db_session: AsyncSession
    ):
        ecn_id = await self._seed_ecn(db_session)
        await self._insert_op(db_session, ecn_id, 10)
        await db_session.flush()

        with pytest.raises(IntegrityError):
            await self._insert_op(db_session, ecn_id, 10)
            await db_session.flush()

    async def test_same_operation_number_on_a_different_item_is_allowed(
        self, db_session: AsyncSession
    ):
        """Operation numbers are per item — op 10 exists on nearly every
        routing. Scoping the constraint too widely would block normal data."""
        ecn_id = await self._seed_ecn(db_session)
        await self._insert_op(db_session, ecn_id, 10, item="LF100001")
        await self._insert_op(db_session, ecn_id, 10, item="LF100002")
        await db_session.flush()  # must not raise


class TestDeletingAnItemKeepsItsRoutingOps:
    async def test_item_delete_nulls_the_link_and_keeps_the_operation(
        self, db_session: AsyncSession
    ):
        """The behaviour change this migration makes. Before 0035 the FK was
        ON DELETE CASCADE, so deleting an item destroyed its routing
        operations outright. Now they survive on their own item_number."""
        ecn_id = str(uuid.uuid4())
        await db_session.execute(
            sa.text(
                "INSERT INTO ecn_instances (id, ecn_number, title, originator_username) "
                "VALUES (:id, :num, 'Routing survives item delete', 'hsalazar')"
            ),
            {"id": ecn_id, "num": f"ECN-RT2-{ecn_id[:8]}"},
        )
        item_id = str(uuid.uuid4())
        await db_session.execute(
            sa.text(
                "INSERT INTO ecn_items (id, ecn_id, line_number, item_number, effectivity_type) "
                "VALUES (:id, :ecn_id, 1, 'LF100001', 'IMMEDIATE')"
            ),
            {"id": item_id, "ecn_id": ecn_id},
        )
        op_id = str(uuid.uuid4())
        await db_session.execute(
            sa.text(
                "INSERT INTO ecn_routing_operations "
                "(id, ecn_id, ecn_item_id, item_number, operation_number, "
                " operation_description, work_centre, run_time, change_type) "
                "VALUES (:id, :ecn_id, :item_id, 'LF100001', 10, 'Op', 'WC01', 2.0, 'ADD')"
            ),
            {"id": op_id, "ecn_id": ecn_id, "item_id": item_id},
        )
        await db_session.flush()

        await db_session.execute(
            sa.text("DELETE FROM ecn_items WHERE id = :id"), {"id": item_id}
        )
        await db_session.flush()

        row = (
            await db_session.execute(
                sa.text(
                    "SELECT ecn_item_id, item_number FROM ecn_routing_operations "
                    "WHERE id = :id"
                ),
                {"id": op_id},
            )
        ).first()
        assert row is not None, "the routing operation was deleted — FK is still CASCADE"
        assert row[0] is None
        assert row[1] == "LF100001"


class TestBackfill:
    async def test_no_row_has_a_null_ecn_id_or_item_number(self, db_session: AsyncSession):
        result = await db_session.execute(
            sa.text(
                "SELECT count(*) FROM ecn_routing_operations "
                "WHERE ecn_id IS NULL OR item_number IS NULL OR TRIM(item_number) = ''"
            )
        )
        assert result.scalar_one() == 0

    async def test_backfilled_item_number_matches_the_linked_item(
        self, db_session: AsyncSession
    ):
        result = await db_session.execute(
            sa.text(
                "SELECT count(*) FROM ecn_routing_operations r "
                "JOIN ecn_items i ON i.id = r.ecn_item_id "
                "WHERE TRIM(r.item_number) <> TRIM(i.item_number)"
            )
        )
        assert result.scalar_one() == 0
