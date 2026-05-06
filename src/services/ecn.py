"""
OSKAR — ECN Service layer (S1-13 through S1-16)

Thin service between the FastAPI router and the database + ECNWorkflowMachine.
All DB writes happen inside the caller's transaction (get_session commits on success).

Responsibilities:
- ECN number generation (ECN-YYYY-{facility}-{seq})
- Auto-assign roles from system_role_users on create
- Build approval steps on stage entry
- Persist transition history with SHA-256 chain
- G-2/G-3: next_action_users[] computation and list filters

Does NOT:
- Send notifications (Sprint 2 / Celery)
- Execute Movex MI calls (Sprint 2 / Celery)
- Touch movex_outbox (Sprint 2)

Sources:
  ai/memory/12-data-model.md  — table schemas, role_id CHECK constraints
  ai/memory/06-ecn-requirements.md §1–3 — status transitions, parallel block
  ai/tasks/sprint-backlog.md G-2/G-3 — list filters + next_action_users
"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import sqlalchemy as sa
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from src.workflow.machine import (
    ECNModel,
    ECNStatus,
    ECNWorkflowMachine,
    GuardFailed,
    InvalidTransition,
    TransitionContext,
)

log = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Known facility codes — validated at application layer (Phase 2 adds DB table)
# ---------------------------------------------------------------------------
VALID_FACILITIES = {"L", "D"}

# Roles recognised by the role_id CHECK constraint on ecn_role_assignments
VALID_ROLE_IDS = {
    "DC", "OR", "SE", "CE", "EM", "QM", "PM",
    "SC", "FN", "AD", "CA", "RD", "TE", "MQ",
}


# ---------------------------------------------------------------------------
# Input / output data classes
# ---------------------------------------------------------------------------

@dataclass
class ECNCreateRequest:
    """Input for POST /api/v1/ecn/"""
    title: str
    description: str | None = None
    facility: str = "L"

    # Change scope flags
    is_new_item: bool = False
    routing_changes: bool = False
    operation_changes: bool = False
    new_parts: bool = False
    lead_time_changes: bool = False
    change_to_documents: bool = False

    # Cost
    wapc_delta_pct: float | None = None
    wapc_threshold_override: bool = False

    # Customer / regulatory
    requires_customer_approval: bool = False
    customer_approval_reference: str | None = None
    regulatory_impact: bool = False

    # Extra (POC safety valve)
    extra_data: dict[str, Any] | None = None


@dataclass
class ECNStatusTransitionRequest:
    """Input for PATCH /api/v1/ecn/{id}/status"""
    trigger: str                          # Machine trigger name (e.g. 'submit', 'accept')
    actor_role: str | None = None         # Role ID the actor is acting as
    notes: str | None = None
    rejection_reason: str | None = None
    hold_reason: str | None = None
    expected_resume_date: str | None = None  # ISO date string
    role_id: str | None = None            # For approve_role trigger


@dataclass
class RoleAssignment:
    role_id: str
    username: str | None
    is_auto_assigned: bool


@dataclass
class RoleAssignmentResult:
    """Returned by ECNService.assign_role()"""
    ecn_id: str
    role_assignments: list[RoleAssignment]
    superseded_username: str | None  # Previous holder of this role, if any


@dataclass
class ECNMPNDetail:
    """One MPN row from ecn_mpns, including extended fields added in migration 0007."""
    id: str
    ecn_item_id: str
    mpn: str
    manufacturer: str | None
    is_default: bool
    alias_written: bool
    # Extended fields (migration 0007 — Engineering Team 2026-04-29)
    msl_level: int | None
    lifecycle: str | None          # 'active' | 'eol' | 'nrnd'
    eol_date: str | None           # ISO date string YYYY-MM-DD
    lead_time_weeks: int | None
    packaging_type: str | None     # 'tape_reel' | 'tray' | 'tube' | 'cut_tape'
    do_not_buy: bool
    alt_mpn: str | None
    supplier_data_at: datetime | None
    created_at: datetime


@dataclass
class ECNItemDetail:
    """One item row from ecn_items with its MPN list."""
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
    effectivity_type: str
    effectivity_from: str | None   # ISO date string
    created_at: datetime
    updated_at: datetime
    mpns: list[ECNMPNDetail] = field(default_factory=list)


@dataclass
class ApprovalStep:
    role_id: str
    username: str | None
    step_status: str        # 'pending' | 'approved' | 'rejected' | 'skipped' | 'superseded'
    skipped: bool
    skip_reason: str | None
    completed_at: datetime | None


@dataclass
class ECNSummary:
    """Returned by GET /api/v1/ecn/ list"""
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
    """Returned by GET /api/v1/ecn/{id}"""
    id: str
    ecn_number: str
    facility: str
    title: str
    description: str | None
    status: int
    status_name: str
    originator_username: str
    revision_number: int

    # Change scope
    is_new_item: bool
    routing_changes: bool
    operation_changes: bool
    new_parts: bool
    lead_time_changes: bool
    change_to_documents: bool

    # Cost
    wapc_delta_pct: float | None
    wapc_threshold_override: bool

    # Customer / regulatory
    requires_customer_approval: bool
    customer_approval_reference: str | None
    customer_approved_at: datetime | None
    regulatory_impact: bool

    # Lifecycle
    is_archived: bool
    archived_at: datetime | None
    archived_by: str | None
    created_at: datetime
    updated_at: datetime

    # Related
    role_assignments: list[RoleAssignment] = field(default_factory=list)
    approval_steps: list[ApprovalStep] = field(default_factory=list)
    extra_data: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class ECNNotFound(Exception):
    pass


class ECNValidationError(Exception):
    pass


class ECNTransitionError(Exception):
    """Wraps GuardFailed / InvalidTransition for the router layer."""


class ECNForbidden(Exception):
    """Actor lacks authority for the requested operation (e.g. non-DC calling assign_role)."""


class ECNPreconditionRequired(Exception):
    """If-Unmodified-Since header absent on a mutating request (ADR-008)."""


class ECNConflict(Exception):
    """Stale write detected — current_updated_at carries the latest timestamp (ADR-008)."""

    def __init__(self, current_updated_at: datetime) -> None:
        self.current_updated_at = current_updated_at
        super().__init__(str(current_updated_at))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ecn_number(facility: str, seq: int, year: int | None = None) -> str:
    """Format: ECN-YYYY-{facility}-{seq:04d}"""
    y = year or datetime.now(timezone.utc).year
    return f"ECN-{y}-{facility}-{seq:04d}"


async def _next_ecn_seq(session: AsyncSession, facility: str, year: int) -> int:
    """Count existing ECNs for this facility+year and return next sequence number."""
    prefix = f"ECN-{year}-{facility}-%"
    row = await session.execute(
        sa.text(
            "SELECT COUNT(*) FROM ecn_instances "
            "WHERE ecn_number LIKE :prefix"
        ),
        {"prefix": prefix},
    )
    count = row.scalar_one()
    return int(count) + 1


async def _get_last_transition_hash(session: AsyncSession, ecn_id: str) -> str | None:
    """Return the sha256_self of the most recent transition for this ECN."""
    row = await session.execute(
        sa.text(
            "SELECT sha256_self FROM ecn_transition_history "
            "WHERE ecn_id = :ecn_id ORDER BY created_at DESC LIMIT 1"
        ),
        {"ecn_id": ecn_id},
    )
    result = row.first()
    return result[0] if result else None


async def _write_transition_history(
    session: AsyncSession,
    machine: ECNWorkflowMachine,
    ecn_id: str,
    from_status: int | None,
    to_status: int,
    action: str,
) -> None:
    """Compute SHA-256 and INSERT one transition history row."""
    record_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc)
    sha256_self = machine.compute_transition_hash(
        record_id=record_id,
        from_status=from_status,
        to_status=to_status,
        action=action,
        created_at=created_at,
    )
    await session.execute(
        sa.text(
            "INSERT INTO ecn_transition_history "
            "(id, ecn_id, from_status, to_status, action, "
            " actor_username, actor_role, notes, movex_payload, "
            " agent_provenance, sha256_self, sha256_prev, created_at) "
            "VALUES (:id, :ecn_id, :from_status, :to_status, :action, "
            "        :actor_username, :actor_role, :notes, :movex_payload::jsonb, "
            "        :agent_provenance::jsonb, :sha256_self, :sha256_prev, :created_at)"
        ),
        {
            "id": record_id,
            "ecn_id": ecn_id,
            "from_status": from_status,
            "to_status": to_status,
            "action": action,
            "actor_username": machine.ctx.actor_username,
            "actor_role": machine.ctx.actor_role,
            "notes": machine.ctx.notes,
            "movex_payload": None,   # Sprint 2
            "agent_provenance": None,
            "sha256_self": sha256_self,
            "sha256_prev": machine._sha256_prev,
            "created_at": created_at,
        },
    )


async def _auto_assign_roles(
    session: AsyncSession,
    ecn_id: str,
    facility: str,
    originator_username: str,
    assigned_by: str,
) -> None:
    """Auto-assign system roles to this ECN from system_role_users.

    Per data model §8.1:
    - 0 active users for a required role → ECN creation fails
    - 1 active user  → auto-assign (is_auto_assigned=TRUE)
    - >1 active users → create unassigned row (username=NULL); DC assigns manually

    For Sprint 1, only DC is a required role (cannot proceed without DC).
    OR (originator) is always auto-assigned to the ECN creator.
    All other roles are opportunistically assigned if exactly 1 user exists.
    """
    # Always assign OR = originator
    await session.execute(
        sa.text(
            "INSERT INTO ecn_role_assignments "
            "(id, ecn_id, facility, role_id, username, is_auto_assigned, assigned_by) "
            "VALUES (:id, :ecn_id, :facility, 'OR', :username, TRUE, :assigned_by)"
        ),
        {
            "id": str(uuid.uuid4()),
            "ecn_id": ecn_id,
            "facility": facility,
            "username": originator_username,
            "assigned_by": "system",
        },
    )

    # Auto-assign all roles from system_role_users for this facility
    rows = await session.execute(
        sa.text(
            "SELECT role_id, username FROM system_role_users "
            "WHERE facility = :facility AND is_active = TRUE AND removed_at IS NULL"
        ),
        {"facility": facility},
    )
    role_users: dict[str, list[str]] = {}
    for role_id, username in rows:
        role_users.setdefault(role_id, []).append(username)

    # DC is required — fail if none configured
    if not role_users.get("DC"):
        raise ECNValidationError(
            f"No active Document Controller (DC) configured for facility '{facility}'. "
            "Add a DC to system_role_users before creating ECNs."
        )

    for role_id, users in role_users.items():
        if role_id == "OR":
            continue  # OR already handled
        if len(users) == 1:
            username = users[0]
            is_auto = True
        else:
            username = None   # type: ignore[assignment]
            is_auto = False

        await session.execute(
            sa.text(
                "INSERT INTO ecn_role_assignments "
                "(id, ecn_id, facility, role_id, username, is_auto_assigned, assigned_by) "
                "VALUES (:id, :ecn_id, :facility, :role_id, :username, :is_auto, :assigned_by) "
                "ON CONFLICT DO NOTHING"
            ),
            {
                "id": str(uuid.uuid4()),
                "ecn_id": ecn_id,
                "facility": facility,
                "role_id": role_id,
                "username": username,
                "is_auto": is_auto,
                "assigned_by": assigned_by,
            },
        )


async def _load_ecn_row(session: AsyncSession, ecn_id: str) -> dict[str, Any] | None:
    """Load a single ecn_instances row as a dict. Returns None if not found."""
    row = await session.execute(
        sa.text("SELECT * FROM ecn_instances WHERE id = :id"),
        {"id": ecn_id},
    )
    result = row.mappings().first()
    return dict(result) if result else None


def _row_to_ecn_model(row: dict[str, Any]) -> ECNModel:
    """Hydrate an ECNModel from a DB row dict."""
    return ECNModel(
        id=str(row["id"]),
        ecn_number=row["ecn_number"],
        facility=row["facility"],
        status=int(row["status"]),
        pre_hold_status=int(row["pre_hold_status"]) if row["pre_hold_status"] is not None else None,
        originator_username=row["originator_username"],
        revision_number=int(row["revision_number"]),
        title=row["title"] or "",
        is_new_item=bool(row["is_new_item"]),
        routing_changes=bool(row["routing_changes"]),
        operation_changes=bool(row["operation_changes"]),
        new_parts=bool(row["new_parts"]),
        lead_time_changes=bool(row["lead_time_changes"]),
        change_to_documents=bool(row["change_to_documents"]),
        wapc_delta_pct=float(row["wapc_delta_pct"]) if row["wapc_delta_pct"] is not None else None,
        wapc_threshold_override=bool(row["wapc_threshold_override"]),
        requires_customer_approval=bool(row["requires_customer_approval"]),
        customer_approved_at=row.get("customer_approved_at"),
        regulatory_impact=bool(row["regulatory_impact"]),
        item_count=0,  # populated below when needed for submit guard
    )


async def _count_ecn_items(session: AsyncSession, ecn_id: str) -> int:
    row = await session.execute(
        sa.text("SELECT COUNT(*) FROM ecn_items WHERE ecn_id = :ecn_id"),
        {"ecn_id": ecn_id},
    )
    return int(row.scalar_one())


async def _get_role_assignments(
    session: AsyncSession, ecn_id: str
) -> list[RoleAssignment]:
    rows = await session.execute(
        sa.text(
            "SELECT role_id, username, is_auto_assigned FROM ecn_role_assignments "
            "WHERE ecn_id = :ecn_id AND superseded_at IS NULL "
            "ORDER BY role_id"
        ),
        {"ecn_id": ecn_id},
    )
    return [
        RoleAssignment(
            role_id=r["role_id"],
            username=r["username"],
            is_auto_assigned=bool(r["is_auto_assigned"]),
        )
        for r in rows.mappings()
    ]


async def _get_approval_steps(
    session: AsyncSession, ecn_id: str
) -> list[ApprovalStep]:
    rows = await session.execute(
        sa.text(
            "SELECT role_id, username, status, skipped, skip_reason, completed_at "
            "FROM ecn_approval_steps "
            "WHERE ecn_id = :ecn_id ORDER BY at_status, role_id"
        ),
        {"ecn_id": ecn_id},
    )
    return [
        ApprovalStep(
            role_id=r["role_id"],
            username=r["username"],
            step_status=r["status"],
            skipped=bool(r["skipped"]),
            skip_reason=r["skip_reason"],
            completed_at=r["completed_at"],
        )
        for r in rows.mappings()
    ]


def _row_to_detail(
    row: dict[str, Any],
    role_assignments: list[RoleAssignment],
    approval_steps: list[ApprovalStep],
) -> ECNDetail:
    status_int = int(row["status"])
    return ECNDetail(
        id=str(row["id"]),
        ecn_number=row["ecn_number"],
        facility=row["facility"],
        title=row["title"],
        description=row.get("description"),
        status=status_int,
        status_name=ECNStatus(status_int).name,
        originator_username=row["originator_username"],
        revision_number=int(row["revision_number"]),
        is_new_item=bool(row["is_new_item"]),
        routing_changes=bool(row["routing_changes"]),
        operation_changes=bool(row["operation_changes"]),
        new_parts=bool(row["new_parts"]),
        lead_time_changes=bool(row["lead_time_changes"]),
        change_to_documents=bool(row["change_to_documents"]),
        wapc_delta_pct=float(row["wapc_delta_pct"]) if row["wapc_delta_pct"] is not None else None,
        wapc_threshold_override=bool(row["wapc_threshold_override"]),
        requires_customer_approval=bool(row["requires_customer_approval"]),
        customer_approval_reference=row.get("customer_approval_reference"),
        customer_approved_at=row.get("customer_approved_at"),
        regulatory_impact=bool(row["regulatory_impact"]),
        is_archived=bool(row["is_archived"]),
        archived_at=row.get("archived_at"),
        archived_by=row.get("archived_by"),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        role_assignments=role_assignments,
        approval_steps=approval_steps,
        extra_data=row.get("extra_data"),
    )


# ---------------------------------------------------------------------------
# next_action_users — G-2
# ---------------------------------------------------------------------------

async def _compute_next_action_users(
    session: AsyncSession,
    ecn_id: str,
    status: int,
) -> list[str]:
    """Return usernames who must act next on this ECN.

    Rules per status:
      DRAFT (0)               → originator (must submit or cancel)
      SUBMITTED (10)          → DC (must accept or reject)
      DC_REVIEW (20)          → DC (must pass_to_engineering or reject)
      ENGINEERING_REVIEW (30) → SE/CE assigned to this ECN
      MANAGEMENT_REVIEW (40)  → all active pending step assignees
      APPROVED (50)           → [] (system / Celery acts next)
      IMPLEMENTED (60)        → DC (must close)
      REJECTED (65)           → originator (must resubmit or cancel)
      ON_HOLD (90)            → DC (must resume)
      CLOSED/CANCELLED        → []
    """
    if status in (ECNStatus.CLOSED, ECNStatus.CANCELLED):
        return []

    if status == ECNStatus.DRAFT:
        row = await session.execute(
            sa.text("SELECT originator_username FROM ecn_instances WHERE id = :id"),
            {"id": ecn_id},
        )
        r = row.first()
        return [r[0]] if r else []

    if status == ECNStatus.REJECTED:
        row = await session.execute(
            sa.text("SELECT originator_username FROM ecn_instances WHERE id = :id"),
            {"id": ecn_id},
        )
        r = row.first()
        return [r[0]] if r else []

    if status in (ECNStatus.SUBMITTED, ECNStatus.DC_REVIEW, ECNStatus.IMPLEMENTED, ECNStatus.ON_HOLD):
        rows = await session.execute(
            sa.text(
                "SELECT username FROM ecn_role_assignments "
                "WHERE ecn_id = :ecn_id AND role_id = 'DC' "
                "AND superseded_at IS NULL AND username IS NOT NULL"
            ),
            {"ecn_id": ecn_id},
        )
        return [r[0] for r in rows]

    if status == ECNStatus.ENGINEERING_REVIEW:
        rows = await session.execute(
            sa.text(
                "SELECT username FROM ecn_role_assignments "
                "WHERE ecn_id = :ecn_id AND role_id IN ('SE','CE') "
                "AND superseded_at IS NULL AND username IS NOT NULL"
            ),
            {"ecn_id": ecn_id},
        )
        return [r[0] for r in rows]

    if status == ECNStatus.MANAGEMENT_REVIEW:
        rows = await session.execute(
            sa.text(
                "SELECT username FROM ecn_approval_steps "
                "WHERE ecn_id = :ecn_id AND at_status = 40 "
                "AND status = 'pending' AND skipped = FALSE AND username IS NOT NULL"
            ),
            {"ecn_id": ecn_id},
        )
        return [r[0] for r in rows]

    return []


# ---------------------------------------------------------------------------
# Optimistic locking helpers (ADR-008)
# ---------------------------------------------------------------------------

async def _check_not_modified(
    session: AsyncSession,
    ecn_id: str,
    if_unmodified_since: datetime | None,
) -> None:
    """Raise ECNPreconditionRequired (428) or ECNConflict (409) per ADR-008.

    Must be called inside the same DB transaction as the subsequent write so
    the check and the write are atomic (TOCTOU prevention).

    if_unmodified_since=None  → 428 Precondition Required
    if_unmodified_since stale → 409 Conflict with current_updated_at
    """
    if if_unmodified_since is None:
        raise ECNPreconditionRequired()

    row = await session.execute(
        sa.text("SELECT updated_at FROM ecn_instances WHERE id = :id FOR UPDATE"),
        {"id": ecn_id},
    )
    result = row.first()
    if result is None:
        raise ECNNotFound(ecn_id)

    current_updated_at: datetime = result[0]
    # Normalise both to UTC for comparison — DB returns timezone-aware TIMESTAMPTZ
    ts_check = if_unmodified_since
    if ts_check.tzinfo is None:
        ts_check = ts_check.replace(tzinfo=timezone.utc)
    if current_updated_at.tzinfo is None:
        current_updated_at = current_updated_at.replace(tzinfo=timezone.utc)

    if current_updated_at != ts_check:
        raise ECNConflict(current_updated_at)


@dataclass
class ECNUpdateRequest:
    """Input for PATCH /api/v1/ecn/{id} (field edits, not status transitions)."""
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


# ---------------------------------------------------------------------------
# Public service API
# ---------------------------------------------------------------------------

class ECNService:
    """Thin service layer between FastAPI ECN router and DB + workflow machine.

    All methods accept an AsyncSession. The session is committed by the
    get_session() dependency in db.py (commit-on-success pattern).
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── Create ────────────────────────────────────────────────────────────────

    async def create(
        self, req: ECNCreateRequest, actor_username: str
    ) -> ECNDetail:
        """Create a new ECN in DRAFT status.

        Steps:
        1. Validate facility
        2. Generate ECN number (ECN-YYYY-{facility}-{seq})
        3. INSERT ecn_instances
        4. Auto-assign roles from system_role_users
        5. Write initial transition history (from_status=NULL, to_status=0, action='create')
        """
        facility = req.facility.upper()
        if facility not in VALID_FACILITIES:
            raise ECNValidationError(
                f"Unknown facility '{facility}'. Valid codes: {sorted(VALID_FACILITIES)}"
            )
        if not req.title or not req.title.strip():
            raise ECNValidationError("title is required.")

        year = datetime.now(timezone.utc).year
        seq = await _next_ecn_seq(self._session, facility, year)
        ecn_number = _ecn_number(facility, seq, year)
        ecn_id = str(uuid.uuid4())

        await self._session.execute(
            sa.text(
                "INSERT INTO ecn_instances "
                "(id, ecn_number, facility, title, description, originator_username, "
                " is_new_item, routing_changes, operation_changes, new_parts, "
                " lead_time_changes, change_to_documents, wapc_delta_pct, "
                " wapc_threshold_override, "
                " requires_customer_approval, customer_approval_reference, "
                " regulatory_impact, extra_data) "
                "VALUES "
                "(:id, :ecn_number, :facility, :title, :description, :originator, "
                " :is_new_item, :routing_changes, :operation_changes, :new_parts, "
                " :lead_time_changes, :change_to_documents, :wapc_delta_pct, "
                " :wapc_threshold_override, "
                " :requires_customer_approval, :customer_approval_reference, "
                " :regulatory_impact, :extra_data::jsonb)"
            ),
            {
                "id": ecn_id,
                "ecn_number": ecn_number,
                "facility": facility,
                "title": req.title.strip(),
                "description": req.description,
                "originator": actor_username,
                "is_new_item": req.is_new_item,
                "routing_changes": req.routing_changes,
                "operation_changes": req.operation_changes,
                "new_parts": req.new_parts,
                "lead_time_changes": req.lead_time_changes,
                "change_to_documents": req.change_to_documents,
                "wapc_delta_pct": req.wapc_delta_pct,
                "wapc_threshold_override": req.wapc_threshold_override,
                "requires_customer_approval": req.requires_customer_approval,
                "customer_approval_reference": req.customer_approval_reference,
                "regulatory_impact": req.regulatory_impact,
                "extra_data": None if req.extra_data is None else str(req.extra_data).replace("'", '"'),
            },
        )

        await _auto_assign_roles(
            self._session, ecn_id, facility, actor_username, assigned_by=actor_username
        )

        # Write initial audit chain entry (from_status=NULL = chain head)
        ecn_model = ECNModel(
            id=ecn_id,
            ecn_number=ecn_number,
            facility=facility,
            status=ECNStatus.DRAFT,
            pre_hold_status=None,
            originator_username=actor_username,
            revision_number=1,
        )
        ctx = TransitionContext(
            actor_username=actor_username,
            actor_role="OR",
        )
        machine = ECNWorkflowMachine(ecn_model, ctx)
        machine.set_sha256_prev(None)
        await _write_transition_history(
            self._session, machine, ecn_id,
            from_status=None, to_status=ECNStatus.DRAFT, action="create",
        )

        log.info("ecn.created", ecn_id=ecn_id, ecn_number=ecn_number, actor=actor_username)
        return await self.get(ecn_id)

    # ── Get ───────────────────────────────────────────────────────────────────

    async def get(self, ecn_id: str) -> ECNDetail:
        """Fetch a single ECN with role assignments and approval steps."""
        row = await _load_ecn_row(self._session, ecn_id)
        if row is None:
            raise ECNNotFound(ecn_id)
        role_assignments = await _get_role_assignments(self._session, ecn_id)
        approval_steps = await _get_approval_steps(self._session, ecn_id)
        return _row_to_detail(row, role_assignments, approval_steps)

    # ── Update fields ─────────────────────────────────────────────────────────

    async def update_ecn(
        self,
        ecn_id: str,
        req: ECNUpdateRequest,
        if_unmodified_since: datetime | None,
    ) -> ECNDetail:
        """Patch writable fields on an ECN (DRAFT or REJECTED status only).

        ADR-008: if_unmodified_since must match updated_at or raises 428/409.
        The timestamp check and the UPDATE run in the same transaction.
        """
        await _check_not_modified(self._session, ecn_id, if_unmodified_since)

        # Verify the ECN exists and is in an editable status
        row = await _load_ecn_row(self._session, ecn_id)
        if row is None:
            raise ECNNotFound(ecn_id)
        if int(row["status"]) not in (ECNStatus.DRAFT, ECNStatus.REJECTED):
            raise ECNValidationError(
                f"ECN can only be edited in DRAFT or REJECTED status. "
                f"Current status: {ECNStatus(int(row['status'])).name}"
            )

        # Build SET clause from non-None fields only
        set_parts: list[str] = []
        params: dict[str, Any] = {"id": ecn_id}

        def _maybe(field: str, value: Any) -> None:
            if value is not None:
                set_parts.append(f"{field} = :{field}")
                params[field] = value

        if req.title is not None:
            if not req.title.strip():
                raise ECNValidationError("title cannot be blank.")
            set_parts.append("title = :title")
            params["title"] = req.title.strip()
        _maybe("description", req.description)
        for flag in (
            "is_new_item", "routing_changes", "operation_changes",
            "new_parts", "lead_time_changes", "change_to_documents",
            "wapc_threshold_override",
            "requires_customer_approval", "regulatory_impact",
        ):
            val = getattr(req, flag)
            if val is not None:
                set_parts.append(f"{flag} = :{flag}")
                params[flag] = val
        _maybe("wapc_delta_pct", req.wapc_delta_pct)
        _maybe("customer_approval_reference", req.customer_approval_reference)
        if req.extra_data is not None:
            set_parts.append("extra_data = :extra_data::jsonb")
            params["extra_data"] = str(req.extra_data).replace("'", '"')

        if not set_parts:
            return await self.get(ecn_id)

        await self._session.execute(
            sa.text(f"UPDATE ecn_instances SET {', '.join(set_parts)} WHERE id = :id"),
            params,
        )
        log.info("ecn.updated", ecn_id=ecn_id)
        return await self.get(ecn_id)

    # ── Status transition ─────────────────────────────────────────────────────

    async def transition(
        self,
        ecn_id: str,
        req: ECNStatusTransitionRequest,
        actor_username: str,
        if_unmodified_since: datetime | None = None,
    ) -> ECNDetail:
        """Apply a workflow trigger to an ECN.

        Steps:
        1. ADR-008: check If-Unmodified-Since (inside transaction — TOCTOU prevention)
        2. Load ECN from DB
        3. Hydrate ECNModel + TransitionContext
        4. Fetch previous SHA-256 hash for chain
        5. Build ECNWorkflowMachine + fire trigger
        6. UPDATE ecn_instances.status (and pre_hold_status if ON_HOLD/resume)
        7. Write ecn_transition_history row
        8. Handle rejection record insert (if trigger='reject')
        9. Return updated detail
        """
        # ADR-008: optimistic lock check BEFORE machine fires (TOCTOU prevention)
        if if_unmodified_since is not None:
            await _check_not_modified(self._session, ecn_id, if_unmodified_since)

        row = await _load_ecn_row(self._session, ecn_id)
        if row is None:
            raise ECNNotFound(ecn_id)

        ecn_model = _row_to_ecn_model(row)
        # Populate item_count for submit guard
        ecn_model.item_count = await _count_ecn_items(self._session, ecn_id)

        ctx = TransitionContext(
            actor_username=actor_username,
            actor_role=req.actor_role,
            notes=req.notes,
            rejection_reason=req.rejection_reason,
            hold_reason=req.hold_reason,
            expected_resume_date=req.expected_resume_date,
            role_id=req.role_id,
        )

        sha256_prev = await _get_last_transition_hash(self._session, ecn_id)

        # For complete_management_review: pre-check all steps approved
        async def _all_approved() -> bool:
            r = await self._session.execute(
                sa.text(
                    "SELECT COUNT(*) FROM ecn_approval_steps "
                    "WHERE ecn_id = :ecn_id AND at_status = 40 "
                    "AND status = 'pending' AND skipped = FALSE"
                ),
                {"ecn_id": ecn_id},
            )
            return int(r.scalar_one()) == 0

        from_status = ecn_model.status

        # For dc_approve: pre-check which new items lack a drawing number
        async def _missing_drawings() -> list[str]:
            r = await self._session.execute(
                sa.text(
                    "SELECT id FROM ecn_items "
                    "WHERE ecn_id = :ecn_id AND is_new_item = TRUE "
                    "AND drawing_number IS NULL"
                ),
                {"ecn_id": ecn_id},
            )
            return [str(row[0]) for row in r]

        machine = ECNWorkflowMachine(
            ecn_model, ctx,
            all_required_approved_fn=_all_approved,
            missing_drawings_fn=_missing_drawings,
        )
        machine.set_sha256_prev(sha256_prev)

        # Pre-populate missing drawings list on the machine so _guard_dc_approve
        # can inspect it synchronously (same pattern as _guard_all_required_approved).
        if req.trigger == "dc_approve":
            machine._pending_missing_drawings = await _missing_drawings()

        try:
            await machine.trigger(req.trigger)
        except GuardFailed as exc:
            raise ECNTransitionError(str(exc)) from exc
        except InvalidTransition as exc:
            raise ECNTransitionError(str(exc)) from exc

        to_status = ecn_model.status  # machine updated this in _after_transition

        # Persist status change
        update_params: dict[str, Any] = {
            "id": ecn_id,
            "status": to_status,
            "pre_hold_status": ecn_model.pre_hold_status,
        }
        await self._session.execute(
            sa.text(
                "UPDATE ecn_instances SET status = :status, "
                "pre_hold_status = :pre_hold_status "
                "WHERE id = :id"
            ),
            update_params,
        )

        await _write_transition_history(
            self._session, machine, ecn_id,
            from_status=from_status,
            to_status=to_status,
            action=req.trigger,
        )

        # Seed parallel approval steps when entering MANAGEMENT_REVIEW
        if to_status == ECNStatus.MANAGEMENT_REVIEW:
            await self._seed_approval_steps(ecn_id, dict(row))

        # Queue MPDDOC.CreateDrawing outbox entries on dc_approve (one per new item)
        if req.trigger == "dc_approve":
            await self._queue_drawing_outbox(ecn_id)

        # Queue MMS025MI.AddAlias outbox entries on movex_write_complete (one per unwritten MPN)
        if req.trigger == "movex_write_complete":
            await self._queue_alias_outbox(ecn_id)

        # Insert rejection record when trigger is 'reject'
        if req.trigger == "reject" and req.rejection_reason:
            await self._insert_rejection(ecn_id, actor_username, req, from_status)

        log.info(
            "ecn.transition",
            ecn_id=ecn_id,
            trigger=req.trigger,
            from_status=from_status,
            to_status=to_status,
            actor=actor_username,
        )
        return await self.get(ecn_id)

    # ── Drawing number ────────────────────────────────────────────────────────

    async def set_drawing_number(
        self,
        ecn_id: str,
        item_id: str,
        *,
        drawing_number: str,
        actor_username: str,
        actor_role: str,
    ) -> ECNDetail:
        """Set a drawing number on a specific ECN item.

        Guards:
        - actor_role must be 'DC'
        - ECN must be in DC_APPROVED status
        - Item must exist, belong to this ECN, and have is_new_item=TRUE
        """
        if actor_role != "DC":
            raise ECNForbidden("Only the DC may set drawing numbers.")

        row = await _load_ecn_row(self._session, ecn_id)
        if row is None:
            raise ECNNotFound(ecn_id)

        if int(row["status"]) != ECNStatus.DC_APPROVED:
            raise ECNValidationError(
                "Drawing numbers may only be set while ECN is in DC_APPROVED status."
            )

        item_row = await self._session.execute(
            sa.text(
                "SELECT id, is_new_item FROM ecn_items "
                "WHERE id = :item_id AND ecn_id = :ecn_id"
            ),
            {"item_id": item_id, "ecn_id": ecn_id},
        )
        item = item_row.mappings().first()
        if item is None:
            raise ECNNotFound(item_id)
        if not bool(item["is_new_item"]):
            raise ECNValidationError(
                "Drawing number can only be set on new items (is_new_item=TRUE)."
            )

        await self._session.execute(
            sa.text(
                "UPDATE ecn_items SET drawing_number = :drawing_number "
                "WHERE id = :item_id"
            ),
            {"drawing_number": drawing_number, "item_id": item_id},
        )

        log.info(
            "ecn.drawing_number.set",
            ecn_id=ecn_id,
            item_id=item_id,
            drawing_number=drawing_number,
            actor=actor_username,
        )
        return await self.get(ecn_id)

    async def _insert_rejection(
        self,
        ecn_id: str,
        actor_username: str,
        req: ECNStatusTransitionRequest,
        rejected_at_status: int,
    ) -> None:
        """INSERT one row into ecn_rejections. rejection_number = next in sequence."""
        row = await self._session.execute(
            sa.text(
                "SELECT COALESCE(MAX(rejection_number), 0) + 1 "
                "FROM ecn_rejections WHERE ecn_id = :ecn_id"
            ),
            {"ecn_id": ecn_id},
        )
        next_num = int(row.scalar_one())
        await self._session.execute(
            sa.text(
                "INSERT INTO ecn_rejections "
                "(id, ecn_id, rejection_number, rejected_by, rejected_at_status, "
                " role_id, description) "
                "VALUES (:id, :ecn_id, :num, :rejected_by, :at_status, :role_id, :desc)"
            ),
            {
                "id": str(uuid.uuid4()),
                "ecn_id": ecn_id,
                "num": next_num,
                "rejected_by": actor_username,
                "at_status": rejected_at_status,
                "role_id": req.actor_role or "DC",
                "desc": req.rejection_reason,
            },
        )

    async def _queue_drawing_outbox(self, ecn_id: str) -> None:
        """Queue one MPDDOC.CreateDrawing outbox entry per is_new_item=TRUE item.

        Stub — waits for @developer-dotnet to implement POST /api/ecn/drawing.
        Idempotency key: ecn_id + item_id ensures safe retry.
        """
        rows = await self._session.execute(
            sa.text(
                "SELECT id, item_number, drawing_number FROM ecn_items "
                "WHERE ecn_id = :ecn_id AND is_new_item = TRUE"
            ),
            {"ecn_id": ecn_id},
        )
        for item_id, item_number, drawing_number in rows:
            idempotency_key = f"MPDDOC.CreateDrawing:{ecn_id}:{item_id}"
            await self._session.execute(
                sa.text(
                    "INSERT INTO movex_outbox "
                    "(id, ecn_id, ecn_item_id, mi_transaction, mi_params, idempotency_key) "
                    "VALUES (:id, :ecn_id, :item_id, :mi_tx, :mi_params::jsonb, :ikey) "
                    "ON CONFLICT (idempotency_key) DO NOTHING"
                ),
                {
                    "id": str(uuid.uuid4()),
                    "ecn_id": ecn_id,
                    "item_id": str(item_id),
                    "mi_tx": "MPDDOC.CreateDrawing",
                    "mi_params": json.dumps({
                        "item_number": item_number,
                        "drawing_number": drawing_number,
                    }),
                    "ikey": idempotency_key,
                },
            )

    # ── Parallel approval block ───────────────────────────────────────────────

    async def _seed_approval_steps(self, ecn_id: str, ecn_row: dict[str, Any]) -> None:
        """Insert ecn_approval_steps rows when an ECN enters MANAGEMENT_REVIEW (status 40).

        Reads ecn_step_conditions for the ECN's facility (stage=40) to determine which
        roles are required.  Condition logic:
          - condition_op='always'  → always required
          - condition_op='eq_true' → required if ecn_row[condition_field] is truthy
          - condition_op='gt'      → required if ecn_row[condition_field] > threshold
            (condition_value holds the env var name for the threshold, e.g. 'FN_THRESHOLD_PCT')

        Uses INSERT ... ON CONFLICT DO NOTHING so re-seeding on a resubmit-proceed path
        is idempotent for roles that were already set.

        Assigns each step to the first active system_role_users row for that role+facility.
        """
        facility = ecn_row["facility"]

        # Load conditions for this facility at MANAGEMENT_REVIEW
        cond_rows = await self._session.execute(
            sa.text(
                "SELECT role_id, condition_field, condition_op, condition_value "
                "FROM ecn_step_conditions "
                "WHERE facility = :facility AND stage = 40"
            ),
            {"facility": facility},
        )
        conditions = list(cond_rows.mappings())

        # Deduplicate: a role can have multiple condition rows (e.g. PM has routing_changes
        # AND operation_changes).  Required if ANY condition evaluates to true.
        required_roles: set[str] = set()
        conditional_roles: set[str] = set()

        for cond in conditions:
            role_id = cond["role_id"]
            op = cond["condition_op"]
            field_name = cond["condition_field"]
            cond_value = cond["condition_value"]

            if op == "always":
                required_roles.add(role_id)
            elif op == "eq_true":
                if bool(ecn_row.get(field_name)):
                    required_roles.add(role_id)
                else:
                    conditional_roles.add(role_id)
            elif op == "gt":
                # condition_value is an env var name holding the numeric threshold
                threshold = float(os.getenv(str(cond_value), "5.0"))
                field_val = ecn_row.get(field_name)
                if field_val is not None and float(field_val) > threshold:
                    required_roles.add(role_id)
                else:
                    conditional_roles.add(role_id)

        # Roles that appeared only as conditional and never met → skipped
        skipped_roles = conditional_roles - required_roles

        # Fetch one assignee per required role from system_role_users
        async def _assignee(role_id: str) -> str | None:
            r = await self._session.execute(
                sa.text(
                    "SELECT username FROM system_role_users "
                    "WHERE role_id = :role_id AND facility = :facility "
                    "AND removed_at IS NULL "
                    "ORDER BY created_at LIMIT 1"
                ),
                {"role_id": role_id, "facility": facility},
            )
            row = r.first()
            return row[0] if row else None

        now = datetime.now(timezone.utc)

        for role_id in required_roles:
            assignee = await _assignee(role_id)
            await self._session.execute(
                sa.text(
                    "INSERT INTO ecn_approval_steps "
                    "(id, ecn_id, at_status, role_id, username, status, skipped, assigned_at) "
                    "VALUES (:id, :ecn_id, 40, :role_id, :username, 'pending', FALSE, :now) "
                    "ON CONFLICT (ecn_id, at_status, role_id) DO NOTHING"
                ),
                {
                    "id": str(uuid.uuid4()),
                    "ecn_id": ecn_id,
                    "role_id": role_id,
                    "username": assignee,
                    "now": now,
                },
            )

        for role_id in skipped_roles:
            await self._session.execute(
                sa.text(
                    "INSERT INTO ecn_approval_steps "
                    "(id, ecn_id, at_status, role_id, username, status, skipped, skip_reason, assigned_at) "
                    "VALUES (:id, :ecn_id, 40, :role_id, NULL, 'skipped', TRUE, :reason, :now) "
                    "ON CONFLICT (ecn_id, at_status, role_id) DO NOTHING"
                ),
                {
                    "id": str(uuid.uuid4()),
                    "ecn_id": ecn_id,
                    "role_id": role_id,
                    "reason": "Condition not met for this ECN",
                    "now": now,
                },
            )

    async def approve_role(
        self,
        ecn_id: str,
        *,
        actor_username: str,
        actor_role: str,
        notes: str | None = None,
    ) -> ECNDetail:
        """Record one role's approval at MANAGEMENT_REVIEW.

        Guards:
        - ECN must be in MANAGEMENT_REVIEW (status 40)
        - actor_role must have a non-skipped pending step for this ECN
        - actor_username must be assigned to that step (or be any valid user for the role)
        - Self-approval prohibition: actor_username must not be the ECN originator

        After marking the step approved, checks if all required non-skipped steps are now
        done.  If so, fires complete_management_review → ECN advances to DC_APPROVED (25).
        Returns the updated ECNDetail (either still MANAGEMENT_REVIEW or now DC_APPROVED).
        """
        row = await _load_ecn_row(self._session, ecn_id)
        if row is None:
            raise ECNNotFound(ecn_id)

        if int(row["status"]) != ECNStatus.MANAGEMENT_REVIEW:
            raise ECNValidationError(
                "approve_role is only valid in MANAGEMENT_REVIEW status."
            )

        # Self-approval prohibition (ADR-003)
        if actor_username == row["originator_username"]:
            raise ECNForbidden(
                f"Self-approval is prohibited: {actor_username} is the originator of this ECN."
            )

        # Load the step for this role
        step_row = await self._session.execute(
            sa.text(
                "SELECT id, status, skipped, username "
                "FROM ecn_approval_steps "
                "WHERE ecn_id = :ecn_id AND at_status = 40 AND role_id = :role_id"
            ),
            {"ecn_id": ecn_id, "role_id": actor_role},
        )
        step = step_row.mappings().first()

        if step is None:
            raise ECNValidationError(
                f"{actor_role} is not a required approver for this ECN."
            )
        if bool(step["skipped"]):
            raise ECNValidationError(
                f"{actor_role} is not a required approver for this ECN."
            )
        if step["status"] == "approved":
            raise ECNValidationError(
                f"{actor_role} step is already approved for this ECN."
            )

        # Verify actor is the assigned user for this role (or the step has no assignee yet)
        assigned = step["username"]
        if assigned is not None and assigned != actor_username:
            raise ECNForbidden(
                f"You are not assigned as {actor_role} for this ECN."
            )

        now = datetime.now(timezone.utc)

        # Mark step approved
        await self._session.execute(
            sa.text(
                "UPDATE ecn_approval_steps "
                "SET status = 'approved', username = :username, "
                "    completed_at = :now, notes = :notes "
                "WHERE ecn_id = :ecn_id AND at_status = 40 AND role_id = :role_id"
            ),
            {
                "username": actor_username,
                "now": now,
                "notes": notes,
                "ecn_id": ecn_id,
                "role_id": actor_role,
            },
        )

        log.info(
            "ecn.approve_role",
            ecn_id=ecn_id,
            role_id=actor_role,
            actor=actor_username,
        )

        # Check if all required non-skipped steps are now approved
        pending = await self._session.execute(
            sa.text(
                "SELECT COUNT(*) FROM ecn_approval_steps "
                "WHERE ecn_id = :ecn_id AND at_status = 40 "
                "AND status = 'pending' AND skipped = FALSE"
            ),
            {"ecn_id": ecn_id},
        )
        remaining = int(pending.scalar_one())

        if remaining == 0:
            # All done — fire complete_management_review via the transition machinery
            await self.transition(
                ecn_id,
                ECNStatusTransitionRequest(
                    trigger="complete_management_review",
                    actor_role=actor_role,
                    notes=notes,
                ),
                actor_username=actor_username,
            )

        return await self.get(ecn_id)

    async def _queue_alias_outbox(self, ecn_id: str) -> None:
        """Queue one MMS025MI.AddAlias outbox entry per unwritten ecn_mpns row.

        Selects ecn_mpns rows where alias_written=FALSE for all items in this ECN.
        Skips rows already written (alias_written=TRUE) — idempotency key provides
        an additional ON CONFLICT DO NOTHING safety net.
        Idempotency key: MMS025MI.AddAlias:{ecn_id}:{mpn_id}
        """
        rows = await self._session.execute(
            sa.text(
                "SELECT m.id, m.ecn_item_id, m.mpn, m.manufacturer, m.is_default "
                "FROM ecn_mpns m "
                "JOIN ecn_items i ON i.id = m.ecn_item_id "
                "WHERE i.ecn_id = :ecn_id AND m.alias_written = FALSE"
            ),
            {"ecn_id": ecn_id},
        )
        for mpn_id, item_id, mpn, manufacturer, is_default in rows:
            idempotency_key = f"MMS025MI.AddAlias:{ecn_id}:{mpn_id}"
            await self._session.execute(
                sa.text(
                    "INSERT INTO movex_outbox "
                    "(id, ecn_id, ecn_item_id, mi_transaction, mi_params, idempotency_key) "
                    "VALUES (:id, :ecn_id, :item_id, :mi_tx, :mi_params::jsonb, :ikey) "
                    "ON CONFLICT (idempotency_key) DO NOTHING"
                ),
                {
                    "id": str(uuid.uuid4()),
                    "ecn_id": ecn_id,
                    "item_id": str(item_id),
                    "mi_tx": "MMS025MI.AddAlias",
                    "mi_params": json.dumps({
                        "mpn": mpn,
                        "manufacturer": manufacturer,
                        "is_default": bool(is_default),
                    }),
                    "ikey": idempotency_key,
                },
            )

    # ── ECN items CRUD ───────────────────────────────────────────────────────

    def _row_to_mpn(self, row: Any) -> "ECNMPNDetail":
        eol_raw = row[9]
        return ECNMPNDetail(
            id=str(row[0]),
            ecn_item_id=str(row[1]),
            mpn=row[2],
            manufacturer=row[3],
            is_default=bool(row[4]),
            alias_written=bool(row[5]),
            msl_level=row[6],
            lifecycle=row[7],
            lead_time_weeks=row[8],
            eol_date=eol_raw.isoformat() if eol_raw else None,
            packaging_type=row[10],
            do_not_buy=bool(row[11]),
            alt_mpn=row[12],
            supplier_data_at=row[13],
            created_at=row[14],
        )

    async def _fetch_mpns(self, item_id: str) -> list["ECNMPNDetail"]:
        rows = await self._session.execute(
            sa.text(
                "SELECT id, ecn_item_id, mpn, manufacturer, is_default, alias_written, "
                "msl_level, lifecycle, lead_time_weeks, eol_date, packaging_type, "
                "do_not_buy, alt_mpn, supplier_data_at, created_at "
                "FROM ecn_mpns WHERE ecn_item_id = :item_id ORDER BY is_default DESC, created_at"
            ),
            {"item_id": item_id},
        )
        return [self._row_to_mpn(r) for r in rows]

    def _row_to_item(self, row: Any, mpns: list["ECNMPNDetail"]) -> "ECNItemDetail":
        eff_raw = row[14]
        return ECNItemDetail(
            id=str(row[0]),
            ecn_id=str(row[1]),
            line_number=row[2],
            is_new_item=bool(row[3]),
            item_number=row[4],
            item_name=row[5],
            description_2=row[6],
            drawing_number=row[7],
            drawing_created=bool(row[8]),
            procurement_group=row[9],
            product_group=row[10],
            unit_of_measure=row[11],
            item_group=row[12],
            customer_alias=row[13],
            effectivity_type=row[15],
            effectivity_from=eff_raw.isoformat() if eff_raw else None,
            created_at=row[16],
            updated_at=row[17],
            mpns=mpns,
        )

    async def create_item(
        self,
        ecn_id: str,
        *,
        line_number: int,
        is_new_item: bool = False,
        item_number: str,
        item_name: str | None = None,
        description_2: str | None = None,
        drawing_number: str | None = None,
        procurement_group: str | None = None,
        product_group: str | None = None,
        unit_of_measure: str | None = None,
        item_group: str | None = None,
        customer_alias: str | None = None,
        effectivity_type: str = "IMMEDIATE",
        effectivity_from: str | None = None,
    ) -> "ECNItemDetail":
        ecn_row = await self._session.execute(
            sa.text("SELECT id FROM ecn_instances WHERE id = :ecn_id"),
            {"ecn_id": ecn_id},
        )
        if not ecn_row.first():
            raise ECNNotFound(ecn_id)

        item_id = str(uuid.uuid4())
        await self._session.execute(
            sa.text(
                "INSERT INTO ecn_items "
                "(id, ecn_id, line_number, is_new_item, item_number, item_name, "
                "description_2, drawing_number, procurement_group, product_group, "
                "unit_of_measure, item_group, customer_alias, effectivity_type, effectivity_from) "
                "VALUES (:id, :ecn_id, :line_number, :is_new_item, :item_number, :item_name, "
                ":description_2, :drawing_number, :procurement_group, :product_group, "
                ":unit_of_measure, :item_group, :customer_alias, :effectivity_type, :effectivity_from)"
            ),
            {
                "id": item_id,
                "ecn_id": ecn_id,
                "line_number": line_number,
                "is_new_item": is_new_item,
                "item_number": item_number,
                "item_name": item_name,
                "description_2": description_2,
                "drawing_number": drawing_number,
                "procurement_group": procurement_group,
                "product_group": product_group,
                "unit_of_measure": unit_of_measure,
                "item_group": item_group,
                "customer_alias": customer_alias,
                "effectivity_type": effectivity_type,
                "effectivity_from": effectivity_from,
            },
        )
        return await self.get_item(ecn_id, item_id)

    async def list_items(self, ecn_id: str) -> list["ECNItemDetail"]:
        rows = await self._session.execute(
            sa.text(
                "SELECT id, ecn_id, line_number, is_new_item, item_number, item_name, "
                "description_2, drawing_number, drawing_created, procurement_group, product_group, "
                "unit_of_measure, item_group, customer_alias, effectivity_from, effectivity_type, "
                "created_at, updated_at "
                "FROM ecn_items WHERE ecn_id = :ecn_id ORDER BY line_number"
            ),
            {"ecn_id": ecn_id},
        )
        items = []
        for row in rows:
            mpns = await self._fetch_mpns(str(row[0]))
            items.append(self._row_to_item(row, mpns))
        return items

    async def get_item(self, ecn_id: str, item_id: str) -> "ECNItemDetail":
        row = await self._session.execute(
            sa.text(
                "SELECT id, ecn_id, line_number, is_new_item, item_number, item_name, "
                "description_2, drawing_number, drawing_created, procurement_group, product_group, "
                "unit_of_measure, item_group, customer_alias, effectivity_from, effectivity_type, "
                "created_at, updated_at "
                "FROM ecn_items WHERE id = :item_id AND ecn_id = :ecn_id"
            ),
            {"item_id": item_id, "ecn_id": ecn_id},
        )
        r = row.first()
        if not r:
            raise ECNNotFound(item_id)
        mpns = await self._fetch_mpns(item_id)
        return self._row_to_item(r, mpns)

    async def update_item(self, ecn_id: str, item_id: str, **fields: Any) -> "ECNItemDetail":
        await self.get_item(ecn_id, item_id)
        allowed = {
            "item_name", "description_2", "drawing_number", "procurement_group",
            "product_group", "unit_of_measure", "item_group", "customer_alias",
            "effectivity_type", "effectivity_from", "is_new_item",
        }
        updates = {k: v for k, v in fields.items() if k in allowed}
        if updates:
            set_clause = ", ".join(f"{k} = :{k}" for k in updates)
            await self._session.execute(
                sa.text(f"UPDATE ecn_items SET {set_clause} WHERE id = :item_id"),
                {**updates, "item_id": item_id},
            )
        return await self.get_item(ecn_id, item_id)

    async def delete_item(self, ecn_id: str, item_id: str) -> None:
        ecn_row = await self._session.execute(
            sa.text("SELECT status FROM ecn_instances WHERE id = :ecn_id"),
            {"ecn_id": ecn_id},
        )
        ecn = ecn_row.first()
        if not ecn:
            raise ECNNotFound(ecn_id)
        if ecn[0] != ECNStatus.DRAFT:
            raise ECNValidationError("Cannot delete item — ECN is not in DRAFT status")
        item_row = await self._session.execute(
            sa.text("SELECT id FROM ecn_items WHERE id = :item_id AND ecn_id = :ecn_id"),
            {"item_id": item_id, "ecn_id": ecn_id},
        )
        if not item_row.first():
            raise ECNNotFound(item_id)
        await self._session.execute(
            sa.text("DELETE FROM ecn_items WHERE id = :item_id"),
            {"item_id": item_id},
        )

    # ── MPN CRUD ──────────────────────────────────────────────────────────────

    async def create_mpn(
        self,
        ecn_id: str,
        item_id: str,
        *,
        mpn: str,
        manufacturer: str | None = None,
        is_default: bool = False,
        msl_level: int | None = None,
        lifecycle: str | None = None,
        eol_date: str | None = None,
        lead_time_weeks: int | None = None,
        packaging_type: str | None = None,
        do_not_buy: bool = False,
        alt_mpn: str | None = None,
    ) -> "ECNMPNDetail":
        item_row = await self._session.execute(
            sa.text("SELECT id FROM ecn_items WHERE id = :item_id AND ecn_id = :ecn_id"),
            {"item_id": item_id, "ecn_id": ecn_id},
        )
        if not item_row.first():
            raise ECNNotFound(item_id)

        mpn_id = str(uuid.uuid4())
        await self._session.execute(
            sa.text(
                "INSERT INTO ecn_mpns "
                "(id, ecn_item_id, mpn, manufacturer, is_default, msl_level, lifecycle, "
                "eol_date, lead_time_weeks, packaging_type, do_not_buy, alt_mpn) "
                "VALUES (:id, :item_id, :mpn, :manufacturer, :is_default, :msl_level, "
                ":lifecycle, :eol_date, :lead_time_weeks, :packaging_type, :do_not_buy, :alt_mpn)"
            ),
            {
                "id": mpn_id,
                "item_id": item_id,
                "mpn": mpn,
                "manufacturer": manufacturer,
                "is_default": is_default,
                "msl_level": msl_level,
                "lifecycle": lifecycle,
                "eol_date": eol_date,
                "lead_time_weeks": lead_time_weeks,
                "packaging_type": packaging_type,
                "do_not_buy": do_not_buy,
                "alt_mpn": alt_mpn,
            },
        )
        return await self._get_mpn(mpn_id)

    async def _get_mpn(self, mpn_id: str) -> "ECNMPNDetail":
        row = await self._session.execute(
            sa.text(
                "SELECT id, ecn_item_id, mpn, manufacturer, is_default, alias_written, "
                "msl_level, lifecycle, lead_time_weeks, eol_date, packaging_type, "
                "do_not_buy, alt_mpn, supplier_data_at, created_at "
                "FROM ecn_mpns WHERE id = :mpn_id"
            ),
            {"mpn_id": mpn_id},
        )
        r = row.first()
        if not r:
            raise ECNNotFound(mpn_id)
        return self._row_to_mpn(r)

    async def update_mpn(self, ecn_id: str, mpn_id: str, **fields: Any) -> "ECNMPNDetail":
        row = await self._session.execute(
            sa.text(
                "SELECT m.id FROM ecn_mpns m "
                "JOIN ecn_items i ON i.id = m.ecn_item_id "
                "WHERE m.id = :mpn_id AND i.ecn_id = :ecn_id"
            ),
            {"mpn_id": mpn_id, "ecn_id": ecn_id},
        )
        if not row.first():
            raise ECNNotFound(mpn_id)
        allowed = {
            "mpn", "manufacturer", "is_default", "msl_level", "lifecycle",
            "eol_date", "lead_time_weeks", "packaging_type", "do_not_buy", "alt_mpn",
        }
        updates = {k: v for k, v in fields.items() if k in allowed}
        if updates:
            set_clause = ", ".join(f"{k} = :{k}" for k in updates)
            await self._session.execute(
                sa.text(f"UPDATE ecn_mpns SET {set_clause} WHERE id = :mpn_id"),
                {**updates, "mpn_id": mpn_id},
            )
        return await self._get_mpn(mpn_id)

    async def delete_mpn(self, ecn_id: str, mpn_id: str) -> None:
        row = await self._session.execute(
            sa.text(
                "SELECT m.id FROM ecn_mpns m "
                "JOIN ecn_items i ON i.id = m.ecn_item_id "
                "WHERE m.id = :mpn_id AND i.ecn_id = :ecn_id"
            ),
            {"mpn_id": mpn_id, "ecn_id": ecn_id},
        )
        if not row.first():
            raise ECNNotFound(mpn_id)
        await self._session.execute(
            sa.text("DELETE FROM ecn_mpns WHERE id = :mpn_id"),
            {"mpn_id": mpn_id},
        )

    # ── List ──────────────────────────────────────────────────────────────────

    async def list_ecns(
        self,
        *,
        facility: str | None = None,
        status: int | None = None,
        assignee: str | None = None,
        overdue: bool | None = None,
        age_days: int | None = None,
        include_archived: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ECNSummary]:
        """G-3 list with filters. G-2 next_action_users[] computed per row."""
        conditions = ["e.is_archived = :include_archived"]
        params: dict[str, Any] = {
            "include_archived": include_archived,
            "limit": limit,
            "offset": offset,
        }

        if facility:
            conditions.append("e.facility = :facility")
            params["facility"] = facility.upper()

        if status is not None:
            conditions.append("e.status = :status")
            params["status"] = status

        if assignee:
            conditions.append(
                "EXISTS ("
                "  SELECT 1 FROM ecn_role_assignments era "
                "  WHERE era.ecn_id = e.id AND era.username = :assignee "
                "  AND era.superseded_at IS NULL"
                ")"
            )
            params["assignee"] = assignee

        if age_days is not None:
            conditions.append(
                "e.created_at <= now() - make_interval(days => :age_days)"
            )
            params["age_days"] = age_days

        # overdue: open ECNs older than 30 days (Sprint 1 definition — revisit with Branko)
        if overdue is True:
            conditions.append(
                "e.status NOT IN (70, 80) "
                "AND e.created_at <= now() - interval '30 days'"
            )

        where_clause = " AND ".join(conditions)
        sql = sa.text(
            f"SELECT e.id, e.ecn_number, e.facility, e.title, e.status, "
            f"       e.originator_username, e.revision_number, e.created_at, "
            f"       e.updated_at, e.is_archived "
            f"FROM ecn_instances e "
            f"WHERE {where_clause} "
            f"ORDER BY e.created_at DESC "
            f"LIMIT :limit OFFSET :offset"
        )
        rows = await self._session.execute(sql, params)

        summaries: list[ECNSummary] = []
        for row in rows.mappings():
            ecn_id = str(row["id"])
            status_int = int(row["status"])
            next_users = await _compute_next_action_users(
                self._session, ecn_id, status_int
            )
            summaries.append(
                ECNSummary(
                    id=ecn_id,
                    ecn_number=row["ecn_number"],
                    facility=row["facility"],
                    title=row["title"],
                    status=status_int,
                    status_name=ECNStatus(status_int).name,
                    originator_username=row["originator_username"],
                    revision_number=int(row["revision_number"]),
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                    is_archived=bool(row["is_archived"]),
                    next_action_users=next_users,
                )
            )

        return summaries

    # ── Role assignment ───────────────────────────────────────────────────────

    async def assign_role(
        self,
        ecn_id: str,
        role_id: str,
        username: str,
        actor_username: str,
        actor_role: str,
        notes: str | None = None,
    ) -> RoleAssignmentResult:
        """Reassign a role on an ECN (DC authority only).

        Guards:
        - actor_role must be 'DC'
        - role_id must be in VALID_ROLE_IDS
        - OR role cannot be reassigned (originator is fixed)
        - ECN must not be in a terminal status (CLOSED=70, CANCELLED=80)

        Uses supersede-and-insert: the existing active row for (ecn_id, role_id)
        has superseded_at set to now(), then a new active row is inserted.
        A transition_history row (action='role_assigned') is written for audit.
        """
        if actor_role != "DC":
            raise ECNForbidden("Only the Document Controller (DC) may reassign roles.")

        if role_id not in VALID_ROLE_IDS:
            raise ECNValidationError(
                f"Unknown role_id '{role_id}'. Valid: {sorted(VALID_ROLE_IDS)}"
            )
        if role_id == "OR":
            raise ECNValidationError(
                "Originator (OR) role cannot be reassigned. "
                "The originator is fixed at ECN creation."
            )

        row = await _load_ecn_row(self._session, ecn_id)
        if row is None:
            raise ECNNotFound(ecn_id)

        current_status = int(row["status"])
        _TERMINAL = {ECNStatus.CLOSED, ECNStatus.CANCELLED}
        if ECNStatus(current_status) in _TERMINAL:
            raise ECNValidationError(
                f"Cannot reassign roles on a terminal ECN "
                f"(status: {ECNStatus(current_status).name})."
            )

        # Find existing active holder of this role, if any
        prev_row = await self._session.execute(
            sa.text(
                "SELECT username FROM ecn_role_assignments "
                "WHERE ecn_id = :ecn_id AND role_id = :role_id "
                "AND superseded_at IS NULL"
            ),
            {"ecn_id": ecn_id, "role_id": role_id},
        )
        prev = prev_row.first()
        superseded_username: str | None = prev[0] if prev else None

        now = datetime.now(timezone.utc)

        if superseded_username is not None:
            await self._session.execute(
                sa.text(
                    "UPDATE ecn_role_assignments "
                    "SET superseded_at = :now "
                    "WHERE ecn_id = :ecn_id AND role_id = :role_id "
                    "AND superseded_at IS NULL"
                ),
                {"now": now, "ecn_id": ecn_id, "role_id": role_id},
            )

        facility = str(row["facility"])
        await self._session.execute(
            sa.text(
                "INSERT INTO ecn_role_assignments "
                "(id, ecn_id, facility, role_id, username, is_auto_assigned, "
                " assigned_by, assigned_at, notes) "
                "VALUES (:id, :ecn_id, :facility, :role_id, :username, FALSE, "
                "        :assigned_by, :now, :notes)"
            ),
            {
                "id": str(uuid.uuid4()),
                "ecn_id": ecn_id,
                "facility": facility,
                "role_id": role_id,
                "username": username,
                "assigned_by": actor_username,
                "now": now,
                "notes": notes,
            },
        )

        # Audit trail — role_assigned action in transition history
        sha256_prev = await _get_last_transition_hash(self._session, ecn_id)
        ecn_model = _row_to_ecn_model(row)
        ctx = TransitionContext(
            actor_username=actor_username,
            actor_role=actor_role,
            notes=notes or (
                f"Role {role_id} reassigned from {superseded_username!r} "
                f"to {username!r}"
                if superseded_username else
                f"Role {role_id} assigned to {username!r}"
            ),
        )
        machine = ECNWorkflowMachine(ecn_model, ctx)
        machine.set_sha256_prev(sha256_prev)
        await _write_transition_history(
            self._session, machine, ecn_id,
            from_status=current_status,
            to_status=current_status,
            action="role_assigned",
        )

        log.info(
            "ecn.role_assigned",
            ecn_id=ecn_id,
            role_id=role_id,
            username=username,
            superseded=superseded_username,
            actor=actor_username,
        )

        role_assignments = await _get_role_assignments(self._session, ecn_id)
        return RoleAssignmentResult(
            ecn_id=ecn_id,
            role_assignments=role_assignments,
            superseded_username=superseded_username,
        )

    # ── Rejection flows ───────────────────────────────────────────────────────

    async def resubmit(
        self,
        ecn_id: str,
        *,
        resolution: str,                   # 'restart' | 'proceed'
        actor_username: str,
        actor_role: str,
        notes: str | None = None,
    ) -> ECNDetail:
        """Resubmit a REJECTED ECN via restart or proceed path.

        Restart: all ecn_approval_steps reset to 'pending'; revision_number
        incremented; ECN → ENGINEERING_REVIEW.

        Proceed: only the rejecting role's most recent ecn_approval_step reset
        to 'pending'; other approvals preserved; ECN → prior stage (the status
        recorded on the most recent ecn_rejections row as rejected_at_status).

        Guards:
        - actor_role must be 'OR' (originator only)
        - ECN must be in REJECTED (65) status
        - resolution must be 'restart' or 'proceed'
        - ecn_rejections must have at least one unresolved row
        """
        if actor_role != "OR":
            raise ECNForbidden("Only the originator (OR) may resubmit a rejected ECN.")

        if resolution not in ("restart", "proceed"):
            raise ECNValidationError(
                f"Invalid resolution '{resolution}'. Must be 'restart' or 'proceed'."
            )

        row = await _load_ecn_row(self._session, ecn_id)
        if row is None:
            raise ECNNotFound(ecn_id)

        current_status = int(row["status"])
        if current_status != ECNStatus.REJECTED:
            raise ECNValidationError(
                f"ECN is not in REJECTED status (current: {current_status})."
            )

        # Verify originator
        if str(row["originator_username"]) != actor_username:
            raise ECNForbidden("Only the originator of this ECN may resubmit it.")

        # Load the most recent unresolved rejection record
        rej_row = await self._session.execute(
            sa.text(
                "SELECT id, rejected_at_status, role_id "
                "FROM ecn_rejections "
                "WHERE ecn_id = :ecn_id AND resolution IS NULL "
                "ORDER BY rejection_number DESC LIMIT 1"
            ),
            {"ecn_id": ecn_id},
        )
        rejection = rej_row.mappings().first()
        if rejection is None:
            raise ECNValidationError(
                "No unresolved rejection record found for this ECN."
            )

        now = datetime.now(timezone.utc)

        if resolution == "restart":
            # Reset ALL approval steps for this ECN to 'pending'
            await self._session.execute(
                sa.text(
                    "UPDATE ecn_approval_steps "
                    "SET step_status = 'pending', actor_username = NULL, "
                    "    acted_at = NULL "
                    "WHERE ecn_id = :ecn_id"
                ),
                {"ecn_id": ecn_id},
            )
            new_status = ECNStatus.ENGINEERING_REVIEW
            new_revision = int(row["revision_number"]) + 1
            await self._session.execute(
                sa.text(
                    "UPDATE ecn_instances "
                    "SET status = :status, revision_number = :rev, updated_at = :now "
                    "WHERE id = :ecn_id"
                ),
                {"status": new_status, "rev": new_revision,
                 "now": now, "ecn_id": ecn_id},
            )
        else:  # proceed
            # Reset only the rejecting role's most recent step
            rejecting_role = str(rejection["role_id"])
            rejected_at_status = int(rejection["rejected_at_status"])
            await self._session.execute(
                sa.text(
                    "UPDATE ecn_approval_steps "
                    "SET step_status = 'pending', actor_username = NULL, "
                    "    acted_at = NULL "
                    "WHERE ecn_id = :ecn_id AND role_id = :role_id "
                    "  AND at_status = :at_status"
                ),
                {
                    "ecn_id": ecn_id,
                    "role_id": rejecting_role,
                    "at_status": rejected_at_status,
                },
            )
            new_status = rejected_at_status
            new_revision = int(row["revision_number"])
            await self._session.execute(
                sa.text(
                    "UPDATE ecn_instances "
                    "SET status = :status, updated_at = :now "
                    "WHERE id = :ecn_id"
                ),
                {"status": new_status, "now": now, "ecn_id": ecn_id},
            )

        # Mark the rejection record as resolved
        await self._session.execute(
            sa.text(
                "UPDATE ecn_rejections "
                "SET resolution = :res, resolved_at = :now, resolved_by = :by "
                "WHERE id = :rej_id"
            ),
            {
                "res": resolution,
                "now": now,
                "by": actor_username,
                "rej_id": str(rejection["id"]),
            },
        )

        # Write audit chain record
        sha256_prev = await _get_last_transition_hash(self._session, ecn_id)
        ecn_model = _row_to_ecn_model(row)
        ctx = TransitionContext(
            actor_username=actor_username,
            actor_role=actor_role,
            notes=notes or f"Resubmit ({resolution})",
        )
        machine = ECNWorkflowMachine(ecn_model, ctx)
        machine.set_sha256_prev(sha256_prev)
        await _write_transition_history(
            self._session, machine, ecn_id,
            from_status=ECNStatus.REJECTED,
            to_status=new_status,
            action="resubmit",
        )

        log.info(
            "ecn.resubmitted",
            ecn_id=ecn_id,
            resolution=resolution,
            new_status=new_status,
            actor=actor_username,
        )

        return await self.get(ecn_id)
