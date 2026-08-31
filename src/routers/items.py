"""
OSKAR — item-scoped endpoints (Slice F, I2-12).

GET /api/v1/items/{item_number}/ecn-history   Per-item ECN history

Distinct from /ecn/{id}/items/... which is ECN-scoped (the items ON one ECN).
This router is keyed on an ITEM NUMBER and looks across every ECN — the
Stargile ECNChangesBrowse direction.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import CurrentUser, get_current_user
from src.db import get_session
from src.services.bom.item_history import get_item_ecn_history

items_router = APIRouter(prefix="/items", tags=["items"])


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
