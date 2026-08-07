"""
OSKAR — ECN BOM change endpoints (Slice E, I2-6, ADR-012).

POST   /ecn/{ecn_id}/items/{item_id}/bom-changes             Add BOM change
GET    /ecn/{ecn_id}/items/{item_id}/bom-changes             List BOM changes
PATCH  /ecn/{ecn_id}/items/{item_id}/bom-changes/{change_id} Update BOM change
DELETE /ecn/{ecn_id}/items/{item_id}/bom-changes/{change_id} Remove BOM change

CHANGE/DELETE change_type rows require old_from_date (service-layer
validation, ECNBomChangesMixin). Edits are blocked once the ECN reaches
DC_APPROVED in workflow order, unless the caller passes actor_role="DC".

At dc_approve, _queue_bom_changes_outbox() (workflow.py) inserts one
PDS002MI.AddComponent row per ADD, one PDS002MI.UpdateComponent close row per
DELETE, and a close+add pair (ordered via movex_outbox.depends_on) per
CHANGE.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import CurrentUser, get_current_user
from src.db import get_session
from src.routers.ecn_schemas import (
    BOMChangeBody,
    BOMChangeOut,
    BOMChangePatchBody,
    bom_change_out,
)
from src.services.ecn import (
    BOMChangeRequest,
    ECNNotFound,
    ECNService,
    ECNValidationError,
)

ecn_bom_router = APIRouter(tags=["ecn"])


@ecn_bom_router.post(
    "/{ecn_id}/items/{item_id}/bom-changes",
    response_model=BOMChangeOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_bom_change(
    ecn_id: str,
    item_id: str,
    body: BOMChangeBody,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    actor_role: str | None = None,
) -> BOMChangeOut:
    svc = ECNService(session)
    req = BOMChangeRequest(
        change_type=body.change_type,
        component_number=body.component_number,
        quantity=body.quantity,
        unit_of_measure=body.unit_of_measure,
        operation_number=body.operation_number,
        sequence_number=body.sequence_number,
        from_date=body.from_date,
        to_date=body.to_date,
        bom_type=body.bom_type,
        notes=body.notes,
        old_quantity=body.old_quantity,
        old_operation_number=body.old_operation_number,
        old_from_date=body.old_from_date,
        old_to_date=body.old_to_date,
        circuit_refs_old=body.circuit_refs_old,
        circuit_refs_new=body.circuit_refs_new,
    )
    try:
        change = await svc.create_bom_change(ecn_id, item_id, req, actor_role=actor_role)
    except ECNNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ECN item not found")
    except ECNValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    return bom_change_out(change)


@ecn_bom_router.get(
    "/{ecn_id}/items/{item_id}/bom-changes",
    response_model=list[BOMChangeOut],
)
async def list_bom_changes(
    ecn_id: str,
    item_id: str,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[BOMChangeOut]:
    svc = ECNService(session)
    try:
        changes = await svc.list_bom_changes(ecn_id, item_id)
    except ECNNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ECN item not found")
    return [bom_change_out(c) for c in changes]


@ecn_bom_router.patch(
    "/{ecn_id}/items/{item_id}/bom-changes/{change_id}",
    response_model=BOMChangeOut,
)
async def update_bom_change(
    ecn_id: str,
    item_id: str,
    change_id: str,
    body: BOMChangePatchBody,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> BOMChangeOut:
    svc = ECNService(session)
    fields = body.model_dump(exclude_none=True, exclude={"actor_role"})
    try:
        change = await svc.update_bom_change(
            ecn_id, item_id, change_id, actor_role=body.actor_role, **fields
        )
    except ECNNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="BOM change not found")
    except ECNValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    return bom_change_out(change)


@ecn_bom_router.delete(
    "/{ecn_id}/items/{item_id}/bom-changes/{change_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
async def delete_bom_change(
    ecn_id: str,
    item_id: str,
    change_id: str,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    actor_role: str | None = None,
) -> None:
    svc = ECNService(session)
    try:
        await svc.delete_bom_change(ecn_id, item_id, change_id, actor_role=actor_role)
    except ECNNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="BOM change not found")
    except ECNValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
