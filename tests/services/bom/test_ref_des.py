"""
OSKAR — src.services.bom.ref_des unit tests

Closes the Slice A documented no-op: BOMLine.ref_des was left None because
bom_circuit_refs (D4) did not exist yet (migration 0030 created it) and the
C-1 endpoint is migration-only by contract. The table now exists and is
written by the outbox on every successful AddComponent
(src/tasks/movex_outbox.py:_upsert_bom_circuit_refs) — but nothing ever read
it back, so designators could be authored and never displayed.

Design note — why enrichment is a SEPARATE function rather than a change to
get_single_level_bom: browse.py is deliberately pure (no DB imports, see
src/services/bom/models.py module docstring). Reaching into Postgres from
inside it would break that convention and make every existing browse test
require a database. enrich_ref_des() takes the already-assembled BOMHead and
a session, so browse stays pure and the router composes the two.

The ERP line key is (facility, parent_item, structure_type, sequence_number,
from_date) — the uq_bom_circuit_refs_erp_line_key constraint from migration
0030. All five parts must match; a partial match is a different line.
"""
from __future__ import annotations

import pytest

from src.services.bom.models import BOMHead, BOMLine
from src.services.bom.ref_des import enrich_ref_des


def _line(
    *,
    sequence_number: int = 10,
    component_number: str = "LF200010",
    from_date: int = 20240101,
) -> BOMLine:
    return BOMLine(
        sequence_number=sequence_number,
        component_number=component_number,
        description="Test component",
        operation_number=20,
        quantity=1.0,
        unit_of_measure="EA",
        from_date=from_date,
        to_date=99999999,
    )


def _head(lines: list[BOMLine], *, facility: str = "D", item: str = "LF999999") -> BOMHead:
    return BOMHead(
        item_number=item,
        structure_type="001",
        facility=facility,
        description="Test Assembly",
        lines=lines,
    )


class _StubSession:
    """Minimal async session double.

    Returns rows keyed by the five-part ERP line key so a test can prove the
    lookup matches on the whole key, not just sequence_number.
    """

    def __init__(self, rows: list[dict]) -> None:
        self.rows = rows
        self.executed_params: dict | None = None

    async def execute(self, _stmt, params=None):
        self.executed_params = params
        rows = self.rows

        class _Result:
            def mappings(self):
                class _Mappings:
                    def all(self_inner):
                        return rows

                return _Mappings()

        return _Result()


class TestEnrichPopulatesRefDes:
    async def test_line_with_stored_designators_is_populated(self):
        head = _head([_line(sequence_number=10, from_date=20240101)])
        session = _StubSession([
            {
                "sequence_number": 10,
                "from_date": 20240101,
                "circuit_refs": ["R1", "R7", "R12"],
            }
        ])

        await enrich_ref_des(session, head)

        assert head.lines[0].ref_des == ["R1", "R7", "R12"]

    async def test_line_with_no_stored_row_stays_none(self):
        """Absence must read as None (unknown), never [] (known-empty) — a
        BOM line with no ref-des row has simply never been recorded, which is
        different from one recorded as having no designators."""
        head = _head([_line(sequence_number=10)])
        session = _StubSession([])

        await enrich_ref_des(session, head)

        assert head.lines[0].ref_des is None

    async def test_stored_empty_list_reads_as_empty_not_none(self):
        head = _head([_line(sequence_number=10, from_date=20240101)])
        session = _StubSession([
            {"sequence_number": 10, "from_date": 20240101, "circuit_refs": []}
        ])

        await enrich_ref_des(session, head)

        assert head.lines[0].ref_des == []


class TestKeyMatching:
    async def test_same_sequence_different_from_date_does_not_match(self):
        """The supersession model (D6) means one MSEQ legitimately has several
        rows over time, distinguished only by from_date. Matching on MSEQ
        alone would attach a superseded line's designators to the live one."""
        head = _head([_line(sequence_number=10, from_date=20260101)])
        session = _StubSession([
            {"sequence_number": 10, "from_date": 20240101, "circuit_refs": ["R1"]}
        ])

        await enrich_ref_des(session, head)

        assert head.lines[0].ref_des is None

    async def test_each_line_gets_its_own_designators(self):
        head = _head([
            _line(sequence_number=10, from_date=20240101),
            _line(sequence_number=20, from_date=20240101),
        ])
        session = _StubSession([
            {"sequence_number": 10, "from_date": 20240101, "circuit_refs": ["R1"]},
            {"sequence_number": 20, "from_date": 20240101, "circuit_refs": ["C4", "C5"]},
        ])

        await enrich_ref_des(session, head)

        assert head.lines[0].ref_des == ["R1"]
        assert head.lines[1].ref_des == ["C4", "C5"]

    async def test_query_is_scoped_to_this_bom(self):
        """facility + parent_item + structure_type must be in the WHERE clause.
        bom_circuit_refs is keyed on the ERP line key, and sequence numbers
        repeat across every assembly in the plant."""
        head = _head([_line()], facility="D", item="LF999999")
        session = _StubSession([])

        await enrich_ref_des(session, head)

        assert session.executed_params["facility"] == "D"
        assert session.executed_params["parent_item"] == "LF999999"
        assert session.executed_params["structure_type"] == "001"


class TestNoWorkCases:
    async def test_empty_bom_does_not_query(self):
        head = _head([])
        session = _StubSession([])

        await enrich_ref_des(session, head)

        assert session.executed_params is None
