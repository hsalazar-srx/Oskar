# Oskar — Data Model Reference Card

Quick-reference for engineers working with the Oskar database schema.

---

## Status Codes

| Code | Constant | Meaning | Terminal? |
|------|----------|---------|-----------|
| 0 | `DRAFT` | Created, not yet submitted | No |
| 25 | `DC_APPROVED` | All managers approved; DC gate | No |
| 30 | `ENGINEERING_REVIEW` | Pending SE/CE technical sign-off | No |
| 40 | `MANAGEMENT_REVIEW` | Parallel approvals running | No |
| 50 | `APPROVED` | All approved; pending implementation | No |
| 60 | `IMPLEMENTED` | Movex MI calls in flight | No |
| 65 | `REJECTED` | Rejected at any stage | No (resubmittable) |
| 70 | `CLOSED` | Movex writes complete; training created | **Yes** |
| 80 | `CANCELLED` | Withdrawn by originator | **Yes** |
| 90 | `ON_HOLD` | Paused; `pre_hold_status` stores prior state | No |

> Numeric codes are stored in `ecn_instances.status` as integers.  
> Use the `ECNStatus` enum from `src/workflow/machine.py` — never raw integers in application code.

---

## Role Codes

| Code | Full Title | Required At | Condition |
|------|------------|-------------|-----------|
| `OR` | Originator | DRAFT creation | Always (creator) |
| `SE` | Senior Engineer | ENGINEERING_REVIEW | Always |
| `CE` | Chief Engineer | ENGINEERING_REVIEW | Alternative to SE |
| `EM` | Engineering Manager | MANAGEMENT_REVIEW | Always |
| `QM` | Quality Manager | MANAGEMENT_REVIEW | Always (ISO 13485) |
| `PM` | Product Manager | MANAGEMENT_REVIEW | `affects_product = true` |
| `SC` | Supply Chain Manager | MANAGEMENT_REVIEW | `affects_supply_chain = true` |
| `FN` | Finance Manager | MANAGEMENT_REVIEW | `affects_cost = true` |
| `DC` | Document Controller | DC_APPROVED | Always |
| `AD` | Admin | Any stage | Override capability |
| `CA`, `RD`, `TE`, `MQ` | Reserved | Future iterations | — |

> Routing conditions for MANAGEMENT_REVIEW are driven by the `ecn_step_conditions` table,
> not hardcoded in Python. To add a new conditional role, insert a row — no code change needed.

---

## Facility Codes

| Code | Location | Notes |
|------|----------|-------|
| `D` | Melbourne, Australia | **Default** — ECNs originate from Melbourne engineering team |
| `L` | Johor Bahru, Malaysia | Manufacturing site |
| _(future)_ | Other Scanfil sites | Facility-scoped; each site has own `ecn_step_conditions` rows |

---

## Table Reference

### `ecn_instances` — ECN Header

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | Oskar internal ID |
| `ecn_number` | VARCHAR | Human-readable (ECN-2026-0001) |
| `title` | VARCHAR | Short description |
| `description` | TEXT | Full technical justification |
| `status` | INT | See Status Codes above |
| `facility` | VARCHAR | Facility code (e.g., `L`) |
| `affects_product` | BOOL | Triggers `PM` approval step |
| `affects_supply_chain` | BOOL | Triggers `SC` approval step |
| `affects_cost` | BOOL | Triggers `FN` approval step |
| `requires_customer_approval` | BOOL | DC must confirm customer sign-off |
| `pre_hold_status` | INT | Status before ON_HOLD; restored on resume |
| `created_by` | VARCHAR | AD username of originator |
| `created_at` | TIMESTAMPTZ | |
| `updated_at` | TIMESTAMPTZ | Used for optimistic locking (ADR-008) |

---

### `ecn_role_assignments` — Who Approves What

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | |
| `ecn_id` | UUID FK | → ecn_instances |
| `role_code` | VARCHAR | e.g., `QM` |
| `assigned_to` | VARCHAR | AD username |
| `assigned_by` | VARCHAR | AD username of assigner |
| `assigned_at` | TIMESTAMPTZ | |
| `superseded_at` | TIMESTAMPTZ | NULL = current assignment |

> **Important:** Role reassignment uses INSERT + supersede pattern (ADR-003). Records are
> never updated or deleted. Query `WHERE superseded_at IS NULL` for current assignments.

---

### `ecn_approval_steps` — Per-Stage Approval Records

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | |
| `ecn_id` | UUID FK | |
| `stage` | VARCHAR | Stage name (e.g., `MANAGEMENT_REVIEW`) |
| `role_code` | VARCHAR | e.g., `EM` |
| `status` | VARCHAR | `pending` / `approved` / `rejected` / `skipped` |
| `decided_by` | VARCHAR | AD username |
| `decided_at` | TIMESTAMPTZ | |
| `notes` | TEXT | Optional approver notes |

---

