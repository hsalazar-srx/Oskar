# ECN Lifecycle Walkthrough — Step by Step

This document follows a single Engineering Change Notice from the moment an engineer decides
a component needs to change all the way to its permanent record in Movex. It is written for
engineers who are new to the platform and want to understand both the **what** and the **why**
behind each step.

---

## Background: What Is an ECN?

An **Engineering Change Notice (ECN)** is the formal record that a product design, bill of
materials, or manufacturing process has been modified. At Scanfil APAC:

- Every change to a released component must be controlled — required by **ISO 13485** (medical),
  **IATF 16949** (automotive), and **ISO 9001** (general quality).
- The old system (Stargile) had no retry on Movex writes, no email notifications, and ECNs
  regularly got stuck with no way to tell why.
- Oskar replaces all of that with a transparent, auditable, retrying workflow.

---

## The Cast: Who Does What

| Role Code | Title | Responsibility |
|-----------|-------|----------------|
| `OR` | Originator | Creates the ECN, resubmits rejections |
| `SE` / `CE` | Senior / Chief Engineer | Technical review gate |
| `EM` | Engineering Manager | Always required at Management Review |
| `QM` | Quality Manager | Always required at Management Review (ISO 13485) |
| `PM` | Product Manager | Required if ECN affects product scope |
| `SC` | Supply Chain Manager | Required if ECN affects supply chain |
| `FN` | Finance Manager | Required if ECN affects cost |
| `DC` | Document Controller | Single gate before Movex write; can reassign roles, pause, resume |
| `AD` | Admin | Override capability; pause/resume any ECN |

> **Important:** The roles at Management Review (`PM`, `SC`, `FN`) are determined by flags on
> the ECN itself (`affects_product`, `affects_supply_chain`, `affects_cost`). The routing logic
> lives in the `ecn_step_conditions` table — **not** in application code. This means adding a new
> conditional role in future only requires a database insert, not a code change.

---

## The Happy Path: Full Walkthrough

### Step 1 — Draft (Originator)

**What happens:**  
An engineer submits a new ECN via the Create form. The ECN is saved with `status = 0 (DRAFT)`.
The system auto-assigns roles based on `system_role_users` (e.g., the current `SE` for that
facility is looked up from the table and set as the assignee).

**Key data recorded:**
- Title and description
- Facility code (e.g., `D` = Melbourne, `L` = Johor Bahru)
- Scope flags: `affects_product`, `affects_supply_chain`, `affects_cost`
- `requires_customer_approval` flag (triggers the DC single gate to hold an extra review)
- Items (stock codes) and any MPN/supplier aliases
- Routing operations (manufacturing steps to be changed)

**Code path:**  
`POST /api/v1/ecn/` → `routers/ecn_core.py` → `services/ecn/service.py:create_ecn()`

---

### Step 2 — Submit for Engineering Review (Originator)

**What happens:**  
The Originator clicks **Submit**. The workflow machine transitions `DRAFT → ENGINEERING_REVIEW`.
An email notification goes to the assigned `SE`/`CE`.

**Validation enforced:**
- At least one item must be attached to the ECN.
- The Originator cannot approve their own ECN (self-approval prohibition).

**Code path:**  
`PATCH /api/v1/ecn/{id}/status` body: `{"action": "submit"}` → `workflow/machine.py:ECNWorkflowMachine.submit()`

**Audit record created:**  
`ecn_transition_history` row inserted — SHA-256 hash over (ecn_id, from_status, to_status, actor,
timestamp, all field values). The `sha256_prev` field links to the previous row, forming a tamper-evident chain.

---

### Step 3 — Engineering Review (SE / CE)

**What happens:**  
The Senior Engineer reviews the technical content of the ECN (design rationale, drawings, items).
They may:
- **Approve their role** → the step is marked `approved`.
- **Reject the ECN** → status moves to `REJECTED` (see Rejection Path below).

When all required Engineering roles are approved, the workflow automatically advances to
`MANAGEMENT_REVIEW`.

**Code path:**  
`PATCH /api/v1/ecn/{id}/status` body: `{"action": "approve_role", "role_code": "SE"}` →
`services/ecn/workflow.py:approve_role_step()`

---

### Step 4 — Management Review (EM, QM + conditional)

**What happens:**  
This is the **parallel approval block** — the most complex part of the workflow.

The following roles run concurrently (any order, any time):

| Role | Required? | Condition |
|------|-----------|-----------|
| `EM` | Always | — |
| `QM` | Always | ISO 13485 §4.1 |
| `PM` | Conditional | `affects_product = true` |
| `SC` | Conditional | `affects_supply_chain = true` |
| `FN` | Conditional | `affects_cost = true` |

The system tracks each role's `ecn_approval_steps` record separately. When the **last pending
step** is approved, a special internal transition `complete_management_review` fires automatically,
moving the ECN to `DC_APPROVED`.

**Why parallel?** A sequential chain would be slower. The DC needs all managers to sign, but there
is no reason for QM to wait for EM to finish first.

**Code path:**  
Each approver: `PATCH /api/v1/ecn/{id}/status` `{"action": "approve_role", "role_code": "QM"}`  
Auto-advance: `services/ecn/workflow.py:_check_management_review_complete()`

---

### Step 5 — DC Single Gate (Document Controller)

