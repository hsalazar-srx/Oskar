"""
OSKAR — movex_outbox.depends_on migration shape (Slice E0, ADR-012 Decision 3)

Real-Postgres schema-shape test for migration 0029. Dispatch-logic tests
(the actual dependency-gating behaviour) live in
tests/tasks/test_outbox_depends_on.py — pure, mocked, no DB needed there.
"""
from __future__ import annotations

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio


class TestOutboxDependsOnColumn:
    async def test_column_exists_and_is_nullable(self, db_session: AsyncSession):
        result = await db_session.execute(
            sa.text(
                "SELECT is_nullable FROM information_schema.columns "
                "WHERE table_name = 'movex_outbox' AND column_name = 'depends_on'"
            )
        )
        row = result.first()
        assert row is not None
        assert row[0] == "YES"

    async def test_depends_on_references_movex_outbox_id(self, db_session: AsyncSession):
        result = await db_session.execute(
            sa.text(
                "SELECT ccu.table_name, ccu.column_name "
                "FROM information_schema.table_constraints tc "
                "JOIN information_schema.key_column_usage kcu "
                "  ON tc.constraint_name = kcu.constraint_name "
                "JOIN information_schema.constraint_column_usage ccu "
                "  ON tc.constraint_name = ccu.constraint_name "
                "WHERE tc.table_name = 'movex_outbox' "
                "  AND kcu.column_name = 'depends_on' "
                "  AND tc.constraint_type = 'FOREIGN KEY'"
            )
        )
        row = result.first()
        assert row is not None
        assert row[0] == "movex_outbox"
        assert row[1] == "id"

    async def test_partial_index_exists(self, db_session: AsyncSession):
        result = await db_session.execute(
            sa.text(
                "SELECT indexdef FROM pg_indexes "
                "WHERE tablename = 'movex_outbox' AND indexname = 'idx_outbox_depends_on'"
            )
        )
        row = result.first()
        assert row is not None
        assert "WHERE" in row[0]
