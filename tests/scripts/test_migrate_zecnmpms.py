"""
OSKAR — ZECNMPMS migration tests: pure transform layer (Slice C).

Pure transform (src/services/bom/zecnmpms_transform.py) — no DB, no I/O.
Exercised directly against tests/fixtures/bom/zecnmpms_sample.csv, which
deliberately covers: leading/trailing whitespace, mixed-case ITNO/MPZMANPN,
MPFDAT/MPTDAT = 0 and 99999999 edge cases, two manufacturer-synonym misses
("ST MICRO", "TEXAS INSTRUMENT"), and one duplicate natural key
(ITNO, SUNO, MPZMANPN).

Column names verified 2026-07-27 against the real Stargile source
(c:/Projects/SuperTool/Stargile_Source_Code/workspace/Startronics/DataModels/
ECN/Maintenance/{MPMDetail,MPMBrowse}.cml) — the plan's original field names
(MPN, MPPRIC, MPMOQ, MPCURR, MPSPQ) were inferred, not verified, and turned
out wrong: the real columns are MPZMANPN, MPMPRC, MPZMPMOQ, MPCUCD, MPZMPSPQ.
MPDIST/MPDISTNM never existed on ZECNMPMS at all — invented with no source.

CLI-script-level behaviour (dry-run, idempotent load, --from-api against the
real scripts/movex_stub.py) needs a live DB and lives in
tests/integration/test_migrate_zecnmpms.py instead — pytest 9 no longer
allows a non-top-level conftest.py to reuse tests/integration/conftest.py's
fixtures via `pytest_plugins`, so DB-dependent tests simply live under
tests/integration/ per the codebase's existing convention.

Verified live 2026-08-03 against the real movex-rest-api M-1 endpoint
(localhost:5000, GET /api/mpm/export) — same lowercase-key convention as
B-1/B-2/B-3 (see tests/adapters/test_movex_bom.py), plus one mixed-case
quirk on this endpoint specifically: the manufacturer field comes back as
"mptX30", not "mptx30" or "MPTX30". transform_row normalises with
str.upper() on every raw key up front, which handles any input casing
uniformly (mixed case included) without needing to special-case it.
"""
from __future__ import annotations

import csv
import datetime
from pathlib import Path

from src.services.bom.zecnmpms_transform import (
    TransformedRow,
    natural_key,
    transform_batch,
    transform_row,
)

_FIXTURE_CSV = (
    Path(__file__).resolve().parent.parent / "fixtures" / "bom" / "zecnmpms_sample.csv"
)


def _load_fixture_rows() -> list[dict]:
    with _FIXTURE_CSV.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


# ── transform_row (pure, single row) ────────────────────────────────────────

