"""
OSKAR — ECN Pydantic request/response schemas and serialiser helpers.

All BaseModel classes and _*_out() helpers used across ecn_core, ecn_items,
and ecn_routing live here so each handler module stays handler-only.
"""

from __future__ import annotations

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any

from fastapi import HTTPException, status
from pydantic import BaseModel, Field, field_validator

from src.services.ecn import (
    VALID_CHANGE_TYPES,
    VALID_FACILITIES,
    VALID_ROLE_IDS,
    ApprovalStep,
    ECNConflict,
    ECNDetail,
    ECNItemDetail,
    ECNMPNDetail,
    ECNPreconditionRequired,
    ECNSummary,
    RoleAssignment,
    RoutingOperationResponse,
)


# ---------------------------------------------------------------------------
# Shared constants
# ---------------------------------------------------------------------------

_LIFECYCLE_VALUES = {"active", "eol", "nrnd"}
_PACKAGING_VALUES = {"tape_reel", "tray", "tube", "cut_tape"}
_EFFECTIVITY_VALUES = {"DATE", "ECN", "IMMEDIATE"}


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------

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


class SetDrawingNumberBody(BaseModel):
    drawing_number: str = Field(..., min_length=1, max_length=20)
    actor_role: str = Field(..., min_length=2, max_length=2)

    @field_validator("actor_role")
    @classmethod
    def _upper_actor_role(cls, v: str) -> str:
        return v.upper()


class ApproveRoleBody(BaseModel):
    actor_role: str = Field(..., min_length=2, max_length=2)
    notes: str | None = None

    @field_validator("actor_role")
    @classmethod
    def _upper_actor_role(cls, v: str) -> str:
        return v.upper()


class CreateItemBody(BaseModel):
    line_number: int = Field(..., ge=1)
    is_new_item: bool = False
    item_number: str = Field(..., min_length=1, max_length=15)
    item_name: str | None = Field(None, max_length=30)
    description_2: str | None = Field(None, max_length=60)
    drawing_number: str | None = Field(None, max_length=20)
    procurement_group: str | None = Field(None, max_length=3)
    product_group: str | None = Field(None, max_length=5)
    unit_of_measure: str | None = Field(None, max_length=3)
    item_group: str | None = Field(None, max_length=3)
    customer_alias: str | None = Field(None, max_length=30)
    customer_part_number: str | None = Field(None, max_length=50)
    effectivity_type: str = Field(..., description="DATE | ECN | IMMEDIATE")
    effectivity_from: str | None = None

    @field_validator("effectivity_type")
    @classmethod
    def _validate_effectivity(cls, v: str) -> str:
        if v not in _EFFECTIVITY_VALUES:
            raise ValueError(f"effectivity_type must be one of {_EFFECTIVITY_VALUES}")
        return v


class UpdateItemBody(BaseModel):
    item_name: str | None = Field(None, max_length=30)
    description_2: str | None = Field(None, max_length=60)
    drawing_number: str | None = Field(None, max_length=20)
    procurement_group: str | None = Field(None, max_length=3)
    product_group: str | None = Field(None, max_length=5)
    unit_of_measure: str | None = Field(None, max_length=3)
    item_group: str | None = Field(None, max_length=3)
    customer_alias: str | None = Field(None, max_length=30)
    customer_part_number: str | None = Field(None, max_length=50)
    effectivity_type: str | None = None
    effectivity_from: str | None = None
    is_new_item: bool | None = None

    @field_validator("effectivity_type")
    @classmethod
    def _validate_effectivity(cls, v: str | None) -> str | None:
        if v is not None and v not in _EFFECTIVITY_VALUES:
            raise ValueError(f"effectivity_type must be one of {_EFFECTIVITY_VALUES}")
        return v


