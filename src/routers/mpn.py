"""
OSKAR — MPN search endpoint (Slice C, ADR-012 D3).

GET /api/v1/mpn/search?q=STM32*&field=mpn&limit=&offset=

Wildcard '*' -> SQL LIKE '%', with literal '%'/'_' in the query escaped
(src.services.bom.mpn_master.wildcard_to_like). field selects which column
is matched: 'item' (item_number), 'mfr' (manufacturer_canonical), or 'mpn'
(default).
"""
from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import CurrentUser, get_current_user
from src.db import get_session
from src.services.bom.mpn_master import search_item_mpns

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
