"""OSKAR — ECN service-layer data classes and error types."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VALID_FACILITIES = {"L", "D"}

VALID_ROLE_IDS = {
    "DC", "OR", "SE", "CE", "EM", "QM", "PM",
    "SC", "FN", "AD", "CA", "RD", "TE", "MQ",
}

# ---------------------------------------------------------------------------
# Input dataclasses
# ---------------------------------------------------------------------------

@dataclass
class ECNCreateRequest:
    title: str
    description: str | None = None
    facility: str = "D"
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


@dataclass
class ECNUpdateRequest:
    title: str | None = None
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


@dataclass
class ECNStatusTransitionRequest:
    trigger: str
    actor_role: str | None = None
    notes: str | None = None
    rejection_reason: str | None = None
    hold_reason: str | None = None
    expected_resume_date: str | None = None
    role_id: str | None = None


# ---------------------------------------------------------------------------
# Output dataclasses
# ---------------------------------------------------------------------------

@dataclass
class RoleAssignment:
    role_id: str
    username: str | None
    is_auto_assigned: bool


@dataclass
class RoleAssignmentResult:
    ecn_id: str
    role_assignments: list[RoleAssignment]
    superseded_username: str | None


@dataclass
class ApprovalStep:
    role_id: str
    username: str | None
    step_status: str
    skipped: bool
    skip_reason: str | None
    completed_at: datetime | None


@dataclass
class ECNMPNDetail:
    """One row from ecn_mpns, including extended fields from migrations 0007 and 0011."""
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


@dataclass
class ECNItemDetail:
    """One row from ecn_items with its MPN list."""
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
    mpns: list[ECNMPNDetail] = field(default_factory=list)


@dataclass
class ECNSummary:
    id: str
    ecn_number: str
    facility: str
    title: str
    status: int
    status_name: str
    originator_username: str
    revision_number: int
    created_at: datetime
    updated_at: datetime
    is_archived: bool
    next_action_users: list[str] = field(default_factory=list)


@dataclass
class ECNDetail:
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
    customer_approved_at: datetime | None
    regulatory_impact: bool
    is_archived: bool
    archived_at: datetime | None
    archived_by: str | None
    created_at: datetime
    updated_at: datetime
    role_assignments: list[RoleAssignment] = field(default_factory=list)
    approval_steps: list[ApprovalStep] = field(default_factory=list)
    extra_data: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Routing operation dataclasses (S2-20)
# ---------------------------------------------------------------------------

VALID_CHANGE_TYPES = {"ADD", "UPDATE", "DELETE"}


@dataclass
class RoutingOperationRequest:
    """One routing operation row authored by an engineer on an ECN item."""
    operation_number: int
    operation_description: str
    work_centre: str
    run_time: float
    change_type: str                    # 'ADD' or 'UPDATE'
    setup_time: float | None = None


@dataclass
class RoutingOperationResponse:
    """Routing operation row as returned by the API."""
    id: str
    ecn_item_id: str
    operation_number: int
    operation_description: str
    work_centre: str
    run_time: float
    setup_time: float | None
    change_type: str
    movex_snapshot: dict | None
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Error types
# ---------------------------------------------------------------------------

class ECNNotFound(Exception):
    pass


class ECNValidationError(Exception):
    pass


class ECNTransitionError(Exception):
    pass


class ECNForbidden(Exception):
    pass


class ECNPreconditionRequired(Exception):
    pass


class ECNConflict(Exception):
    def __init__(self, current_updated_at: datetime) -> None:
        self.current_updated_at = current_updated_at
        super().__init__(str(current_updated_at))
