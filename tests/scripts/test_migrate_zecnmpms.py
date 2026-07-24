"""
OSKAR — ZECNMPMS migration tests (Slice C).

Two layers, per ai/tasks/oskar-iteration-2.md "ZECNMPMS migration plan" step 2
and the Slice C bullet list:

  1. Pure transform (src/services/bom/zecnmpms_transform.py) — no DB, no I/O.
     Exercised directly against tests/fixtures/bom/zecnmpms_sample.csv, which
     deliberately covers: leading/trailing whitespace, mixed-case ITNO/MPN,
     MPFDAT/MPTDAT = 0 and 99999999 edge cases, two manufacturer-synonym
     misses ("ST MICRO", "TEXAS INSTRUMENT"), and one duplicate natural key
     (ITNO, SUNO, MPN).

  2. CLI script (scripts/migrate_zecnmpms.py) — dry-run (writes nothing),
     idempotency (re-run produces no duplicate/changed rows), --report output.
     These run against the live Postgres test DB (tests/services/bom/conftest.py
     plugin reused here too).
"""
from __future__ import annotations

import csv
import datetime
from pathlib import Path

import pytest

from src.services.bom.zecnmpms_transform import (
    TransformedRow,
    natural_key,
    transform_batch,
    transform_row,
)

pytest_plugins = ["tests.integration.conftest"]

_FIXTURE_CSV = (
    Path(__file__).resolve().parent.parent / "fixtures" / "bom" / "zecnmpms_sample.csv"
)


def _load_fixture_rows() -> list[dict]:
    with _FIXTURE_CSV.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


# ── transform_row (pure, single row) ────────────────────────────────────────

class TestTransformRowFieldMapping:
    def test_itno_and_mpn_are_trimmed_and_uppercased(self):
        raw = {"ITNO": " lf200010 ", "SUNO": "SUP001", "MPN": " STM32F103C8T6 "}
        row = transform_row(raw, {})
        assert row.item_number == "LF200010"
        assert row.mpn == "STM32F103C8T6"

    def test_supplier_number_is_trimmed_not_uppercased(self):
        raw = {"ITNO": "LF1", "SUNO": " sup001 ", "MPN": "X"}
        row = transform_row(raw, {})
        assert row.supplier_number == "sup001"

    def test_mpzdeffl_1_maps_to_true(self):
        raw = {"ITNO": "LF1", "SUNO": "S", "MPN": "X", "MPZDEFFL": "1"}
        assert transform_row(raw, {}).is_default is True

    def test_mpzdeffl_0_maps_to_false(self):
        raw = {"ITNO": "LF1", "SUNO": "S", "MPN": "X", "MPZDEFFL": "0"}
        assert transform_row(raw, {}).is_default is False

    def test_mpfdat_zero_becomes_none(self):
        raw = {"ITNO": "LF1", "SUNO": "S", "MPN": "X", "MPFDAT": "0"}
        assert transform_row(raw, {}).from_date is None

    def test_mptdat_99999999_becomes_none(self):
        raw = {"ITNO": "LF1", "SUNO": "S", "MPN": "X", "MPTDAT": "99999999"}
        assert transform_row(raw, {}).to_date is None

    def test_valid_yyyymmdd_becomes_date(self):
        raw = {"ITNO": "LF1", "SUNO": "S", "MPN": "X", "MPFDAT": "20240101"}
        assert transform_row(raw, {}).from_date == datetime.date(2024, 1, 1)

    def test_price_currency_moq_spq_parsed(self):
        raw = {
            "ITNO": "LF1", "SUNO": "S", "MPN": "X",
            "MPPRIC": "1.25", "MPCURR": "USD", "MPMOQ": "10", "MPSPQ": "100",
        }
        row = transform_row(raw, {})
        assert row.price == 1.25
        assert row.currency == "USD"
        assert row.moq == 10
        assert row.spq == 100

    def test_empty_distributor_fields_become_none(self):
        raw = {"ITNO": "LF1", "SUNO": "S", "MPN": "X", "MPDIST": "", "MPDISTNM": ""}
        row = transform_row(raw, {})
        assert row.distributor_number is None
        assert row.distributor_name is None

    def test_zero_price_is_not_none(self):
        raw = {"ITNO": "LF1", "SUNO": "S", "MPN": "X", "MPPRIC": "0.00"}
        assert transform_row(raw, {}).price == 0.0

    def test_leftover_column_goes_to_legacy_extra(self):
        raw = {"ITNO": "LF1", "SUNO": "S", "MPN": "X", "MPLMDT": "20250601"}
        row = transform_row(raw, {})
        assert row.legacy_extra == {"MPLMDT": "20250601"}

    def test_source_system_is_zecnmpms(self):
        raw = {"ITNO": "LF1", "SUNO": "S", "MPN": "X"}
        assert transform_row(raw, {}).source_system == "zecnmpms"


