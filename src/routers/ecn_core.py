"""
OSKAR — ECN core endpoints.

POST   /ecn/                          Create ECN
GET    /ecn/                          List ECNs (filters + next_action_users)
GET    /ecn/{ecn_id}                  Get ECN detail (+ Last-Modified header)
PATCH  /ecn/{ecn_id}                  Update writable fields
PATCH  /ecn/{ecn_id}/status           Fire workflow trigger
POST   /ecn/{ecn_id}/role-assignments Reassign a role (DC only)
POST   /ecn/{ecn_id}/resubmit         Resubmit after rejection
PATCH  /ecn/{ecn_id}/items/{item_id}/drawing  Set drawing number (DC only)
POST   /ecn/{ecn_id}/approve          Approve a management-review step
"""

from __future__ import annotations

from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.adapters.erp.movex import MovexRestAdapter
from src.auth.dependencies import CurrentUser, get_current_user
from src.db import get_session
from src.services.ecn import (
    ECNConflict,
    ECNCreateRequest,
    ECNForbidden,
    ECNNotFound,
    ECNPreconditionRequired,
    ECNService,
    ECNStatusTransitionRequest,
    ECNTransitionError,
    ECNUpdateRequest,
    ECNValidationError,
    RoleAssignmentResult,
)
from src.routers.ecn_schemas import (
    ApproveRoleBody,
    ECNCreateBody,
    ECNDetailOut,
    ECNSummaryOut,
    ECNTransitionBody,
    ECNUpdateBody,
    RoleAssignBody,
    RoleAssignmentOut,
    RoleAssignmentResultOut,
    ResubmitBody,
    SetDrawingNumberBody,
    detail_out,
    parse_if_unmodified_since,
    raise_optimistic_lock_errors,
    summary_out,
)

log = structlog.get_logger(__name__)

ecn_core_router = APIRouter(tags=["ecn"])


def _get_erp_adapter(request: Request) -> MovexRestAdapter:
    return request.app.state.erp_adapter


async def _resolve_customer_name(erp: MovexRestAdapter, cuno: str | None) -> str | None:
    """Return the customer name for a CUNO by looking up the cached customer list."""
    if not cuno:
        return None
    if cuno == "AC":
        return "Generic / Common Stock"
    try:
        customers = await erp.list_customers()
        for c in customers:
            if c.get("cuno", "").upper() == cuno.upper():
                return c.get("name") or None
    except Exception:
        pass
    return None


@ecn_core_router.post("/", response_model=ECNDetailOut, status_code=status.HTTP_201_CREATED)
async def create_ecn(
    body: ECNCreateBody,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    erp: Annotated[MovexRestAdapter, Depends(_get_erp_adapter)],
) -> ECNDetailOut:
    """Create a new ECN in DRAFT status.

    The requesting user becomes the originator (OR role).
    DC is auto-assigned from system_role_users if exactly one is configured for the facility.
    Returns 422 if facility is unknown or no DC is configured for the facility.
    """
    svc = ECNService(session)
    req = ECNCreateRequest(
        title=body.title,
        description=body.description,
        facility=body.facility,
        customer_number=body.customer_number,
        customer_ecn_refs=body.customer_ecn_refs,
        is_new_item=body.is_new_item,
        routing_changes=body.routing_changes,
        operation_changes=body.operation_changes,
        new_parts=body.new_parts,
        lead_time_changes=body.lead_time_changes,
        change_to_documents=body.change_to_documents,
        wapc_delta_pct=body.wapc_delta_pct,
        wapc_threshold_override=body.wapc_threshold_override,
        requires_customer_approval=body.requires_customer_approval,
        customer_approval_reference=body.customer_approval_reference,
        regulatory_impact=body.regulatory_impact,
        extra_data=body.extra_data,
    )
    try:
        detail = await svc.create(req, actor_username=user.username)
    except ECNValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    detail.customer_name = await _resolve_customer_name(erp, detail.customer_number)
    return detail_out(detail)


