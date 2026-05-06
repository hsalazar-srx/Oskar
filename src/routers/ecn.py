"""
Oskar — ECN endpoints (S1-13 through S1-16)

POST   /api/v1/ecn/                — Create ECN (OSKAR-Engineers)
GET    /api/v1/ecn/                — List ECNs with G-2/G-3 filters (OSKAR-Engineers)
GET    /api/v1/ecn/{ecn_id}        — Get ECN detail (OSKAR-Engineers)
PATCH  /api/v1/ecn/{ecn_id}/status — Trigger a workflow transition (OSKAR-Engineers)

All endpoints require a valid JWT (OSKAR-Engineers group minimum).
Role-level guards (e.g. only DC may accept) are enforced by ECNWorkflowMachine,
not by a second group gate here. actor_role in the request body tells the machine
which role the caller is exercising.

Sources:
  src/services/ecn.py     — ECNService, request/response dataclasses, error types
  src/workflow/machine.py — ECNStatus, trigger names
  ai/tasks/sprint-backlog.md G-2/G-3 — list filters + next_action_users
"""

from __future__ import annotations

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import CurrentUser, get_current_user
from src.db import get_session
from src.services.ecn import (
    ECNConflict,
    ECNCreateRequest,
    ECNDetail,
    ECNForbidden,
    ECNNotFound,
    ECNPreconditionRequired,
    ECNService,
    ECNStatusTransitionRequest,
    ECNSummary,
    ECNTransitionError,
    ECNUpdateRequest,
    ECNValidationError,
    RoleAssignmentResult,
    VALID_FACILITIES,
    VALID_ROLE_IDS,
)

log = structlog.get_logger(__name__)

ecn_router = APIRouter(prefix="/ecn", tags=["ecn"])


# ── Request / response schemas ────────────────────────────────────────────────


