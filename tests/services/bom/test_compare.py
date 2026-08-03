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
