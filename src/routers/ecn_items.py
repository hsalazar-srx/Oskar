"""
OSKAR — ECN item and MPN endpoints.

POST   /ecn/{ecn_id}/items                              Add item to ECN
GET    /ecn/{ecn_id}/items                              List items (with MPNs)
GET    /ecn/{ecn_id}/items/{item_id}                   Get single item
PATCH  /ecn/{ecn_id}/items/{item_id}                   Update item fields
DELETE /ecn/{ecn_id}/items/{item_id}                   Remove item

POST   /ecn/{ecn_id}/items/{item_id}/mpns              Add MPN
PATCH  /ecn/{ecn_id}/items/{item_id}/mpns/{mpn_id}    Update MPN
DELETE /ecn/{ecn_id}/items/{item_id}/mpns/{mpn_id}    Remove MPN
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import CurrentUser, get_current_user
from src.db import get_session
from src.services.ecn import (
    ECNNotFound,
    ECNService,
    ECNValidationError,
)
from src.routers.ecn_schemas import (
    CreateItemBody,
    CreateMPNBody,
    ECNItemOut,
    MPNOut,
    UpdateItemBody,
    UpdateMPNBody,
    item_out,
    mpn_out,
)

ecn_items_router = APIRouter(tags=["ecn"])


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
