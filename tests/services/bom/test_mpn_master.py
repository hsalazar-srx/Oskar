"""
OSKAR — MPN master service tests: pure logic only (Slice C, ADR-012 D3).

normalize_manufacturer() / is_current_default() / wildcard_to_like() are pure
(no DB, no I/O) — TDD mechanics classifies manufacturer-normalisation as pure
unit logic, same as the compare engine and explode math.

DB-touching behaviour (upsert_item_mpn ON CONFLICT + partial-unique-index
demotion, load_synonyms, search_item_mpns) lives in
tests/integration/test_mpn_master.py instead — pytest 9 no longer allows a
non-top-level conftest.py to declare `pytest_plugins` to reuse the real-DB
fixtures here, and hoisting that declaration to the suite root would force
every test in the whole suite to open a live Postgres connection at session
start. Matching the codebase's existing convention, DB-dependent tests simply
live under tests/integration/, which already owns those fixtures.
"""
from __future__ import annotations

import datetime

from src.services.bom.mpn_master import (
    NormalizeResult,
    is_current_default,
    normalize_manufacturer,
    wildcard_to_like,
)


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


# ── wildcard_to_like (pure) ──────────────────────────────────────────────────

class TestWildcardToLike:
    def test_star_becomes_percent(self):
        assert wildcard_to_like("STM32*") == "STM32%"

    def test_literal_percent_is_escaped(self):
        assert wildcard_to_like("50%RES") == "50\\%RES"

    def test_literal_underscore_is_escaped(self):
        assert wildcard_to_like("A_B") == "A\\_B"

    def test_multiple_stars(self):
        assert wildcard_to_like("*LM358*") == "%LM358%"

    def test_no_wildcard_is_unchanged_aside_from_escaping(self):
        assert wildcard_to_like("STM32F103") == "STM32F103"
