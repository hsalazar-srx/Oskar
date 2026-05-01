# ADR-009 — DC Single Gate and Per-ECN Role Customisation

**Status:** Accepted
**Date:** 2026-04-30
**Owner:** Lead Engineer
**Reviewed by:** @architect-system-design
**Type:** Architectural — type-2 (significant; affects workflow engine, approval routing, and role assignment model)

---

## Context

### The DC redundancy problem

In the current Sprint 1 design the Document Controller acts at **three** points in the workflow:

| Step | Action | Status transition |
|------|--------|------------------|
| 1 | Accept ECN into review queue | SUBMITTED (10) → DC_REVIEW (20) |
| 2 | Pass to engineering after completeness check | DC_REVIEW (20) → ENGINEERING_REVIEW (30) |
| 3 | Post-implementation sign-off | IMPLEMENTED (60) → CLOSED (70) |

In Stargile (`IECNStatus.java`, `RequestECN.awf`) the Document Controller appears **once** in
the linear workflow, at status 35 (`DC_APPROVAL_PENDING`) — positioned just before the Movex
write at status 50. Stargile status 25 (`DC_CHECK_PENDING`) was an internal queue state, not
a separate user action. In practice the DC's meaningful approval is the gate immediately
before Movex commits the change.

Three DC actions in OSKAR creates:
- Redundant work items for the DC on every ECN
- Two separable statuses (SUBMITTED + DC_REVIEW) where the business process has one continuous
  DC activity
- A SUBMITTED status that is a waiting room with no substantive user action — the transition
  history record already captures the submission handoff

### The role customisation gap

The Sprint 1 model auto-assigns roles from `system_role_users` at ECN creation but provides
no mechanism to replace an assigned user mid-workflow (e.g. primary SE on leave) or to
assign a role user after ECN creation. The `ecn_role_assignments` table supports this
structurally (INSERT-only, superseded_at pattern from ADR-003), but no endpoint or
service-layer guard exists.

### Alternatives considered for DC gate placement

**Option A — Keep three DC actions; optimise by removing the accept click.**
Reduces clicks but retains three conceptual checkpoints. Rejected: the business does not
need DC involved at both the start and end of the workflow. DC's role is coordination and
final pre-Movex sign-off; engineering and management review is the substantive approval chain.

**Option B — DC acts only at the start (completeness check), remove post-implementation step.**
Rejected: the ISO 13485 post-implementation verification is a compliance requirement
(`ai/memory/07-compliance-requirements.md`). The DC must certify readiness before Movex
commits the change.

**Option C (selected) — Single DC gate immediately before Movex write; remove early DC statuses.**
Remove SUBMITTED (10) and DC_REVIEW (20). Insert `DC_APPROVED` (25) between MANAGEMENT_REVIEW
and APPROVED. This mirrors Stargile status 35 (`DC_APPROVAL_PENDING`) exactly — the DC
reviews the full change package (engineering content, all management approvals, BOM snapshot,
customer approval reference if required) and either authorises the Movex write or rejects.

The post-implementation check (currently IMPLEMENTED → CLOSED) is absorbed into this single
gate: the DC certifies everything before committing to Movex, not after. IMPLEMENTED → CLOSED
becomes automatic (Celery-driven), mirroring how APPROVED → IMPLEMENTED already works.

---

## Decision

### 1. Collapse to a single DC gate — DC_APPROVED before Movex write

**Remove SUBMITTED (10) and DC_REVIEW (20) as valid status codes.**
**Add DC_APPROVED (25) between MANAGEMENT_REVIEW (40) and APPROVED (50).**

**Updated status set (10 active statuses):**

| Code | Name | Description | Entry | Exit |
|------|------|-------------|-------|------|
| 0 | DRAFT | Being authored by originator | ECN created | Originator submits |
| 30 | ENGINEERING_REVIEW | SE/CE technical review | Originator submits | SE/CE approves or rejects |
| 40 | MANAGEMENT_REVIEW | Parallel approval block | SE/CE approves | All required approvers complete |
| 25 | DC_APPROVED | DC final sign-off before Movex write | All parallel approvals done | DC approves or rejects |
| 50 | APPROVED | All human approvals done; Movex writes queued | DC approves | Celery confirms all MI calls |
| 60 | IMPLEMENTED | All Movex writes confirmed | Outbox fully processed | System auto-advances |
| 70 | CLOSED | Post-implementation complete | Movex writes confirmed | — terminal |
| 65 | REJECTED | Any-stage rejection | Any approver rejects | Originator resubmits or withdraws |
| 80 | CANCELLED | Withdrawn; no Movex writes | Originator withdraws | — terminal |
| 90 | ON_HOLD | Suspended | DC places on hold | DC resumes |