@ecn_core_router.get("/", response_model=list[ECNSummaryOut])
async def list_ecns(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    erp: Annotated[MovexRestAdapter, Depends(_get_erp_adapter)],
    facility: Annotated[str | None, Query(description="Filter by facility code")] = None,
    status_filter: Annotated[
        int | None, Query(alias="status", description="Filter by ECNStatus integer")
    ] = None,
    assignee: Annotated[
        str | None, Query(description="Filter ECNs where this username has an active role")
    ] = None,
    needs_my_action: Annotated[
        bool | None, Query(description="Only ECNs where the current user has a pending role")
    ] = None,
    overdue: Annotated[bool | None, Query(description="Only ECNs open longer than 7 days in active status")] = None,
    age_days: Annotated[int | None, Query(description="Only ECNs older than N days")] = None,
    search: Annotated[str | None, Query(description="Full-text search across ECN number, title, description, customer, customer ECN refs")] = None,
    customer_number: Annotated[str | None, Query(description="Filter by customer code")] = None,
    originator: Annotated[str | None, Query(description="Filter by originator username")] = None,
    sort_by: Annotated[str, Query(description="Sort column: ecn_number | created_at | status | originator_username | customer_number")] = "created_at",
    sort_dir: Annotated[str, Query(description="asc or desc")] = "desc",
    include_archived: Annotated[bool, Query()] = False,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[ECNSummaryOut]:
    """List ECNs with optional filters.

    Each result includes `next_action_users[]` — the usernames who must act
    next to advance the ECN (G-2, replaces DBCHK_OpenECN SQL Server Agent job).
    """
    svc = ECNService(session)

    # Build a customer name lookup map to enrich summaries without N+1 calls.
    customer_name_map: dict[str, str] = {}
    try:
        customers = await erp.list_customers()
        customer_name_map = {c.get("cuno", ""): c.get("name") or "" for c in customers}
        customer_name_map["AC"] = "Generic / Common Stock"
    except Exception:
        pass

    summaries = await svc.list_ecns(
        facility=facility,
        status=status_filter,
        assignee=assignee,
        needs_my_action=user.username if needs_my_action else None,
        overdue=overdue,
        age_days=age_days,
        search=search,
        customer_number=customer_number,
        originator=originator,
        sort_by=sort_by,
        sort_dir=sort_dir,
        include_archived=include_archived,
        limit=limit,
        offset=offset,
    )

    for s in summaries:
        if s.customer_number:
            s.customer_name = customer_name_map.get(s.customer_number) or None

    return [summary_out(s) for s in summaries]


@ecn_core_router.get("/{ecn_id}", response_model=ECNDetailOut)
async def get_ecn(
    ecn_id: str,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    erp: Annotated[MovexRestAdapter, Depends(_get_erp_adapter)],
    response: Response,
) -> ECNDetailOut:
    """Fetch a single ECN with role assignments and approval steps.

    Returns Last-Modified header (RFC 7231) so clients can supply
    If-Unmodified-Since on subsequent mutation requests (ADR-008).
    """
    svc = ECNService(session)
    try:
        detail = await svc.get(ecn_id)
    except ECNNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"ECN {ecn_id!r} not found",
        )
    detail.customer_name = await _resolve_customer_name(erp, detail.customer_number)
    response.headers["Last-Modified"] = detail.updated_at.strftime("%a, %d %b %Y %H:%M:%S GMT")
    return detail_out(detail)


@ecn_core_router.patch("/{ecn_id}", response_model=ECNDetailOut)
async def update_ecn(
    ecn_id: str,
    body: ECNUpdateBody,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    erp: Annotated[MovexRestAdapter, Depends(_get_erp_adapter)],
    if_unmodified_since: Annotated[str | None, Header()] = None,
) -> ECNDetailOut:
    """Edit writable fields on an ECN (DRAFT or REJECTED status only).

    Requires If-Unmodified-Since header (RFC 7231) matching the ECN's
    current updated_at value (ADR-008).
      428 — header absent
      409 — ECN was modified since the client last fetched it
    """
    svc = ECNService(session)
    req = ECNUpdateRequest(
        title=body.title,
        description=body.description,
        customer_ecn_refs=body.customer_ecn_refs,
        is_new_item=body.is_new_item,
        routing_changes=body.routing_changes,
        operation_changes=body.operation_changes,
        new_parts=body.new_parts,
        lead_time_changes=body.lead_time_changes,
        change_to_documents=body.change_to_documents,
        wapc_delta_pct=body.wapc_delta_pct,
        wapc_threshold_override=body.wapc_threshold_override,
        requires_customer_approval=body.requires_customer_approval,
        customer_approval_reference=body.customer_approval_reference,
        regulatory_impact=body.regulatory_impact,
        extra_data=body.extra_data,
    )
    ts = parse_if_unmodified_since(if_unmodified_since)
    try:
        detail = await svc.update_ecn(ecn_id, req, if_unmodified_since=ts)
    except (ECNPreconditionRequired, ECNConflict) as exc:
        raise_optimistic_lock_errors(exc)
    except ECNNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"ECN {ecn_id!r} not found",
        )
    except ECNValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    detail.customer_name = await _resolve_customer_name(erp, detail.customer_number)  # type: ignore[union-attr]
    return detail_out(detail)  # type: ignore[return-value]


