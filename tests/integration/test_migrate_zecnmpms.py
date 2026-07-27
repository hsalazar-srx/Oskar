"""
OSKAR — ZECNMPMS migration CLI tests: DB-touching behaviour (Slice C).

Pure transform-layer tests live in tests/scripts/test_migrate_zecnmpms.py
instead — no DB needed there.

This file covers scripts/migrate_zecnmpms.py's async core against the real
Postgres test DB: dry-run (writes nothing), load (persists deduped rows),
idempotency (re-run doesn't duplicate), and --from-api mode exercised
end-to-end against the real Slice 0 stub (scripts/movex_stub.py) in-process
via httpx.ASGITransport — a genuine exercise of the M-1 contract, not a mock.
"""
from __future__ import annotations

import csv
from pathlib import Path

import httpx
import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from scripts.migrate_zecnmpms import _fetch_all_pages, migrate_zecnmpms_async
from scripts.movex_stub import create_app

pytestmark = pytest.mark.asyncio

_FIXTURE_CSV = (
    Path(__file__).resolve().parent.parent / "fixtures" / "bom" / "zecnmpms_sample.csv"
)


def _load_fixture_rows() -> list[dict]:
    with _FIXTURE_CSV.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


class TestMigrateDryRun:
    async def test_dry_run_writes_nothing(self, db_session: AsyncSession):
        rows = _load_fixture_rows()
        report = await migrate_zecnmpms_async(db_session, rows, dry_run=True)
        assert report.dry_run is True
        assert report.loaded_rows == 6
        count = (await db_session.execute(sa.text("SELECT COUNT(*) FROM item_mpns"))).scalar_one()
        assert count == 0


class TestMigrateLoad:
    async def test_load_persists_all_deduped_rows(self, db_session: AsyncSession):
        rows = _load_fixture_rows()
        report = await migrate_zecnmpms_async(db_session, rows, dry_run=False)
        assert report.loaded_rows == 6
        count = (await db_session.execute(sa.text("SELECT COUNT(*) FROM item_mpns"))).scalar_one()
        assert count == 6

    async def test_loaded_row_has_transformed_fields(self, db_session: AsyncSession):
        rows = _load_fixture_rows()
        await migrate_zecnmpms_async(db_session, rows, dry_run=False)
        result = await db_session.execute(
            sa.text(
                "SELECT source_system, migrated_at, from_date, to_date "
                "FROM item_mpns WHERE item_number = 'LF200011'"
            )
        )
        row = result.mappings().first()
        assert row is not None
        assert row["source_system"] == "zecnmpms"
        assert row["migrated_at"] is not None
        assert row["from_date"] is None  # MPFDAT=0 -> NULL
        assert row["to_date"] is None    # MPTDAT=99999999 -> NULL

    async def test_duplicate_natural_key_loads_as_one_row(self, db_session: AsyncSession):
        rows = _load_fixture_rows()
        await migrate_zecnmpms_async(db_session, rows, dry_run=False)
        count = (
            await db_session.execute(
                sa.text(
                    "SELECT COUNT(*) FROM item_mpns WHERE item_number = 'LF200010' "
                    "AND supplier_number = 'SUP001' AND mpn = 'STM32F103C8T6'"
                )
            )
        ).scalar_one()
        assert count == 1


class TestMigrateIdempotent:
    async def test_rerun_does_not_duplicate_rows(self, db_session: AsyncSession):
        rows = _load_fixture_rows()
        await migrate_zecnmpms_async(db_session, rows, dry_run=False)
        count_after_first = (
            await db_session.execute(sa.text("SELECT COUNT(*) FROM item_mpns"))
        ).scalar_one()

        report2 = await migrate_zecnmpms_async(db_session, rows, dry_run=False)
        count_after_second = (
            await db_session.execute(sa.text("SELECT COUNT(*) FROM item_mpns"))
        ).scalar_one()

        assert count_after_first == 6
        assert count_after_second == count_after_first
        assert report2.loaded_rows == 6


# ── --from-api mode, exercised against the real Slice 0 stub (in-process) ───

class TestFetchAllPagesAgainstMovexStub:
    async def test_fetches_all_seven_raw_rows_across_pages(self):
        transport = httpx.ASGITransport(app=create_app())
        async with httpx.AsyncClient(transport=transport, base_url="http://stub") as client:
            rows = await _fetch_all_pages(client, cono="300", limit=3)
        assert len(rows) == 7
        assert rows[0]["ITNO"] == " lf200010 "  # raw, untransformed — confirms this hit the real stub

    async def test_migrate_from_stub_rows_end_to_end(self, db_session: AsyncSession):
        transport = httpx.ASGITransport(app=create_app())
        async with httpx.AsyncClient(transport=transport, base_url="http://stub") as client:
            rows = await _fetch_all_pages(client, cono="300")
        report = await migrate_zecnmpms_async(db_session, rows, dry_run=False)
        assert report.loaded_rows == 6