### `ecn_transition_history` — Immutable Audit Chain

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | |
| `ecn_id` | UUID FK | |
| `from_status` | INT | Status before transition |
| `to_status` | INT | Status after transition |
| `actor` | VARCHAR | AD username |
| `action` | VARCHAR | Trigger action name |
| `notes` | TEXT | Optional actor notes |
| `sha256_hash` | VARCHAR(64) | SHA-256 over all fields (canonical JSON) |
| `sha256_prev` | VARCHAR(64) | Hash of previous row (NULL for first row) |
| `transitioned_at` | TIMESTAMPTZ | |

> **RLS enforced:** INSERT-only. No UPDATE or DELETE is possible, even for admin users.
> Auditors can verify the chain by recomputing each hash and checking the linked list.

---

### `movex_outbox` — Transactional Outbox

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | |
| `ecn_id` | UUID FK | |
| `status` | VARCHAR | `pending` / `processing` / `completed` / `failed` / `abandoned` |
| `mi_calls` | JSONB | Array of MI call specs to execute |
| `attempt_count` | INT | Incremented on each retry |
| `last_error` | TEXT | Last exception message |
| `next_attempt_at` | TIMESTAMPTZ | Used by Celery scheduler |
| `created_at` | TIMESTAMPTZ | |
| `completed_at` | TIMESTAMPTZ | NULL until success |

> Retry schedule: attempt 1 = 30 s, attempt 2 = 5 min, attempt 3 = 30 min (DC alert sent),
> attempt 10 = abandoned (DC must intervene).

---

### `ecn_items` — ECN Line Items

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | |
| `ecn_id` | UUID FK | |
| `item_number` | VARCHAR | Scanfil internal stock code (Movex MITMAS.MMITNO) |
| `customer_part_number` | VARCHAR | Optional CPN (for reverse alias lookup) |
| `change_type` | VARCHAR | `add` / `change` / `delete` |
| `effectivity_date` | DATE | When change takes effect |
| `notes` | TEXT | |

---

### `ecn_mpns` — Manufacturer Part Number Aliases

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | |
| `item_id` | UUID FK | → ecn_items |
| `mpn` | VARCHAR | Manufacturer Part Number |
| `manufacturer` | VARCHAR | e.g., `Nichicon` |
| `lifecycle_status` | VARCHAR | `active` / `nrnd` / `eol` |
| `eol_date` | DATE | End-of-life date if known |
| `do_not_buy` | BOOL | Sourcing flag |
| `supplier_data` | JSONB | Raw DigiKey / Nexar enrichment payload |

---

### `ecn_step_conditions` — Data-Driven Routing

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | |
| `facility` | VARCHAR | Scope to facility (e.g., `L`) |
| `role_code` | VARCHAR | Role to conditionally require |
| `condition_field` | VARCHAR | Column in `ecn_instances` that triggers this role |
| `stage` | VARCHAR | Stage where this condition applies |

> Seed data (migration 0002): 7 rows for facility `L`. The workflow engine reads these at
> runtime to determine which approval steps to create.

---

### `ecn_training_acknowledgements` — ISO 13485 §6.2

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | |
| `ecn_id` | UUID FK | |
| `username` | VARCHAR | Engineer who must acknowledge |
| `acknowledged_at` | TIMESTAMPTZ | NULL until acknowledged |
| `created_at` | TIMESTAMPTZ | Populated when ECN reaches CLOSED |

---

## Key Constraints & Rules

| Rule | Enforcement |
|------|-------------|
| Self-approval prohibited | Application layer check in `services/ecn/workflow.py` |
| Audit chain INSERT-only | PostgreSQL RLS policy (migration 0003) |
| Role assignments supersede-not-update | Application layer; supersede pattern |
| Optimistic locking on ECN edits | `If-Unmodified-Since` header → 409 on stale (ADR-008) |
| CONO in all Movex queries | `MovexRestAdapter` always appends CONO from config |
| UUID PKs everywhere | All tables use `gen_random_uuid()` as default |

---

## Useful Diagnostic Queries

```sql
-- All active ECNs waiting for action
SELECT ecn_number, status, updated_at
FROM ecn_instances
WHERE status NOT IN (70, 80)  -- not CLOSED or CANCELLED
ORDER BY updated_at;

-- Current role assignments for an ECN
SELECT role_code, assigned_to, assigned_at
FROM ecn_role_assignments
WHERE ecn_id = '<uuid>' AND superseded_at IS NULL;

-- Pending approval steps for an ECN
SELECT stage, role_code, status
FROM ecn_approval_steps
WHERE ecn_id = '<uuid>' AND status = 'pending';

-- Outbox entries in retry/failed state
SELECT ecn_id, status, attempt_count, last_error, next_attempt_at
FROM movex_outbox
WHERE status IN ('failed', 'processing', 'abandoned')
ORDER BY next_attempt_at;

-- Full audit trail for an ECN (verify chain)
SELECT from_status, to_status, actor, sha256_hash, sha256_prev, transitioned_at
FROM ecn_transition_history
WHERE ecn_id = '<uuid>'
ORDER BY transitioned_at;
```