class ECNCreateBody(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: str | None = None
    facility: str = Field("L", max_length=10)

    is_new_item: bool = False
    routing_changes: bool = False
    operation_changes: bool = False
    new_parts: bool = False
    lead_time_changes: bool = False
    change_to_documents: bool = False

    wapc_delta_pct: float | None = None
    wapc_threshold_override: bool = False

    requires_customer_approval: bool = False
    customer_approval_reference: str | None = None
    regulatory_impact: bool = False

    extra_data: dict[str, Any] | None = None

    @field_validator("facility")
    @classmethod
    def validate_facility(cls, v: str) -> str:
        upper = v.upper()
        if upper not in VALID_FACILITIES:
            raise ValueError(f"Unknown facility '{v}'. Valid: {sorted(VALID_FACILITIES)}")
        return upper


class ECNUpdateBody(BaseModel):
    """Body for PATCH /api/v1/ecn/{id} — field edits (ADR-008)."""
    title: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = None
    is_new_item: bool | None = None
    routing_changes: bool | None = None
    operation_changes: bool | None = None
    new_parts: bool | None = None
    lead_time_changes: bool | None = None
    change_to_documents: bool | None = None
    wapc_delta_pct: float | None = None
    wapc_threshold_override: bool | None = None
    requires_customer_approval: bool | None = None
    customer_approval_reference: str | None = None
    regulatory_impact: bool | None = None
    extra_data: dict[str, Any] | None = None


class ECNTransitionBody(BaseModel):
    trigger: str = Field(..., description="Workflow trigger name (e.g. 'submit', 'accept')")
    actor_role: str | None = Field(None, max_length=2)
    notes: str | None = None
    rejection_reason: str | None = None
    hold_reason: str | None = None
    expected_resume_date: str | None = Field(
        None, description="ISO date string YYYY-MM-DD; required for place_on_hold"
    )
    role_id: str | None = Field(None, max_length=2, description="For approve_role trigger")


class RoleAssignmentOut(BaseModel):
    role_id: str
    username: str | None
    is_auto_assigned: bool


class ApprovalStepOut(BaseModel):
    role_id: str
    username: str | None
    status: str
    skipped: bool
    skip_reason: str | None
    completed_at: str | None


class ECNDetailOut(BaseModel):
    id: str
    ecn_number: str
    facility: str
    title: str
    description: str | None
    status: int
    status_name: str
    originator_username: str
    revision_number: int
    is_new_item: bool
    routing_changes: bool
    operation_changes: bool
    new_parts: bool
    lead_time_changes: bool
    change_to_documents: bool
    wapc_delta_pct: float | None
    wapc_threshold_override: bool
    requires_customer_approval: bool
    customer_approval_reference: str | None
    customer_approved_at: str | None
    regulatory_impact: bool
    is_archived: bool
    archived_at: str | None
    archived_by: str | None
    created_at: str
    updated_at: str
    role_assignments: list[RoleAssignmentOut]
    approval_steps: list[ApprovalStepOut]
    extra_data: dict[str, Any] | None


class ECNSummaryOut(BaseModel):
    id: str
    ecn_number: str
    facility: str
    title: str
    status: int
    status_name: str
    originator_username: str
    revision_number: int
    created_at: str
    updated_at: str
    is_archived: bool
    next_action_users: list[str]


# ── Serialisation helpers ─────────────────────────────────────────────────────


def _ts(dt: Any) -> str | None:
    if dt is None:
        return None
    return dt.isoformat() if hasattr(dt, "isoformat") else str(dt)


def _detail_out(d: ECNDetail) -> ECNDetailOut:
    return ECNDetailOut(
        id=d.id,
        ecn_number=d.ecn_number,
        facility=d.facility,
        title=d.title,
        description=d.description,
        status=d.status,
        status_name=d.status_name,
        originator_username=d.originator_username,
        revision_number=d.revision_number,
        is_new_item=d.is_new_item,
        routing_changes=d.routing_changes,
        operation_changes=d.operation_changes,
        new_parts=d.new_parts,
        lead_time_changes=d.lead_time_changes,
        change_to_documents=d.change_to_documents,
        wapc_delta_pct=d.wapc_delta_pct,
        wapc_threshold_override=d.wapc_threshold_override,
        requires_customer_approval=d.requires_customer_approval,
        customer_approval_reference=d.customer_approval_reference,
        customer_approved_at=_ts(d.customer_approved_at),
        regulatory_impact=d.regulatory_impact,
        is_archived=d.is_archived,
        archived_at=_ts(d.archived_at),
        archived_by=d.archived_by,
        created_at=_ts(d.created_at),
        updated_at=_ts(d.updated_at),
        role_assignments=[
            RoleAssignmentOut(
                role_id=ra.role_id,
                username=ra.username,
                is_auto_assigned=ra.is_auto_assigned,
            )
            for ra in d.role_assignments
        ],
        approval_steps=[
            ApprovalStepOut(
                role_id=ap.role_id,
                username=ap.username,
                status=ap.step_status,
                skipped=ap.skipped,
                skip_reason=ap.skip_reason,
                completed_at=_ts(ap.completed_at),
            )
            for ap in d.approval_steps
        ],
        extra_data=d.extra_data,
    )


def _summary_out(s: ECNSummary) -> ECNSummaryOut:
    return ECNSummaryOut(
        id=s.id,
        ecn_number=s.ecn_number,
        facility=s.facility,
        title=s.title,
        status=s.status,
        status_name=s.status_name,
        originator_username=s.originator_username,
        revision_number=s.revision_number,
        created_at=_ts(s.created_at),
        updated_at=_ts(s.updated_at),
        is_archived=s.is_archived,
        next_action_users=s.next_action_users,
    )


# ── Helpers ───────────────────────────────────────────────────────────────────


def _parse_if_unmodified_since(header: str | None) -> datetime | None:
    """Parse RFC 7231 If-Unmodified-Since header to UTC datetime, or None."""
    if header is None:
        return None
    try:
        dt = parsedate_to_datetime(header)
        return dt.astimezone(timezone.utc).replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _raise_optimistic_lock_errors(exc: ECNConflict | ECNPreconditionRequired) -> None:
    if isinstance(exc, ECNPreconditionRequired):
        raise HTTPException(
            status_code=status.HTTP_428_PRECONDITION_REQUIRED,
            detail="If-Unmodified-Since header is required for this operation.",
        )
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "code": "ECN_MODIFIED",
            "message": "This ECN was modified by another user. Reload and reapply your changes.",
            "current_updated_at": exc.current_updated_at.isoformat(),
        },
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────


