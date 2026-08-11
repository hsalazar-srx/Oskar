"""
OSKAR — ECN BOM change endpoints (Slice E, I2-6, ADR-012).

POST   /ecn/{ecn_id}/items/{item_id}/bom-changes              Add BOM change
GET    /ecn/{ecn_id}/items/{item_id}/bom-changes              List BOM changes
GET    /ecn/{ecn_id}/bom-changes                               List across every item (aggregate tab)
GET    /ecn/{ecn_id}/bom-changes/export                        Export to .xlsx (IMPLEMENTED only)
POST   /ecn/{ecn_id}/bom-changes/bulk                          Bulk upload (.xlsx/.csv, multi-item)
PATCH  /ecn/{ecn_id}/items/{item_id}/bom-changes/{change_id}  Update BOM change
DELETE /ecn/{ecn_id}/items/{item_id}/bom-changes/{change_id}  Remove BOM change

CHANGE/DELETE change_type rows require old_from_date (service-layer
validation, ECNBomChangesMixin). Edits are blocked once the ECN reaches
DC_APPROVED in workflow order, unless the caller passes actor_role="DC".

At dc_approve, _queue_bom_changes_outbox() (workflow.py) inserts one
PDS002MI.AddComponent row per ADD, one PDS002MI.UpdateComponent close row per
DELETE, and a close+add pair (ordered via movex_outbox.depends_on) per
CHANGE.

Bulk upload is ECN-wide, multi-item — like routing's bulk upload, NOT scoped
to a single pre-selected item. Verified against the real Stargile source
(2026-08-11, c:/Projects/SuperTool/Stargile_Source_Code/workspace/Startronics/
src/java/com/startronics/ecn/upload/rules/UploadECNBoMs.java): each row
carries its own zecnln (ECN line number) / prno (parent item) — an upload
can spread across many items on one ECN, exactly like
_ROUTING_UPLOAD_SPEC/bulk_create_routing_operations. An earlier draft of
this endpoint read Stargile's upload as per-item and scoped the route under
.../items/{item_id}/bom-changes/bulk; corrected before landing once the
actual column layout was checked.

Route declaration order matters within this router: /{ecn_id}/bom-changes
(the GET aggregate list) and /{ecn_id}/bom-changes/bulk are declared before
any route with a variable path segment could shadow them, and the bulk
upload's own path has no ambiguity with the .../items/{item_id}/... routes
(different first path segment after ecn_id).
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
from src.routers.ecn_schemas import (
    BOMChangeBody,
    BOMChangeOut,
    BOMChangePatchBody,
    BulkBomChangeRow,
    bom_change_out,
)
from src.services.ecn import (
    BOMChangeRequest,
    ECNNotFound,
    ECNService,
    ECNValidationError,
)
from src.workflow.machine import ECNStatus

_XLSX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

_BOM_CHANGES_EXPORT_SPEC = BulkExportSpec(
    sheet_name="BOM Changes",
    columns=[
        ExportColumn(header="Item No", getter=lambda c: c.item_number),
        ExportColumn(header="Component Number", getter=lambda c: c.component_number),
        ExportColumn(header="Change Type", getter=lambda c: c.change_type),
        ExportColumn(header="Quantity", getter=lambda c: c.quantity),
        ExportColumn(header="Unit of Measure", getter=lambda c: c.unit_of_measure),
        ExportColumn(header="Operation No", getter=lambda c: c.operation_number),
        ExportColumn(header="From Date", getter=lambda c: c.from_date),
        ExportColumn(header="Old Quantity", getter=lambda c: c.old_quantity),
        ExportColumn(header="Old Operation No", getter=lambda c: c.old_operation_number),
        ExportColumn(header="Old From Date", getter=lambda c: c.old_from_date),
    ],
)


async def _require_implemented_for_export(session: AsyncSession, ecn_id: str) -> str:
    """Raise unless the ECN exists and is IMPLEMENTED. Returns ecn_number for
    the filename. Duplicated from ecn_routing.py/ecn_items.py's identical
    helper — each export router keeps its own copy, matching this codebase's
    existing convention (no shared cross-router helper module for this)."""
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


ecn_bom_router = APIRouter(tags=["ecn"])


@ecn_bom_router.get(
    "/{ecn_id}/bom-changes",
    response_model=list[BOMChangeOut],
    summary="List BOM changes across every item on this ECN (aggregate BOM Changes tab)",
)
async def list_all_bom_changes(
    ecn_id: str,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[BOMChangeOut]:
    svc = ECNService(session)
    try:
        changes = await svc.list_all_bom_changes(ecn_id)
    except ECNNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ECN not found")
    return [bom_change_out(c) for c in changes]


@ecn_bom_router.get(
    "/{ecn_id}/bom-changes/export",
    summary="Export BOM changes to .xlsx — only available once the ECN is Movex Updated",
)
async def export_bom_changes(
    ecn_id: str,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Response:
    ecn_number = await _require_implemented_for_export(session, ecn_id)
    svc = ECNService(session)
    changes = await svc.list_all_bom_changes(ecn_id)
    xlsx = build_xlsx(changes, _BOM_CHANGES_EXPORT_SPEC)
    return _xlsx_response(xlsx, f"{ecn_number}-bom-changes.xlsx")

# ---------------------------------------------------------------------------
# Bulk BOM-change upload spec (Stargile's UploadECNBoMs parity, S9-8 pattern)
# — multi-item, ECN-wide, same shape as _ROUTING_UPLOAD_SPEC. A row is
# treated as real data if item_number is present (same convention as bulk
# routing/bulk items).
# ---------------------------------------------------------------------------

_BOM_CHANGE_UPLOAD_SPEC = BulkUploadSpec(
    template_name="BOM change upload template",
    required_columns={
        "Item No",
        "Component Number",
        "Change Type",
    },
    column_map={
        "item no": "item_number",
        "component number": "component_number",
        "change type": "change_type",
        "quantity": "quantity",
        "unit of measure": "unit_of_measure",
        "operation number": "operation_number",
        "from date": "from_date",
        "old from date": "old_from_date",
        "old quantity": "old_quantity",
    },
    row_key_field="item_number",
)


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


@ecn_bom_router.post(
    "/{ecn_id}/bom-changes/bulk",
    response_model=list[BOMChangeOut],
    status_code=status.HTTP_201_CREATED,
    summary="Bulk upload BOM changes for one or many items (.xlsx or .csv)",
)
async def bulk_create_bom_changes(
    ecn_id: str,
    file: UploadFile,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    actor_role: str | None = None,
) -> list[BOMChangeOut]:
    rows = await parse_bulk_upload(file, _BOM_CHANGE_UPLOAD_SPEC)

    # -- Batch-level duplicate check (within the upload) -----------------------
    # Key includes item_number — the same (component_number, operation_number)
    # pair on two DIFFERENT items is not a duplicate (matches bulk routing's
    # own (item_number, operation_number) convention).
    seen: set[tuple[str, str, str]] = set()
    for idx, row in enumerate(rows, start=1):
        key = (
            (row.get("item_number") or "").strip(),
            (row.get("component_number") or "").strip(),
            (row.get("operation_number") or "").strip(),
        )
        if key in seen:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Row {idx}: operation_number '{key[2]}' for component "
                    f"'{key[1]}' on item '{key[0]}' appears more than once in the upload."
                ),
            )
        seen.add(key)

    # -- Pydantic row validation -------------------------------------------
    validated_rows: list[dict] = []
    errors: list[str] = []
    for idx, row in enumerate(rows, start=1):
        try:
            validated = BulkBomChangeRow(**row)
            validated_rows.append(validated.model_dump())
        except Exception as exc:
            errors.append(f"Row {idx} ({row.get('component_number', '?')}): {exc}")

    if errors:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="; ".join(errors),
        )

    # -- Service call (atomic insert) -------------------------------------
    svc = ECNService(session)
    try:
        changes = await svc.bulk_create_bom_changes(
            ecn_id, validated_rows, actor_role=actor_role
        )
    except ECNNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ECN not found")
    except ECNValidationError as exc:
        msg = str(exc)
        http_status = (
            status.HTTP_409_CONFLICT
            if "DC_APPROVED" in msg or "duplicate" in msg.lower() or "appears more than once" in msg
            else status.HTTP_422_UNPROCESSABLE_ENTITY
        )
        raise HTTPException(status_code=http_status, detail=msg)

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
