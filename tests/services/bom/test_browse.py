"""
OSKAR — src.services.bom.browse unit tests (Slice A, ADR-012)

Pure service-layer tests: no DB, no HTTP — ERPAdapter is either FakeERPAdapter
(tests/helpers/fake_erp.py, real fixture data) or a plain stub object for cases
that need control over exact ERP-call arguments or malformed/scrambled input.

Date-dependent assertions always pass an explicit `as_of=date(...)` literal —
never rely on date.today() inside a test. Fixture dates (FDAT/TDAT) are fixed
absolute integers baked into the JSON files, so pairing them with a fixed
as_of makes every effectivity-filter test fully deterministic regardless of
when the suite actually runs. Only the production default path (as_of
omitted) calls date.today() — see TestEffectivityFilterDefaultsToToday, which
is written to tolerate any real "today" between now and year 9999.

Ref-des / CPN-alias enrichment (2026-07-23 judgment call, see browse.py module
docstring for full rationale): bom_circuit_refs (D4) does not exist until Slice
E's migration 0028, and the C-1 circuit-refs contract endpoint is explicitly
scoped "migration/backfill only" — not meant for live per-request browse
traffic. Slice A leaves BOMLine.ref_des / customer_alias as a documented None
no-op; test_ref_des_and_customer_alias_are_none_in_slice_a below is the
regression guard for that decision so a future slice touching this file
notices if it silently changes.
"""
from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock

import pytest

from src.adapters.erp.base import BOMNotFound
from src.services.bom.browse import get_single_level_bom
from tests.helpers.fake_erp import FakeERPAdapter


class _StubERP:
    """Minimal ERPAdapter double for tests that need to control the exact
    payload/records shape or spy on the arguments browse.py passes through —
    FakeERPAdapter only varies by item_number, which isn't enough for those
    cases (e.g. proving sort actually happens, not just fixture order)."""

    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.get_bom = AsyncMock(return_value=payload)


def _payload(records: list[dict], head: dict | None = None) -> dict:
    return {
        "data": {
            "head": head or {"PRNO": "LF999999", "STRT": "001", "FACI": "D", "ITDS": "Test Assembly"},
            "records": records,
        }
    }


class TestHeadMapping:
    async def test_merges_head_fields_from_erp_response(self):
        erp = FakeERPAdapter()

        head = await get_single_level_bom(erp, "LF100001", "D")

        assert head.item_number == "LF100001"
        assert head.structure_type == "001"
        assert head.facility == "D"
        assert head.description == "Widget Assembly A"

    async def test_all_lines_present_for_fully_effective_fixture(self):
        erp = FakeERPAdapter()

        head = await get_single_level_bom(erp, "LF100001", "D")

        assert len(head.lines) == 12


class TestERPCallArguments:
    async def test_passes_facility_structure_type_bom_type_effective_on(self):
        erp = _StubERP(_payload([]))

        await get_single_level_bom(
            erp, "LF999999", "D",
            structure_type="002", bom_type="M", effective_on="20260101",
        )

        erp.get_bom.assert_awaited_once_with(
            "LF999999", "D", structure_type="002", bom_type="M", effective_on="20260101",
        )


class TestOrdering:
    async def test_preserves_mseq_ordering_even_when_source_is_scrambled(self):
        records = [
            {"MSEQ": 30, "MTNO": "LF200012", "ITDS": "IC", "OPNO": 10, "CNQT": 1.0,
             "PEUN": "EA", "FDAT": 20240101, "TDAT": 99999999, "ITTY": "3", "STAT": "20"},
            {"MSEQ": 10, "MTNO": "LF200010", "ITDS": "Resistor", "OPNO": 10, "CNQT": 4.0,
             "PEUN": "EA", "FDAT": 20240101, "TDAT": 99999999, "ITTY": "3", "STAT": "20"},
            {"MSEQ": 20, "MTNO": "LF200011", "ITDS": "Capacitor", "OPNO": 10, "CNQT": 8.0,
             "PEUN": "EA", "FDAT": 20240101, "TDAT": 99999999, "ITTY": "3", "STAT": "20"},
        ]
        erp = _StubERP(_payload(records))

        head = await get_single_level_bom(erp, "LF999999", "D")

        assert [ln.sequence_number for ln in head.lines] == [10, 20, 30]
        assert [ln.component_number for ln in head.lines] == ["LF200010", "LF200011", "LF200012"]


