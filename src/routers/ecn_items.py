"""
OSKAR — ECN item and MPN endpoints.

POST   /ecn/{ecn_id}/items                              Add item to ECN
GET    /ecn/{ecn_id}/items                              List items (with MPNs)
GET    /ecn/{ecn_id}/items/{item_id}                   Get single item
PATCH  /ecn/{ecn_id}/items/{item_id}                   Update item fields
DELETE /ecn/{ecn_id}/items/{item_id}                   Remove item

POST   /ecn/{ecn_id}/items/bulk                        Bulk upload items from .xlsx/.csv

POST   /ecn/{ecn_id}/items/{item_id}/mpns              Add MPN
PATCH  /ecn/{ecn_id}/items/{item_id}/mpns/{mpn_id}    Update MPN
DELETE /ecn/{ecn_id}/items/{item_id}/mpns/{mpn_id}    Remove MPN
"""

from __future__ import annotations

import csv
import io
import logging
from typing import Annotated

import openpyxl
from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import CurrentUser, get_current_user
from src.db import get_session
from src.services.ecn import (
    ECNNotFound,
    ECNService,
    ECNValidationError,
)
from src.routers.ecn_schemas import (
    BulkItemRow,
    CreateItemBody,
    CreateMPNBody,
    ECNItemOut,
    MPNOut,
    UpdateItemBody,
    UpdateMPNBody,
    item_out,
    mpn_out,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Bulk upload constants
# ---------------------------------------------------------------------------

_MAX_UPLOAD_BYTES = 1 * 1024 * 1024  # 1 MB

_ALLOWED_CONTENT_TYPES = {
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-excel",
    "text/csv",
    "application/csv",
}

# Canonical column headers that must be present in the upload template.
# Header matching is case-insensitive and whitespace-stripped.
_REQUIRED_COLUMNS = {
    "Item No",
    "Item Name",
    "Item Status",
    "Procurement Group",
    "Product Group",
    "Order Type",
    "Lead Free Code",
    "Good Receiving Method",
}

# Map from template column header → BulkItemRow field name
_COLUMN_MAP: dict[str, str] = {
    "is new item": "is_new_item",
    "item no": "item_number",
    "item name": "item_name",
    "item status": "item_status",
    "item description": "description_2",
    "drawing no": "drawing_number",
    "procurement group": "procurement_group",
    "product group": "product_group",
    "item group": "item_group",
    "unit of measurement": "unit_of_measure",
    "revision no": "revision_number",
    "supplier": "supplier_number",
    "responsible": "responsible_engineer",
    "customer alias": "customer_alias",
    "order type": "order_type",
    "lead free code": "lead_free_code",
    "good receiving method": "good_receiving_method",
}


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def _normalise_header(h: str) -> str:
    return h.strip().lower()


def _check_headers(headers: list[str]) -> list[str]:
    """Return list of required columns missing from the uploaded file."""
    normalised = {_normalise_header(h) for h in headers}
    missing = [
        col for col in _REQUIRED_COLUMNS
        if _normalise_header(col) not in normalised
    ]
    return missing


def _coerce_bool(val: str | None) -> bool:
    if val is None:
        return False
    return str(val).strip().lower() in {"1", "true", "yes", "1.0"}


def _row_to_dict(headers: list[str], row_values: list) -> dict:
    """Map a data row to BulkItemRow field names using _COLUMN_MAP."""
    out: dict = {}
    for header, value in zip(headers, row_values):
        field = _COLUMN_MAP.get(_normalise_header(header))
        if field is None:
            continue
        raw = str(value).strip() if value is not None else ""
        if field == "is_new_item":
            out[field] = _coerce_bool(raw)
        else:
            # Preserve the raw string — never let openpyxl/csv coerce numbers
            out[field] = raw if raw else None
    # Default effectivity
    out.setdefault("effectivity_type", "IMMEDIATE")
    return out


def _parse_xlsx(content: bytes) -> tuple[list[str], list[dict]]:
    """Parse xlsx bytes → (headers, rows). Skips blank rows."""
    wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    ws = wb.active
    rows_iter = ws.iter_rows(values_only=True)

    # First non-empty row is the header
    headers: list[str] = []
    for raw_row in rows_iter:
        candidates = [str(c).strip() if c is not None else "" for c in raw_row]
        if any(candidates):
            headers = candidates
            break

    data_rows: list[dict] = []
    for raw_row in rows_iter:
        values = [str(c).strip() if c is not None else "" for c in raw_row]
        # Skip fully blank rows and template instruction rows (all mapped fields empty)
        if not any(values):
            continue
        row_dict = _row_to_dict(headers, list(raw_row))
        # Skip rows where item_number is blank (instruction/example rows)
        if not row_dict.get("item_number"):
            continue
        data_rows.append(row_dict)

    wb.close()
    return headers, data_rows


def _parse_csv(content: bytes) -> tuple[list[str], list[dict]]:
    """Parse csv bytes → (headers, rows). Handles UTF-8 and CP1252."""
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
        row_dict = _row_to_dict(headers, [raw_row.get(h, "") for h in headers])
        if not row_dict.get("item_number"):
            continue
        data_rows.append(row_dict)
    return headers, data_rows

ecn_items_router = APIRouter(tags=["ecn"])


# ---------------------------------------------------------------------------
# Bulk upload — must be declared BEFORE /{item_id} routes so FastAPI
# does not match "bulk" as an item_id path parameter.
# ---------------------------------------------------------------------------

@ecn_items_router.post(
    "/{ecn_id}/items/bulk",
    response_model=list[ECNItemOut],
    status_code=status.HTTP_201_CREATED,
    summary="Bulk upload items from .xlsx or .csv template",
)
async def bulk_create_items(
    ecn_id: str,
    file: UploadFile,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[ECNItemOut]:
    # -- 1. Content-type guard ------------------------------------------------
    content_type = (file.content_type or "").lower().split(";")[0].strip()
    if content_type not in _ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Unsupported content type '{content_type}'. "
                "Upload an .xlsx or .csv file."
            ),
        )

    # -- 2. Size guard --------------------------------------------------------
    content = await file.read()
    if len(content) > _MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds the 1 MB limit ({len(content):,} bytes received).",
        )

    # -- 3. Parse file --------------------------------------------------------
    try:
        if content_type == "text/csv" or content_type == "application/csv":
            headers, rows = _parse_csv(content)
        else:
            headers, rows = _parse_xlsx(content)
    except Exception as exc:
        logger.warning("Bulk upload parse error for ECN %s: %s", ecn_id, exc)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Could not parse the uploaded file. Ensure it is a valid .xlsx or .csv.",
        )

    # -- 4. Header fingerprint check ------------------------------------------
    missing = _check_headers(headers)
    if missing:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Missing required columns: {', '.join(sorted(missing))}. "
                "Use the standard Oskar item upload template."
            ),
        )

    # -- 5. Empty file guard --------------------------------------------------
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="The file contains no data rows. Add items below the header row.",
        )

    # -- 6. Batch-level duplicate check (within the upload) -------------------
    seen: set[str] = set()
    for idx, row in enumerate(rows, start=1):
        num = (row.get("item_number") or "").strip()
        if num in seen:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Row {idx}: item_number '{num}' appears more than once in the upload.",
            )
        seen.add(num)

    # -- 7. Pydantic row validation -------------------------------------------
    validated_rows: list[dict] = []
    errors: list[str] = []
    for idx, row in enumerate(rows, start=1):
        try:
            validated = BulkItemRow(**row)
            validated_rows.append(validated.model_dump())
        except Exception as exc:
            errors.append(f"Row {idx} ({row.get('item_number', '?')}): {exc}")

    if errors:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="; ".join(errors),
        )

    # -- 8. Service call (atomic insert) -------------------------------------
    svc = ECNService(session)
    try:
        items = await svc.bulk_create_items(ecn_id, validated_rows)
    except ECNNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ECN not found")
    except ECNValidationError as exc:
        msg = str(exc)
        http_status = (
            status.HTTP_409_CONFLICT
            if "DRAFT" in msg or "duplicate" in msg.lower() or "appears more than once" in msg
            else status.HTTP_422_UNPROCESSABLE_ENTITY
        )
        raise HTTPException(status_code=http_status, detail=msg)

    return [item_out(i) for i in items]


