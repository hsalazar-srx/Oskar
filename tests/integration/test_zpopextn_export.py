"""
OSKAR — ZPOPEXTN replacement export tests (Slice C, ADR-012 Decision 5 / R7).

Stargile's PurchaseExtensionNightJob wrote default-MPN data to a physical
DB2/M3 table (ZPOPEXTN) that Purchasing's PO-print process read. Oskar has no
DB2/M3 write path of its own (that's movex-rest-api's domain, out of Slice C
scope) and 0026+ migration numbers are reserved for Slice D/E per the plan's
"New Alembic migrations" section — so this replacement is deliberately a CSV
file export rather than a new physical table, avoiding both problems while
still giving Purchasing something concrete to consume. See the module
docstring in src/tasks/zpopextn_export.py for the full judgment-call writeup;
this is explicitly flagged in the final report as needing real Purchasing
sign-off on the actual delivery mechanism before go-live.

DB-touching — lives under tests/integration/ per this codebase's convention.
"""
from __future__ import annotations

import csv
import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.bom.mpn_master import upsert_item_mpn
from src.tasks.zpopextn_export import export_default_mpns_async

pytestmark = pytest.mark.asyncio


class TestZpopextnExport:
    async def test_writes_current_default_row(self, db_session: AsyncSession, tmp_path):
        item_number = f"LFZPX{uuid.uuid4().hex[:6].upper()}"
        await upsert_item_mpn(
            db_session, item_number=item_number, mpn="ZPXPART1", supplier_number="SUP001",
            manufacturer_canonical="Murata", is_default=True,
            price=1.23, currency="USD", moq=1, spq=1,
            distributor_number="DK", distributor_name="Digi-Key",
        )
        out_file = tmp_path / "export.csv"

        count = await export_default_mpns_async(db_session, out_file)
        assert count >= 1

        with out_file.open(newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        match = [r for r in rows if r["item_number"] == item_number]
        assert len(match) == 1
        assert match[0]["mpn"] == "ZPXPART1"
        assert match[0]["manufacturer_canonical"] == "Murata"
        assert match[0]["distributor_number"] == "DK"

    async def test_non_default_row_excluded(self, db_session: AsyncSession, tmp_path):
        item_number = f"LFZPX{uuid.uuid4().hex[:6].upper()}"
        await upsert_item_mpn(
            db_session, item_number=item_number, mpn="ZPXPART2", is_default=False,
        )
        out_file = tmp_path / "export.csv"
        await export_default_mpns_async(db_session, out_file)

        with out_file.open(newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        assert not any(r["item_number"] == item_number for r in rows)

    async def test_end_dated_default_excluded(self, db_session: AsyncSession, tmp_path):
        import datetime
        item_number = f"LFZPX{uuid.uuid4().hex[:6].upper()}"
        await upsert_item_mpn(
            db_session, item_number=item_number, mpn="ZPXPART3", is_default=True,
            end_effective_date=datetime.date(2020, 1, 1),
        )
        out_file = tmp_path / "export.csv"
        await export_default_mpns_async(db_session, out_file)

        with out_file.open(newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        assert not any(r["item_number"] == item_number for r in rows)

    async def test_creates_parent_directory_if_missing(self, db_session: AsyncSession, tmp_path):
        out_file = tmp_path / "nested" / "dir" / "export.csv"
        count = await export_default_mpns_async(db_session, out_file)
        assert out_file.exists()
        assert isinstance(count, int)