`ARCHIVED` remains a flag (`is_archived=TRUE`) on CLOSED records only — not a status.

**IMPLEMENTED → CLOSED is now automatic** (Celery triggers it after outbox fully completes,
same pattern as APPROVED → IMPLEMENTED). No manual DC action required post-implementation.

**Updated state transition table:**

| From | Action | To | Guard | Who |
|------|--------|----|-------|-----|
| DRAFT | submit | ENGINEERING_REVIEW | Mandatory fields; ≥1 item; effectivity set on all items | Originator |
| ENGINEERING_REVIEW | approve | MANAGEMENT_REVIEW | — | SE or CE assigned |
| ENGINEERING_REVIEW | reject | REJECTED | Reason mandatory | SE or CE assigned |
| MANAGEMENT_REVIEW | approve (per role) | MANAGEMENT_REVIEW (partial) | Role required per `ecn_step_conditions` | Assigned role member |
| MANAGEMENT_REVIEW | all required approved | DC_APPROVED | All required non-skipped roles approved | System — automatic |
| DC_APPROVED | approve | APPROVED | Customer approval gate if `requires_customer_approval=TRUE` | DC assigned |
| DC_APPROVED | reject | REJECTED | Reason mandatory | DC assigned |
| APPROVED | movex_write_complete | IMPLEMENTED | All outbox entries completed | System — Celery |
| APPROVED | movex_write_failed | APPROVED (stays) | ≥1 outbox failed after 3 retries; DC alerted | System — Celery |
| IMPLEMENTED | auto_close | CLOSED | — automatic, no guard | System — Celery |
| REJECTED | resubmit | ENGINEERING_REVIEW | Originator acknowledged reason | Originator |
| REJECTED | withdraw | CANCELLED | — | Originator |
| DRAFT | cancel | CANCELLED | No Movex writes | Originator |
| ANY (not terminal) | place_on_hold | ON_HOLD | Reason mandatory | DC |
| ON_HOLD | resume | (prior status) | `pre_hold_status` set | DC |

**Self-approval prohibition unchanged**: originator cannot approve any stage of their own ECN.

**Stargile alignment:**

| Stargile status | Stargile name | OSKAR equivalent |
|----------------|--------------|-----------------|
| 5, 10 | PRELIMINARY / INITIATION | DRAFT (0) |
| 15, 20, 25 | Review pending statuses | (removed — folded into ENGINEERING_REVIEW entry) |
| 30, 55, 65 | APPROVAL_PENDING, COST_REVIEW, FINAL_APPROVAL | MANAGEMENT_REVIEW (40) |
| **35** | **DC_APPROVAL_PENDING** | **DC_APPROVED (25)** — direct alignment |
| **50** | **MOVEX_UPDATED_PENDING** | **APPROVED (50)** |
| 60 | ACTION_NOTIFICATION_PENDING | (notifications fire on transition — not a status) |
| 90, 99 | ECN_COMPLETE / ECN_CANCELLED | CLOSED (70) / CANCELLED (80) |

**Notification changes:**

| Event | Recipients |
|-------|-----------|
| DRAFT → ENGINEERING_REVIEW | SE/CE assigned |
| MANAGEMENT_REVIEW → DC_APPROVED | DC assigned |
| DC_APPROVED → APPROVED | DC, Originator |
| IMPLEMENTED → CLOSED | Originator, all approvers, observer roles RD/TE/MQ |

DC escalation timer (48h → DC + manager; 96h → EM added) starts at DC_APPROVED entry.

### 2. Per-ECN Role Customisation

**Principle:** Role assignments remain INSERT-only (ADR-003). A controlled supersede-and-insert
path is added, guarded by role authority.

**Authority:**

| Target role | Who may assign | When allowed |
|------------|----------------|-------------|
| SE, CE | DC | Before ENGINEERING_REVIEW entry |
| EM, QM, PM, SC, FN, CA | DC | Before MANAGEMENT_REVIEW entry |
| DC | DC (self-replacement to another user) | Before DC_APPROVED |

Self-assignment is prohibited. An actor cannot assign themselves to a role on an ECN they
originated. No Admin override path — if escalation is needed, the DC role holder handles it.

**New endpoint:**

```
POST /api/v1/ecn/{ecn_id}/role-assignments
Body:    { "role_id": "SE", "username": "jsmith", "notes": "Primary SE on leave" }
Response: { "assignment_id": "uuid", "superseded_id": "uuid | null", "role_id": "SE" }
```

