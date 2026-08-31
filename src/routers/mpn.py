"""
OSKAR — MPN search endpoint (Slice C, ADR-012 D3).

GET /api/v1/mpn/search?q=STM32*&field=mpn&limit=&offset=

Wildcard '*' -> SQL LIKE '%', with literal '%'/'_' in the query escaped
(src.services.bom.mpn_master.wildcard_to_like). field selects which column
is matched: 'item' (item_number), 'mfr' (manufacturer_canonical), or 'mpn'
(default).
"""
from __future__ import annotations

from typing import Annotated, Any, Literal

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.adapters.suppliers.chain import SupplierChain
from src.auth.dependencies import CurrentUser, get_current_user
from src.db import get_session
from src.services.bom.mpn_master import search_item_mpns
from src.services.bom.mpn_prefill import build_mpn_ecn_prefill

mpn_router = APIRouter(prefix="/mpn", tags=["mpn"])


class MpnSearchHitResponse(BaseModel):
    id: str
    item_number: str
    supplier_number: str
    mpn: str
    manufacturer_name: str | None
    manufacturer_canonical: str | None
    is_default: bool
    end_effective_date: str | None


class MpnSearchResponse(BaseModel):
    results: list[MpnSearchHitResponse]
    total: int
    limit: int
    offset: int


@mpn_router.get(
    "/search",
    response_model=MpnSearchResponse,
    summary="Wildcard MPN search over item_mpns (Slice C)",
)
async def search_mpn(
    q: Annotated[str, Query(min_length=1, max_length=60, description="'*' wildcard, e.g. STM32*")],
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    field: Annotated[Literal["item", "mfr", "mpn"], Query(description="Column to search")] = "mpn",
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> MpnSearchResponse:
    """Wildcard-search item_mpns (the Oskar MPN master, migration 0025).

    '*' in `q` becomes a SQL '%' wildcard; a literal '%' or '_' in the query
    is escaped first so it matches literally rather than acting as a SQL
    wildcard itself (search_item_mpns / wildcard_to_like).
    """
    result = await search_item_mpns(session, query=q, field=field, limit=limit, offset=offset)
    return MpnSearchResponse(
        results=[
            MpnSearchHitResponse(
                id=hit.id,
                item_number=hit.item_number,
                supplier_number=hit.supplier_number,
                mpn=hit.mpn,
                manufacturer_name=hit.manufacturer_name,
                manufacturer_canonical=hit.manufacturer_canonical,
                is_default=hit.is_default,
                end_effective_date=(
                    hit.end_effective_date.isoformat() if hit.end_effective_date else None
                ),
            )
            for hit in result.hits
        ],
        total=result.total,
        limit=result.limit,
        offset=result.offset,
    )


# ── Slice F: MPN-not-found → "Create ECN" prefill (I2-12) ────────────────────

class MPNPrefillResponse(BaseModel):
    """A ready-to-post ECN draft for adding an MPN Oskar does not yet have.

    `ecn_draft` goes to the existing POST /ecn/ endpoint unchanged;
    `staged_mpn` is then attached to the created ECN's item. This endpoint
    deliberately does NOT create anything — see
    src/services/bom/mpn_prefill.py on why there is one creation route.
    """

    mpn: str
    ecn_draft: dict[str, Any]
    staged_mpn: dict[str, Any]
    supplier_data_found: bool
    supplier_attributes: dict[str, Any] = {}


@mpn_router.get(
    "/prefill-ecn",
    response_model=MPNPrefillResponse,
    summary="Build a Create-ECN payload for an MPN not in the master (Slice F, I2-12)",
)
async def prefill_ecn_for_mpn(
    mpn: Annotated[str, Query(min_length=1, max_length=30, description="The MPN to add")],
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    request: Request,
    facility: Annotated[str, Query(max_length=10, description="Facility for the new ECN")] = "D",
) -> MPNPrefillResponse:
    """Turn an MPN search miss into a ready-to-submit ECN draft.

    Returns 409 if the MPN already exists in item_mpns — offering to "add"
    something already on file would produce a duplicate ECN and hide the
    existing record from the user, which is worse than saying so plainly.

    Supplier lookup is best-effort: `supplier_data_found` says whether the
    chain answered, so the UI can distinguish "no supplier knows this part"
    from "we could not reach the suppliers".
    """
    cleaned = mpn.strip().upper()

    existing = await session.execute(
        sa.text("SELECT item_number FROM item_mpns WHERE UPPER(mpn) = :mpn LIMIT 1"),
        {"mpn": cleaned},
    )
    row = existing.first()
    if row is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"MPN {cleaned!r} already exists in the MPN master "
                f"(item {row[0]}) — no ECN is needed to add it."
            ),
        )

    chain = SupplierChain(session, getattr(request.app.state, "supplier_adapters", []))
    prefill = await build_mpn_ecn_prefill(cleaned, chain, facility=facility)

    return MPNPrefillResponse(
        mpn=cleaned,
        ecn_draft=prefill.ecn_draft,
        staged_mpn=prefill.staged_mpn,
        supplier_data_found=prefill.supplier_data_found,
        supplier_attributes=prefill.supplier_attributes,
    )
