"""Slice F / I2-12 — BOM export service tests.

Golden-fixture driven, per the Iteration 2 plan's Slice F line: "TXT/CSV
export GET /api/v1/bom/{itno}/export?format= vs golden expected-output
fixture".

Format rationale (decided here, recorded so it isn't re-litigated):
  - CSV  — RFC 4180 quoting, CRLF line endings. The consumers are Excel and
           the Movex-adjacent tooling on Windows; LF-only CSV is the more
           common source of "why is it all on one line" support calls.
  - TXT  — fixed-width columns, which is what the legacy Stargile/PLM TXT
           exports produced and what downstream eyeball-comparison depends
           on. Not tab-separated: a tab export would just be a worse CSV.

Both formats export the SAME field set in the same order, so a diff between
a CSV and a TXT export of the same BOM is purely presentational.
"""

from __future__ import annotations

import pytest

from src.services.bom.export import (
    BOM_EXPORT_COLUMNS,
    UnsupportedExportFormat,
    bom_to_csv,
    bom_to_txt,
    export_bom,
)
from src.services.bom.models import BOMHead, BOMLine


def _line(
    *,
    seq: int = 10,
    component: str = "LCAP010001",
    description: str = "CAP CER 100NF 50V",
    op: int = 10,
    qty: float = 2.0,
    uom: str = "PCS",
    from_date: int = 20240118,
    to_date: int = 99999999,
    ref_des: list[str] | None = None,
) -> BOMLine:
    return BOMLine(
        sequence_number=seq,
        component_number=component,
        description=description,
        operation_number=op,
        quantity=qty,
        unit_of_measure=uom,
        from_date=from_date,
        to_date=to_date,
        ref_des=ref_des,
    )


def _head(lines: list[BOMLine] | None = None) -> BOMHead:
    return BOMHead(
        item_number="LFAM050001",
        structure_type="001",
        facility="D",
        description="MAIN ASSEMBLY",
        lines=lines if lines is not None else [_line()],
    )


class TestCSVExport:
    def test_header_row_matches_declared_columns(self):
        out = bom_to_csv(_head())
        first = out.split("\r\n")[0]
        assert first == ",".join(BOM_EXPORT_COLUMNS)

    def test_uses_crlf_line_endings(self):
        """Excel on Windows is the primary consumer — see module docstring."""
        out = bom_to_csv(_head())
        assert "\r\n" in out
        # no bare LF that isn't part of a CRLF
        assert out.replace("\r\n", "") .count("\n") == 0

    def test_one_row_per_line(self):
        head = _head([_line(seq=10), _line(seq=20), _line(seq=30)])
        rows = [r for r in bom_to_csv(head).split("\r\n") if r]
        assert len(rows) == 4  # header + 3

    def test_quotes_fields_containing_commas(self):
        head = _head([_line(description="RES, 10K, 1%")])
        out = bom_to_csv(head)
        assert '"RES, 10K, 1%"' in out

    def test_escapes_embedded_quotes(self):
        head = _head([_line(description='SPACER 1/4" NYLON')])
        out = bom_to_csv(head)
        # RFC 4180: embedded " is doubled, whole field quoted
        assert '"SPACER 1/4"" NYLON"' in out

    def test_open_ended_to_date_renders_empty_not_99999999(self):
        """99999999 is a sentinel, not a date a human should ever read."""
        out = bom_to_csv(_head([_line(to_date=99999999)]))
        assert "99999999" not in out

    def test_real_to_date_is_rendered(self):
        out = bom_to_csv(_head([_line(to_date=20260901)]))
        assert "20260901" in out

    def test_ref_des_list_is_joined(self):
        out = bom_to_csv(_head([_line(ref_des=["C1", "C2", "C7"])]))
        assert "C1 C2 C7" in out

    def test_ref_des_none_is_empty_not_the_word_none(self):
        out = bom_to_csv(_head([_line(ref_des=None)]))
        assert "None" not in out

    def test_empty_bom_still_emits_header(self):
        out = bom_to_csv(_head([]))
        assert out.strip() == ",".join(BOM_EXPORT_COLUMNS)


class TestTXTExport:
    def test_columns_are_fixed_width_and_aligned(self):
        head = _head([
            _line(component="LCAP010001", description="SHORT"),
            _line(component="LRESISTOR0000123", description="A MUCH LONGER DESCRIPTION HERE"),
        ])
        lines = [ln for ln in bom_to_txt(head).split("\r\n") if ln]
        # header + separator + 2 data rows
        assert len(lines) == 4
        # every row padded to the same width
        assert len({len(ln) for ln in lines}) == 1

    def test_has_separator_rule_under_header(self):
        lines = bom_to_txt(_head()).split("\r\n")
        assert set(lines[1].strip()) == {"-"}

    def test_overlong_value_is_truncated_not_wrapped(self):
        """A wrapped row would break column alignment for every downstream
        eyeball comparison — truncate instead."""
        head = _head([_line(description="X" * 200)])
        lines = [ln for ln in bom_to_txt(head).split("\r\n") if ln]
        assert len({len(ln) for ln in lines}) == 1
        assert "X" * 200 not in bom_to_txt(head)

    def test_open_ended_to_date_renders_blank(self):
        assert "99999999" not in bom_to_txt(_head([_line(to_date=99999999)]))


class TestExportDispatch:
    def test_csv_format(self):
        content, media_type, ext = export_bom(_head(), "csv")
        assert ext == "csv"
        assert media_type == "text/csv"
        assert content.startswith(",".join(BOM_EXPORT_COLUMNS))

    def test_txt_format(self):
        content, media_type, ext = export_bom(_head(), "txt")
        assert ext == "txt"
        assert media_type == "text/plain"

    def test_format_is_case_insensitive(self):
        assert export_bom(_head(), "CSV")[2] == "csv"

    def test_unsupported_format_raises(self):
        with pytest.raises(UnsupportedExportFormat):
            export_bom(_head(), "pdf")

    def test_xlsx_is_explicitly_unsupported_here(self):
        """xlsx export already exists for comparisons via openpyxl in the
        router; this endpoint is the TXT/CSV one per I2-12. Kept explicit so
        nobody assumes it silently falls through."""
        with pytest.raises(UnsupportedExportFormat):
            export_bom(_head(), "xlsx")
