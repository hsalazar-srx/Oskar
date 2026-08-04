"""
OSKAR — Shared bulk-export xlsx generation (list[dict] -> xlsx bytes).

Write-direction counterpart to bulk_upload.py's parse-direction helpers.
Each caller supplies a BulkExportSpec describing which columns to write and
in what order — the same shape as BulkUploadSpec's column_map, inverted.

Entity-agnostic by design (no ECN-specific base class) — reused as-is once
BOM export needs it too.
"""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from typing import Any, Callable

import openpyxl


@dataclass(frozen=True)
class ExportColumn:
    """One column in an exported xlsx: header text + how to read it off a row."""

    header: str
    """Display header written to row 1."""

    getter: Callable[[Any], Any]
    """Extracts this column's value from one row object (dict, dataclass, etc.)."""


@dataclass(frozen=True)
class BulkExportSpec:
    """Describes how to render one entity type's rows as an xlsx sheet."""

    sheet_name: str
    columns: list[ExportColumn]


def build_xlsx(rows: list[Any], spec: BulkExportSpec) -> bytes:
    """Render rows to xlsx bytes per spec.columns, header row first."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = spec.sheet_name

    ws.append([col.header for col in spec.columns])
    for row in rows:
        ws.append([col.getter(row) for col in spec.columns])

    for col_idx, col in enumerate(spec.columns, start=1):
        width = max(len(col.header) + 2, 12)
        ws.column_dimensions[ws.cell(row=1, column=col_idx).column_letter].width = width

    buf = BytesIO()
    wb.save(buf)
    wb.close()
    return buf.getvalue()
