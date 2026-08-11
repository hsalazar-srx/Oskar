"""
OSKAR — ecn_bom_changes supersession extension + bom_circuit_refs (Slice E,
ADR-012 D4/D6, migration 0030).

Real-Postgres schema-shape test for migration 0030. This extends the
skeletal ecn_bom_changes table from migration 0001 (which has no old-value/
ref-des/sequence columns — see ADR-012's "Verified code anchors") rather than
creating it fresh, and adds the new bom_circuit_refs table (D4 — Stargile
ZECNCIRF migrates into an Oskar-owned table keyed by the ERP line key).
"""
from __future__ import annotations

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio


class TestEcnBomChangesSupersessionColumns:
    """New columns added to the existing (migration 0001) ecn_bom_changes table."""

    @pytest.mark.parametrize(
        "column_name,expected_nullable",
        [
            ("sequence_number", "YES"),
            ("old_quantity", "YES"),
            ("old_operation_number", "YES"),
            ("old_from_date", "YES"),
            ("old_to_date", "YES"),
            ("circuit_refs_old", "YES"),
            ("circuit_refs_new", "YES"),
            ("snapshot_id", "YES"),
        ],
    )
    async def test_column_exists_and_is_nullable(
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

    async def test_snapshot_id_references_bom_snapshots(self, db_session: AsyncSession):
        result = await db_session.execute(
            sa.text(
                "SELECT ccu.table_name, ccu.column_name "
                "FROM information_schema.table_constraints tc "
                "JOIN information_schema.key_column_usage kcu "
                "  ON tc.constraint_name = kcu.constraint_name "
                "JOIN information_schema.constraint_column_usage ccu "
                "  ON tc.constraint_name = ccu.constraint_name "
                "WHERE tc.table_name = 'ecn_bom_changes' "
                "  AND kcu.column_name = 'snapshot_id' "
                "  AND tc.constraint_type = 'FOREIGN KEY'"
            )
        )
        row = result.first()
        assert row is not None
        assert row[0] == "bom_snapshots"
        assert row[1] == "id"

    async def test_old_quantity_is_decimal(self, db_session: AsyncSession):
        result = await db_session.execute(
            sa.text(
                "SELECT data_type FROM information_schema.columns "
                "WHERE table_name = 'ecn_bom_changes' AND column_name = 'old_quantity'"
            )
        )
        row = result.first()
        assert row is not None
        assert row[0] == "numeric"


class TestBomCircuitRefsTable:
    """New bom_circuit_refs table (D4) — ERP line key (facility, parent_item,
    structure_type, sequence_number, from_date) UNIQUE."""

    async def test_table_exists_with_expected_columns(self, db_session: AsyncSession):
        result = await db_session.execute(
            sa.text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'bom_circuit_refs'"
            )
        )
        columns = {r[0] for r in result.fetchall()}
        expected = {
            "id", "facility", "parent_item", "structure_type", "sequence_number",
            "from_date", "to_date", "circuit_refs", "source_ecn", "source_system",
        }
        assert expected.issubset(columns), f"missing columns: {expected - columns}"

    async def test_unique_constraint_on_erp_line_key(self, db_session: AsyncSession):
        result = await db_session.execute(
            sa.text(
                "SELECT kcu.column_name FROM information_schema.table_constraints tc "
                "JOIN information_schema.key_column_usage kcu "
                "  ON tc.constraint_name = kcu.constraint_name "
                "WHERE tc.table_name = 'bom_circuit_refs' "
                "  AND tc.constraint_type = 'UNIQUE'"
            )
        )
        cols = {r[0] for r in result.fetchall()}
        assert cols == {"facility", "parent_item", "structure_type", "sequence_number", "from_date"}

    async def test_insert_and_select_round_trip(self, db_session: AsyncSession):
        await db_session.execute(
            sa.text(
                "INSERT INTO bom_circuit_refs "
                "(id, facility, parent_item, structure_type, sequence_number, from_date, "
                " to_date, circuit_refs, source_ecn, source_system) "
                "VALUES (gen_random_uuid(), 'D', 'LF100001', '001', 10, 20240101, "
                " 99999999, CAST(:refs AS JSONB), NULL, 'oskar')"
            ),
            {"refs": '["R1", "R7", "R12"]'},
        )
        result = await db_session.execute(
            sa.text(
                "SELECT circuit_refs FROM bom_circuit_refs "
                "WHERE facility = 'D' AND parent_item = 'LF100001' AND sequence_number = 10"
            )
        )
        row = result.first()
        assert row is not None
        assert row[0] == ["R1", "R7", "R12"]

    async def test_duplicate_erp_line_key_rejected(self, db_session: AsyncSession):
        await db_session.execute(
            sa.text(
                "INSERT INTO bom_circuit_refs "
                "(id, facility, parent_item, structure_type, sequence_number, from_date, circuit_refs, source_system) "
                "VALUES (gen_random_uuid(), 'D', 'LF100002', '001', 20, 20240101, CAST('[]' AS JSONB), 'oskar')"
            )
        )
        with pytest.raises(Exception):
            await db_session.execute(
                sa.text(
                    "INSERT INTO bom_circuit_refs "
                    "(id, facility, parent_item, structure_type, sequence_number, from_date, circuit_refs, source_system) "
                    "VALUES (gen_random_uuid(), 'D', 'LF100002', '001', 20, 20240101, CAST('[]' AS JSONB), 'oskar')"
                )
            )
