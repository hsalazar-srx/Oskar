"""
Integration tests — migration 0025 (item_mpns + manufacturer_synonyms), Slice C.

Runs against the real Postgres test DB (tests/integration/conftest.py: db_engine
applies `alembic upgrade head` once per session; db_session gives each test a
rolled-back connection). See ai/tasks/oskar-iteration-2.md "New Alembic
migrations" section for the schema spec and ADR-012 Decision 8 (R5 fix-forward)
for why manufacturer_synonyms exists as its own table.
"""
from __future__ import annotations

import datetime
import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio


async def _insert_item_mpn(session: AsyncSession, **overrides) -> str:
    row = {
        "id": str(uuid.uuid4()),
        "item_number": "LF200010",
        "supplier_number": "SUP001",
        "mpn": "STM32F103C8T6",
        "manufacturer_name": "STMICROELECTRONICS",
        "manufacturer_canonical": "STMicroelectronics",
        "is_default": True,
        "end_effective_date": None,
        "from_date": datetime.date(2024, 1, 1),
        "to_date": None,
        "source_ecn": None,
        "price": 1.25,
        "currency": "USD",
        "moq": 1,
        "spq": 1,
        "distributor_number": "DK",
        "distributor_name": "Digi-Key",
        "legacy_extra": None,
        "source_system": "oskar",
    }
    row.update(overrides)
    await session.execute(
        sa.text(
            "INSERT INTO item_mpns "
            "(id, item_number, supplier_number, mpn, manufacturer_name, manufacturer_canonical, "
            "is_default, end_effective_date, from_date, to_date, source_ecn, price, currency, "
            "moq, spq, distributor_number, distributor_name, legacy_extra, source_system) "
            "VALUES (:id, :item_number, :supplier_number, :mpn, :manufacturer_name, "
            ":manufacturer_canonical, :is_default, :end_effective_date, :from_date, :to_date, "
            ":source_ecn, :price, :currency, :moq, :spq, :distributor_number, :distributor_name, "
            "CAST(:legacy_extra AS JSONB), :source_system)"
        ),
        row,
    )
    return row["id"]


class TestItemMpnsTableShape:
    async def test_table_exists_with_expected_columns(self, db_session: AsyncSession):
        result = await db_session.execute(
            sa.text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'item_mpns'"
            )
        )
        columns = {r[0] for r in result}
        expected = {
            "id", "item_number", "supplier_number", "mpn", "manufacturer_name",
            "manufacturer_canonical", "is_default", "end_effective_date",
            "from_date", "to_date", "source_ecn", "price", "currency", "moq",
            "spq", "distributor_number", "distributor_name", "legacy_extra",
            "source_system", "migrated_at", "created_at", "updated_at",
        }
        assert expected <= columns

    async def test_supplier_number_defaults_to_empty_string(self, db_session: AsyncSession):
        mpn_id = str(uuid.uuid4())
        await db_session.execute(
            sa.text(
                "INSERT INTO item_mpns (id, item_number, mpn) "
                "VALUES (:id, 'LF200099', 'GENERIC-01')"
            ),
            {"id": mpn_id},
        )
        result = await db_session.execute(
            sa.text("SELECT supplier_number, source_system FROM item_mpns WHERE id = :id"),
            {"id": mpn_id},
        )
        row = result.one()
        assert row.supplier_number == ""
        assert row.source_system == "oskar"

    async def test_insert_full_row(self, db_session: AsyncSession):
        mpn_id = await _insert_item_mpn(db_session)
        result = await db_session.execute(
            sa.text("SELECT mpn, manufacturer_canonical FROM item_mpns WHERE id = :id"),
            {"id": mpn_id},
        )
        row = result.one()
        assert row.mpn == "STM32F103C8T6"
        assert row.manufacturer_canonical == "STMicroelectronics"


class TestItemMpnsNaturalKeyUnique:
    async def test_duplicate_natural_key_rejected(self, db_session: AsyncSession):
        await _insert_item_mpn(
            db_session, id=str(uuid.uuid4()),
            item_number="LF200011", supplier_number="SUP001", mpn="GRM188R71H104KA93D",
        )
        with pytest.raises(Exception):
            await _insert_item_mpn(
                db_session, id=str(uuid.uuid4()),
                item_number="LF200011", supplier_number="SUP001", mpn="GRM188R71H104KA93D",
            )
        await db_session.rollback()

    async def test_same_mpn_different_supplier_allowed(self, db_session: AsyncSession):
        await _insert_item_mpn(
            db_session, id=str(uuid.uuid4()),
            item_number="LF200012", supplier_number="SUP001", mpn="TI-LM358",
        )
        await _insert_item_mpn(
            db_session, id=str(uuid.uuid4()),
            item_number="LF200012", supplier_number="SUP002", mpn="TI-LM358",
        )