Service layer contract:
1. Validate actor authority per table above; return 403 if insufficient.
2. If active assignment exists for role: mark `superseded_at = now()`.
3. INSERT new assignment row (`is_auto_assigned = FALSE`).
4. Both operations in a single DB transaction.
5. Append to `ecn_transition_history`: `action = "role_reassigned"`, role and new username
   in `notes`.

**Read endpoint (existing behaviour preserved):**

```
GET /api/v1/ecn/{ecn_id}/role-assignments
```

Returns current (non-superseded) assignments only. Superseded rows are in the transition history.

---

## Rationale

**Why DC_APPROVED at integer 25:** Status integers are contractually stable once rows exist
(`ai/memory/12-data-model.md §3`). Integer 25 is available (not in the current CHECK
constraint), fits between the management block (40) and the Movex write authorisation (50),
and preserves the higher-number meaning of APPROVED (50 = Movex write authorised). It also
matches Stargile's slot — status 35 was the DC gate, and 25 is positioned analogously in the
reduced status set.

**Why remove IMPLEMENTED → CLOSED as a manual DC step:** The DC_APPROVED gate consolidates
all human verification into one checkpoint. Splitting verification across DC_APPROVED and a
manual CLOSED step adds no additional control — the Movex write either succeeded or failed
deterministically; there is nothing new for the DC to verify after the outbox confirms
completion. Making IMPLEMENTED → CLOSED automatic mirrors how APPROVED → IMPLEMENTED already
works and reduces DC click burden further.

**Why ENGINEERING_REVIEW is now the direct submission target:** Removing SUBMITTED and
DC_REVIEW eliminates two statuses that had no substantive human decision attached (SUBMITTED
was a queue; DC_REVIEW was replaced by the consolidated DC_APPROVED gate). The originator's
submission already creates a transition history record capturing actor, timestamp, and intent.

**Why no Admin override path for role assignment:** The current scope has no emergency ECN
path and no Admin role for fast-tracking workflow (see §6 of `ai/memory/06-ecn-requirements.md`
for emergency ECN — deferred to Sprint 2+). Adding an Admin override now would create
authority without a defined use case, which is a security anti-pattern per
`ai/memory/08-security-controls.md`.

---

## Consequences

### Schema changes (migration 0006)

- `ecn_instances` CHECK constraint on `status`: replace
  `(0,10,20,30,40,50,60,65,70,80,90)` with `(0,25,30,40,50,60,65,70,80,90)`.
- `ecn_instances` CHECK constraint on `pre_hold_status`: same replacement.
- Integers 10 and 20 are tombstoned — not reused for any future status.
- No new columns required for this ADR.

### Code changes (Sprint 2)

- `src/workflow/machine.py`:
  - Remove `SUBMITTED` and `DC_REVIEW` from `ECNStatus`; add `DC_APPROVED = 25`.
  - Update `_STATE_NAMES` and `_TRANSITIONS`: remove `accept` and `pass_to_engineering`;
    update `submit` dest → `"ENGINEERING_REVIEW"`; add `dc_approve` trigger
    (DC_APPROVED → APPROVED, `_guard_dc_approve` for customer approval ISO gate);
    add `auto_close` trigger (IMPLEMENTED → CLOSED, no guard);
    update `cancel` source list (remove SUBMITTED, DC_REVIEW);
    update `place_on_hold` source list.
  - Move `_guard_close` logic → `_guard_dc_approve`.
- `src/routers/ecn.py`: remove `/accept` and `/pass` endpoints; add `/dc-approve` and
  `/role-assignments` endpoints.
- `src/services/ecn.py`: remove `accept` and `pass_to_engineering`; add `dc_approve`
  and `assign_role` with authority guard.
- `tests/workflow/test_machine.py`: replace SUBMITTED/DC_REVIEW tests with
  DC_APPROVED and auto_close tests.
- `tests/routers/test_ecn.py`: replace accept/pass tests with dc-approve and
  role-assignment tests.
- `ai/memory/06-ecn-requirements.md` §1–3: update status table, transition table, approval chain.
- `ai/memory/12-data-model.md` §3: update status codes.
- `ai/memory/03-oskar-architecture.md` §14: update workflow diagram.

### IQ/OQ/PQ impact

IQ test for the status machine: update status set (Manal — IQ author).
OQ test cases OQ-10 through OQ-25 (SUBMITTED and DC_REVIEW state tests): replace with
DC_APPROVED and auto_close cases.
Notify Divya (QM): ISO 13485 §7.3.9 customer approval gate relocates to DC_APPROVED.

### Backward compatibility

No production rows exist. The CHECK constraint narrowing (removing 10 and 20, adding 25)
is safe. If applied to a future live system, a pre-check is required:
`SELECT COUNT(*) FROM ecn_instances WHERE status IN (10, 20)` must return 0.
