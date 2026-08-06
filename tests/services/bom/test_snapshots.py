"""
OSKAR — src.services.bom.snapshots pure-logic tests (Slice D, ADR-012 D2).

content_hash() is pure (no DB, no I/O) — canonicalises a lines list to a
key-order-independent, line-order-DEPENDENT JSON encoding and SHA-256
hashes it. Line order is preserved intentionally: two snapshots of the same
BOM captured with lines in a different order are not guaranteed to BE the
same BOM state (a real MSEQ resequence is itself a change worth detecting at
the concurrency-gate level, Slice E) — only key ordering WITHIN each line
dict is normalised away, since that's an incidental JSON-encoding detail
with no semantic meaning.

DB-touching insert_snapshot()/get_snapshot() are covered in
tests/integration/test_bom_snapshots.py (real Postgres, migration 0026).
"""
from __future__ import annotations

from src.services.bom.snapshots import content_hash


class TestContentHashKeyOrderIndependence:
    def test_same_lines_different_key_order_hash_identically(self):
        lines_a = [{"component_number": "LF200010", "quantity": 4.0}]
        lines_b = [{"quantity": 4.0, "component_number": "LF200010"}]

        assert content_hash(lines_a) == content_hash(lines_b)

    def test_different_line_content_hashes_differently(self):
        lines_a = [{"component_number": "LF200010", "quantity": 4.0}]
        lines_b = [{"component_number": "LF200010", "quantity": 6.0}]

        assert content_hash(lines_a) != content_hash(lines_b)

    def test_hash_is_stable_across_repeated_calls(self):
        lines = [{"component_number": "LF200010", "quantity": 4.0}]

        assert content_hash(lines) == content_hash(lines)

    def test_hash_output_is_a_64_char_hex_sha256(self):
        lines = [{"component_number": "LF200010", "quantity": 4.0}]

        h = content_hash(lines)

        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_empty_lines_list_hashes_deterministically(self):
        assert content_hash([]) == content_hash([])

    def test_line_order_change_produces_a_different_hash(self):
        """Line ORDER is significant (unlike key order within a line) — see
        module docstring for why this is intentional, not an oversight."""
        lines_a = [
            {"component_number": "LF200010", "quantity": 4.0},
            {"component_number": "LF200011", "quantity": 8.0},
        ]
        lines_b = [
            {"component_number": "LF200011", "quantity": 8.0},
            {"component_number": "LF200010", "quantity": 4.0},
        ]

        assert content_hash(lines_a) != content_hash(lines_b)