@ecn_core_router.patch("/{ecn_id}/status", response_model=ECNDetailOut)
async def transition_ecn_status(
    ecn_id: str,
    body: ECNTransitionBody,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    if_unmodified_since: Annotated[str | None, Header()] = None,
) -> ECNDetailOut:
    """Fire a workflow trigger on an ECN.

    Trigger names match ECNWorkflowMachine methods:
      submit, accept, pass_to_engineering, approve_engineering,
      approve_role, complete_management_review, movex_write_complete,
      close, reject, resubmit, cancel, place_on_hold, resume

    `actor_role` identifies which role the caller is exercising (e.g. 'DC', 'QM').
    Guard conditions are enforced by the state machine — 422 is returned if the
    caller's role or the ECN's current state does not permit the trigger.

    Requires If-Unmodified-Since header (ADR-008):
      428 — header absent
      409 — stale write (ECN modified since client last fetched it)
    """
    svc = ECNService(session)
    req = ECNStatusTransitionRequest(
        trigger=body.trigger,
        actor_role=body.actor_role,
        notes=body.notes,
        rejection_reason=body.rejection_reason,
        hold_reason=body.hold_reason,
        expected_resume_date=body.expected_resume_date,
        role_id=body.role_id,
    )
    ts = parse_if_unmodified_since(if_unmodified_since)
    try:
        detail = await svc.transition(
            ecn_id, req, actor_username=user.username, if_unmodified_since=ts
        )
    except (ECNPreconditionRequired, ECNConflict) as exc:
        raise_optimistic_lock_errors(exc)
    except ECNNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"ECN {ecn_id!r} not found",
        )
    except ECNTransitionError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    return detail_out(detail)  # type: ignore[return-value]


@ecn_core_router.post(
    "/{ecn_id}/role-assignments",
    response_model=RoleAssignmentResultOut,
    status_code=status.HTTP_201_CREATED,
)
async def assign_ecn_role(
    ecn_id: str,
    body: RoleAssignBody,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> RoleAssignmentResultOut:
    """Reassign a role on an ECN (DC authority only).

    Supersedes the existing active assignment for the given role_id and inserts
    a new one. Writes an audit record to ecn_transition_history.
    Returns 403 if actor_role is not 'DC'.
    Returns 404 if the ECN does not exist.
    Returns 422 if role_id is invalid, OR is specified, or ECN is terminal.
    """
    svc = ECNService(session)
    try:
        result: RoleAssignmentResult = await svc.assign_role(
            ecn_id=ecn_id,
            role_id=body.role_id,
            username=body.username,
            actor_username=user.username,
            actor_role=body.actor_role,
            notes=body.notes,
        )
    except ECNForbidden as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    except ECNNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"ECN {ecn_id!r} not found",
        )
    except ECNValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    return RoleAssignmentResultOut(
        ecn_id=result.ecn_id,
        role_assignments=[
            RoleAssignmentOut(
                role_id=ra.role_id,
                username=ra.username,
                is_auto_assigned=ra.is_auto_assigned,
            )
            for ra in result.role_assignments
        ],
        superseded_username=result.superseded_username,
    )


@ecn_core_router.post(
    "/{ecn_id}/resubmit",
    response_model=ECNDetailOut,
    status_code=status.HTTP_200_OK,
)
async def resubmit_ecn(
    ecn_id: str,
    body: ResubmitBody,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ECNDetailOut:
    """Resubmit a REJECTED ECN via restart or proceed path.

    Restart: all approval steps reset; revision incremented; → ENGINEERING_REVIEW.
    Proceed: only rejecting role's step reset; other approvals preserved; → prior stage.
    """
    svc = ECNService(session)
    try:
        detail = await svc.resubmit(
            ecn_id,
            resolution=body.resolution,
            actor_username=user.username,
            actor_role=body.actor_role,
            notes=body.notes,
        )
    except ECNForbidden as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    except ECNNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ECN not found")
    except ECNValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    except ECNTransitionError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    return detail_out(detail)


@ecn_core_router.patch(
    "/{ecn_id}/items/{item_id}/drawing",
    response_model=ECNDetailOut,
)
async def set_drawing_number(
    ecn_id: str,
    item_id: str,
    body: SetDrawingNumberBody,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ECNDetailOut:
    """Set a drawing number on a new item (is_new_item=TRUE).

    DC role only. ECN must be in DC_APPROVED status.
    Returns 422 if ECN is not DC_APPROVED or item is not is_new_item=TRUE.
    Returns 403 if actor_role is not 'DC'.
    Returns 404 if ECN or item not found.
    """
    svc = ECNService(session)
    try:
        detail = await svc.set_drawing_number(
            ecn_id,
            item_id,
            drawing_number=body.drawing_number,
            actor_username=user.username,
            actor_role=body.actor_role,
        )
    except ECNForbidden as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    except ECNNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ECN or item not found")
    except ECNValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    return detail_out(detail)


@ecn_core_router.post(
    "/{ecn_id}/approve",
    response_model=ECNDetailOut,
    status_code=status.HTTP_200_OK,
)
async def approve_role(
    ecn_id: str,
    body: ApproveRoleBody,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ECNDetailOut:
    """Approve one role's step in the MANAGEMENT_REVIEW parallel block.

    Records the actor's approval for their assigned role. If this is the last
    pending step, the ECN automatically advances to DC_APPROVED (25).
    Returns 422 if ECN is not in MANAGEMENT_REVIEW, role is not required, or
    step is already approved. Returns 403 for wrong assignee or self-approval.
    """
    svc = ECNService(session)
    try:
        detail = await svc.approve_role(
            ecn_id,
            actor_username=user.username,
            actor_role=body.actor_role,
            notes=body.notes,
        )
    except ECNForbidden as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    except ECNNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ECN not found")
    except ECNValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    return detail_out(detail)