@ecn_router.post("/", response_model=ECNDetailOut, status_code=status.HTTP_201_CREATED)
async def create_ecn(
    body: ECNCreateBody,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
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

    return _detail_out(detail)


@ecn_router.get("/", response_model=list[ECNSummaryOut])
async def list_ecns(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    facility: Annotated[str | None, Query(description="Filter by facility code")] = None,
    status_filter: Annotated[
        int | None, Query(alias="status", description="Filter by ECNStatus integer")
    ] = None,
    assignee: Annotated[
        str | None, Query(description="Filter ECNs where this username has an active role")
    ] = None,
    overdue: Annotated[bool | None, Query(description="Only ECNs open longer than 30 days")] = None,
    age_days: Annotated[int | None, Query(description="Only ECNs older than N days")] = None,
    include_archived: Annotated[bool, Query()] = False,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[ECNSummaryOut]:
    """List ECNs with optional filters.

    Each result includes `next_action_users[]` — the usernames who must act
    next to advance the ECN (G-2, replaces DBCHK_OpenECN SQL Server Agent job).
    """
    svc = ECNService(session)
    summaries = await svc.list_ecns(
        facility=facility,
        status=status_filter,
        assignee=assignee,
        overdue=overdue,
        age_days=age_days,
        include_archived=include_archived,
        limit=limit,
        offset=offset,
    )
    return [_summary_out(s) for s in summaries]


@ecn_router.get("/{ecn_id}", response_model=ECNDetailOut)
async def get_ecn(
    ecn_id: str,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
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
    response.headers["Last-Modified"] = detail.updated_at.strftime(
        "%a, %d %b %Y %H:%M:%S GMT"
    )
    return _detail_out(detail)


@ecn_router.patch("/{ecn_id}", response_model=ECNDetailOut)
async def update_ecn(
    ecn_id: str,
    body: ECNUpdateBody,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
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
    ts = _parse_if_unmodified_since(if_unmodified_since)
    try:
        detail = await svc.update_ecn(ecn_id, req, if_unmodified_since=ts)
    except (ECNPreconditionRequired, ECNConflict) as exc:
        _raise_optimistic_lock_errors(exc)
    except ECNNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"ECN {ecn_id!r} not found",
        )
    except ECNValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )
    return _detail_out(detail)  # type: ignore[return-value]


class RoleAssignBody(BaseModel):
    role_id: str = Field(..., min_length=2, max_length=2)
    username: str = Field(..., min_length=1, max_length=50)
    actor_role: str = Field(..., min_length=2, max_length=2)
    notes: str | None = None

    @field_validator("role_id")
    @classmethod
    def validate_role_id(cls, v: str) -> str:
        upper = v.upper()
        if upper not in VALID_ROLE_IDS:
            raise ValueError(f"Unknown role_id '{v}'. Valid: {sorted(VALID_ROLE_IDS)}")
        return upper

    @field_validator("actor_role")
    @classmethod
    def validate_actor_role(cls, v: str) -> str:
        return v.upper()


class RoleAssignmentResultOut(BaseModel):
    ecn_id: str
    role_assignments: list[RoleAssignmentOut]
    superseded_username: str | None


@ecn_router.patch("/{ecn_id}/status", response_model=ECNDetailOut)
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
    ts = _parse_if_unmodified_since(if_unmodified_since)
    try:
        detail = await svc.transition(
            ecn_id, req, actor_username=user.username, if_unmodified_since=ts
        )
    except (ECNPreconditionRequired, ECNConflict) as exc:
        _raise_optimistic_lock_errors(exc)
    except ECNNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"ECN {ecn_id!r} not found",
        )
    except ECNTransitionError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )
    return _detail_out(detail)  # type: ignore[return-value]


@ecn_router.post(
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
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )
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


# ── Resubmit (rejection flows) ───────────────────────────────────────────────

class ResubmitBody(BaseModel):
    resolution: str = Field(..., description="'restart' or 'proceed'")
    actor_role: str = Field(..., min_length=2, max_length=2)
    notes: str | None = None

    @field_validator("resolution")
    @classmethod
    def _validate_resolution(cls, v: str) -> str:
        if v not in ("restart", "proceed"):
            raise ValueError("resolution must be 'restart' or 'proceed'")
        return v

    @field_validator("actor_role")
    @classmethod
    def _upper_actor_role(cls, v: str) -> str:
        return v.upper()


@ecn_router.post(
    "/{ecn_id}/resubmit",
    response_model=ECNDetailOut,
    status_code=status.HTTP_200_OK,
)
async def resubmit_ecn(
    ecn_id: str,
    body: ResubmitBody,
    user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
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
    return _detail_out(detail)


# ── Drawing number ────────────────────────────────────────────────────────────

class SetDrawingNumberBody(BaseModel):
    drawing_number: str = Field(..., min_length=1, max_length=20)
    actor_role: str = Field(..., min_length=2, max_length=2)

    @field_validator("actor_role")
    @classmethod
    def _upper_actor_role(cls, v: str) -> str:
        return v.upper()


@ecn_router.patch(
    "/{ecn_id}/items/{item_id}/drawing",
    response_model=ECNDetailOut,
)
async def set_drawing_number(
    ecn_id: str,
    item_id: str,
    body: SetDrawingNumberBody,
    user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
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
    return _detail_out(detail)
