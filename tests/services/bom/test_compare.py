"""
OSKAR — src.services.bom.compare unit tests (Slice D, ADR-012 D5)

Pure engine tests: no DB, no HTTP, no ERPAdapter — diff_boms() takes plain
line dicts in and returns a BOMDiff out. This is the "TDD showcase" slice
(ai/tasks/oskar-iteration-2.md, Slice D) — one seam (diff_boms), ~30 cases,
built vertically (one behaviour, one test, one minimal implementation change
at a time), not written as one big batch up front.

Case-sensitivity rule (documented here, and in compare.py's module
docstring): Oskar uses ONE consistent rule for every field, including the
match key — all string comparison and key derivation is case-INSENSITIVE
(upper-cased before comparing). PLM is case-insensitive for MPN/MFR/
Designator and case-sensitive elsewhere (a defect, ADR-012 Decision 9); Oskar
extends the more-permissive rule uniformly rather than the stricter one,
because MPN/MFR/Designator are exactly the fields most likely to have
inconsistent human-entered casing across two BOM sources (upload vs ERP vs
customer file) — case-sensitive-everywhere would produce false "changed"
noise on those fields, which is the actual PLM pain point this fixes.

Regression fixtures referenced below (Slice 0, tests/fixtures/bom/):
- single_level.json: LF200010 appears twice, at OPNO 10 and OPNO 20 — the
  array/duplicate-key-derivation regression fixture.
- customer_bom.csv / .xlsx: LF200010 row 6 has Quantity "N/A" — the
  quantity-diffing regression fixture (parseFloat/NaN defect).
- large_500.json: 500-line single-level BOM — performance assertion.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from src.services.bom.compare import CompareOptions, diff_boms

_FIXTURES_DIR = Path(__file__).parent.parent.parent / "fixtures" / "bom"


def _load_lines(filename: str) -> list[dict]:
    payload = json.loads((_FIXTURES_DIR / filename).read_text())
    return payload["data"]["records"]


# ---------------------------------------------------------------------------
# Identical BOMs
# ---------------------------------------------------------------------------


class TestIdenticalBOMs:
    def test_identical_lines_produce_no_changes(self):
        left = [
            {"component_number": "LF200010", "operation_number": 10, "quantity": 4.0},
        ]
        right = [
            {"component_number": "LF200010", "operation_number": 10, "quantity": 4.0},
        ]

        result = diff_boms(left, right, opts=CompareOptions())

        assert result.changed == []

    def test_identical_lines_produce_no_additions(self):
        left = [{"component_number": "LF200010", "operation_number": 10, "quantity": 4.0}]
        right = [{"component_number": "LF200010", "operation_number": 10, "quantity": 4.0}]

        result = diff_boms(left, right, opts=CompareOptions())

        assert result.added == []

    def test_identical_lines_produce_no_removals(self):
        left = [{"component_number": "LF200010", "operation_number": 10, "quantity": 4.0}]
        right = [{"component_number": "LF200010", "operation_number": 10, "quantity": 4.0}]

        result = diff_boms(left, right, opts=CompareOptions())

        assert result.removed == []

    def test_identical_lines_stats_report_zero_changes(self):
        left = [{"component_number": "LF200010", "operation_number": 10, "quantity": 4.0}]
        right = [{"component_number": "LF200010", "operation_number": 10, "quantity": 4.0}]

        result = diff_boms(left, right, opts=CompareOptions())

        assert result.stats.changed_count == 0
        assert result.stats.added_count == 0
        assert result.stats.removed_count == 0

    def test_reordered_but_otherwise_identical_lines_produce_no_changes(self):
        """Matching is key-based, not positional — a BOM whose lines were
        simply resequenced diffs as identical (parity with PLM's key-based
        compare, see module docstring)."""
        left = [
            {"component_number": "LF200010", "operation_number": 10, "quantity": 4.0},
            {"component_number": "LF200011", "operation_number": 10, "quantity": 8.0},
        ]
        right = [
            {"component_number": "LF200011", "operation_number": 10, "quantity": 8.0},
            {"component_number": "LF200010", "operation_number": 10, "quantity": 4.0},
        ]

        result = diff_boms(left, right, opts=CompareOptions())

        assert result.changed == []
        assert result.added == []
        assert result.removed == []


# ---------------------------------------------------------------------------
# Additions / removals
# ---------------------------------------------------------------------------


class TestAdditionsAndRemovals:
    def test_line_only_in_right_is_an_addition(self):
        left = [{"component_number": "LF200010", "operation_number": 10, "quantity": 4.0}]
        right = [
            {"component_number": "LF200010", "operation_number": 10, "quantity": 4.0},
            {"component_number": "LF200099", "operation_number": 10, "quantity": 1.0},
        ]

        result = diff_boms(left, right, opts=CompareOptions())

        assert len(result.added) == 1
        assert result.added[0]["component_number"] == "LF200099"

    def test_line_only_in_left_is_a_removal(self):
        left = [
            {"component_number": "LF200010", "operation_number": 10, "quantity": 4.0},
            {"component_number": "LF200099", "operation_number": 10, "quantity": 1.0},
        ]
        right = [{"component_number": "LF200010", "operation_number": 10, "quantity": 4.0}]

        result = diff_boms(left, right, opts=CompareOptions())

        assert len(result.removed) == 1
        assert result.removed[0]["component_number"] == "LF200099"

    def test_addition_and_removal_counts_are_independent(self):
        left = [{"component_number": "LF200010", "operation_number": 10, "quantity": 4.0}]
        right = [{"component_number": "LF200099", "operation_number": 10, "quantity": 1.0}]

        result = diff_boms(left, right, opts=CompareOptions())

        assert result.stats.added_count == 1
        assert result.stats.removed_count == 1
        assert result.stats.changed_count == 0


# ---------------------------------------------------------------------------
# Field changes: quantity, UOM, effectivity, ref-des
# ---------------------------------------------------------------------------


class TestFieldChanges:
    def test_quantity_change_is_reported_as_a_field_change(self):
        left = [{"component_number": "LF200010", "operation_number": 10, "quantity": 4.0}]
        right = [{"component_number": "LF200010", "operation_number": 10, "quantity": 6.0}]

        result = diff_boms(left, right, opts=CompareOptions())

        assert len(result.changed) == 1
        change = result.changed[0]
        assert len(change.field_changes) == 1
        fc = change.field_changes[0]
        assert fc.field == "quantity"
        assert fc.old_value == 4.0
        assert fc.new_value == 6.0

    def test_uom_change_is_reported_as_a_field_change(self):
        left = [{"component_number": "LF200010", "operation_number": 10, "unit_of_measure": "EA"}]
        right = [{"component_number": "LF200010", "operation_number": 10, "unit_of_measure": "PK"}]

        result = diff_boms(left, right, opts=CompareOptions())

        assert result.changed[0].field_changes[0].field == "unit_of_measure"

    def test_effectivity_date_change_is_reported_as_a_field_change(self):
        left = [{"component_number": "LF200010", "operation_number": 10, "to_date": 20250614}]
        right = [{"component_number": "LF200010", "operation_number": 10, "to_date": 99999999}]

        result = diff_boms(left, right, opts=CompareOptions())

        assert result.changed[0].field_changes[0].field == "to_date"

    def test_ref_des_array_field_change_is_reported(self):
        left = [{"component_number": "LF200010", "operation_number": 10, "ref_des": ["R1", "R2"]}]
        right = [{"component_number": "LF200010", "operation_number": 10, "ref_des": ["R1", "R3"]}]

        result = diff_boms(left, right, opts=CompareOptions())

        assert result.changed[0].field_changes[0].field == "ref_des"

    def test_ref_des_array_field_reordered_is_not_a_change(self):
        """Array-valued non-key fields use the same order-independent rule
        as array-valued key fields — defect (a) consistency applied to
        every array field, not only the ones used as the match key."""
        left = [{"component_number": "LF200010", "operation_number": 10, "ref_des": ["R1", "R2"]}]
        right = [{"component_number": "LF200010", "operation_number": 10, "ref_des": ["R2", "R1"]}]

        result = diff_boms(left, right, opts=CompareOptions())

        assert result.changed == []

    def test_multiple_field_changes_on_one_line_are_all_reported(self):
        left = [{"component_number": "LF200010", "operation_number": 10, "quantity": 4.0, "unit_of_measure": "EA"}]
        right = [{"component_number": "LF200010", "operation_number": 10, "quantity": 6.0, "unit_of_measure": "PK"}]

        result = diff_boms(left, right, opts=CompareOptions())

        changed_fields = {fc.field for fc in result.changed[0].field_changes}
        assert changed_fields == {"quantity", "unit_of_measure"}


# ---------------------------------------------------------------------------
# Op-moved: behaviour depends on whether operation_number is part of the key
# ---------------------------------------------------------------------------


class TestOpMoved:
    def test_op_move_under_default_key_is_a_remove_plus_add(self):
        """Default key includes operation_number, so a line whose op moved
        has no counterpart at its old key — Stargile/M3 terms, MSEQ-within-
        operation identity genuinely changed. See module docstring."""
        left = [{"component_number": "LF200010", "operation_number": 10, "quantity": 4.0}]
        right = [{"component_number": "LF200010", "operation_number": 20, "quantity": 4.0}]

        result = diff_boms(left, right, opts=CompareOptions())

        assert result.changed == []
        assert len(result.removed) == 1
        assert len(result.added) == 1

    def test_op_move_under_component_only_key_is_a_field_change(self):
        """Selecting a key that excludes operation_number (dynamic key
        selection) turns an op-move into an ordinary field change instead."""
        left = [{"component_number": "LF200010", "operation_number": 10, "quantity": 4.0}]
        right = [{"component_number": "LF200010", "operation_number": 20, "quantity": 4.0}]

        result = diff_boms(left, right, opts=CompareOptions(key=("component_number",)))

        assert len(result.changed) == 1
        assert result.changed[0].field_changes[0].field == "operation_number"
        assert result.added == []
        assert result.removed == []


# ---------------------------------------------------------------------------
# Stargile padding equivalence (D5: OPNO/MSEQ pad-4, STRT pad-3,
# undefined to-date = 99999999)
# ---------------------------------------------------------------------------


class TestPaddingEquivalence:
    def test_string_and_int_operation_number_compare_equal(self):
        left = [{"component_number": "LF200010", "operation_number": "10"}]
        right = [{"component_number": "LF200010", "operation_number": 10}]

        result = diff_boms(left, right, opts=CompareOptions())

        assert result.added == []
        assert result.removed == []

    def test_zero_padded_operation_number_compares_equal_to_unpadded(self):
        left = [{"component_number": "LF200010", "operation_number": "0010"}]
        right = [{"component_number": "LF200010", "operation_number": "10"}]

        result = diff_boms(left, right, opts=CompareOptions())

        assert result.added == []
        assert result.removed == []

    def test_zero_padded_key_field_matches_and_diffs_other_fields_normally(self):
        left = [{"component_number": "LF200010", "operation_number": "0010", "quantity": 4.0}]
        right = [{"component_number": "LF200010", "operation_number": "10", "quantity": 6.0}]

        result = diff_boms(left, right, opts=CompareOptions())

        assert len(result.changed) == 1
        assert result.changed[0].field_changes[0].field == "quantity"

    def test_padding_equivalence_applies_to_non_key_numeric_fields_too(self):
        """_values_equal uses the same numeric-parse rule as key derivation
        — "0004" and "4" are the same quantity, not a string mismatch."""
        left = [{"component_number": "LF200010", "operation_number": 10, "quantity": "0004"}]
        right = [{"component_number": "LF200010", "operation_number": 10, "quantity": "4"}]

        result = diff_boms(left, right, opts=CompareOptions())

        assert result.changed == []


# ---------------------------------------------------------------------------
# Duplicate component at different operations — matched independently
# (regression fixture: tests/fixtures/bom/single_level.json, LF200010 appears
# at MSEQ 10/OPNO 10 and MSEQ 70/OPNO 20)
# ---------------------------------------------------------------------------


class TestDuplicateComponentAtDifferentOperations:
    def _erp_lines(self, filename: str) -> list[dict]:
        records = _load_lines(filename)
        return [
            {
                "component_number": r["MTNO"],
                "operation_number": r["OPNO"],
                "quantity": r["CNQT"],
                "sequence_number": r["MSEQ"],
            }
            for r in records
        ]

    def test_repeated_component_at_two_ops_both_present_and_unchanged(self):
        lines = self._erp_lines("single_level.json")

        result = diff_boms(lines, lines, opts=CompareOptions())

        assert result.changed == []
        assert result.added == []
        assert result.removed == []

    def test_repeated_component_changing_qty_at_only_one_op_reports_one_change(self):
        left = self._erp_lines("single_level.json")
        right = [dict(ln) for ln in left]
        # LF200010 @ OPNO 10 (MSEQ 10): bump quantity. The OPNO 20 occurrence
        # (MSEQ 70) is untouched and must not be affected by this change.
        for ln in right:
            if ln["component_number"] == "LF200010" and ln["operation_number"] == 10:
                ln["quantity"] = 999.0

        result = diff_boms(left, right, opts=CompareOptions())

        assert len(result.changed) == 1
        changed = result.changed[0]
        assert changed.key == ("LF200010", 10.0)
        assert changed.field_changes[0].new_value == 999.0

    def test_repeated_component_removed_at_only_one_op_is_one_removal(self):
        left = self._erp_lines("single_level.json")
        right = [
            ln for ln in left
            if not (ln["component_number"] == "LF200010" and ln["operation_number"] == 20)
        ]

        result = diff_boms(left, right, opts=CompareOptions())

        assert len(result.removed) == 1
        assert result.removed[0]["operation_number"] == 20
        assert result.changed == []


# ---------------------------------------------------------------------------
# Same key colliding more than once on the SAME side (a true collision,
# distinct from the different-operation_number case above)
# ---------------------------------------------------------------------------


class TestSameKeyDuplicatesOnBothSides:
    def test_two_lines_sharing_a_key_on_both_sides_match_pairwise_by_encounter_order(self):
        left = [
            {"component_number": "LF200010", "operation_number": 10, "quantity": 1.0},
            {"component_number": "LF200010", "operation_number": 10, "quantity": 2.0},
        ]
        right = [
            {"component_number": "LF200010", "operation_number": 10, "quantity": 1.0},
            {"component_number": "LF200010", "operation_number": 10, "quantity": 2.0},
        ]

        result = diff_boms(left, right, opts=CompareOptions())

        assert result.changed == []
        assert result.added == []
        assert result.removed == []

    def test_unequal_count_of_same_key_duplicates_produces_addition(self):
        left = [{"component_number": "LF200010", "operation_number": 10, "quantity": 1.0}]
        right = [
            {"component_number": "LF200010", "operation_number": 10, "quantity": 1.0},
            {"component_number": "LF200010", "operation_number": 10, "quantity": 1.0},
        ]

        result = diff_boms(left, right, opts=CompareOptions())

        assert len(result.added) == 1
        assert result.removed == []
