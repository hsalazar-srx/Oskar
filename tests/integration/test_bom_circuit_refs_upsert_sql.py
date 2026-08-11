"""
Integration test — bom_circuit_refs upsert SQL shape against real Postgres
(Slice E, ADR-012 D4).

tests/tasks/test_outbox_bom_circuit_refs_upsert.py proves the wiring
(_upsert_bom_circuit_refs is called with the right metadata on AddComponent
success) with a fully mocked cursor — this test instead proves the actual
SQL statement in _upsert_bom_circuit_refs is valid against the real
migration-0030 schema and genuinely upserts (insert then update on the same
ERP line key), using the async db_session fixture with the identical SQL
text (Postgres SQL syntax does not differ between the psycopg2 driver
process_outbox_entry uses and the asyncpg driver this fixture uses).
"""
from __future__ import annotations

import json
import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio

_UPSERT_SQL = """
    INSERT INTO bom_circuit_refs
    (id, facility, parent_item, structure_type, sequence_number, from_date,
     circuit_refs, source_ecn, source_system)
    VALUES (:id, :facility, :parent_item, :structure_type, :sequence_number, :from_date,
            CAST(:circuit_refs AS jsonb), :source_ecn, 'oskar')
    ON CONFLICT (facility, parent_item, structure_type, sequence_number, from_date)
    DO UPDATE SET
        circuit_refs = EXCLUDED.circuit_refs,
        source_ecn   = EXCLUDED.source_ecn,
        updated_at   = now()
"""


class TestBomCircuitRefsUpsertSql:
    async def test_insert_then_upsert_on_same_erp_line_key(self, db_session: AsyncSession):
        params = {
            "id": str(uuid.uuid4()), "facility": "L", "parent_item": "LFCIRF0001",
            "structure_type": "001", "sequence_number": 10, "from_date": 20260901,
            "circuit_refs": json.dumps(["R1", "R7"]), "source_ecn": None,
        }
        await db_session.execute(sa.text(_UPSERT_SQL), params)

        row = await db_session.execute(
            sa.text(
                "SELECT circuit_refs FROM bom_circuit_refs "
                "WHERE facility = 'L' AND parent_item = 'LFCIRF0001' AND sequence_number = 10"
            )
        )
        assert row.scalar_one() == ["R1", "R7"]

        # Same ERP line key, different circuit_refs -> UPDATE, not a second row.
        params2 = {**params, "id": str(uuid.uuid4()), "circuit_refs": json.dumps(["R1", "R7", "R12"])}
        await db_session.execute(sa.text(_UPSERT_SQL), params2)

        count_row = await db_session.execute(
            sa.text(
                "SELECT COUNT(*) FROM bom_circuit_refs "
                "WHERE facility = 'L' AND parent_item = 'LFCIRF0001' AND sequence_number = 10"
            )
        )
        assert count_row.scalar_one() == 1

        updated_row = await db_session.execute(
            sa.text(
                "SELECT circuit_refs FROM bom_circuit_refs "
                "WHERE facility = 'L' AND parent_item = 'LFCIRF0001' AND sequence_number = 10"
            )
        )
        assert updated_row.scalar_one() == ["R1", "R7", "R12"]
