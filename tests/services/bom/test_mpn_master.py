"""
OSKAR — MPN master service tests (Slice C, ADR-012 D3).

normalize_manufacturer() / is_current_default() are pure (no DB) — TDD
mechanics classifies manufacturer-normalisation as pure unit logic, same as
the compare engine and explode math.

upsert_item_mpn() needs real persistence (ON CONFLICT + the partial unique
index on current defaults are genuinely Postgres behaviour, not something a
mock can verify) — those tests run against the live Postgres test DB via
tests/services/bom/conftest.py, which reuses tests/integration/conftest.py's
db_session/db_engine fixtures.
"""
from __future__ import annotations

import datetime
import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.bom.mpn_master import (
    ItemMPN,
    NormalizeResult,
    get_item_mpn,
    is_current_default,
    load_synonyms,
    normalize_manufacturer,
    upsert_item_mpn,
)

pytestmark = pytest.mark.asyncio


# ── normalize_manufacturer (pure) ──────────────────────────────────────────

class TestNormalizeManufacturer:
    def test_exact_match_returns_canonical(self):
        synonyms = {"ST MICRO": "STMicroelectronics"}
        result = normalize_manufacturer("ST MICRO", synonyms)
        assert result == NormalizeResult(canonical="STMicroelectronics", matched=True)

    def test_lookup_is_case_insensitive(self):
        synonyms = {"ST MICRO": "STMicroelectronics"}
        result = normalize_manufacturer("st micro", synonyms)
        assert result.canonical == "STMicroelectronics"
        assert result.matched is True

    def test_lookup_trims_whitespace(self):
        synonyms = {"TEXAS INSTRUMENT": "Texas Instruments"}
        result = normalize_manufacturer("  Texas Instrument  ", synonyms)
        assert result.canonical == "Texas Instruments"
        assert result.matched is True

    def test_miss_passes_through_trimmed_raw(self):
        result = normalize_manufacturer("  Some Unknown Mfr  ", {})
        assert result.canonical == "Some Unknown Mfr"
        assert result.matched is False

    def test_empty_string_is_a_miss_with_empty_canonical(self):
        result = normalize_manufacturer("   ", {})
        assert result.canonical == ""
        assert result.matched is False

    def test_none_is_a_miss_with_empty_canonical(self):
        result = normalize_manufacturer(None, {})
        assert result.canonical == ""
        assert result.matched is False


# ── is_current_default (pure) ──────────────────────────────────────────────

class TestIsCurrentDefault:
    def test_not_default_is_never_current(self):
        assert is_current_default(False, None) is False
        assert is_current_default(False, datetime.date(2099, 1, 1)) is False

    def test_default_with_no_end_date_is_current(self):
        assert is_current_default(True, None) is True

    def test_default_with_future_end_date_is_current(self):
        today = datetime.date(2026, 7, 23)
        assert is_current_default(True, today + datetime.timedelta(days=1), today=today) is True

    def test_default_with_end_date_equal_to_today_is_current(self):
        today = datetime.date(2026, 7, 23)
        assert is_current_default(True, today, today=today) is True

    def test_default_with_past_end_date_is_not_current(self):
        today = datetime.date(2026, 7, 23)
        assert is_current_default(True, today - datetime.timedelta(days=1), today=today) is False

    def test_defaults_to_real_today_when_not_supplied(self):
        # Fixed far-future date is always "current" regardless of the day this
        # suite runs — avoids depending on wall-clock date in the assertion.
        far_future = datetime.date(2099, 12, 31)
        assert is_current_default(True, far_future) is True


# ── load_synonyms (DB) ───────────────────────────────────────────────────────

class TestLoadSynonyms:
    async def test_includes_plm_seeded_synonym(self, db_session: AsyncSession):
        synonyms = await load_synonyms(db_session)
        assert synonyms["ST MICRO"] == "STMICROELECTRONICS"
        assert synonyms["TEXAS INSTRUMENT"] == "TEXAS INSTRUMENTS INCORPORATED"


# ── upsert_item_mpn (DB) ─────────────────────────────────────────────────────

class TestUpsertItemMpn:
    async def test_insert_new_row(self, db_session: AsyncSession):
        item_number = f"LFTEST{uuid.uuid4().hex[:8].upper()}"
        result = await upsert_item_mpn(
            db_session,
            item_number=item_number,
            mpn="MPN-001",
            supplier_number="SUP001",
            manufacturer_name="Murata",
            manufacturer_canonical="Murata",
            is_default=True,
        )
        assert isinstance(result, ItemMPN)
        assert result.item_number == item_number
        assert result.mpn == "MPN-001"
        assert result.is_default is True

    async def test_reinsert_same_natural_key_updates_not_duplicates(
        self, db_session: AsyncSession
    ):
        item_number = f"LFTEST{uuid.uuid4().hex[:8].upper()}"
        await upsert_item_mpn(
            db_session, item_number=item_number, mpn="MPN-002",
            supplier_number="SUP001", manufacturer_name="Old Name",
        )
        second = await upsert_item_mpn(
            db_session, item_number=item_number, mpn="MPN-002",
            supplier_number="SUP001", manufacturer_name="New Name",
        )
        assert second.manufacturer_name == "New Name"

        fetched = await get_item_mpn(db_session, item_number, "SUP001", "MPN-002")
        assert fetched is not None
        assert fetched.manufacturer_name == "New Name"

    async def test_setting_new_default_demotes_old_default(self, db_session: AsyncSession):
        item_number = f"LFTEST{uuid.uuid4().hex[:8].upper()}"
        await upsert_item_mpn(
            db_session, item_number=item_number, mpn="MPN-OLD",
            supplier_number="SUP001", is_default=True,
        )
        await upsert_item_mpn(
            db_session, item_number=item_number, mpn="MPN-NEW",
            supplier_number="SUP001", is_default=True,
        )
        old = await get_item_mpn(db_session, item_number, "SUP001", "MPN-OLD")
        new = await get_item_mpn(db_session, item_number, "SUP001", "MPN-NEW")
        assert old.end_effective_date is not None
        assert new.is_default is True
        assert new.end_effective_date is None

    async def test_get_item_mpn_returns_none_when_missing(self, db_session: AsyncSession):
        result = await get_item_mpn(db_session, "NOPE99999", "", "NOPE")
        assert result is None