class TestTransformRowManufacturerNormalization:
    def test_synonym_hit_sets_canonical_and_clears_miss_flag(self):
        raw = {"ITNO": "LF1", "SUNO": "S", "MPN": "X", "MPTX30": "ST MICRO"}
        row = transform_row(raw, {"ST MICRO": "STMicroelectronics"})
        assert row.manufacturer_canonical == "STMicroelectronics"
        assert row.manufacturer_miss is False

    def test_synonym_miss_passes_through_raw_and_sets_miss_flag(self):
        raw = {"ITNO": "LF1", "SUNO": "S", "MPN": "X", "MPTX30": "SOME UNKNOWN MFR"}
        row = transform_row(raw, {})
        assert row.manufacturer_canonical == "SOME UNKNOWN MFR"
        assert row.manufacturer_miss is True


class TestNaturalKey:
    def test_natural_key_is_item_supplier_mpn(self):
        row = TransformedRow(
            item_number="LF1", supplier_number="S1", mpn="X",
            manufacturer_name=None, manufacturer_canonical=None, manufacturer_miss=False,
            is_default=False, from_date=None, to_date=None, price=None, currency=None,
            moq=None, spq=None, distributor_number=None, distributor_name=None,
            legacy_extra={}, source_system="zecnmpms",
        )
        assert natural_key(row) == ("LF1", "S1", "X")


# ── transform_batch (pure, whole file) ──────────────────────────────────────

class TestTransformBatchAgainstFixture:
    def test_seven_raw_rows_collapse_to_six_natural_keys(self):
        result = transform_batch(_load_fixture_rows(), {})
        assert len(result.rows) == 6

    def test_duplicate_natural_key_reported(self):
        result = transform_batch(_load_fixture_rows(), {})
        assert len(result.duplicate_collapses) == 1
        dup = result.duplicate_collapses[0]
        assert dup.natural_key == ("LF200010", "SUP001", "STM32F103C8T6")
        assert dup.occurrences == 2

    def test_manufacturer_misses_reported_when_synonyms_empty(self):
        result = transform_batch(_load_fixture_rows(), {})
        assert "MURATA" in result.manufacturer_misses
        assert "GENERIC MFR" in result.manufacturer_misses

    def test_st_micro_and_texas_instrument_resolved_when_synonyms_supplied(self):
        synonyms = {
            "ST MICRO": "STMicroelectronics",
            "STMICROELECTRONICS": "STMicroelectronics",
            "TEXAS INSTRUMENT": "Texas Instruments",
        }
        result = transform_batch(_load_fixture_rows(), synonyms)
        assert "ST MICRO" not in result.manufacturer_misses
        assert "TEXAS INSTRUMENT" not in result.manufacturer_misses

    def test_no_default_flag_violations_in_fixture(self):
        result = transform_batch(_load_fixture_rows(), {})
        assert result.default_flag_violations == []


class TestTransformBatchDefaultFlagViolation:
    def test_two_defaults_same_item_supplier_flagged(self):
        rows = [
            {"ITNO": "LF1", "SUNO": "S1", "MPN": "A", "MPZDEFFL": "1"},
            {"ITNO": "LF1", "SUNO": "S1", "MPN": "B", "MPZDEFFL": "1"},
        ]
        result = transform_batch(rows, {})
        assert len(result.default_flag_violations) == 1
        v = result.default_flag_violations[0]
        assert v.item_number == "LF1"
        assert v.supplier_number == "S1"
        assert v.mpn_count == 2

    def test_defaults_across_different_suppliers_not_flagged(self):
        rows = [
            {"ITNO": "LF1", "SUNO": "S1", "MPN": "A", "MPZDEFFL": "1"},
            {"ITNO": "LF1", "SUNO": "S2", "MPN": "B", "MPZDEFFL": "1"},
        ]
        result = transform_batch(rows, {})
        assert result.default_flag_violations == []
