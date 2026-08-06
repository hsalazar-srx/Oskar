"""
Integration tests — migration 0027 (bom_comparisons), Slice D, ADR-012 D5.

Runs against the real Postgres test DB (tests/integration/conftest.py).
Sides are descriptors ({type: erp|snapshot|upload, ...}), never a local BOM
mirror — see migration 0027's own docstring.
"""
from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.bom.comparisons import get_comparison, insert_comparison

pytestmark = pytest.mark.asyncio


class TestBomComparisonsTableShape:
    async def test_table_exists_with_expected_columns(self, db_session: AsyncSession):
        result = await db_session.execute(
            sa.text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'bom_comparisons'"
            )
        )
        columns = {r[0] for r in result}
        expected = {
            "id", "left_descriptor", "right_descriptor", "comparison_result",
            "cost_impact", "risk_flags", "created_by", "created_at",
        }
        assert expected <= columns

    async def test_risk_flags_defaults_to_empty_array(self, db_session: AsyncSession):
        row_id = str(uuid.uuid4())
        await db_session.execute(
            sa.text(
                "INSERT INTO bom_comparisons "
                "(id, left_descriptor, right_descriptor, comparison_result, created_by) "
                "VALUES (:id, '{}'::jsonb, '{}'::jsonb, '{}'::jsonb, 'tester')"
            ),
            {"id": row_id},
        )
        result = await db_session.execute(
            sa.text("SELECT risk_flags FROM bom_comparisons WHERE id = :id"), {"id": row_id}
        )
        assert result.scalar_one() == []


class TestInsertAndGetComparison:
    async def test_insert_then_get_round_trips_descriptors_and_result(
        self, db_session: AsyncSession
    ):
        left = {"type": "erp", "item_number": "LF100001", "facility": "D"}
        right = {"type": "snapshot", "snapshot_id": str(uuid.uuid4())}
        result_payload = {
            "added": [], "removed": [], "changed": [], "unresolved": [],
            "stats": {"left_count": 1, "right_count": 1, "added_count": 0,
                      "removed_count": 0, "changed_count": 0, "unresolved_count": 0},
        }

        inserted = await insert_comparison(
            db_session,
            left_descriptor=left,
            right_descriptor=right,
            comparison_result=result_payload,
            created_by="eng_user",
        )
        fetched = await get_comparison(db_session, inserted.id)

        assert fetched is not None
        assert fetched.left_descriptor == left
        assert fetched.right_descriptor == right
        assert fetched.comparison_result == result_payload
        assert fetched.risk_flags == []

    async def test_get_comparison_returns_none_for_unknown_id(self, db_session: AsyncSession):
        result = await get_comparison(db_session, str(uuid.uuid4()))
        assert result is None

    async def test_insert_with_risk_flags_and_cost_impact(self, db_session: AsyncSession):
        inserted = await insert_comparison(
            db_session,
            left_descriptor={"type": "upload", "filename": "old.csv"},
            right_descriptor={"type": "upload", "filename": "new.csv"},
            comparison_result={"added": [], "removed": [], "changed": [], "unresolved": [], "stats": {}},
            created_by="eng_user",
            risk_flags=["high_qty_change"],
            cost_impact=1234.56,
        )

        assert inserted.risk_flags == ["high_qty_change"]
        assert float(inserted.cost_impact) == 1234.56
