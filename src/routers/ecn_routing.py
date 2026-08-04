"""
OSKAR — ECN routing operation endpoints.

POST   /ecn/{ecn_id}/routing/bulk                         Bulk upload routing ops (multi-item)
POST   /ecn/{ecn_id}/items/{item_id}/routing             Add routing op
GET    /ecn/{ecn_id}/items/{item_id}/routing             List routing ops
PATCH  /ecn/{ecn_id}/items/{item_id}/routing/{op_id}    Update routing op
DELETE /ecn/{ecn_id}/items/{item_id}/routing/{op_id}    Remove routing op

GET    /ecn/{ecn_id}/routing/export                       Export routing ops to .xlsx (IMPLEMENTED only)

At DC_APPROVED, _queue_routing_operations_outbox() inserts one
PDS002MI.AddOperation or UpdateOperation outbox entry per row.
"""

from __future__ import annotations

from typing import Annotated

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Response, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import CurrentUser, get_current_user
from src.db import get_session
from src.routers.bulk_export import BulkExportSpec, ExportColumn, build_xlsx
from src.routers.bulk_upload import BulkUploadSpec, parse_bulk_upload
from src.services.ecn import (
    ECNConflict,
    ECNNotFound,
    ECNService,
    ECNValidationError,
    RoutingOperationRequest,
)
from src.workflow.machine import ECNStatus
from src.routers.ecn_schemas import (
    BulkRoutingRow,
    RoutingOpBody,
    RoutingOpOut,
    RoutingOpPatchBody,
    routing_op_out,
)

_XLSX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

_ROUTING_EXPORT_SPEC = BulkExportSpec(
    sheet_name="Routing",
    columns=[
        ExportColumn(header="Item No", getter=lambda r: r.item_number),
        ExportColumn(header="Operation No", getter=lambda r: r.operation_number),
        ExportColumn(header="Operation Description", getter=lambda r: r.operation_description),
        ExportColumn(header="Work Centre", getter=lambda r: r.work_centre),
        ExportColumn(header="Run Time", getter=lambda r: r.run_time),
        ExportColumn(header="Setup Time", getter=lambda r: r.setup_time),
        ExportColumn(header="Change Type", getter=lambda r: r.change_type),
    ],
)


async def _require_implemented_for_export(
    session: AsyncSession, ecn_id: str
) -> str:
    """Raise unless the ECN exists and is IMPLEMENTED. Returns ecn_number for the filename."""
    row = await session.execute(
        sa.text("SELECT status, ecn_number FROM ecn_instances WHERE id = :id"),
        {"id": ecn_id},
    )
    ecn = row.first()
    if ecn is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ECN not found")
    if ecn[0] != ECNStatus.IMPLEMENTED:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Export is only available once the ECN reaches Movex Updated status.",
        )
    return ecn[1]


def _xlsx_response(xlsx_bytes: bytes, filename: str) -> Response:
    return Response(
        content=xlsx_bytes,
        media_type=_XLSX_CONTENT_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

# ---------------------------------------------------------------------------
# Bulk routing upload spec — multi-item, ECN-wide template. A row is treated
# as real data if item_number is present (same convention as bulk items);
# operation_number/work_centre/etc. missing on a real row surfaces as a
# Pydantic validation error instead of being silently skipped.
# ---------------------------------------------------------------------------

_ROUTING_UPLOAD_SPEC = BulkUploadSpec(
    template_name="routing upload template",
    required_columns={
        "Item No",
        "Operation No",
        "Operation Description",
        "Work Centre",
        "Run Time",
        "Change Type",
    },
    column_map={
        "item no": "item_number",
        "operation no": "operation_number",
        "operation description": "operation_description",
        "work centre": "work_centre",
        "work center": "work_centre",
        "run time": "run_time",
        "setup time": "setup_time",
        "change type": "change_type",
    },
    row_key_field="item_number",
)

ecn_routing_router = APIRouter(tags=["ecn"])


# ---------------------------------------------------------------------------
# Bulk upload — must be declared BEFORE /{item_id}/routing routes so FastAPI
# does not match "bulk" (or, without this ordering, an item_id) incorrectly.
# DRAFT-only, same as bulk items — items referenced by Item No must already
# exist on the ECN (bulk routing upload does not create items).
# ---------------------------------------------------------------------------

@ecn_routing_router.post(
    "/{ecn_id}/routing/bulk",
    response_model=list[RoutingOpOut],
    status_code=status.HTTP_201_CREATED,
    summary="Bulk upload routing operations for one or many items (.xlsx or .csv)",
)
async def bulk_create_routing_operations(
    ecn_id: str,
    file: UploadFile,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[RoutingOpOut]:
    rows = await parse_bulk_upload(file, _ROUTING_UPLOAD_SPEC)

    # -- Batch-level duplicate check (within the upload) -----------------------
    seen: set[tuple[str, str]] = set()
    for idx, row in enumerate(rows, start=1):
        key = ((row.get("item_number") or "").strip(), (row.get("operation_number") or "").strip())
        if key in seen:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Row {idx}: operation_number '{key[1]}' for item '{key[0]}' "
                    "appears more than once in the upload."
                ),
            )
        seen.add(key)

    # -- Pydantic row validation -------------------------------------------
    validated_rows: list[dict] = []
    errors: list[str] = []
    for idx, row in enumerate(rows, start=1):
        try:
            validated = BulkRoutingRow(**row)
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
        ops = await svc.bulk_create_routing_operations(ecn_id, validated_rows)
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

    return [routing_op_out(op) for op in ops]


@ecn_routing_router.get(
    "/{ecn_id}/routing",
    response_model=list[RoutingOpOut],
    summary="List routing operations across every item on this ECN (aggregate Routing tab)",
)
async def list_all_routing_operations(
    ecn_id: str,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[RoutingOpOut]:
    svc = ECNService(session)
    try:
        ops = await svc.list_all_routing_operations(ecn_id)
    except ECNNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ECN not found")
    return [routing_op_out(op) for op in ops]


@ecn_routing_router.get(
    "/{ecn_id}/routing/export",
    summary="Export routing operations to .xlsx — only available once the ECN is Movex Updated",
)
async def export_routing(
    ecn_id: str,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Response:
    ecn_number = await _require_implemented_for_export(session, ecn_id)
    svc = ECNService(session)
    ops = await svc.list_all_routing_operations(ecn_id)
    xlsx = build_xlsx(ops, _ROUTING_EXPORT_SPEC)
    return _xlsx_response(xlsx, f"{ecn_number}-routing.xlsx")


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
