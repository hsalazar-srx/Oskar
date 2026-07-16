"""
OSKAR — Shared bulk-upload parsing helpers (xlsx/csv -> list[dict]).

Extracted from ecn_items.py's original bulk item upload implementation so
routing (ecn_routing.py) and MPN (ecn_items.py) bulk endpoints don't each
duplicate the same content-type/size guards and xlsx/csv parsing logic.

Each caller supplies a BulkUploadSpec describing its own column mapping,
required columns, and which mapped field marks a row as "real data" (as
opposed to a blank template/instruction row, which is silently skipped).
"""

from __future__ import annotations

import csv
import io
import logging
from dataclasses import dataclass, field

import openpyxl
from fastapi import HTTPException, UploadFile, status

logger = logging.getLogger(__name__)

MAX_UPLOAD_BYTES = 1 * 1024 * 1024  # 1 MB

ALLOWED_CONTENT_TYPES = {
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-excel",
    "text/csv",
    "application/csv",
}


@dataclass(frozen=True)
class BulkUploadSpec:
    """Describes how to parse one bulk-upload template."""

    template_name: str
    """Human-readable name used in error messages, e.g. 'item upload template'."""

    required_columns: set[str]
    """Canonical (display-case) column headers that must be present."""

    column_map: dict[str, str]
    """Normalised (lower/stripped) header -> parsed row field name."""

    row_key_field: str
    """Mapped field name that must be non-blank for a row to count as data
    (rather than a blank/instruction row to skip)."""

    bool_fields: frozenset[str] = field(default_factory=frozenset)
    """Mapped field names to coerce via _coerce_bool instead of raw string."""


def _normalise_header(h: str) -> str:
    return h.strip().lower()


def _check_headers(headers: list[str], required: set[str]) -> list[str]:
    """Return the subset of required columns missing from the uploaded file."""
    normalised = {_normalise_header(h) for h in headers}
    return [col for col in required if _normalise_header(col) not in normalised]


def _coerce_bool(val: str | None) -> bool:
    if val is None:
        return False
    return str(val).strip().lower() in {"1", "true", "yes", "1.0"}


def _row_to_dict(headers: list[str], row_values: list, spec: BulkUploadSpec) -> dict:
    """Map one raw row to spec.column_map field names."""
    out: dict = {}
    for header, value in zip(headers, row_values):
        mapped_field = spec.column_map.get(_normalise_header(header))
        if mapped_field is None:
            continue
        raw = str(value).strip() if value is not None else ""
        if mapped_field in spec.bool_fields:
            out[mapped_field] = _coerce_bool(raw)
        else:
            out[mapped_field] = raw if raw else None
    return out


def _parse_xlsx(content: bytes, spec: BulkUploadSpec) -> tuple[list[str], list[dict]]:
    """Parse xlsx bytes -> (headers, rows). Skips blank rows."""
    wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    ws = wb.active
    rows_iter = ws.iter_rows(values_only=True)

    headers: list[str] = []
    for raw_row in rows_iter:
        candidates = [str(c).strip() if c is not None else "" for c in raw_row]
        if any(candidates):
            headers = candidates
            break

    data_rows: list[dict] = []
    for raw_row in rows_iter:
        values = [str(c).strip() if c is not None else "" for c in raw_row]
        if not any(values):
            continue
        row_dict = _row_to_dict(headers, list(raw_row), spec)
        if not row_dict.get(spec.row_key_field):
            continue
        data_rows.append(row_dict)

    wb.close()
    return headers, data_rows


def _parse_csv(content: bytes, spec: BulkUploadSpec) -> tuple[list[str], list[dict]]:
    """Parse csv bytes -> (headers, rows). Handles UTF-8 and CP1252."""
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            text = content.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        text = content.decode("utf-8", errors="replace")

    reader = csv.DictReader(io.StringIO(text))
    headers = list(reader.fieldnames or [])
    data_rows: list[dict] = []
    for raw_row in reader:
        row_dict = _row_to_dict(headers, [raw_row.get(h, "") for h in headers], spec)
        if not row_dict.get(spec.row_key_field):
            continue
        data_rows.append(row_dict)
    return headers, data_rows


async def parse_bulk_upload(file: UploadFile, spec: BulkUploadSpec) -> list[dict]:
    """Full guard sequence for a bulk upload: content-type, size, parse, headers, empty.

    Returns the parsed data rows (list of dicts keyed by spec.column_map values).
    Raises HTTPException on any guard failure — callers still need to run their
    own batch-duplicate check and Pydantic row validation afterward.
    """
    content_type = (file.content_type or "").lower().split(";")[0].strip()
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Unsupported content type '{content_type}'. "
                "Upload an .xlsx or .csv file."
            ),
        )

    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds the 1 MB limit ({len(content):,} bytes received).",
        )

    try:
        if content_type in ("text/csv", "application/csv"):
            headers, rows = _parse_csv(content, spec)
        else:
            headers, rows = _parse_xlsx(content, spec)
    except Exception as exc:
        logger.warning("Bulk upload parse error (%s): %s", spec.template_name, exc)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Could not parse the uploaded file. Ensure it is a valid .xlsx or .csv.",
        )

    missing = _check_headers(headers, spec.required_columns)
    if missing:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Missing required columns: {', '.join(sorted(missing))}. "
                f"Use the standard Oskar {spec.template_name}."
            ),
        )

    if not rows:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="The file contains no data rows. Add rows below the header row.",
        )

    return rows