class CreateMPNBody(BaseModel):
    mpn: str = Field(..., min_length=1, max_length=30)
    manufacturer: str | None = Field(None, max_length=60)
    is_default: bool = False
    msl_level: int | None = Field(None, ge=1, le=6)
    lifecycle: str | None = None
    eol_date: str | None = None
    lead_time_weeks: int | None = Field(None, ge=0)
    packaging_type: str | None = None
    do_not_buy: bool = False
    alt_mpn: str | None = Field(None, max_length=100)
    notes: str | None = None

    @field_validator("lifecycle")
    @classmethod
    def _validate_lifecycle(cls, v: str | None) -> str | None:
        if v is not None and v not in _LIFECYCLE_VALUES:
            raise ValueError(f"lifecycle must be one of {_LIFECYCLE_VALUES}")
        return v

    @field_validator("packaging_type")
    @classmethod
    def _validate_packaging(cls, v: str | None) -> str | None:
        if v is not None and v not in _PACKAGING_VALUES:
            raise ValueError(f"packaging_type must be one of {_PACKAGING_VALUES}")
        return v


class UpdateMPNBody(BaseModel):
    mpn: str | None = Field(None, min_length=1, max_length=30)
    manufacturer: str | None = Field(None, max_length=60)
    is_default: bool | None = None
    msl_level: int | None = Field(None, ge=1, le=6)
    lifecycle: str | None = None
    eol_date: str | None = None
    lead_time_weeks: int | None = Field(None, ge=0)
    packaging_type: str | None = None
    do_not_buy: bool | None = None
    alt_mpn: str | None = Field(None, max_length=100)
    notes: str | None = None

    @field_validator("lifecycle")
    @classmethod
    def _validate_lifecycle(cls, v: str | None) -> str | None:
        if v is not None and v not in _LIFECYCLE_VALUES:
            raise ValueError(f"lifecycle must be one of {_LIFECYCLE_VALUES}")
        return v

    @field_validator("packaging_type")
    @classmethod
    def _validate_packaging(cls, v: str | None) -> str | None:
        if v is not None and v not in _PACKAGING_VALUES:
            raise ValueError(f"packaging_type must be one of {_PACKAGING_VALUES}")
        return v


class RoutingOpBody(BaseModel):
    operation_number: int = Field(..., ge=1)
    operation_description: str = Field(..., min_length=1, max_length=30)
    work_centre: str = Field(..., min_length=1, max_length=8)
    run_time: float = Field(..., ge=0)
    setup_time: float | None = Field(None, ge=0)
    change_type: str

    @field_validator("change_type")
    @classmethod
    def validate_change_type(cls, v: str) -> str:
        if v not in VALID_CHANGE_TYPES:
            raise ValueError(f"change_type must be one of {sorted(VALID_CHANGE_TYPES)}")
        return v


class RoutingOpPatchBody(BaseModel):
    operation_description: str | None = Field(None, min_length=1, max_length=30)
    work_centre: str | None = Field(None, min_length=1, max_length=8)
    run_time: float | None = Field(None, ge=0)
    setup_time: float | None = Field(None, ge=0)
    change_type: str | None = None

    @field_validator("change_type")
    @classmethod
    def validate_change_type(cls, v: str | None) -> str | None:
        if v is not None and v not in VALID_CHANGE_TYPES:
            raise ValueError(f"change_type must be one of {sorted(VALID_CHANGE_TYPES)}")
        return v


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------

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


class RoleAssignmentResultOut(BaseModel):
    ecn_id: str
    role_assignments: list[RoleAssignmentOut]
    superseded_username: str | None


class MPNOut(BaseModel):
    id: str
    ecn_item_id: str
    mpn: str
    manufacturer: str | None
    is_default: bool
    alias_written: bool
    msl_level: int | None
    lifecycle: str | None
    eol_date: str | None
    lead_time_weeks: int | None
    packaging_type: str | None
    do_not_buy: bool
    alt_mpn: str | None
    notes: str | None
    supplier_data_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ECNItemOut(BaseModel):
    id: str
    ecn_id: str
    line_number: int
    is_new_item: bool
    item_number: str
    item_name: str | None
    description_2: str | None
    drawing_number: str | None
    drawing_created: bool
    procurement_group: str | None
    product_group: str | None
    unit_of_measure: str | None
    item_group: str | None
    customer_alias: str | None
    customer_part_number: str | None
    effectivity_type: str
    effectivity_from: str | None
    created_at: datetime
    updated_at: datetime
    mpns: list[MPNOut] = []

    model_config = {"from_attributes": True}


