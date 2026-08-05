"""
Integration tests — migration 0026 (bom_snapshots), Slice D, ADR-012 D2.

Runs against the real Postgres test DB (tests/integration/conftest.py:
db_engine applies `alembic upgrade head` once per session; db_session gives
each test a rolled-back connection).

Hash stability / key-order independence: content_hash is computed
application-side by src/services/bom/snapshots.py's content_hash() — pure
logic, also covered without a DB in tests/services/bom/test_snapshots.py.
The tests here exercise the DB-touching insert_snapshot()/get_snapshot()
round trip and the table shape itself.
"""
from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.bom.snapshots import content_hash, get_snapshot, insert_snapshot, list_snapshots

pytestmark = pytest.mark.asyncio


class TestBomSnapshotsTableShape:
    async def test_table_exists_with_expected_columns(self, db_session: AsyncSession):
        result = await db_session.execute(
            sa.text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'bom_snapshots'"
            )
        )
        columns = {r[0] for r in result}
        expected = {
            "id", "item_number", "facility", "structure_type", "level_mode",
            "lines", "line_count", "content_hash", "reason", "ecn_id",
            "captured_by", "captured_at",
        }
        assert expected <= columns

    async def test_reason_check_constraint_rejects_invalid_value(self, db_session: AsyncSession):
        with pytest.raises(Exception):
            await db_session.execute(
                sa.text(
                    "INSERT INTO bom_snapshots "
                    "(id, item_number, facility, lines, line_count, content_hash, reason, captured_by) "
                    "VALUES (:id, 'LF100001', 'D', '[]'::jsonb, 0, :hash, 'not_a_real_reason', 'tester')"
                ),
                {"id": str(uuid.uuid4()), "hash": "0" * 64},
            )


class TestSnapshotInsertAndFetch:
    async def test_insert_then_get_round_trips_lines(self, db_session: AsyncSession):
        lines = [{"component_number": "LF200010", "quantity": 4.0}]

        inserted = await insert_snapshot(
            db_session,
            item_number="LF100001",
            facility="D",
            lines=lines,
            reason="compare",
            captured_by="eng_user",
        )
        fetched = await get_snapshot(db_session, inserted.id)

        assert fetched is not None
        assert fetched.lines == lines
        assert fetched.item_number == "LF100001"
        assert fetched.line_count == 1

    async def test_content_hash_is_stored_and_stable_regardless_of_key_order(
        self, db_session: AsyncSession
    ):
        lines_a = [{"component_number": "LF200010", "quantity": 4.0}]
        lines_b = [{"quantity": 4.0, "component_number": "LF200010"}]

        snap_a = await insert_snapshot(
            db_session, item_number="LF100001", facility="D", lines=lines_a,
            reason="compare", captured_by="eng_user",
        )
        snap_b = await insert_snapshot(
            db_session, item_number="LF100001", facility="D", lines=lines_b,
            reason="compare", captured_by="eng_user",
        )

        assert snap_a.content_hash == snap_b.content_hash
        assert snap_a.content_hash == content_hash(lines_a)

    async def test_get_snapshot_returns_none_for_unknown_id(self, db_session: AsyncSession):
        result = await get_snapshot(db_session, str(uuid.uuid4()))
        assert result is None

    async def test_list_snapshots_orders_newest_first(self, db_session: AsyncSession):
        await insert_snapshot(
            db_session, item_number="LF300001", facility="D", lines=[{"a": 1}],
            reason="manual", captured_by="eng_user",
        )
        await insert_snapshot(
            db_session, item_number="LF300001", facility="D", lines=[{"a": 2}],
            reason="manual", captured_by="eng_user",
        )

        results = await list_snapshots(db_session, item_number="LF300001", facility="D")

        assert len(results) == 2
        assert results[0].captured_at >= results[1].captured_at
