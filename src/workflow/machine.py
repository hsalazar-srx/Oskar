"""
OSKAR ECN Workflow State Machine

Uses the `transitions` library to enforce legal state transitions, guard conditions,
and before/after hooks.

LAYERED RESPONSIBILITY (ai/memory/03 §12):
  This file:      Legal transitions, guard conditions, before/after hooks
  PostgreSQL:     All persistent ECN state — the only source of truth
  Celery workers: Side-effect execution (Movex MI calls, email, Redis stream)

USAGE (from a FastAPI route or service):
    machine = ECNWorkflowMachine(ecn, context)
    await machine.submit()          # raises InvalidTransition if guard fails
    await machine.approve_role(role_id="QM")

IMPORTANT — this class does NOT write to the database directly.
It calls the hook callbacks provided via WorkflowContext. The caller
(a FastAPI service layer) is responsible for the outer DB transaction:

    async with db.begin():
        machine = ECNWorkflowMachine(ecn, context)
        await machine.submit()          ← validates guard, calls on_submit hook
        await db.commit()               ← commits status update + transition history row atomically

Sources:
  ai/memory/06-ecn-requirements.md §1–3 — status table, transitions, parallel block rules
  ai/memory/03-oskar-architecture.md §14 — 10-status machine (ADR-009)
  ai/memory/12-data-model.md §3 — status integer codes
  decisions/ADR-009-dc-single-gate-role-customisation.md — DC single gate rationale
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import IntEnum
from typing import Any, Callable, Coroutine
from uuid import uuid4

from transitions import Machine, MachineError  # type: ignore[import]

from src.workflow.audit_hash import compute_transition_hash as _compute_transition_hash


# ---------------------------------------------------------------------------
# Status codes — must match ecn_instances CHECK constraint (12-data-model §3)
# ---------------------------------------------------------------------------

class ECNStatus(IntEnum):
    DRAFT               = 0
    DC_APPROVED         = 25   # ADR-009: single DC gate before Movex write
    ENGINEERING_REVIEW  = 30
    MANAGEMENT_REVIEW   = 40
    APPROVED            = 50
    IMPLEMENTED         = 60
    REJECTED            = 65
    CLOSED              = 70
    CANCELLED           = 80
    ON_HOLD             = 90
    # SUBMITTED(10) and DC_REVIEW(20) removed by ADR-009 — integers tombstoned

    @property
    def is_terminal(self) -> bool:
        return self in (ECNStatus.CLOSED, ECNStatus.CANCELLED)


# ---------------------------------------------------------------------------
# Data classes passed into the machine
# ---------------------------------------------------------------------------

@dataclass
class ECNModel:
    """Snapshot of the relevant ecn_instances fields needed by the state machine.

    The caller hydrates this from the DB row before constructing the machine.
    Do NOT pass a SQLAlchemy ORM object here — keep the machine DB-agnostic.
    """
    id: str                         # UUID as str
    ecn_number: str
    facility: str
    status: int                     # Current ECNStatus value
    pre_hold_status: int | None     # Saved status; restored on resume
    originator_username: str
    revision_number: int
    title: str = ""                 # ECN title — checked by submit guard
    item_count: int = 0             # COUNT(*) from ecn_items — checked by submit guard

    # Change scope flags — used by guard conditions
    is_new_item: bool = False
    routing_changes: bool = False
    operation_changes: bool = False
    new_parts: bool = False
    lead_time_changes: bool = False
    change_to_documents: bool = False

    # Cost
    wapc_delta_pct: float | None = None
    wapc_threshold_override: bool = False
    requires_customer_approval: bool = False
    customer_approved_at: datetime | None = None
    regulatory_impact: bool = False

    # Items (used by submit guard)
    item_count: int = 0             # COUNT(*) from ecn_items for this ECN


@dataclass
class TransitionContext:
    """Runtime context for a single transition — who is acting and why.

    Constructed by the FastAPI route layer and passed to the machine.
    """
    actor_username: str             # sAMAccountName, lowercase-normalised
    actor_role: str | None          # Role ID at time of action (e.g. 'DC', 'QM')
    notes: str | None = None
    movex_payload: dict[str, Any] | None = None
    agent_provenance: dict[str, Any] | None = None

    # Populated for role-level approvals at MANAGEMENT_REVIEW
    role_id: str | None = None      # Role being approved/rejected

    # Populated for ON_HOLD
    hold_reason: str | None = None
    expected_resume_date: str | None = None  # ISO date string

    # Populated for REJECTED path
    rejection_reason: str | None = None


# Hook type — async callable the machine fires; caller implements persistence
HookFn = Callable[["ECNWorkflowMachine", str, str], Coroutine[Any, Any, None]]


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class InvalidTransition(Exception):
    """Raised when a transition is attempted that the state machine disallows."""


class GuardFailed(InvalidTransition):
    """Raised when a transition trigger is valid but a guard condition blocks it."""


# ---------------------------------------------------------------------------
# State machine
# ---------------------------------------------------------------------------

class ECNWorkflowMachine:
    """ECN state machine — wraps the `transitions` library.

    Responsible for:
    - Enforcing legal transitions (MachineError → InvalidTransition)
    - Evaluating guard conditions before each transition
    - Computing the SHA-256 audit chain entry
    - Calling the registered before/after hooks (caller persists to DB)

    Does NOT:
    - Write to the database directly
    - Send notifications
    - Execute Movex MI calls
    """

    # State names used by transitions — maps from ECNStatus integer values
    # transitions requires string state names; we prefix with 's' to stay valid identifiers
    _STATE_NAMES: dict[int, str] = {
        ECNStatus.DRAFT:              "DRAFT",
        ECNStatus.DC_APPROVED:        "DC_APPROVED",
        ECNStatus.ENGINEERING_REVIEW: "ENGINEERING_REVIEW",
        ECNStatus.MANAGEMENT_REVIEW:  "MANAGEMENT_REVIEW",
        ECNStatus.APPROVED:           "APPROVED",
        ECNStatus.IMPLEMENTED:        "IMPLEMENTED",
        ECNStatus.REJECTED:           "REJECTED",
        ECNStatus.CLOSED:             "CLOSED",
        ECNStatus.CANCELLED:          "CANCELLED",
        ECNStatus.ON_HOLD:            "ON_HOLD",
    }

    # ---------------------------------------------------------------------------
    # Transitions table — (trigger, source, dest)
    # All guard conditions are registered via `conditions` kwarg.
    # `unless` is used to express negative conditions.
    # ---------------------------------------------------------------------------
    _TRANSITIONS = [
        # ── Normal workflow (ADR-009) ──────────────────────────────────────
        # submit goes directly to ENGINEERING_REVIEW — no SUBMITTED queue step
        {
            "trigger": "submit",
            "source":  "DRAFT",
            "dest":    "ENGINEERING_REVIEW",
            "conditions": ["_guard_submit"],
            "before":  "_before_transition",
            "after":   "_after_transition",
        },
        {
            "trigger": "approve_engineering",
            "source":  "ENGINEERING_REVIEW",
            "dest":    "MANAGEMENT_REVIEW",
            "conditions": ["_guard_is_se_or_ce"],
            "before":  "_before_transition",
            "after":   "_after_transition",
        },
        # MANAGEMENT_REVIEW parallel block: approve_role fires per-role.
        # complete_management_review auto-advances to DC_APPROVED (ADR-009).
        {
            "trigger": "approve_role",
            "source":  "MANAGEMENT_REVIEW",
            "dest":    "MANAGEMENT_REVIEW",   # stays — caller checks if block is complete
            "conditions": ["_guard_management_review_approver"],
            "before":  "_before_transition",
            "after":   "_after_transition",
        },
        {
            "trigger": "complete_management_review",
            "source":  "MANAGEMENT_REVIEW",
            "dest":    "DC_APPROVED",         # ADR-009: DC gate before Movex write
            "conditions": ["_guard_all_required_approved"],
            "before":  "_before_transition",
            "after":   "_after_transition",
        },
        # DC_APPROVED: single DC gate — combines former DC_REVIEW + IMPLEMENTED→CLOSED manual step
        {
            "trigger": "dc_approve",
            "source":  "DC_APPROVED",
            "dest":    "APPROVED",
            "conditions": ["_guard_dc_approve"],
            "before":  "_before_transition",
            "after":   "_after_transition",
        },
        # System-triggered (Celery): all outbox entries completed
        {
            "trigger": "movex_write_complete",
            "source":  "APPROVED",
            "dest":    "IMPLEMENTED",
            "before":  "_before_transition",
            "after":   "_after_transition",
        },
        # System-triggered (Celery): automatic after outbox fully completes (ADR-009)
        {
            "trigger": "auto_close",
            "source":  "IMPLEMENTED",
            "dest":    "CLOSED",
            "before":  "_before_transition",
            "after":   "_after_transition",
        },

        # ── Rejection paths ────────────────────────────────────────────────
        {
            "trigger": "reject",
            "source":  ["ENGINEERING_REVIEW", "MANAGEMENT_REVIEW", "DC_APPROVED"],
            "dest":    "REJECTED",
            "conditions": ["_guard_rejection_reason"],
            "before":  "_before_transition",
            "after":   "_after_transition",
        },
        # resubmit goes to ENGINEERING_REVIEW — no SUBMITTED holding state (ADR-009)
        {
            "trigger": "resubmit",
            "source":  "REJECTED",
            "dest":    "ENGINEERING_REVIEW",
            "conditions": ["_guard_is_originator"],
            "before":  "_before_transition",
            "after":   "_after_transition",
        },

        # ── Cancellation ───────────────────────────────────────────────────
        {
            "trigger": "cancel",
            "source":  ["DRAFT"],
            "dest":    "CANCELLED",
            "conditions": ["_guard_cancel"],
            "before":  "_before_transition",
            "after":   "_after_transition",
        },

        # ── ON_HOLD ────────────────────────────────────────────────────────
        # ON_HOLD is reachable from any non-terminal, non-hold status.
        {
            "trigger": "place_on_hold",
            "source":  [
                "DRAFT", "ENGINEERING_REVIEW", "MANAGEMENT_REVIEW",
                "DC_APPROVED", "APPROVED", "IMPLEMENTED", "REJECTED",
            ],
            "dest":    "ON_HOLD",
            "conditions": ["_guard_place_on_hold"],
            "before":  "_before_transition",
            "after":   "_after_transition",
        },
        {
            "trigger": "resume",
            "source":  "ON_HOLD",
            "dest":    "=",             # transitions special: reflexive (stays in same Machine state)
            "conditions": ["_guard_resume"],
            "before":  "_before_resume",
            "after":   "_after_resume",  # special: must NOT re-read self.state (still ON_HOLD)
        },
    ]

    def __init__(
        self,
        ecn: ECNModel,
        ctx: TransitionContext,
        *,
        # Hooks called after each successful transition. The caller registers
        # these to persist state changes and write transition history.
        on_transition: HookFn | None = None,
        # For MANAGEMENT_REVIEW parallel block: called to check if all required
        # roles have approved (caller queries ecn_approval_steps).
        all_required_approved_fn: Callable[[], Coroutine[Any, Any, bool]] | None = None,
        # For DC_APPROVED gate: called to get item IDs missing drawing numbers.
        # Returns list of item IDs that are is_new_item=TRUE with drawing_number IS NULL.
        missing_drawings_fn: Callable[[], Coroutine[Any, Any, list[str]]] | None = None,
    ) -> None:
        self.ecn = ecn
        self.ctx = ctx
        self._on_transition = on_transition
        self._all_required_approved_fn = all_required_approved_fn
        self._missing_drawings_fn = missing_drawings_fn

        # Transition record built by _before_transition, consumed by _after_transition
        self._pending_from_status: int | None = None
        self._pending_action: str | None = None
        self._pending_to_status: int | None = None

        # SHA-256 chain — caller must supply the previous hash from DB
        self._sha256_prev: str | None = None

        current_state_name = self._STATE_NAMES[ecn.status]
        self._machine = Machine(
            model=self,
            states=list(self._STATE_NAMES.values()),
            transitions=self._TRANSITIONS,
            initial=current_state_name,
            ignore_invalid_triggers=False,  # raise MachineError on bad trigger
            auto_transitions=False,
        )

    # ---------------------------------------------------------------------------
    # Public API
    # ---------------------------------------------------------------------------

    def set_sha256_prev(self, sha256_prev: str | None) -> None:
        """Set the previous SHA-256 hash for chain computation.

        Call this after constructing the machine, before triggering any transition.
        The value comes from:
          SELECT sha256_self FROM ecn_transition_history
          WHERE ecn_id = $ecn_id ORDER BY created_at DESC LIMIT 1
        Pass None if this is the first transition (chain head).
        """
        self._sha256_prev = sha256_prev

    async def trigger(self, trigger_name: str) -> None:
        """Fire a named trigger, converting MachineError to InvalidTransition."""
        try:
            result = getattr(self, trigger_name)()
            # transitions returns False when a condition is not met
            if result is False:
                raise GuardFailed(
                    f"Trigger '{trigger_name}' was blocked by a guard condition. "
                    f"ECN {self.ecn.ecn_number} is in status {ECNStatus(self.ecn.status).name}."
                )
        except (MachineError, AttributeError) as exc:
            # AttributeError: trigger was removed (e.g. accept, pass_to_engineering — ADR-009)
            raise InvalidTransition(str(exc)) from exc

    def current_status(self) -> ECNStatus:
        return ECNStatus(self.ecn.status)

    # ---------------------------------------------------------------------------
    # SHA-256 audit chain computation (ADR-004)
    # ---------------------------------------------------------------------------

    def compute_transition_hash(
        self,
        record_id: str,
        from_status: int | None,
        to_status: int,
        action: str,
        created_at: datetime,
    ) -> str:
        return _compute_transition_hash(
            record_id=record_id,
            ecn_id=self.ecn.id,
            from_status=from_status,
            to_status=to_status,
            action=action,
            actor_username=self.ctx.actor_username,
            actor_role=self.ctx.actor_role,
            notes=self.ctx.notes,
            movex_payload=self.ctx.movex_payload,
            agent_provenance=self.ctx.agent_provenance,
            sha256_prev=self._sha256_prev,
            created_at=created_at,
        )

    # ---------------------------------------------------------------------------
    # Before / after hooks (called by transitions library)
    # ---------------------------------------------------------------------------

    def _before_transition(self, event_data=None) -> None:
        """Record the from-status before state changes.

        The transitions library passes EventData as a positional arg when the
        callback is defined as a method. We capture from-status here; the action
        name is read from event_data.event.name if available.
        """
        self._pending_from_status = self.ecn.status
        if event_data is not None and hasattr(event_data, "event"):
            self._pending_action = event_data.event.name
        else:
            self._pending_action = "unknown"

    def _before_resume(self, _event_data=None) -> None:
        """Special before-hook for resume: restore the pre_hold_status."""
        self._pending_from_status = self.ecn.status
        self._pending_action = "resume"
        # The dest='=' means transitions will not change state automatically.
        # We restore the saved status here; _after_transition fires next.
        if self.ecn.pre_hold_status is None:
            raise GuardFailed("Cannot resume: pre_hold_status is NULL. Data integrity error.")
        self.ecn.status = self.ecn.pre_hold_status
        self.ecn.pre_hold_status = None

    def _after_transition(self) -> None:
        """Update ecn.status from the new state name, compute the hash."""
        name_to_int = {v: k for k, v in self._STATE_NAMES.items()}
        new_status = name_to_int[self.state]
        self._pending_to_status = new_status
        self.ecn.status = new_status

        if new_status == ECNStatus.ON_HOLD:
            self.ecn.pre_hold_status = self._pending_from_status

    def _after_resume(self) -> None:
        """After resume: ecn.status was already set by _before_resume; do not re-read self.state.

        With dest='=', the Machine does not change its internal state string — self.state
        remains 'ON_HOLD'. Reading name_to_int[self.state] would overwrite the restored status.
        Instead, capture the status _before_resume already set on ecn.
        """
        self._pending_to_status = self.ecn.status

    # ---------------------------------------------------------------------------
    # Guard conditions
    # ---------------------------------------------------------------------------

    def _guard_submit(self) -> bool:
        """DRAFT → ENGINEERING_REVIEW: mandatory header + ≥1 item (ADR-009)."""
        if self.ctx.actor_username != self.ecn.originator_username:
            raise GuardFailed("Only the originator can submit an ECN.")
        if not self.ecn.title or not self.ecn.title.strip():
            raise GuardFailed("ECN title is required before submission.")
        if self.ecn.item_count < 1:
            raise GuardFailed("At least one ECN item must be defined before submission.")
        return True

    def _guard_is_dc(self) -> bool:
        """Actor must hold the DC role on this ECN."""
        if self.ctx.actor_role != "DC":
            raise GuardFailed(
                f"Only the Document Controller (DC) may perform this action. "
                f"Actor role: {self.ctx.actor_role!r}."
            )
        return True

    def _guard_is_se_or_ce(self) -> bool:
        """Actor must hold SE or CE role on this ECN."""
        if self.ctx.actor_role not in ("SE", "CE"):
            raise GuardFailed(
                f"Only SE or CE may approve at ENGINEERING_REVIEW. "
                f"Actor role: {self.ctx.actor_role!r}."
            )
        return True

    def _guard_is_originator(self) -> bool:
        if self.ctx.actor_username != self.ecn.originator_username:
            raise GuardFailed("Only the originator may resubmit a rejected ECN.")
        return True

    def _guard_rejection_reason(self) -> bool:
        if not self.ctx.rejection_reason or not self.ctx.rejection_reason.strip():
            raise GuardFailed("A rejection reason is mandatory.")
        return True

    def _guard_management_review_approver(self) -> bool:
        """Actor must hold a required, non-skipped role at MANAGEMENT_REVIEW."""
        valid_roles = {"EM", "QM", "PM", "SC", "FN", "CE", "CA"}
        if self.ctx.actor_role not in valid_roles:
            raise GuardFailed(
                f"Role {self.ctx.actor_role!r} is not a valid MANAGEMENT_REVIEW approver."
            )
        # Self-approval prohibition (ai/memory/06 §2)
        if self.ctx.actor_username == self.ecn.originator_username:
            raise GuardFailed(
                "Self-approval is prohibited. The originator cannot approve their own ECN."
            )
        return True

    def _guard_all_required_approved(self) -> bool:
        """All required non-skipped approval steps must be in 'approved' state.

        The caller registers all_required_approved_fn to perform the actual DB query
        (COUNT pending non-skipped steps = 0). If no fn is registered we fail safe.
        """
        # This guard runs synchronously within transitions; for async callers,
        # the caller should await the check BEFORE calling complete_management_review.
        # The fn registered here is the synchronous result cached by the caller.
        if self._all_required_approved_fn is None:
            raise GuardFailed(
                "complete_management_review requires all_required_approved_fn to be registered."
            )
        # Caller pre-validates; this guard acts as the final gate.
        return True

    def _guard_dc_approve(self) -> bool:
        """DC_APPROVED → APPROVED: DC role + drawing numbers + customer approval gate.

        ADR-009: consolidates former _guard_is_dc + _guard_close into one gate.
        DC certifies the full change package before the Movex write is authorised.
        Drawing numbers must be set on all is_new_item=TRUE items before dc_approve.
        Customer approval gate: ISO 13485 §7.3.9.
        """
        if self.ctx.actor_role != "DC":
            raise GuardFailed(
                f"Only the Document Controller (DC) may approve at DC_APPROVED. "
                f"Actor role: {self.ctx.actor_role!r}."
            )
        if (
            self.ecn.requires_customer_approval
            and self.ecn.customer_approved_at is None
        ):
            raise GuardFailed(
                "Customer approval is required for this ECN (ISO 13485 §7.3.9). "
                "Set customer_approved_at before DC approval."
            )
        # Drawing number check: caller pre-validates via missing_drawings_fn.
        # The _pending_missing_drawings attr is set by ECNService.transition
        # before firing the trigger (same pattern as _all_required_approved_fn).
        missing = getattr(self, "_pending_missing_drawings", None)
        if missing:
            ids = ", ".join(missing)
            raise GuardFailed(
                f"All new items must have a drawing number before DC approval. "
                f"Missing: {ids}."
            )
        return True

    def _guard_cancel(self) -> bool:
        """Only originator or Admin may cancel; only from DRAFT or SUBMITTED."""
        if self.ctx.actor_role not in ("AD",) and self.ctx.actor_username != self.ecn.originator_username:
            raise GuardFailed("Only the originator or an Admin may cancel an ECN.")
        return True

    def _guard_place_on_hold(self) -> bool:
        """DC or Admin only; reason + expected resume date mandatory."""
        if self.ctx.actor_role not in ("DC", "AD"):
            raise GuardFailed("Only DC or Admin may place an ECN on hold.")
        if not self.ctx.hold_reason or not self.ctx.hold_reason.strip():
            raise GuardFailed("A hold reason is mandatory.")
        if not self.ctx.expected_resume_date:
            raise GuardFailed("An expected resume date is mandatory when placing an ECN on hold.")
        return True

    def _guard_resume(self) -> bool:
        """DC or Admin only; pre_hold_status must be set."""
        if self.ctx.actor_role not in ("DC", "AD"):
            raise GuardFailed("Only DC or Admin may resume an ECN from ON_HOLD.")
        if self.ecn.pre_hold_status is None:
            raise GuardFailed("Cannot resume: pre_hold_status is NULL.")
        return True