**What happens:**  
This is the most important gate in the entire system. The DC reviews:
- All approvals are present and correctly recorded.
- If `requires_customer_approval = true`, customer sign-off has been obtained (recorded as a
  separate flag by the DC before approving).
- The ECN is technically accurate and meets quality documentation standards.

The DC then clicks **DC Approve** → `DC_APPROVED → APPROVED`.

**Why is this gate here?** (ADR-009)  
The DC is the last human check before the system writes irreversible data into Movex. This gate
enforces the **non-negotiable rule**: *no Movex write without explicit human approval*.

**Code path:**  
`PATCH /api/v1/ecn/{id}/status` `{"action": "dc_approve"}`

---

### Step 6 — Mark Implemented (DC → triggers Movex writes)

**What happens:**  
The DC marks the ECN as Implemented once the physical change has been enacted. This triggers the
**Transactional Outbox** pattern:

1. Database transaction commits atomically:
   - `ecn_instances.status` → `IMPLEMENTED`
   - `ecn_transition_history` — new SHA-256 row
   - `movex_outbox` — new row with `status=pending`, `mi_calls=[...]` (array of MI API calls)

2. Celery picks up the outbox row (polls every 30 seconds).

3. Celery sends each MI call via `movex-rest-api` → Movex.

4. On success: outbox row → `completed`; ECN → `IMPLEMENTED` (already set; Celery confirms).

5. On failure: retry at 30 s → 5 min → 30 min. At attempt 3, DC receives an alert email. At
   attempt 10, outbox is marked `abandoned` and DC must investigate via the admin error panel.

**Why the Outbox pattern?**  
Without it, a crash between the API response and the MI call would leave the ECN approved in
Oskar but unchanged in Movex. The Outbox ensures the write is **at-least-once**: if Celery
crashes, the pending outbox row survives the restart and is retried.

**Code path:**  
`PATCH /api/v1/ecn/{id}/status` `{"action": "mark_implemented"}` → `tasks/movex_outbox.py`

---

### Step 7 — Auto-Close (Celery)

**What happens:**  
Once all Movex MI calls complete, Celery automatically transitions `IMPLEMENTED → CLOSED`.
At this point:
- An `ecn_training_acknowledgements` row is created for every engineer who needs to
  acknowledge the change (ISO 13485 §6.2 training requirement).
- The ECN enters terminal state — no further transitions are possible.

**Code path:**  
`tasks/movex_outbox.py:_complete_outbox()` → `workflow/machine.py:auto_close()`

---

## Exception Paths

### Rejection & Rework

Any approver at any stage can reject an ECN. When they do:
1. Status → `REJECTED`.
2. Mandatory rejection reason recorded in `ecn_rejections`.
3. An email goes to the Originator with the reason.
4. The Originator reviews and either:
   - **Resubmit** (resolution = `restart`) → back to `ENGINEERING_REVIEW` for a full re-review.
   - **Withdraw** → `CANCELLED` (terminal).

```
ENGINEERING_REVIEW ──reject──► REJECTED ──resubmit──► ENGINEERING_REVIEW
MANAGEMENT_REVIEW  ──reject──► REJECTED ──resubmit──► ENGINEERING_REVIEW
DC_APPROVED        ──reject──► REJECTED ──resubmit──► ENGINEERING_REVIEW
APPROVED           ──reject──► REJECTED ──withdraw──► CANCELLED
```

### On-Hold / Resume

DC or Admin can pause any non-terminal ECN:
1. Status → `ON_HOLD`; `pre_hold_status` is stored in the DB row.
2. All pending tasks (Celery jobs for this ECN) are paused.
3. Resume → status restored to `pre_hold_status`.

This is used when an ECN is blocked on an external event (waiting for customer drawing, waiting
for supplier quote, key approver on leave, etc.).

---

## What the Code Does on Each Transition

Every status transition goes through this pipeline:

```
PATCH /api/v1/ecn/{id}/status
     │
     ▼
routers/ecn_core.py          ← validates request, extracts actor from JWT
     │
     ▼
services/ecn/workflow.py     ← authorisation: can this role perform this action now?
     │
     ▼
workflow/machine.py          ← ECNWorkflowMachine: is the transition valid from current state?
     │
     ▼
                  ┌─────────────────────────────────┐
                  │   PostgreSQL TRANSACTION         │
                  │   ┌──────────────────────────┐  │
                  │   │ UPDATE ecn_instances     │  │
                  │   │ INSERT transition_history│  │
                  │   │ INSERT movex_outbox (*)  │  │
                  │   │ UPDATE approval_steps    │  │
                  │   └──────────────────────────┘  │
                  └─────────────────────────────────┘
                              │
                              ▼
                  PostgreSQL NOTIFY 'ecn_updates'
                              │
                              ▼
                  SSE stream → FE updates without polling
```

> `(*)` Outbox row only created on `mark_implemented` action.

---

## Self-Check Questions

1. Which roles are **always** required at Management Review, and why?
2. What prevents an engineer from approving their own ECN?
3. If Celery crashes after writing the `movex_outbox` row but before calling Movex, what happens next?
4. What is the difference between `REJECTED` and `CANCELLED`?
5. What triggers the creation of training acknowledgement records?
6. Where does the routing condition for `FN` (Finance Manager) live in the codebase — in Python code or in the database?