class RoutingOpOut(BaseModel):
    id: str
    ecn_item_id: str
    operation_number: int
    operation_description: str
    work_centre: str
    run_time: float
    setup_time: float | None
    change_type: str
    movex_snapshot: dict[str, Any] | None
    created_at: str
    updated_at: str


# ---------------------------------------------------------------------------
# Serialiser helpers
# ---------------------------------------------------------------------------

def _ts(dt: Any) -> str | None:
    if dt is None:
        return None
    return dt.isoformat() if hasattr(dt, "isoformat") else str(dt)


def _role_assignment_out(ra: RoleAssignment) -> RoleAssignmentOut:
    return RoleAssignmentOut(
        role_id=ra.role_id,
        username=ra.username,
        is_auto_assigned=ra.is_auto_assigned,
    )


def _approval_step_out(ap: ApprovalStep) -> ApprovalStepOut:
    return ApprovalStepOut(
        role_id=ap.role_id,
        username=ap.username,
        status=ap.step_status,
        skipped=ap.skipped,
        skip_reason=ap.skip_reason,
        completed_at=_ts(ap.completed_at),
    )


def detail_out(d: ECNDetail) -> ECNDetailOut:
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
        role_assignments=[_role_assignment_out(ra) for ra in d.role_assignments],
        approval_steps=[_approval_step_out(ap) for ap in d.approval_steps],
        extra_data=d.extra_data,
    )


def summary_out(s: ECNSummary) -> ECNSummaryOut:
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


def mpn_out(m: ECNMPNDetail) -> MPNOut:
    return MPNOut(
        id=m.id,
        ecn_item_id=m.ecn_item_id,
        mpn=m.mpn,
        manufacturer=m.manufacturer,
        is_default=m.is_default,
        alias_written=m.alias_written,
        msl_level=m.msl_level,
        lifecycle=m.lifecycle,
        eol_date=m.eol_date,
        lead_time_weeks=m.lead_time_weeks,
        packaging_type=m.packaging_type,
        do_not_buy=m.do_not_buy,
        alt_mpn=m.alt_mpn,
        notes=m.notes,
        supplier_data_at=m.supplier_data_at,
        created_at=m.created_at,
    )


def item_out(i: ECNItemDetail) -> ECNItemOut:
    return ECNItemOut(
        id=i.id,
        ecn_id=i.ecn_id,
        line_number=i.line_number,
        is_new_item=i.is_new_item,
        item_number=i.item_number,
        item_name=i.item_name,
        description_2=i.description_2,
        drawing_number=i.drawing_number,
        drawing_created=i.drawing_created,
        procurement_group=i.procurement_group,
        product_group=i.product_group,
        unit_of_measure=i.unit_of_measure,
        item_group=i.item_group,
        customer_alias=i.customer_alias,
        customer_part_number=i.customer_part_number,
        effectivity_type=i.effectivity_type,
        effectivity_from=i.effectivity_from,
        created_at=i.created_at,
        updated_at=i.updated_at,
        mpns=[mpn_out(m) for m in i.mpns],
    )


def routing_op_out(op: RoutingOperationResponse) -> RoutingOpOut:
    return RoutingOpOut(
        id=op.id,
        ecn_item_id=op.ecn_item_id,
        operation_number=op.operation_number,
        operation_description=op.operation_description,
        work_centre=op.work_centre,
        run_time=op.run_time,
        setup_time=op.setup_time,
        change_type=op.change_type,
        movex_snapshot=op.movex_snapshot,
        created_at=op.created_at.isoformat(),
        updated_at=op.updated_at.isoformat(),
    )


# ---------------------------------------------------------------------------
# Shared HTTP helpers
# ---------------------------------------------------------------------------

def parse_if_unmodified_since(header: str | None) -> datetime | None:
    """Parse RFC 7231 If-Unmodified-Since header to UTC datetime, or None."""
    if header is None:
        return None
    try:
        dt = parsedate_to_datetime(header)
        return dt.astimezone(timezone.utc).replace(tzinfo=timezone.utc)
    except Exception:
        return None


def raise_optimistic_lock_errors(exc: ECNConflict | ECNPreconditionRequired) -> None:
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
