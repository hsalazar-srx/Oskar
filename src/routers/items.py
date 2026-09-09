"""
OSKAR — item-scoped endpoints (Slice F, I2-12).

GET /api/v1/items/search                       Item search (I2-15/I2-23)
GET /api/v1/items/{item_number}/routing        Current M3 routing operations
GET /api/v1/items/{item_number}/ecn-history    Per-item ECN history

Distinct from /ecn/{id}/items/... which is ECN-scoped (the items ON one ECN).
This router is keyed on an ITEM NUMBER and looks across every ECN — the
Stargile ECNChangesBrowse direction.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.adapters.erp.movex import MovexRestAdapter
from src.auth.dependencies import CurrentUser, get_current_user
from src.db import get_session
from src.services.bom.item_history import get_item_ecn_history

items_router = APIRouter(prefix="/items", tags=["items"])


def _get_erp_adapter(request: Request) -> MovexRestAdapter:
    return request.app.state.erp_adapter


def _raise_for_erp_error(exc: Exception) -> None:
    """Map ERPAdapter exceptions to HTTP errors — same convention as
    routers/bom.py and routers/parts.py."""
    if isinstance(exc, RuntimeError):
        if "circuit breaker" not in str(exc):
            raise exc
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ERP system unavailable (circuit breaker open). Try again shortly.",
        )
    if isinstance(exc, httpx.HTTPStatusError):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"ERP returned unexpected status {exc.response.status_code}.",
        )
    if isinstance(exc, (httpx.ConnectError, httpx.TimeoutException)):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="ERP connection failed after retries.",
        )
    raise exc


class ItemSearchResult(BaseModel):
    item_number: str
    description: str
    facility: str


class RoutingOperationSnapshot(BaseModel):
    """One live M3 routing operation, as PDS002MI.LstOperation returns it."""
    operation_number: int
    operation_description: str
    work_centre: str
    run_time: float | None
    setup_time: float | None


# ── Search — declared BEFORE "/{item_number}/..." ────────────────────────────
# Otherwise "search" is captured as an item_number, the same ordering care
# ecn_items.py takes for its bulk-upload route.

@items_router.get(
    "/search",
    response_model=list[ItemSearchResult],
    summary="Search the M3 item master by number or description (I2-15)",
)
async def search_items(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    erp: Annotated[MovexRestAdapter, Depends(_get_erp_adapter)],
    q: Annotated[str, Query(min_length=2, description="Item number or description substring")],
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    facility: Annotated[str | None, Query(max_length=5)] = None,
) -> list[ItemSearchResult]:
    """Find items by number or description.

    Minimum two characters: the underlying MMS200MI.LstItmFac returns the
    facility's whole item list and the substring match is applied
    application-side, so a one-character query would match nearly everything
    and be useless as well as slow. Callers should debounce.
    """
    try:
        results = await erp.search_items(q, limit=limit, facility=facility)
    except (RuntimeError, httpx.HTTPStatusError, httpx.ConnectError, httpx.TimeoutException) as exc:
        _raise_for_erp_error(exc)
        raise  # unreachable — _raise_for_erp_error always raises

    return [ItemSearchResult(**r) for r in results]


@items_router.get(
    "/{item_number}/routing",
    response_model=list[RoutingOperationSnapshot],
    summary="Current routing operations for an item, live from M3",
)
async def get_item_routing(
    item_number: str,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    erp: Annotated[MovexRestAdapter, Depends(_get_erp_adapter)],
    facility: Annotated[str, Query(max_length=5)] = "D",
    structure_type: Annotated[str, Query(max_length=3)] = "001",
) -> list[RoutingOperationSnapshot]:
    """Read an item's live routing from M3 (PDS002MI.LstOperation).

    The adapter has wrapped this transaction since Slice E but nothing called
    it, so the routing tab had no way to show current state — the gap that
    blocked the routing side of the before/after comparison.

    Returns [] for an item with no routing rather than 404: "this product has
    no operations" is a normal answer, not an error, and a CHANGE authored
    against an empty routing is still legitimate.
    """
    try:
        records = await erp.get_routing_operations(
            item_number, facility, structure_type=structure_type
        )
    except (RuntimeError, httpx.HTTPStatusError, httpx.ConnectError, httpx.TimeoutException) as exc:
        _raise_for_erp_error(exc)
        raise  # unreachable

    def _num(value: Any) -> float | None:
        if value in (None, ""):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    ops: list[RoutingOperationSnapshot] = []
    for r in records:
        opno = r.get("OPNO")
        if opno in (None, ""):
            continue
        ops.append(
            RoutingOperationSnapshot(
                operation_number=int(opno),
                operation_description=str(r.get("OPDS") or "").strip(),
                work_centre=str(r.get("PLGR") or "").strip(),
                run_time=_num(r.get("PITI")),
                setup_time=_num(r.get("SETI")),
            )
        )
    ops.sort(key=lambda o: o.operation_number)
    return ops


class ItemECNHistoryEntryResponse(BaseModel):
    ecn_id: str
    ecn_number: str
    ecn_title: str
    ecn_status: int
    originator_username: str
    facility: str
    created_at: datetime
    change_type: str
    detail: str
    related_item: str | None


class ItemECNHistoryResponse(BaseModel):
    item_number: str
    entries: list[ItemECNHistoryEntryResponse]
    total: int
    limit: int
    offset: int


@items_router.get(
    "/{item_number}/ecn-history",
    response_model=ItemECNHistoryResponse,
    summary="Every ECN that has touched this item (Slice F, I2-12)",
)
async def get_ecn_history(
    item_number: str,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ItemECNHistoryResponse:
    """Aggregate every way this item has been touched by an ECN, newest first.

    Four structurally different sources in one list — item-master changes,
    its own BOM changing, it changing inside someone else's BOM, and MPN
    changes. See src/services/bom/item_history.py for why they belong
    together rather than behind four separate endpoints.

    An item with no history returns an empty list, not a 404 — "nobody has
    changed this part" is a legitimate answer, and 404 would wrongly suggest
    the item does not exist.
    """
    entries, total = await get_item_ecn_history(
        session, item_number, limit=limit, offset=offset
    )
    return ItemECNHistoryResponse(
        item_number=item_number.strip(),
        entries=[
            ItemECNHistoryEntryResponse(
                ecn_id=e.ecn_id,
                ecn_number=e.ecn_number,
                ecn_title=e.ecn_title,
                ecn_status=e.ecn_status,
                originator_username=e.originator_username,
                facility=e.facility,
                created_at=e.created_at,
                change_type=e.change_type,
                detail=e.detail,
                related_item=e.related_item,
            )
            for e in entries
        ],
        total=total,
        limit=limit,
        offset=offset,
    )
