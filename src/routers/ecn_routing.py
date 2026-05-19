"""
OSKAR — ECN routing operation endpoints.

POST   /ecn/{ecn_id}/items/{item_id}/routing             Add routing op
GET    /ecn/{ecn_id}/items/{item_id}/routing             List routing ops
PATCH  /ecn/{ecn_id}/items/{item_id}/routing/{op_id}    Update routing op
DELETE /ecn/{ecn_id}/items/{item_id}/routing/{op_id}    Remove routing op

At DC_APPROVED, _queue_routing_operations_outbox() inserts one
PDS002MI.AddOperation or UpdateOperation outbox entry per row.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import CurrentUser, get_current_user
from src.db import get_session
from src.services.ecn import (
    ECNConflict,
    ECNNotFound,
    ECNService,
    ECNValidationError,
    RoutingOperationRequest,
)
from src.routers.ecn_schemas import (
    RoutingOpBody,
    RoutingOpOut,
    RoutingOpPatchBody,
    routing_op_out,
)

ecn_routing_router = APIRouter(tags=["ecn"])


@ecn_routing_router.post(
    "/{ecn_id}/items/{item_id}/routing",
    response_model=RoutingOpOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_routing_operation(
    ecn_id: str,
    item_id: str,
    body: RoutingOpBody,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> RoutingOpOut:
    svc = ECNService(session)
    req = RoutingOperationRequest(
        operation_number=body.operation_number,
        operation_description=body.operation_description,
        work_centre=body.work_centre,
        run_time=body.run_time,
        setup_time=body.setup_time,
        change_type=body.change_type,
    )
    try:
        op = await svc.create_routing_operation(ecn_id, item_id, req)
    except ECNNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ECN item not found")
    except ECNConflict:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An operation with this operation_number already exists on this item",
        )
    except ECNValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    return routing_op_out(op)


@ecn_routing_router.get(
    "/{ecn_id}/items/{item_id}/routing",
    response_model=list[RoutingOpOut],
)
async def list_routing_operations(
    ecn_id: str,
    item_id: str,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[RoutingOpOut]:
    svc = ECNService(session)
    try:
        ops = await svc.list_routing_operations(ecn_id, item_id)
    except ECNNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ECN item not found")
    return [routing_op_out(op) for op in ops]


@ecn_routing_router.patch(
    "/{ecn_id}/items/{item_id}/routing/{op_id}",
    response_model=RoutingOpOut,
)
async def update_routing_operation(
    ecn_id: str,
    item_id: str,
    op_id: str,
    body: RoutingOpPatchBody,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> RoutingOpOut:
    svc = ECNService(session)
    try:
        op = await svc.update_routing_operation(
            ecn_id, item_id, op_id, **body.model_dump(exclude_none=True)
        )
    except ECNNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Routing operation not found"
        )
    except ECNValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    return routing_op_out(op)


@ecn_routing_router.delete(
    "/{ecn_id}/items/{item_id}/routing/{op_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
async def delete_routing_operation(
    ecn_id: str,
    item_id: str,
    op_id: str,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> None:
    svc = ECNService(session)
    try:
        await svc.delete_routing_operation(ecn_id, item_id, op_id)
    except ECNNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Routing operation not found"
        )