class TestItemMpnsDefaultPartialUniqueIndex:
    async def test_two_current_defaults_for_same_item_supplier_rejected(
        self, db_session: AsyncSession
    ):
        await _insert_item_mpn(
            db_session, id=str(uuid.uuid4()),
            item_number="LF200013", supplier_number="SUP003", mpn="JST-PH-4",
            is_default=True, end_effective_date=None,
        )
        with pytest.raises(Exception):
            await _insert_item_mpn(
                db_session, id=str(uuid.uuid4()),
                item_number="LF200013", supplier_number="SUP003", mpn="JST-PH-4-ALT",
                is_default=True, end_effective_date=None,
            )
        await db_session.rollback()

    async def test_second_default_allowed_once_first_is_end_dated(
        self, db_session: AsyncSession
    ):
        await _insert_item_mpn(
            db_session, id=str(uuid.uuid4()),
            item_number="LF200014", supplier_number="SUP001", mpn="OLD-DEFAULT",
            is_default=True, end_effective_date=datetime.date(2020, 1, 1),
        )
        await _insert_item_mpn(
            db_session, id=str(uuid.uuid4()),
            item_number="LF200014", supplier_number="SUP001", mpn="NEW-DEFAULT",
            is_default=True, end_effective_date=None,
        )

    async def test_non_default_rows_not_constrained(self, db_session: AsyncSession):
        await _insert_item_mpn(
            db_session, id=str(uuid.uuid4()),
            item_number="LF200015", supplier_number="SUP001", mpn="ALT-1", is_default=False,
        )
        await _insert_item_mpn(
            db_session, id=str(uuid.uuid4()),
            item_number="LF200015", supplier_number="SUP001", mpn="ALT-2", is_default=False,
        )


class TestItemMpnsMpnWildcardIndex:
    async def test_text_pattern_ops_index_exists_on_mpn(self, db_session: AsyncSession):
        result = await db_session.execute(
            sa.text(
                "SELECT indexdef FROM pg_indexes "
                "WHERE tablename = 'item_mpns' AND indexdef ILIKE '%text_pattern_ops%'"
            )
        )
        rows = result.fetchall()
        assert len(rows) == 1
        assert "mpn" in rows[0][0]


class TestManufacturerSynonymsTable:
    async def test_table_exists_with_expected_columns(self, db_session: AsyncSession):
        result = await db_session.execute(
            sa.text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'manufacturer_synonyms'"
            )
        )
        columns = {r[0] for r in result}
        assert {"raw_string", "canonical_name", "source"} <= columns

    async def test_raw_string_is_primary_key(self, db_session: AsyncSession):
        await db_session.execute(
            sa.text(
                "INSERT INTO manufacturer_synonyms (raw_string, canonical_name, source) "
                "VALUES ('ZZZ-TEST-DUPE-CHECK', 'Canonical A', 'manual')"
            )
        )
        with pytest.raises(Exception):
            await db_session.execute(
                sa.text(
                    "INSERT INTO manufacturer_synonyms (raw_string, canonical_name, source) "
                    "VALUES ('ZZZ-TEST-DUPE-CHECK', 'Canonical B', 'manual')"
                )
            )
        await db_session.rollback()

    async def test_plm_seed_data_loaded(self, db_session: AsyncSession):
        result = await db_session.execute(
            sa.text("SELECT COUNT(*) FROM manufacturer_synonyms WHERE source = 'plm_migration'")
        )
        count = result.scalar_one()
        assert count > 1000

    async def test_plm_seed_covers_st_micro_and_texas_instrument(self, db_session: AsyncSession):
        result = await db_session.execute(
            sa.text(
                "SELECT raw_string, canonical_name FROM manufacturer_synonyms "
                "WHERE raw_string IN ('ST MICRO', 'TEXAS INSTRUMENT')"
            )
        )
        rows = {r.raw_string: r.canonical_name for r in result}
        assert rows["ST MICRO"] == "STMICROELECTRONICS"
        assert rows["TEXAS INSTRUMENT"] == "TEXAS INSTRUMENTS INCORPORATED"
