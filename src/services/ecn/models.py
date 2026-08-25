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
    customer_number: str | None = None
    customer_ecn_refs: str | None = None
    dmr_url: str | None = None
    is_new_item: bool = False
    routing_changes: bool = False
    operation_changes: bool = False
    new_parts: bool = False
    change_parts: bool = False
    bom_changes: bool = False
    lead_time_changes: bool = False
    change_to_documents: bool = False
    add_mpn: bool = False
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
    customer_ecn_refs: str | None = None
    is_new_item: bool | None = None
    routing_changes: bool | None = None
    operation_changes: bool | None = None
    new_parts: bool | None = None
    change_parts: bool | None = None
    bom_changes: bool | None = None
    lead_time_changes: bool | None = None
    change_to_documents: bool | None = None
    add_mpn: bool | None = None
    wapc_delta_pct: float | None = None
    wapc_threshold_override: bool | None = None
    requires_customer_approval: bool | None = None
    customer_approval_reference: str | None = None
    regulatory_impact: bool | None = None
    dmr_url: str | None = None
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
    # Populated only by list_all_mpns (ECN-wide aggregate view) — None on the
    # per-item paths (_fetch_mpns/_get_mpn), which already scope by item.
    item_number: str | None = None
    line_number: int | None = None


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
    mounting_type: str | None = None
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
    customer_number: str | None = None
    customer_name: str | None = None
    customer_ecn_refs: str | None = None
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
    change_parts: bool
    bom_changes: bool
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
    customer_number: str | None = None
    customer_name: str | None = None
    customer_ecn_refs: str | None = None
    dmr_url: str | None = None
    add_mpn: bool = False
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
    # Populated only by list_all_routing_operations (ECN-wide aggregate view)
    # — None on the per-item path (list_routing_operations), already scoped.
    item_number: str | None = None
    line_number: int | None = None


# ---------------------------------------------------------------------------
# BOM change dataclasses (Slice E, ADR-012 D6/D4)
# ---------------------------------------------------------------------------

VALID_BOM_CHANGE_TYPES = {"ADD", "CHANGE", "DELETE"}


@dataclass
class BOMChangeRequest:
    """One ecn_bom_changes row authored by an engineer.

    CHANGE/DELETE require old_from_date (validated in the service layer, not
    here — see ECNBomChangesMixin.create_bom_change) since it identifies
    which live Movex line (MPDMAT key: CONO+FACI+PRNO+STRT+MSEQ+OPNO+FDAT) is
    being superseded/closed at dc_approve (D6).

    ADR-014 — parent_item_number is only supplied on the ECN-scoped path
    (no item on the ECN, Stargile's BMPRNO model). On the item-scoped path
    it stays None and is resolved from the item row instead.
    """
    change_type: str                    # 'ADD' | 'CHANGE' | 'DELETE'
    component_number: str
    parent_item_number: str | None = None
    quantity: float | None = None
    unit_of_measure: str | None = None
    operation_number: int | None = None
    sequence_number: int | None = None
    from_date: int | None = None
    to_date: int | None = None
    bom_type: str = "M"
    notes: str | None = None
    old_quantity: float | None = None
    old_operation_number: int | None = None
    old_from_date: int | None = None
    old_to_date: int | None = None
    circuit_refs_old: list[str] | None = None
    circuit_refs_new: list[str] | None = None


@dataclass
class BOMChangeResponse:
    """ecn_bom_changes row as returned by the API."""
    id: str
    ecn_id: str
    parent_item_number: str
    change_type: str
    component_number: str
    quantity: float | None
    unit_of_measure: str | None
    operation_number: int | None
    sequence_number: int | None
    from_date: int | None
    to_date: int | None
    bom_type: str
    notes: str | None
    old_quantity: float | None
    old_operation_number: int | None
    old_from_date: int | None
    old_to_date: int | None
    circuit_refs_old: list[str] | None
    circuit_refs_new: list[str] | None
    snapshot_id: str | None
    movex_snapshot_at_review: dict | None
    created_at: datetime
    # ADR-014 — convenience link only, no semantic load. None when the BOM
    # change was authored without a parent item on the ECN (BOM-only ECN).
    ecn_item_id: str | None = None
    # Populated only by an ECN-wide aggregate list, mirroring the routing-op
    # response's item_number/line_number convention — None on the per-item path.
    item_number: str | None = None


# ---------------------------------------------------------------------------
# Error types
# ---------------------------------------------------------------------------

class ECNNotFound(Exception):
    pass


class ECNValidationError(Exception):
    pass


class ECNTransitionError(Exception):
    """Raised when a workflow trigger's guard fails or is otherwise invalid.

    `payload` is optional structured detail attached for callers that need
    more than a message string — introduced by Slice E's BOM concurrency
    gate (ADR-012, dc_approve re-fetch-and-diff), which attaches the BOMDiff
    JSONB so the frontend can render a conflict banner. Existing call sites
    (workflow.py's guard/invalid-transition mapping, resubmit's rejection
    check) construct this with just a message and get payload=None, so this
    is a backward-compatible addition, not a breaking change to the
    exception's existing single-string-arg call sites.
    """
    def __init__(self, message: str, *, payload: dict[str, Any] | None = None) -> None:
        self.payload = payload
        super().__init__(message)


class ECNForbidden(Exception):
    pass


class ECNPreconditionRequired(Exception):
    pass


class ECNConflict(Exception):
    def __init__(self, current_updated_at: datetime) -> None:
        self.current_updated_at = current_updated_at
        super().__init__(str(current_updated_at))
