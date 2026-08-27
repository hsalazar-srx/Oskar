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

import httpx
import sqlalchemy as sa
import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, Response, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.adapters.erp.movex import MovexRestAdapter
from src.auth.dependencies import CurrentUser, get_current_user
from src.db import get_session
from src.routers.bulk_export import BulkExportSpec, ExportColumn, build_xlsx
from src.routers.bulk_upload import BulkUploadSpec, parse_bulk_upload
from src.routers.ecn_schemas import (
    BOMChangeBody,
    BOMChangeOut,
    BOMChangePatchBody,
    BOMCrossRefOut,
    BulkBomChangeRow,
    ECNScopedBOMChangeBody,
    bom_change_out,
)
from src.services.bom.crossref import build_bom_crossref
from src.services.ecn import (
    BOMChangeRequest,
    ECNNotFound,
    ECNService,
    ECNValidationError,
)
from src.workflow.machine import ECNStatus

log = structlog.get_logger(__name__)

_XLSX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _get_erp_adapter(request: Request) -> MovexRestAdapter:
    return request.app.state.erp_adapter


async def _require_parents_exist_in_movex(
    erp: MovexRestAdapter, parent_item_numbers: set[str]
) -> None:
    """Validate that every named parent assembly exists in Movex (ADR-014).

    This replaces the ECN-membership rule Oskar invented with the rule
    Stargile actually enforced: RequestECNBoMDetailValidationHelper.java
    :342-352 checks the parent against MITMAS + MPDHED. v1 checks MITMAS
    only (via erp.get_item) — the MPDHED half is recorded as an open
    question in ADR-014's "Still to confirm" §1, not settled parity.

    Lives in the router, not the service, because the ERP adapter is
    injected per-route; routers/parts.py:407-440 is the existing precedent
    for this error-handling shape (circuit breaker -> 503, 404 -> user-
    facing message, connect/timeout -> 503).

    Callers must de-duplicate first: a 200-row upload typically names only
    1-10 distinct parents, so this is a handful of calls, not 200.
    """
    for parent in sorted(parent_item_numbers):
        try:
            # get_item returns {} for a nonexistent item — the MI route reports
            # not-found as 422/success-false rather than raising, so an empty
            # result is the "does not exist" signal, not an exception.
            item = await erp.get_item(parent)
            if not item:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=(
                        f"Parent item {parent!r} does not exist in Movex. A BOM change "
                        "must name a parent assembly that already exists in the ERP."
                    ),
                )
        except RuntimeError as exc:
            if "circuit breaker" not in str(exc):
                raise
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="ERP system unavailable (circuit breaker open). Try again shortly.",
            )
        except httpx.HTTPStatusError as exc:
            # get_item already absorbs the not-found statuses (404/422) and
            # returns {}, handled above. Anything still raising here is a
            # genuine ERP fault, not a missing item.
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"ERP returned unexpected status {exc.response.status_code}.",
            )
        except (httpx.ConnectError, httpx.TimeoutException):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="ERP system unreachable. Try again shortly.",
            )

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


async def _ecn_facility(session: AsyncSession, ecn_id: str) -> str:
    """The ECN's facility, for the where-used lookups.

    Falls back to 'D' if the ECN row somehow has no facility — the advisory
    degrading to a default-facility answer is better than it 500ing, and the
    column is NOT NULL DEFAULT anyway (migration 0001).
    """
    row = await session.execute(
        sa.text("SELECT facility FROM ecn_instances WHERE id = :id"),
        {"id": ecn_id},
    )
    found = row.first()
    return (found[0] if found and found[0] else "D")


