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

POST   /ecn/{ecn_id}/mpns/bulk                         Bulk upload MPNs from .xlsx/.csv
                                                         (CAD BOM export shape — C P/N +
                                                         Manufacturer 1/2 + Part Number 1/2)
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import CurrentUser, get_current_user
from src.db import get_session
from src.routers.bulk_upload import BulkUploadSpec, parse_bulk_upload
from src.services.ecn import (
    ECNNotFound,
    ECNService,
    ECNValidationError,
)
from src.routers.ecn_schemas import (
    BulkItemRow,
    BulkMPNRow,
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
# Bulk item upload spec
# ---------------------------------------------------------------------------

_ITEM_UPLOAD_SPEC = BulkUploadSpec(
    template_name="item upload template",
    required_columns={
        "Item No",
        "Item Name",
        "Item Status",
        "Procurement Group",
        "Product Group",
        "Order Type",
        "Lead Free Code",
        "Good Receiving Method",
    },
    column_map={
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
    },
    row_key_field="item_number",
    bool_fields=frozenset({"is_new_item"}),
)

# ---------------------------------------------------------------------------
# Bulk MPN upload spec — CAD BOM export shape (see BOM-LI_RFSoC_8X8_GNSS_V2I1.csv).
# row_key_field is "mpn_1" (not "item_number"): a genuine component line always
# carries a Manufacturer 1 Part Number, so this only skips fully-blank filler
# rows — a row with a part but no C P/N still reaches BulkMPNRow validation and
# fails with a clear "item_number required" error instead of being silently
# dropped (auto-resolving those against Movex/DigiKey is Iteration 2, see plan).
# ---------------------------------------------------------------------------

_MPN_UPLOAD_SPEC = BulkUploadSpec(
    template_name="MPN upload template",
    required_columns={
        "C P/N",
        "Manufacturer 1",
        "Manufacturer 1 Part Number",
    },
    column_map={
        "c p/n": "item_number",
        "manufacturer 1": "manufacturer_1",
        "manufacturer 1 part number": "mpn_1",
        "manufacturer 2": "manufacturer_2",
        "manufacturer 2 part number": "mpn_2",
    },
    row_key_field="mpn_1",
)


def _expand_mpn_rows(raw_rows: list[dict]) -> list[dict]:
    """One CAD BOM row -> 1 or 2 MPN rows (primary + optional alternate)."""
    expanded: list[dict] = []
    for raw in raw_rows:
        expanded.append({
            "item_number": raw.get("item_number"),
            "mpn": raw.get("mpn_1"),
            "manufacturer": raw.get("manufacturer_1"),
            "is_default": True,
        })
        if raw.get("mpn_2") and raw.get("manufacturer_2"):
            expanded.append({
                "item_number": raw.get("item_number"),
                "mpn": raw.get("mpn_2"),
                "manufacturer": raw.get("manufacturer_2"),
                "is_default": False,
            })
    return expanded


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
    # -- 1-5. Content-type/size guards, parse, header check, empty check ------
    rows = await parse_bulk_upload(file, _ITEM_UPLOAD_SPEC)

    for row in rows:
        row.setdefault("effectivity_type", "IMMEDIATE")

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


# ---------------------------------------------------------------------------
# Bulk MPN upload — must be declared BEFORE /{item_id}/mpns routes so FastAPI
# does not match "bulk" as an item_id path parameter. DRAFT-only, same as
# bulk items — items referenced by C P/N must already exist on the ECN.
# ---------------------------------------------------------------------------

@ecn_items_router.post(
    "/{ecn_id}/mpns/bulk",
    response_model=list[MPNOut],
    status_code=status.HTTP_201_CREATED,
    summary="Bulk upload MPNs from a CAD BOM export (.xlsx or .csv)",
)
async def bulk_create_mpns(
    ecn_id: str,
    file: UploadFile,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[MPNOut]:
    raw_rows = await parse_bulk_upload(file, _MPN_UPLOAD_SPEC)
    rows = _expand_mpn_rows(raw_rows)

    # -- Batch-level duplicate check (within the upload) -----------------------
    seen: set[tuple[str, str]] = set()
    for idx, row in enumerate(rows, start=1):
        key = ((row.get("item_number") or "").strip(), (row.get("mpn") or "").strip())
        if key in seen:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Row {idx}: MPN '{key[1]}' for item '{key[0]}' appears more than once in the upload.",
            )
        seen.add(key)

    # -- Pydantic row validation -------------------------------------------
    validated_rows: list[dict] = []
    errors: list[str] = []
    for idx, row in enumerate(rows, start=1):
        try:
            validated = BulkMPNRow(**row)
            validated_rows.append(validated.model_dump())
        except Exception as exc:
            errors.append(f"Row {idx} ({row.get('item_number', '?')}): {exc}")

    if errors:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="; ".join(errors),
        )

    # -- Service call (atomic insert) -------------------------------------
    svc = ECNService(session)
    try:
        mpns = await svc.bulk_create_mpns(ecn_id, validated_rows)
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

    return [mpn_out(m) for m in mpns]


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
