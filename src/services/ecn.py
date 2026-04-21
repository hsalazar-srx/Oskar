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

import os
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
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

    # Emergency — Sprint 2 workflow; data model accepted now
    is_emergency: bool = False
    emergency_reason: str | None = None

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

    # Emergency
    is_emergency: bool
    emergency_reason: str | None
    emergency_approved_by: str | None
    emergency_approved_at: datetime | None

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
        is_emergency=bool(row["is_emergency"]),
        emergency_reason=row.get("emergency_reason"),
        emergency_approved_by=row.get("emergency_approved_by"),
        emergency_approved_at=row.get("emergency_approved_at"),
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
                " wapc_threshold_override, is_emergency, emergency_reason, "
                " requires_customer_approval, customer_approval_reference, "
                " regulatory_impact, extra_data) "
                "VALUES "
                "(:id, :ecn_number, :facility, :title, :description, :originator, "
                " :is_new_item, :routing_changes, :operation_changes, :new_parts, "
                " :lead_time_changes, :change_to_documents, :wapc_delta_pct, "
                " :wapc_threshold_override, :is_emergency, :emergency_reason, "
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
                "is_emergency": req.is_emergency,
                "emergency_reason": req.emergency_reason,
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

    # ── Status transition ─────────────────────────────────────────────────────

    async def transition(
        self,
        ecn_id: str,
        req: ECNStatusTransitionRequest,
        actor_username: str,
    ) -> ECNDetail:
        """Apply a workflow trigger to an ECN.

        Steps:
        1. Load ECN from DB
        2. Hydrate ECNModel + TransitionContext
        3. Fetch previous SHA-256 hash for chain
        4. Build ECNWorkflowMachine + fire trigger
        5. UPDATE ecn_instances.status (and pre_hold_status if ON_HOLD/resume)
        6. Write ecn_transition_history row
        7. Handle rejection record insert (if trigger='reject')
        8. Return updated detail
        """
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

        machine = ECNWorkflowMachine(
            ecn_model, ctx,
            all_required_approved_fn=_all_approved,
        )
        machine.set_sha256_prev(sha256_prev)

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