@ecn_items_router.post(
    "/{ecn_id}/items",
    response_model=ECNItemOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_item(
    ecn_id: str,
    body: CreateItemBody,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ECNItemOut:
    svc = ECNService(session)
    try:
        item = await svc.create_item(ecn_id, **body.model_dump())
    except ECNNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ECN not found")
    except ECNValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    return item_out(item)


@ecn_items_router.get("/{ecn_id}/items", response_model=list[ECNItemOut])
async def list_items(
    ecn_id: str,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[ECNItemOut]:
    svc = ECNService(session)
    items = await svc.list_items(ecn_id)
    return [item_out(i) for i in items]


@ecn_items_router.get("/{ecn_id}/items/{item_id}", response_model=ECNItemOut)
async def get_item(
    ecn_id: str,
    item_id: str,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ECNItemOut:
    svc = ECNService(session)
    try:
        item = await svc.get_item(ecn_id, item_id)
    except ECNNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")
    return item_out(item)


@ecn_items_router.patch("/{ecn_id}/items/{item_id}", response_model=ECNItemOut)
async def update_item(
    ecn_id: str,
    item_id: str,
    body: UpdateItemBody,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ECNItemOut:
    svc = ECNService(session)
    try:
        item = await svc.update_item(
            ecn_id, item_id,
            **{k: v for k, v in body.model_dump().items() if v is not None},
        )
    except ECNNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")
    except ECNValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    return item_out(item)


@ecn_items_router.delete(
    "/{ecn_id}/items/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
async def delete_item(
    ecn_id: str,
    item_id: str,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> None:
    svc = ECNService(session)
    try:
        await svc.delete_item(ecn_id, item_id)
    except ECNNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")
    except ECNValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))


@ecn_items_router.post(
    "/{ecn_id}/items/{item_id}/mpns",
    response_model=MPNOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_mpn(
    ecn_id: str,
    item_id: str,
    body: CreateMPNBody,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> MPNOut:
    svc = ECNService(session)
    try:
        m = await svc.create_mpn(ecn_id, item_id, **body.model_dump())
    except ECNNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")
    except ECNValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    return mpn_out(m)


@ecn_items_router.patch(
    "/{ecn_id}/items/{item_id}/mpns/{mpn_id}",
    response_model=MPNOut,
)
async def update_mpn(
    ecn_id: str,
    item_id: str,
    mpn_id: str,
    body: UpdateMPNBody,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> MPNOut:
    svc = ECNService(session)
    try:
        m = await svc.update_mpn(
            ecn_id, mpn_id,
            **{k: v for k, v in body.model_dump().items() if v is not None},
        )
    except ECNNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="MPN not found")
    except ECNValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    return mpn_out(m)


@ecn_items_router.delete(
    "/{ecn_id}/items/{item_id}/mpns/{mpn_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
async def delete_mpn(
    ecn_id: str,
    item_id: str,
    mpn_id: str,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> None:
    svc = ECNService(session)
    try:
        await svc.delete_mpn(ecn_id, mpn_id)
    except ECNNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="MPN not found")