@ecn_bom_router.get(
    "/{ecn_id}/bom-crossref",
    response_model=list[BOMCrossRefOut],
    summary="Advisory: other live assemblies consuming components this ECN removes (Slice F, I2-12)",
)
async def get_bom_crossref(
    ecn_id: str,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    erp: Annotated[MovexRestAdapter, Depends(_get_erp_adapter)],
) -> list[BOMCrossRefOut]:
    """For each DELETE/CHANGE BOM change on this ECN, which OTHER live
    assemblies still consume that component.

    Advisory only — never blocks a transition, and never returns an ERP error.
    If Movex is unreachable the affected findings come back with
    check_failed=true so the reviewer can tell "could not check" apart from
    "nothing found". An empty list means genuinely nothing shared.
    """
    svc = ECNService(session)
    try:
        changes = await svc.list_all_bom_changes(ecn_id)
    except ECNNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ECN not found")

    facility = await _ecn_facility(session, ecn_id)
    findings = await build_bom_crossref(erp, changes, facility=facility)
    return [
        BOMCrossRefOut(
            bom_change_id=f.bom_change_id,
            component_number=f.component_number,
            parent_item_number=f.parent_item_number,
            change_type=f.change_type,
            other_parents=f.other_parents,
            parents_also_on_this_ecn=f.parents_also_on_this_ecn,
            check_failed=f.check_failed,
        )
        for f in findings
    ]


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
# Bulk BOM-change upload spec — Oskar's own template. Stargile's
# UploadECNBoMs.java (the legacy ECN/BOM upload tool this module succeeds)
# used a raw positional CSV keyed on Sequence No/Action Flag codes with live
# per-row Movex validation during upload; Oskar takes the same underlying
# capability — bulk-author ADD/CHANGE/DELETE BOM lines against an ECN — and
# gives it a clearer, self-describing header row (Item No/Change Type/Old
# From Date) plus a deferred, single, cheaper conflict check at dc_approve
# (the concurrency gate diffs a submit-time snapshot against the live BOM
# once per ECN, rather than hitting Movex on every uploaded row). A file
# exported from the legacy tool needs its header row reworded to this
# template — a one-off manual step during the transition, not an ongoing
# maintenance burden of supporting two column vocabularies long-term.
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
        "sequence number": "sequence_number",
        "from date": "from_date",
        "old from date": "old_from_date",
        "old quantity": "old_quantity",
        "circuit reference": "circuit_refs_new",
        "notes": "notes",
    },
    row_key_field="item_number",
)


@ecn_bom_router.post(
    "/{ecn_id}/bom-changes",
    response_model=BOMChangeOut,
    status_code=status.HTTP_201_CREATED,
    summary="Add a BOM change with no item on the ECN (BOM-only ECN, ADR-014)",
)
async def create_ecn_scoped_bom_change(
    ecn_id: str,
    body: ECNScopedBOMChangeBody,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    erp: Annotated[MovexRestAdapter, Depends(_get_erp_adapter)],
    actor_role: str | None = None,
) -> BOMChangeOut:
    """Create a BOM change that stands alone — no ecn_items row required.

    ADR-014: Stargile's ZECNBOMS rows carry their own parent (BMPRNO) and
    never referenced the items table; the check requiring the parent to be
    on the ECN was written and then deliberately commented out there. Oskar
    adopts the rule Stargile actually kept instead: the parent must exist in
    Movex, validated here before the row is written.
    """
    await _require_parents_exist_in_movex(erp, {body.parent_item_number})

    svc = ECNService(session)
    req = BOMChangeRequest(
        change_type=body.change_type,
        component_number=body.component_number,
        parent_item_number=body.parent_item_number,
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
        change = await svc.create_bom_change(ecn_id, None, req, actor_role=actor_role)
    except ECNNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ECN not found")
    except ECNValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    return bom_change_out(change)


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
    erp: Annotated[MovexRestAdapter, Depends(_get_erp_adapter)],
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

    # -- Movex-existence check for parents not already on this ECN (ADR-014)
    # A parent that IS on the ECN was already validated when the item was
    # added, so only the off-ECN ones need an ERP round-trip. De-duplicated
    # by distinct parent first: a 200-row upload names 1-10 distinct
    # parents, so this is a handful of calls rather than one per row.
    on_ecn_rows = await session.execute(
        sa.text("SELECT item_number FROM ecn_items WHERE ecn_id = :ecn_id"),
        {"ecn_id": ecn_id},
    )
    on_ecn = {r[0] for r in on_ecn_rows}
    off_ecn_parents = {
        r["item_number"] for r in validated_rows if r["item_number"] not in on_ecn
    }
    if off_ecn_parents:
        await _require_parents_exist_in_movex(erp, off_ecn_parents)

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