class TestTransformRowFieldMapping:
    def test_itno_and_mpn_are_trimmed_and_uppercased(self):
        raw = {"ITNO": " lf200010 ", "SUNO": "SUP001", "MPZMANPN": " STM32F103C8T6 "}
        row = transform_row(raw, {})
        assert row.item_number == "LF200010"
        assert row.mpn == "STM32F103C8T6"

    def test_lowercase_keys_from_real_m1_response_are_handled(self):
        """M-1's real response uses lowercase keys (itno, suno, mpzmanpn, ...)
        — verified live 2026-08-03 — not the uppercase keys the CSV/fixture
        path uses. transform_row must handle both without the caller having
        to normalise first."""
        raw = {"itno": " lf200010 ", "suno": "sup001", "mpzmanpn": "stm32f103c8t6"}
        row = transform_row(raw, {})
        assert row.item_number == "LF200010"
        assert row.mpn == "STM32F103C8T6"

    def test_mixed_case_key_from_real_m1_response_is_handled(self):
        """The real M-1 response's manufacturer column comes back as the
        mixed-case key "mptX30", not "MPTX30" or "mptx30" — a genuine wire
        quirk, verified live 2026-08-03."""
        raw = {"ITNO": "LF1", "SUNO": "S", "MPZMANPN": "X", "mptX30": "STMicroelectronics"}
        row = transform_row(raw, {})
        assert row.manufacturer_name == "STMicroelectronics"

    def test_supplier_number_is_trimmed_not_uppercased(self):
        raw = {"ITNO": "LF1", "SUNO": " sup001 ", "MPZMANPN": "X"}
        row = transform_row(raw, {})
        assert row.supplier_number == "sup001"

    def test_mpzdeffl_1_maps_to_true(self):
        raw = {"ITNO": "LF1", "SUNO": "S", "MPZMANPN": "X", "MPZDEFFL": "1"}
        assert transform_row(raw, {}).is_default is True

    def test_mpzdeffl_0_maps_to_false(self):
        raw = {"ITNO": "LF1", "SUNO": "S", "MPZMANPN": "X", "MPZDEFFL": "0"}
        assert transform_row(raw, {}).is_default is False

    def test_mpfdat_zero_becomes_none(self):
        raw = {"ITNO": "LF1", "SUNO": "S", "MPZMANPN": "X", "MPFDAT": "0"}
        assert transform_row(raw, {}).from_date is None

    def test_mptdat_99999999_becomes_none(self):
        raw = {"ITNO": "LF1", "SUNO": "S", "MPZMANPN": "X", "MPTDAT": "99999999"}
        assert transform_row(raw, {}).to_date is None

    def test_valid_yyyymmdd_becomes_date(self):
        raw = {"ITNO": "LF1", "SUNO": "S", "MPZMANPN": "X", "MPFDAT": "20240101"}
        assert transform_row(raw, {}).from_date == datetime.date(2024, 1, 1)

    def test_price_currency_moq_spq_parsed(self):
        raw = {
            "ITNO": "LF1", "SUNO": "S", "MPZMANPN": "X",
            "MPMPRC": "1.25", "MPCUCD": "USD", "MPZMPMOQ": "10", "MPZMPSPQ": "100",
        }
        row = transform_row(raw, {})
        assert row.price == 1.25
        assert row.currency == "USD"
        assert row.moq == 10
        assert row.spq == 100

    def test_distributor_fields_are_always_none(self):
        """ZECNMPMS has no distributor number/name columns at all (verified
        against real source 2026-07-27, see module docstring) — item_mpns'
        distributor_number/distributor_name columns exist for a future
        Iteration 3 supplier-chain source, not this one. A raw row can't
        carry these fields since Stargile never had them; this just locks
        in that transform_row doesn't invent them either."""
        raw = {"ITNO": "LF1", "SUNO": "S", "MPZMANPN": "X"}
        row = transform_row(raw, {})
        assert row.distributor_number is None
        assert row.distributor_name is None

    def test_zero_price_is_not_none(self):
        raw = {"ITNO": "LF1", "SUNO": "S", "MPZMANPN": "X", "MPMPRC": "0.00"}
        assert transform_row(raw, {}).price == 0.0

    def test_leftover_column_goes_to_legacy_extra(self):
        raw = {"ITNO": "LF1", "SUNO": "S", "MPZMANPN": "X", "MPLMDT": "20250601"}
        row = transform_row(raw, {})
        assert row.legacy_extra == {"MPLMDT": "20250601"}

    def test_effective_date_and_ecn_id_go_to_legacy_extra(self):
        """MPZEEFDT (effective date) and MPZECNID (originating ECN) are real
        ZECNMPMS columns with no dedicated item_mpns field — they fall
        through to legacy_extra like any other unmapped column."""
        raw = {
            "ITNO": "LF1", "SUNO": "S", "MPZMANPN": "X",
            "MPZEEFDT": "20240101", "MPZECNID": "ECN-0912",
        }
        row = transform_row(raw, {})
        assert row.legacy_extra == {"MPZEEFDT": "20240101", "MPZECNID": "ECN-0912"}

    def test_source_system_is_zecnmpms(self):
        raw = {"ITNO": "LF1", "SUNO": "S", "MPZMANPN": "X"}
        assert transform_row(raw, {}).source_system == "zecnmpms"


class TestTransformRowManufacturerNormalization:
    def test_synonym_hit_sets_canonical_and_clears_miss_flag(self):
        raw = {"ITNO": "LF1", "SUNO": "S", "MPZMANPN": "X", "MPTX30": "ST MICRO"}
        row = transform_row(raw, {"ST MICRO": "STMicroelectronics"})
        assert row.manufacturer_canonical == "STMicroelectronics"
        assert row.manufacturer_miss is False

    def test_synonym_miss_passes_through_raw_and_sets_miss_flag(self):
        raw = {"ITNO": "LF1", "SUNO": "S", "MPZMANPN": "X", "MPTX30": "SOME UNKNOWN MFR"}
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
            {"ITNO": "LF1", "SUNO": "S1", "MPZMANPN": "A", "MPZDEFFL": "1"},
            {"ITNO": "LF1", "SUNO": "S1", "MPZMANPN": "B", "MPZDEFFL": "1"},
        ]
        result = transform_batch(rows, {})
        assert len(result.default_flag_violations) == 1
        v = result.default_flag_violations[0]
        assert v.item_number == "LF1"
        assert v.supplier_number == "S1"
        assert v.mpn_count == 2

    def test_defaults_across_different_suppliers_not_flagged(self):
        rows = [
            {"ITNO": "LF1", "SUNO": "S1", "MPZMANPN": "A", "MPZDEFFL": "1"},
            {"ITNO": "LF1", "SUNO": "S2", "MPZMANPN": "B", "MPZDEFFL": "1"},
        ]
        result = transform_batch(rows, {})
        assert result.default_flag_violations == []


# ── --from-api auth header (pure, no network) ───────────────────────────────
# Discovered 2026-08-03: --from-api against the real movex-rest-api (unlike
# scripts/movex_stub.py, which requires no auth) 401s, because
# load_rows_from_api never sent X-API-Key. _build_headers() is the pure
# piece of that fix — safe to unit test without a network layer.

class TestBuildHeaders:
    def test_no_env_var_means_no_auth_header(self, monkeypatch):
        monkeypatch.delenv("MOVEX_API_KEY", raising=False)
        from scripts.migrate_zecnmpms import _build_headers
        assert _build_headers() == {}

    def test_env_var_set_adds_x_api_key_header(self, monkeypatch):
        monkeypatch.setenv("MOVEX_API_KEY", "test-key-123")
        from scripts.migrate_zecnmpms import _build_headers
        assert _build_headers() == {"X-API-Key": "test-key-123"}
