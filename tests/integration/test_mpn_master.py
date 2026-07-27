"""
OSKAR — MPN master service tests: DB-touching behaviour (Slice C, ADR-012 D3).

Pure logic (normalize_manufacturer, is_current_default, wildcard_to_like)
lives in tests/services/bom/test_mpn_master.py instead — no DB needed there.

This file covers load_synonyms, upsert_item_mpn (ON CONFLICT + the
partial-unique-index current-default demotion — genuinely Postgres behaviour,
not something a mock can verify), get_item_mpn, and search_item_mpns — all
against the real Postgres test DB via tests/integration/conftest.py's
db_session/db_engine fixtures (same pattern as test_helpers.py).
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.bom.mpn_master import (
    ItemMPN,
    get_item_mpn,
    load_synonyms,
    search_item_mpns,
    upsert_item_mpn,
)

pytestmark = pytest.mark.asyncio


# ── load_synonyms ────────────────────────────────────────────────────────────

class TestLoadSynonyms:
    async def test_includes_plm_seeded_synonym(self, db_session: AsyncSession):
        synonyms = await load_synonyms(db_session)
        assert synonyms["ST MICRO"] == "STMICROELECTRONICS"
        assert synonyms["TEXAS INSTRUMENT"] == "TEXAS INSTRUMENTS INCORPORATED"


# ── upsert_item_mpn ──────────────────────────────────────────────────────────

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


# ── search_item_mpns ─────────────────────────────────────────────────────────

class TestSearchItemMpns:
    async def test_wildcard_prefix_search_on_mpn(self, db_session: AsyncSession):
        item_number = f"LFSRCH{uuid.uuid4().hex[:6].upper()}"
        await upsert_item_mpn(db_session, item_number=item_number, mpn="STM32F103C8T6")
        await upsert_item_mpn(db_session, item_number=item_number, mpn="STM32F407VET6")
        await upsert_item_mpn(db_session, item_number=item_number, mpn="LM358")

        result = await search_item_mpns(db_session, query="STM32*", field="mpn")
        mpns = {hit.mpn for hit in result.hits if hit.item_number == item_number}
        assert mpns == {"STM32F103C8T6", "STM32F407VET6"}

    async def test_search_by_item_field(self, db_session: AsyncSession):
        item_number = f"LFITEM{uuid.uuid4().hex[:6].upper()}"
        await upsert_item_mpn(db_session, item_number=item_number, mpn="PARTX")

        result = await search_item_mpns(db_session, query=f"{item_number}*", field="item")
        assert any(hit.item_number == item_number for hit in result.hits)

    async def test_search_by_manufacturer_field(self, db_session: AsyncSession):
        item_number = f"LFMFR{uuid.uuid4().hex[:6].upper()}"
        await upsert_item_mpn(
            db_session, item_number=item_number, mpn="PARTY",
            manufacturer_canonical="UniqueCanonicalMfrXYZ",
        )
        result = await search_item_mpns(db_session, query="UniqueCanonicalMfrXYZ*", field="mfr")
        assert any(hit.item_number == item_number for hit in result.hits)

    async def test_pagination_limit_and_offset(self, db_session: AsyncSession):
        item_number = f"LFPAGE{uuid.uuid4().hex[:6].upper()}"
        for i in range(5):
            await upsert_item_mpn(db_session, item_number=item_number, mpn=f"PAGEPART{i}")

        page1 = await search_item_mpns(db_session, query=f"{item_number}*", field="item", limit=2, offset=0)
        page2 = await search_item_mpns(db_session, query=f"{item_number}*", field="item", limit=2, offset=2)

        assert len(page1.hits) == 2
        assert len(page2.hits) == 2
        assert page1.total == 5
        assert {h.mpn for h in page1.hits}.isdisjoint({h.mpn for h in page2.hits})

    async def test_underscore_in_query_is_literal_not_wildcard(self, db_session: AsyncSession):
        item_number = f"LFUND{uuid.uuid4().hex[:6].upper()}"
        await upsert_item_mpn(db_session, item_number=item_number, mpn="A_B")
        await upsert_item_mpn(db_session, item_number=item_number, mpn="AXB")

        result = await search_item_mpns(db_session, query="A_B", field="mpn")
        mpns = {hit.mpn for hit in result.hits if hit.item_number == item_number}
        assert mpns == {"A_B"}
