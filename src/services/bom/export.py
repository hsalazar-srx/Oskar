"""OSKAR — src.services.bom.export — TXT/CSV BOM export (Slice F, I2-12).

Pure formatting over a BOMHead. No DB, no ERP, no I/O — the router fetches
the BOM via the existing Slice A browse path and hands the assembled head
here, which keeps this testable against golden fixtures with no fakes.

Why TXT *and* CSV rather than just xlsx (which Slice D already has):
  - CSV feeds Excel and the Windows-side Movex tooling. RFC 4180 quoting,
    CRLF endings — LF-only CSV is a recurring "it's all on one line" support
    call on Windows Excel.
  - TXT is fixed-width, matching what the legacy Stargile/PLM TXT exports
    produced. Downstream eyeball-comparison and any column-slicing script
    depends on the alignment holding, so overlong values TRUNCATE rather
    than wrap — a wrapped row silently breaks every column position after it.

Both formats emit BOM_EXPORT_COLUMNS in the same order, so a CSV and a TXT
export of one BOM differ only in presentation.
"""

from __future__ import annotations

import csv
import io

from src.services.bom.models import BOMHead, BOMLine

# 99999999 is the Movex open-ended TDAT sentinel (see browse.py). It is a
# sentinel, not a date, and must never reach a human-readable export.
_OPEN_ENDED_TDAT = 99999999

BOM_EXPORT_COLUMNS: tuple[str, ...] = (
    "Sequence",
    "Component",
    "Description",
    "Operation",
    "Quantity",
    "UoM",
    "From Date",
    "To Date",
    "Ref Des",
)

# Fixed-width layout for the TXT format, in BOM_EXPORT_COLUMNS order.
_TXT_WIDTHS: tuple[int, ...] = (8, 18, 40, 9, 12, 5, 10, 10, 30)

_CSV_MEDIA_TYPE = "text/csv"
_TXT_MEDIA_TYPE = "text/plain"


class UnsupportedExportFormat(ValueError):
    """Raised for a format this service does not produce.

    xlsx is deliberately *not* handled here — comparison xlsx export lives in
    the router via openpyxl (Slice D). I2-12 scopes this endpoint to TXT/CSV.
    """


def _to_date_display(to_date: int) -> str:
    return "" if to_date >= _OPEN_ENDED_TDAT else str(to_date)


def _ref_des_display(ref_des: list[str] | None) -> str:
    # None means "not enriched" (see BOMLine docstring), which is an empty
    # cell — never the literal string "None".
    return " ".join(ref_des) if ref_des else ""


def _quantity_display(quantity: float) -> str:
    """Trim a float that is really an integer: 2.0 -> "2".

    BOM quantities come off CNQT as floats but are overwhelmingly whole
    numbers; "2.0" in an export column reads as noise.
    """
    if quantity == int(quantity):
        return str(int(quantity))
    return str(quantity)


def _row(line: BOMLine) -> list[str]:
    """One export row, in BOM_EXPORT_COLUMNS order. Shared by both formats so
    the two can never drift apart."""
    return [
        str(line.sequence_number),
        line.component_number,
        line.description,
        str(line.operation_number),
        _quantity_display(line.quantity),
        line.unit_of_measure,
        str(line.from_date),
        _to_date_display(line.to_date),
        _ref_des_display(line.ref_des),
    ]


def bom_to_csv(head: BOMHead) -> str:
    """RFC 4180 CSV, CRLF line endings, header row always present.

    An empty BOM still emits the header — a zero-byte file is
    indistinguishable from a failed export.
    """
    buf = io.StringIO()
    # QUOTE_MINIMAL + csv's own escaping gives RFC 4180 behaviour: fields
    # containing the delimiter, a quote or a newline get quoted, embedded
    # quotes get doubled.
    writer = csv.writer(buf, lineterminator="\r\n", quoting=csv.QUOTE_MINIMAL)
    writer.writerow(BOM_EXPORT_COLUMNS)
    for line in head.lines:
        writer.writerow(_row(line))
    return buf.getvalue()


def _fixed(value: str, width: int) -> str:
    """Pad or truncate to exactly `width`. Truncation is intentional — see
    the module docstring on why wrapping is not an option here."""
    if len(value) > width:
        return value[:width]
    return value.ljust(width)


def _txt_row(values: tuple[str, ...] | list[str]) -> str:
    return " ".join(_fixed(v, w) for v, w in zip(values, _TXT_WIDTHS))


def bom_to_txt(head: BOMHead) -> str:
    """Fixed-width text, CRLF endings, header + separator rule + rows.

    Every emitted line is the same character width, including the header and
    the rule, so column positions are stable for downstream slicing.
    """
    header = _txt_row(BOM_EXPORT_COLUMNS)
    rule = "-" * len(header)
    rows = [_txt_row(_row(line)) for line in head.lines]
    return "\r\n".join([header, rule, *rows]) + "\r\n"


def export_bom(head: BOMHead, fmt: str) -> tuple[str, str, str]:
    """Dispatch on format.

    Returns (content, media_type, file_extension) so the router does not need
    its own format->media-type mapping.
    """
    normalised = fmt.strip().lower()
    if normalised == "csv":
        return bom_to_csv(head), _CSV_MEDIA_TYPE, "csv"
    if normalised == "txt":
        return bom_to_txt(head), _TXT_MEDIA_TYPE, "txt"
    raise UnsupportedExportFormat(
        f"Unsupported export format {fmt!r} — this endpoint produces 'csv' or 'txt'."
    )
