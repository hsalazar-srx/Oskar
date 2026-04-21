# ADR-002 — Workflow Engine: Celery + PostgreSQL + `transitions`

**Status:** Accepted
**Date:** 2026-04-10
**Owner:** Lead Engineer
**Reviewed by:** @architect-system-design (expert review 2026-04-10)
**Type:** Architectural — type-1 (foundational; affects all ECN workflow code)

---

## Context

OSKAR replaces Stargile's `AsynchControl` — a Java-based BPMN-style workflow engine that managed
10 DB tables per ECN and wrapped every transition in a `LogicalUnitOfWork`. The LUoW attempted
a two-phase write: Stargile DB → Movex. On Movex failure, the rollback could fail silently,
leaving ECNs stuck at status 50 with no retry mechanism — the most reported Stargile operational
pain point.

OSKAR uses Python 3.12 / FastAPI / Celery / PostgreSQL. Three alternatives were evaluated:
- **Celery + PostgreSQL + `transitions`** — task execution + state persistence + state machine
- **Temporal** — distributed workflow engine with built-in saga and state
- **Prefect** — data pipeline orchestrator

---

## Decision

**Celery + PostgreSQL + `transitions` library.** Do not adopt Temporal or Prefect.

The three layers have distinct responsibilities:

| Layer | Technology | Responsibility |
|---|---|---|
| State machine | `transitions` (`ECNWorkflowMachine`) | Legal transitions, guard conditions, before/after hooks |
| Workflow state | PostgreSQL (12 tables) | All ECN state — permanent, auditable, authoritative |
| Side-effect execution | Celery (async workers) | Movex MI calls, email dispatch, audit writes |

**Critical rule:** Workflow state lives in PostgreSQL only. Celery executes side effects. A worker
crash must never leave an ECN in an unknown state (PostgreSQL outbox is the source of truth).

### Transactional Outbox Pattern

Replaces `LogicalUnitOfWork`:

1. Human confirms → single DB transaction commits: `ecn_instances.status` advance + `movex_outbox`
   entry + `ecn_transition_history` record (SHA-256)
2. Celery picks up outbox entry → executes MI calls in declared order, idempotent (`acks_late=True`)
3. On MI failure → exponential retry (30s → 5min → 30min); ECN stays at APPROVED (correct);
   `ecn_movex_errors` updated; DC alerted at attempt 3; ABANDONED after attempt 10
4. On success → ECN advances to IMPLEMENTED; Celery dispatches email notification (ADR-007: Redis eliminated; HTTP polling for frontend status)

Idempotency key on `movex_outbox` prevents double MI calls on retry. The outbox stores
OSKAR-defined operations (e.g., `add_product`), not raw MI call names — the adapter translates.
This makes the outbox ERP-agnostic for IFS migration.

---

## Rationale

**Why not Temporal:** Operationally inappropriate for this scale. Requires its own server cluster,
steep learning curve, second persistence layer — all on a 2-vCPU/4 GB VM for 50 users.
Temporal is the correct answer for large distributed systems; it is a cannon for this target.

**Why not Prefect:** Designed for data pipelines, not human-in-the-loop approval workflows.
No concept of per-instance role assignments or ISO 13485 audit chains.

**Why `transitions` over a hand-coded state machine:** Declarative definition (auditable in git),
guard conditions prevent invalid transitions at the library level, machine-readable state
definition for IQ documentation, `before`/`after` hooks decouple audit writes from transition
logic. The machine is stateless — state is always read from and persisted to PostgreSQL.

---

## ECN Status Set (12 statuses — replaces Stargile's 13)

| Code | Name | Note |
|---|---|---|
| 0 | DRAFT | Authoring |
| 10 | SUBMITTED | Awaiting DC |
| 20 | DC_REVIEW | DC completeness check |
| 30 | ENGINEERING_REVIEW | SE/CE technical review |
| 40 | MANAGEMENT_REVIEW | Parallel approval block |
| 50 | APPROVED | All human approvals done; Movex writes queued |
| 60 | IMPLEMENTED | All Movex writes confirmed |
| 65 | REJECTED | Any-stage rejection; routes to originator |
| 70 | CLOSED | Post-implementation sign-off |
| 80 | CANCELLED | Withdrawn; no Movex writes |
| 90 | ON_HOLD | Suspended; mandatory reason required |
| 99 | ARCHIVED | Logical flag only — not a status transition |

Stargile 50 (Movex Pending) + 60 (Movex Updated) are collapsed into APPROVED + IMPLEMENTED.
Movex write state is infrastructure — engineers never see "Movex Pending" as an ECN status.
The DC sees Movex write job state via the dedicated DC Recovery UI panel.

---

## Consequences

- `transitions==0.9.2` in `requirements.txt` (added Phase 2 F-7)
- `ECNWorkflowMachine` implemented at `src/workflow/machine.py` (2026-04-16)
- `ECNStatus` IntEnum defines 11 integer status values; `ARCHIVED` is a flag, not a status
- All transitions declared in `_TRANSITIONS` list — auditable in git, no scattered conditionals
- Guard conditions are methods on `ECNWorkflowMachine`; `GuardFailed` / `InvalidTransition` exceptions surfaced to FastAPI route layer
- `_before_transition` / `_after_transition` hooks update `ecn.status` on the in-memory `ECNModel`; SHA-256 chain computed via `compute_transition_hash()` — Python only, never DB triggers
- Machine is DB-agnostic: `ECNModel` and `TransitionContext` are plain dataclasses; no SQLAlchemy objects
- Caller (FastAPI service layer) wraps the machine trigger in a DB transaction: status update + outbox entry + transition history row commit atomically
- `after_transition` hooks do NOT dispatch Celery tasks directly — fire-and-forget dispatch happens after `await db.commit()` in the service layer to prevent task execution before commit
- Celery tasks never call `ECNWorkflowMachine` — they write directly to `ecn_instances.status` only for the APPROVED → IMPLEMENTED system transition (`movex_write_complete` trigger)
- Tests in `tests/workflow/test_machine.py` — pure unit tests, no DB required; 30+ cases covering happy path, guards, ON_HOLD, rejection/resubmit, SHA-256 chain, terminal states
- Stargile historical ECNs to be imported to a separate `legacy_ecn_history` table at go-live — not inserted into the OSKAR SHA-256 chain (untrusted source; no tamper evidence in Stargile audit trail)

## Implementation Notes (2026-04-16)

The machine location was moved from the planned `src/ecn/workflow.py` to `src/workflow/machine.py`
to keep the workflow engine as a standalone, reusable layer independent of the ECN HTTP layer.
This allows the BOM module (Iteration 2) to use the same pattern without coupling to ECN routes.

The `all_required_approved_fn` callback parameter on `ECNWorkflowMachine.__init__` allows the
caller to inject an async function that queries `ecn_approval_steps` — keeping the machine
stateless with respect to DB queries while still enforcing the parallel block completion guard.
