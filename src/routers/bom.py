"""
OSKAR — BOM browse + explosion endpoints (Slice A/B, ADR-012)

GET /api/v1/bom/{item_number}                 Single-level BOM browse (Slice A, B-1)
GET /api/v1/bom/{item_number}/indented         Multi-level explosion (Slice B, B-2)
GET /api/v1/bom/{item_number}/where-used       Where-used lookup (Slice B, B-3)
"""

from __future__ import annotations

from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel

from src.adapters.erp.base import BOMNotFound
from src.adapters.erp.movex import MovexRestAdapter
from src.auth.dependencies import CurrentUser, get_current_user
from src.services.bom.browse import get_single_level_bom
from src.services.bom.explode import assemble_where_used, build_bom_tree
from src.services.bom.models import BOMCycleError, BOMHead, BOMTreeNode, WhereUsedLine

bom_router = APIRouter(prefix="/bom", tags=["bom"])


# ── Dependencies ─────────────────────────────────────────────────────────────

def _get_erp_adapter(request: Request) -> MovexRestAdapter:
    return request.app.state.erp_adapter


# ── Response models ───────────────────────────────────────────────────────────

class BOMLineResponse(BaseModel):
    sequence_number: int
    component_number: str
    description: str
    operation_number: int
    quantity: float
    unit_of_measure: str
    from_date: int
    to_date: int
    item_type: str | None
    status: str | None
    ref_des: list[str] | None
    customer_alias: str | None


class BOMHeadResponse(BaseModel):
    item_number: str
    structure_type: str
    facility: str
    description: str
    lines: list[BOMLineResponse]


def _to_response(head: BOMHead) -> BOMHeadResponse:
    return BOMHeadResponse(
        item_number=head.item_number,
        structure_type=head.structure_type,
        facility=head.facility,
        description=head.description,
        lines=[BOMLineResponse(**vars(line)) for line in head.lines],
    )


class BOMTreeNodeResponse(BaseModel):
    component_number: str
    description: str
    operation_number: int
    quantity: float
    cumulative_quantity: float
    item_type: str | None
    is_phantom: bool
    children: list["BOMTreeNodeResponse"] = []


BOMTreeNodeResponse.model_rebuild()


def _tree_to_response(node: BOMTreeNode) -> BOMTreeNodeResponse:
    return BOMTreeNodeResponse(
        component_number=node.component_number,
        description=node.description,
        operation_number=node.operation_number,
        quantity=node.quantity,
        cumulative_quantity=node.cumulative_quantity,
        item_type=node.item_type,
        is_phantom=node.is_phantom,
        children=[_tree_to_response(child) for child in node.children],
    )


class WhereUsedResponse(BaseModel):
    parent_item: str
    structure_type: str
    facility: str
    sequence_number: int
    component_number: str
    operation_number: int
    quantity: float
    unit_of_measure: str
    from_date: int
    to_date: int


def _where_used_to_response(line: WhereUsedLine) -> WhereUsedResponse:
    return WhereUsedResponse(**vars(line))


# ── Shared ERP error mapping ───────────────────────────────────────────────────

def _raise_for_erp_error(exc: Exception) -> None:
    """Map ERPAdapter exceptions to HTTP errors, matching src/routers/parts.py's
    established convention for MovexRestAdapter call sites."""
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


# ── Slice A: single-level browse ──────────────────────────────────────────────