class TestPaddingEquivalence:
    async def test_zero_padded_mseq_normalises_to_same_int_as_plain_int(self):
        """Stargile padding-equivalence rule (D5): '0010' and 10 refer to the
        same sequence position. browse.py must normalise both representations
        to the same int so ordering and downstream key matching (Slice D) are
        stable regardless of which format an ERP source happens to send."""
        records = [
            {"MSEQ": "0020", "MTNO": "LF200011", "ITDS": "Capacitor", "OPNO": "0010", "CNQT": 8.0,
             "PEUN": "EA", "FDAT": 20240101, "TDAT": 99999999, "ITTY": "3", "STAT": "20"},
            {"MSEQ": 10, "MTNO": "LF200010", "ITDS": "Resistor", "OPNO": 10, "CNQT": 4.0,
             "PEUN": "EA", "FDAT": 20240101, "TDAT": 99999999, "ITTY": "3", "STAT": "20"},
        ]
        erp = _StubERP(_payload(records))

        head = await get_single_level_bom(erp, "LF999999", "D")

        assert [ln.sequence_number for ln in head.lines] == [10, 20]
        assert head.lines[0].operation_number == 10
        assert isinstance(head.lines[1].sequence_number, int)
        assert isinstance(head.lines[1].operation_number, int)


class TestEffectivityFilter:
    """All assertions here pin as_of to a fixed literal date — see module
    docstring. Deterministic forever, independent of real execution date."""

    async def test_include_expired_false_drops_expired_lines(self):
        erp = FakeERPAdapter()

        head = await get_single_level_bom(
            erp, "LF100002", "D",
            include_expired=False, as_of=date(2026, 7, 23),
        )

        # expired_lines.json has 4 records: an old LF200010 (TDAT=20250614,
        # expired), a new LF200010 (TDAT=99999999, open), a discontinued
        # LF200099 (TDAT=20211231, expired), and an open LF200011.
        component_numbers = [ln.component_number for ln in head.lines]
        assert "LF200099" not in component_numbers
        assert len(head.lines) == 2
        assert all(ln.to_date >= 20260723 for ln in head.lines)

    async def test_include_expired_true_returns_all_lines(self):
        erp = FakeERPAdapter()

        head = await get_single_level_bom(
            erp, "LF100002", "D",
            include_expired=True, as_of=date(2026, 7, 23),
        )

        assert len(head.lines) == 4

    async def test_as_of_boundary_is_inclusive(self):
        """to_date >= as_of keeps a line whose effective window ends exactly
        on the comparison date (Stargile TDAT semantics: TDAT is the last
        effective day, not the first ineffective one)."""
        records = [
            {"MSEQ": 10, "MTNO": "LF200010", "ITDS": "Resistor", "OPNO": 10, "CNQT": 4.0,
             "PEUN": "EA", "FDAT": 20240101, "TDAT": 20260723, "ITTY": "3", "STAT": "20"},
        ]
        erp = _StubERP(_payload(records))

        head = await get_single_level_bom(erp, "LF999999", "D", as_of=date(2026, 7, 23))

        assert len(head.lines) == 1


class TestEffectivityFilterDefaultsToToday:
    async def test_no_as_of_still_drops_long_expired_lines(self):
        """No as_of passed -> production default (date.today()). Written to
        tolerate any real execution date: LF200099's TDAT=20211231 is in the
        past for any today between 2022 and 9999, so this holds indefinitely
        without pinning a literal date."""
        erp = FakeERPAdapter()

        head = await get_single_level_bom(erp, "LF100002", "D")

        component_numbers = [ln.component_number for ln in head.lines]
        assert "LF200099" not in component_numbers


class TestRefDesAndCustomerAliasNoOp:
    async def test_ref_des_and_customer_alias_are_none_in_slice_a(self):
        """Regression guard for the documented Slice A judgment call — see
        module docstring above and src/services/bom/browse.py."""
        erp = FakeERPAdapter()

        head = await get_single_level_bom(erp, "LF100001", "D")

        assert all(ln.ref_des is None for ln in head.lines)
        assert all(ln.customer_alias is None for ln in head.lines)


class TestBomNotFoundPropagates:
    async def test_unknown_item_propagates_bom_not_found(self):
        erp = FakeERPAdapter()

        with pytest.raises(BOMNotFound):
            await get_single_level_bom(erp, "NOPE99999", "D")
