"""
OSKAR — scripts/add_manufacturer_synonym.py tests (Slice C, ADR-012 Decision 8 / R5).

Insert-only CLI: raw string + canonical name -> manufacturer_synonyms, then
re-runs affected item_mpns rows through normalize_manufacturer() again — lets
synonym misses surfaced by the ZECNMPMS migration's review file get corrected
same-day without a deploy or the Iteration 3 admin UI.

DB-touching (insert + item_mpns update) — lives under tests/integration/ per
the codebase's convention (see tests/services/bom/test_mpn_master.py's
docstring for why pytest 9 rules out the conftest.py pytest_plugins trick).
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from scripts.add_manufacturer_synonym import SynonymAlreadyExists, add_manufacturer_synonym_async
from src.services.bom.mpn_master import get_item_mpn, upsert_item_mpn

pytestmark = pytest.mark.asyncio


class TestAddManufacturerSynonym:
    async def test_inserts_new_synonym(self, db_session: AsyncSession):
        raw = f"UNIT TEST MFR {uuid.uuid4().hex[:8].upper()}"
        result = await add_manufacturer_synonym_async(
            db_session, raw=raw, canonical="Unit Test Manufacturer Inc"
        )
        assert result.raw_string == raw.upper()
        assert result.canonical_name == "Unit Test Manufacturer Inc"

    async def test_raw_is_trimmed_and_uppercased_for_storage(self, db_session: AsyncSession):
        raw = f"  unit test mfr {uuid.uuid4().hex[:8]}  "
        result = await add_manufacturer_synonym_async(
            db_session, raw=raw, canonical="Whatever Inc"
        )
        assert result.raw_string == raw.strip().upper()

    async def test_duplicate_raw_string_raises(self, db_session: AsyncSession):
        raw = f"DUPE MFR {uuid.uuid4().hex[:8].upper()}"
        await add_manufacturer_synonym_async(db_session, raw=raw, canonical="First Canonical")
        with pytest.raises(SynonymAlreadyExists):
            await add_manufacturer_synonym_async(db_session, raw=raw, canonical="Second Canonical")

    async def test_no_affected_rows_when_no_item_mpns_use_this_raw_string(
        self, db_session: AsyncSession
    ):
        raw = f"UNUSED MFR {uuid.uuid4().hex[:8].upper()}"
        result = await add_manufacturer_synonym_async(db_session, raw=raw, canonical="Nobody Uses This")
        assert result.item_mpns_updated == 0

    async def test_existing_item_mpns_rows_get_renormalized(self, db_session: AsyncSession):
        item_number = f"LFSYN{uuid.uuid4().hex[:6].upper()}"
        raw = f"MISSED MFR {uuid.uuid4().hex[:8].upper()}"

        # Simulate a migration-time miss: manufacturer_canonical == raw pass-through.
        await upsert_item_mpn(
            db_session, item_number=item_number, mpn="SYNPART1",
            manufacturer_name=raw, manufacturer_canonical=raw,
        )

        result = await add_manufacturer_synonym_async(
            db_session, raw=raw, canonical="Corrected Canonical Name"
        )
        assert result.item_mpns_updated == 1

        fetched = await get_item_mpn(db_session, item_number, "", "SYNPART1")
        assert fetched.manufacturer_canonical == "Corrected Canonical Name"

    async def test_unrelated_item_mpns_rows_untouched(self, db_session: AsyncSession):
        item_number = f"LFSYN{uuid.uuid4().hex[:6].upper()}"
        raw = f"TARGET MFR {uuid.uuid4().hex[:8].upper()}"
        other_raw = f"OTHER MFR {uuid.uuid4().hex[:8].upper()}"

        await upsert_item_mpn(
            db_session, item_number=item_number, mpn="SYNPART2",
            manufacturer_name=other_raw, manufacturer_canonical=other_raw,
        )

        await add_manufacturer_synonym_async(db_session, raw=raw, canonical="Some Canonical")

        fetched = await get_item_mpn(db_session, item_number, "", "SYNPART2")
        assert fetched.manufacturer_canonical == other_raw  # unchanged

    async def test_matching_is_case_and_whitespace_insensitive(self, db_session: AsyncSession):
        item_number = f"LFSYN{uuid.uuid4().hex[:6].upper()}"
        suffix = uuid.uuid4().hex[:8].upper()
        stored_raw = f"  st micro {suffix}  "

        await upsert_item_mpn(
            db_session, item_number=item_number, mpn="SYNPART3",
            manufacturer_name=stored_raw, manufacturer_canonical=stored_raw.strip(),
        )

        result = await add_manufacturer_synonym_async(
            db_session, raw=f"ST MICRO {suffix}", canonical="STMicroelectronics"
        )
        assert result.item_mpns_updated == 1

        fetched = await get_item_mpn(db_session, item_number, "", "SYNPART3")
        assert fetched.manufacturer_canonical == "STMicroelectronics"