@bom_router.get(
    "/{item_number}",
    response_model=BOMHeadResponse,
    summary="Single-level BOM browse (Slice A, B-1)",
)
async def get_bom(
    item_number: str,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    erp: Annotated[MovexRestAdapter, Depends(_get_erp_adapter)],
    facility: Annotated[str, Query(max_length=5, description="Movex facility (MPDHED.FACI)")] = "D",
    structure_type: Annotated[str, Query(max_length=3, description="Movex structure type (MPDHED.STRT)")] = "001",
    bom_type: Annotated[str, Query(max_length=1, description="'M' = manufacturing BOM (default)")] = "M",
    effective_on: Annotated[str | None, Query(description="YYYYMMDD — optional as-of date passed to the ERP call")] = None,
    include_expired: Annotated[bool, Query(description="Include lines whose to_date has already passed")] = False,
) -> BOMHeadResponse:
    """Fetch a single-level BOM (MPDHED head + MPDMAT lines) for an item.

    Effectivity-filtered (to_date >= today, or >= effective_on when provided)
    unless include_expired=true. Lines are returned in MSEQ order.
    """
    try:
        head = await get_single_level_bom(
            erp,
            item_number,
            facility,
            structure_type=structure_type,
            bom_type=bom_type,
            effective_on=effective_on,
            include_expired=include_expired,
        )
    except BOMNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No BOM found for item {item_number!r}.",
        )
    except (RuntimeError, httpx.HTTPStatusError, httpx.ConnectError, httpx.TimeoutException) as exc:
        _raise_for_erp_error(exc)
        raise  # unreachable — _raise_for_erp_error always raises

    return _to_response(head)


# ── Slice B: multi-level explosion ────────────────────────────────────────────

@bom_router.get(
    "/{item_number}/indented",
    response_model=BOMTreeNodeResponse,
    summary="Multi-level (indented) BOM explosion (Slice B, B-2)",
)
async def get_bom_indented(
    item_number: str,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    erp: Annotated[MovexRestAdapter, Depends(_get_erp_adapter)],
    facility: Annotated[str, Query(max_length=5, description="Movex facility (MPDHED.FACI)")] = "D",
    structure_type: Annotated[str, Query(max_length=3, description="Movex structure type (MPDHED.STRT)")] = "001",
    depth: Annotated[int, Query(ge=1, le=12, description="Maximum explosion depth")] = 12,
) -> BOMTreeNodeResponse:
    """Fetch the multi-level explosion tree for an item.

    B-2 returns a flat, depth-first record list (recursive CTE over MPDMAT —
    PDZ100MI is broken in M3 and is not an option); this endpoint assembles it
    into a tree client-side via src/services/bom/explode.py.

    Note: B-2's own recursive-CTE performance against a large real multi-level
    UAT item (<2s target, ADR-012 Decision 4) is an external checkpoint owned
    by the movex-rest-api team — it cannot be validated from Oskar's side and
    is not exercised by this endpoint's tests.
    """
    try:
        payload = await erp.get_bom_indented(
            item_number,
            facility,
            structure_type=structure_type,
            max_depth=depth,
        )
    except (RuntimeError, httpx.HTTPStatusError, httpx.ConnectError, httpx.TimeoutException) as exc:
        _raise_for_erp_error(exc)
        raise  # unreachable

    try:
        data = payload.get("data", payload)
        tree = build_bom_tree(item_number, data.get("records", []), max_depth=depth)
    except BOMCycleError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Could not assemble BOM tree for {item_number!r}: {exc}",
        )

    return _tree_to_response(tree)


# ── Slice B: where-used ────────────────────────────────────────────────────────

@bom_router.get(
    "/{item_number}/where-used",
    response_model=list[WhereUsedResponse],
    summary="Where-used lookup: assemblies that consume this component (Slice B, B-3)",
)
async def get_where_used(
    item_number: str,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    erp: Annotated[MovexRestAdapter, Depends(_get_erp_adapter)],
    facility: Annotated[str, Query(max_length=5, description="Movex facility (MPDMAT.FACI)")] = "D",
    effective_on: Annotated[str | None, Query(description="YYYYMMDD — optional as-of date passed to the ERP call")] = None,
) -> list[WhereUsedResponse]:
    """List every parent assembly that consumes item_number as a component.

    An empty result is a legitimate "used nowhere" answer, not a 404.
    """
    try:
        payload = await erp.get_where_used(item_number, facility, effective_on=effective_on)
    except (RuntimeError, httpx.HTTPStatusError, httpx.ConnectError, httpx.TimeoutException) as exc:
        _raise_for_erp_error(exc)
        raise  # unreachable

    lines = assemble_where_used(payload)
    return [_where_used_to_response(line) for line in lines]
