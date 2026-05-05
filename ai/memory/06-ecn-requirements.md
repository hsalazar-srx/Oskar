# OSKAR — ECN Behavioural Specification

> **PROVIDER-AGNOSTIC — Non-Negotiable #12**
> No tool-specific syntax. Readable by any LLM tool or none.

**Version:** 1.2
**Date:** 2026-05-04
**Phase:** Phase 1 Track B deliverable
**Status:** Draft — pending Branko/Nick UAT validation (post-POC)

**Sources:**
- `ai/memory/05-stargile-ecn-reference.md` — Stargile ground truth (DDL, statuses, roles, MI calls, graph analysis)
- `ai/memory/03-oskar-architecture.md` — Platform architecture (12-table schema, workflow engine, RBAC model)
- `.providers/claude/skills/Tier1/oskar-ecn-rules.md` — State machine rules reference
- `context/OSKAR_Integrated_Plan_v5.1.md` Section 11b — expert review findings (2026-04-10)
- `decisions/ADR-002` (workflow engine), `ADR-003` (RBAC), `ADR-004` (audit chain), `ADR-005` (ERP write gate)

**Scope:** OSKAR Iteration 1 — ECN module only. BOM and Supplier modules are Iterations 2–3.

**Reading guide:** This is the OSKAR forward-looking spec. It does NOT duplicate Stargile DDL — reference `ai/memory/05-stargile-ecn-reference.md` for field-by-field Stargile detail. This spec defines what OSKAR builds and why.

---

## 1. ECN Status Machine — 10 Statuses

> **ADR-009 (2026-05-01):** DC single gate. SUBMITTED (10) and DC_REVIEW (20) removed.
> DC_APPROVED (25) added between MANAGEMENT_REVIEW and APPROVED.
> IMPLEMENTED → CLOSED is now automatic (Celery). See `decisions/ADR-009`.

### Status Table

| Code | Name | Description | Entry condition | Exit condition |
|------|------|-------------|----------------|---------------|
| 0 | DRAFT | Being authored by originator | ECN created | Originator submits |
| 30 | ENGINEERING_REVIEW | SE/CE technical review in progress | Originator submits | SE/CE approves or rejects |
| 40 | MANAGEMENT_REVIEW | Parallel approval block active (EM + QM always; PM/SC/FN conditional) | SE/CE approves | All required approvers complete |
| 25 | DC_APPROVED | DC final sign-off before Movex write | All parallel approvals done | DC approves or rejects |
| 50 | APPROVED | All human approvals complete; Movex writes queued in outbox | DC approves | Celery confirms all MI calls succeeded |
| 60 | IMPLEMENTED | All Movex writes confirmed by Celery | Outbox fully processed | System auto-advances to CLOSED |
| 70 | CLOSED | Post-implementation complete; ISO 13485 gate | Movex writes confirmed | — terminal |
| 65 | REJECTED | Rejected at any stage; routed back to originator with mandatory reason | Any approver rejects | Originator resubmits (→ ENGINEERING_REVIEW) or withdraws (→ CANCELLED) |
| 80 | CANCELLED | Withdrawn before approval; no Movex writes made | Originator withdraws | — terminal |
| 90 | ON_HOLD | Suspended pending external input | DC places on hold | DC resumes; prior status restored |
| — | ARCHIVED | Logical flag (`is_archived=TRUE`); not a status | CLOSED records only | — irreversible flag, not a status transition |

**ARCHIVED is a flag, not a status.** Set by DC on CLOSED records only. No state machine transition involved.

**Tombstoned integers:** 10 (SUBMITTED) and 20 (DC_REVIEW) are removed from the valid set and must never be reused.

### Stargile → OSKAR Status Mapping

| Stargile code | Stargile name | OSKAR equivalent | Collapse rationale |
|--------------|--------------|-----------------|-------------------|
| 5 | PRELIMINARY | DRAFT (0) | No separate preliminary step needed |
| 10 | INITIATION | DRAFT (0) | Originator fills header in DRAFT |
| 15, 20, 25 | Review pending statuses | (removed) | Folded into ENGINEERING_REVIEW entry — no separate DC gate at submission |
| 30, 55, 65 | APPROVAL_PENDING, COST_REVIEW, FINAL_APPROVAL | MANAGEMENT_REVIEW (40) | Parallel block covers all |
| **35** | **DC_APPROVAL_PENDING** | **DC_APPROVED (25)** | Single DC gate immediately before Movex write — exact Stargile alignment |
| **50** | **MOVEX_UPDATED_PENDING** | **APPROVED (50)** | Human approvals done; outbox queued |
| 60 | ACTION_NOTIFICATION_PENDING | (removed) | Notifications fire on transition — not a status |
| 90 | ECN_COMPLETE | CLOSED (70) | |
| 99 | ECN_CANCELLED | CANCELLED (80) | |

---

## 2. State Transition Table

> **ADR-009 (2026-05-01):** accept and pass_to_engineering triggers removed; dc_approve and auto_close added.

| From | Action | To | Guard conditions | Who triggers |
|------|--------|----|-----------------|-------------|
| DRAFT | submit | ENGINEERING_REVIEW | All mandatory header fields populated; ≥1 ECN item defined; `effectivity_type` set on all items | Originator |
| ENGINEERING_REVIEW | approve | MANAGEMENT_REVIEW | — | SE or CE assigned to this ECN |
| ENGINEERING_REVIEW | reject | REJECTED | Rejection reason mandatory | SE or CE assigned to this ECN |
| MANAGEMENT_REVIEW | approve (per role) | — partial, parallel block | Role must be required for this ECN per `ecn_step_conditions` | Assigned role member |
| MANAGEMENT_REVIEW | all required approved | DC_APPROVED | All required non-skipped roles approved; no outstanding rejections | System — automatic on last approval |
| MANAGEMENT_REVIEW | reject (any role) | REJECTED | Rejection reason mandatory | Any required role member |
| DC_APPROVED | dc_approve | APPROVED | Customer approval gate if `requires_customer_approval=TRUE` and `customer_approved_at IS NULL` | DC assigned to this ECN |
| DC_APPROVED | reject | REJECTED | Rejection reason mandatory | DC assigned to this ECN |
| APPROVED | movex_write_complete | IMPLEMENTED | All `movex_outbox` entries for this ECN in `completed` state | System — Celery worker |
| APPROVED | movex_write_failed | APPROVED (stays) | ≥1 outbox entry in `failed` after 3 retries; DC alerted | System — Celery worker |
| IMPLEMENTED | auto_close | CLOSED | — automatic, no human action required | System — Celery worker |
| REJECTED | resubmit | ENGINEERING_REVIEW | Originator acknowledged rejection reason | Originator |
| REJECTED | withdraw | CANCELLED | — | Originator |
| ANY (not CLOSED/CANCELLED) | place_on_hold | ON_HOLD | Reason + expected resume date mandatory | DC |
| ON_HOLD | resume | (prior status) | Prior status stored in `ecn_instances.pre_hold_status` | DC |
| DRAFT | cancel | CANCELLED | No Movex writes made for this ECN | Originator |

**Self-approval prohibition:** The originator cannot approve any stage of their own ECN regardless of role. Enforced at the application layer on every approval endpoint — not only in the state machine guard.

---

## 3. Approval Chain

> **ADR-009 (2026-05-01):** DC acts once — at DC_APPROVED, immediately before Movex write.

```
DRAFT
  └─► [Originator: submit] ──► ENGINEERING_REVIEW
                                  └─► [SE/CE: technical review]
                                        └─► [Parallel block — all required simultaneously]
                                              EM  (always required)
                                              QM  (always required — ISO 13485)
                                              PM  (if routing_changes=TRUE or operation_changes=TRUE)
                                              SC  (if new_parts=TRUE or lead_time_changes=TRUE)
                                              FN  (if wapc_delta_pct > configured threshold)
                                            ──► MANAGEMENT_REVIEW
                                                  └─► [All required approved — system auto-advances] ──► DC_APPROVED
                                                                                                           └─► [DC: final sign-off before Movex write] ──► APPROVED
                                                                                                                                                            └─► [Celery: Movex outbox] ──► IMPLEMENTED
                                                                                                                                                                                            └─► [Celery: auto-close] ──► CLOSED
```

### Parallel Block Rules

- All required roles receive work items **simultaneously** on MANAGEMENT_REVIEW entry.
- Roles whose condition evaluates to FALSE get their `ecn_approval_steps` record set to `skipped=TRUE` automatically — not notified, not required.
- MANAGEMENT_REVIEW → DC_APPROVED fires automatically when the last required non-skipped approver completes.
- **Any single rejection** at MANAGEMENT_REVIEW sends the ECN to REJECTED immediately.
- On proceed-path resubmit: only the rejecting role's step resets; other approvals are preserved.

### Sequential vs Parallel

| Stage | Type | Reason |
|-------|------|--------|
| DRAFT → ENGINEERING_REVIEW | Sequential (submit) | Originator submits; goes directly to engineering — no DC gate at submission (ADR-009) |
| MANAGEMENT_REVIEW | Parallel | All management roles have equal standing; eliminates sequential bottleneck |
| DC_APPROVED → APPROVED | Sequential (DC gate) | DC certifies the full change package before Movex write is authorised |
| APPROVED → IMPLEMENTED | Automatic (Celery) | Movex write execution — not a human decision |
| IMPLEMENTED → CLOSED | Automatic (Celery) | auto_close; no DC action required post-Movex write (ADR-009) |

---

## 4. Role Definitions

### Active Roles (11)

| Role ID | Name | Abbreviation | Required when | Notes |
|---------|------|-------------|--------------|-------|
| DC | Document Controller | DC | All ECNs — every gate | Mandatory; coordinates entire workflow |
| OR | Originator | OR | All ECNs | Submits, resubmits, cancels own ECNs |
| SE | Systems / Senior Engineer | SE | ENGINEERING_REVIEW | Technical review |
| CE | Chief Engineer | CE | ENGINEERING_REVIEW | Escalation path; co-reviews with SE |
| EM | Engineering Manager | EM | MANAGEMENT_REVIEW — always | Required in all parallel blocks |
| QM | Quality Manager | QM | MANAGEMENT_REVIEW — always | Required (ISO 13485) |
| PM | Production Manager | PM | MANAGEMENT_REVIEW — conditional | If `routing_changes=TRUE` or `operation_changes=TRUE` |
| SC | Supply Chain / Purchasing | SC | MANAGEMENT_REVIEW — conditional | If `new_parts=TRUE` or `lead_time_changes=TRUE` |
| FN | Finance | FN | MANAGEMENT_REVIEW — conditional | If `wapc_delta_pct` > configured threshold |
| AD | Admin | AD | Platform admin only | ON_HOLD control, assignment override — no approval authority |
| CA | Cost Accountant | CA | MANAGEMENT_REVIEW | Reviews cost fields — no veto; observer-plus |

### Observer Roles (3)

| Role ID | Name | When notified |
|---------|------|--------------|
| RD | R&D / Product Engineering | ECN affects their product family |
| TE | Test Engineering | ECN includes test/document changes (`change_to_documents=TRUE`) |
| MQ | Manufacturing Quality | ECN reaches CLOSED |

### Retired Stargile Roles

| Stargile role | Reason retired |
|--------------|---------------|
| MG (Management) | Absorbed into EM |
| HR (Human Resources) | Never used in ECN workflow |
| QT (Quotations) | Preliminary review — OSKAR has no preliminary step |
| PE (Production Engineer) | Absorbed into PM |
| SM (SMT Engineer) | Absorbed into SE |

### Role-to-AD Group Mapping

| OSKAR Role(s) | AD Group |
|--------------|---------|
| DC, SE, CE, EM, PM, QM, SC, FN, CA | `OSKAR-Approvers` |
| OR, RD, TE, MQ | `OSKAR-Engineers` |
| AD | `OSKAR-Admins` |

Per-ECN role assignment is derived from `system_role_users` table at ECN creation — not from the JWT AD group claim alone.

---

## 5. ECNItem Field Specification

OSKAR `ecn_items` table is the equivalent of Stargile `ZECNITMN` + `ECNItem.java` DTO (see `ai/memory/05-stargile-ecn-reference.md` §8.1 for graph analysis detail).

| Field | PostgreSQL type | Nullable | Who populates | Notes |
|-------|----------------|---------|--------------|-------|
| `id` | UUID | No | System | Primary key |
| `ecn_id` | UUID | No | System | FK → `ecn_instances` |
| `line_number` | INTEGER | No | System | Auto-increment per ECN |
| `is_new_item` | BOOLEAN | No | Originator | Drives `PDS001MI.AddProduct` at APPROVED |
| `item_number` | VARCHAR(15) | No | Originator | MITMAS.MMITNO |
| `item_status` | VARCHAR(2) | Yes | Originator | 20=active, 90=inactive |
| `item_name` | VARCHAR(30) | Yes | Originator | MITMAS.MMITDS |
| `description_2` | VARCHAR(60) | Yes | Originator | MITMAS.MMFUDS |
| `drawing_number` | VARCHAR(20) | Yes | System / Originator | Auto-created via MPDDOC template when `is_new_item=TRUE` |
| `drawing_created` | BOOLEAN | No | System | TRUE when MPDDOC entry confirmed |
| `procurement_group` | VARCHAR(3) | Yes | Originator | MITMAS.MMPRGP |
| `product_group` | VARCHAR(5) | Yes | Originator | MITMAS.MMITCL |
| `item_group` | VARCHAR(3) | Yes | Originator | 3-char item group code. Used as ALWQ qualifier in MMS025MI.AddAlias. Distinct from product_group. Added migration 0006. |
| `customer_alias` | VARCHAR(30) | Yes | Originator | Customer-assigned alias / MPN for this item. Maps to MITPOP.POPN (MMS025MI.AddAlias). Promoted from questionnaire_data JSONB, migration 0006. |
| `unit_of_measure` | VARCHAR(3) | Yes | Originator | MITMAS.MMUNMS |
| `revision_number` | VARCHAR(4) | Yes | Originator | MITMAS.MMECVE |
| `item_template` | VARCHAR(15) | Yes | Originator | MITMAS.MMATPL |
| `supplier_number` | VARCHAR(10) | Yes | Originator | MITMAS.MMSUNO |
| `responsible_engineer` | VARCHAR(10) | Yes | Originator | MITMAS.MMRESP |
| `buyer` | VARCHAR(10) | Yes | Originator | MITMAS.MMBUYE |
| `purchase_price` | DECIMAL(17,6) | Yes | Purchasing | MITMAS.MMPUPR |
| `lead_time_days` | INTEGER | Yes | Originator / SC | MITMAS.MMLEA1 |
| `lead_time_internal` | INTEGER | Yes | Originator | MITMAS.MMLEA4 |
| `safety_lead_time` | INTEGER | Yes | Originator | MITMAS.MMSATD |
| `business_area` | VARCHAR(3) | Yes | Originator | MITMAS.MMBUAR |
| `wapc` | DECIMAL(17,6) | Yes | Purchasing | Weighted avg purchase cost — FN gate input |
| `alias_written` | BOOLEAN | No | System | TRUE when `MMS025MI.AddAlias` confirmed for all MPNs |
| **`effectivity_type`** | VARCHAR(10) | **No** | Originator | **ISO 13485 mandatory.** Values: `DATE`, `ECN`, `IMMEDIATE` |
| **`effectivity_from`** | DATE | Yes | Originator | Required when `effectivity_type=DATE`. ISO 13485 §4.2.5. |
| `questionnaire_data` | JSONB | Yes | Originator | ZQ01–ZQ18 equivalent — JSONB safety valve; UI deferred post-POC |
| `created_at` | TIMESTAMPTZ | No | System | |
| `updated_at` | TIMESTAMPTZ | No | System | |

`effectivity_type` and `effectivity_from` are validated by an `ecn_step_conditions` rule at submit (before ENGINEERING_REVIEW entry) — not hardcoded in Python.

---

## 6. Emergency ECN — Data Model Reservation

Workflow Sprint 2+. Fields reserved now to avoid a migration later.

| Field on `ecn_instances` | Type | Notes |
|--------------------------|------|-------|
| `is_emergency` | BOOLEAN | Default FALSE. Set by originator at creation. |
| `emergency_reason` | TEXT | Mandatory if `is_emergency=TRUE`. |
| `emergency_approved_by` | VARCHAR(10) | EM or Admin who authorises the flag. |
| `emergency_approved_at` | TIMESTAMPTZ | |

**Sprint 2+ behaviour:** Emergency ECNs compress MANAGEMENT_REVIEW to DC + EM co-approval only. QM review remains mandatory (ISO 13485 cannot be skipped). All bypassed roles receive mandatory notification.

---

## 7. Notification Matrix

### Transition-triggered Notifications

| Event | Recipients | Escalation |
|-------|-----------|-----------|
| ECN created | Originator (confirmation) | — |
| DRAFT → ENGINEERING_REVIEW | SE/CE assigned | 48h: SE/CE + EM |
| ENGINEERING_REVIEW → MANAGEMENT_REVIEW | All required parallel role members simultaneously | 48h: assignee + manager; 96h: DC added |
| Each parallel approval received | DC (progress update) | — |
| MANAGEMENT_REVIEW → DC_APPROVED | DC assigned | 48h: DC + manager; 96h: EM added |
| DC_APPROVED → APPROVED | DC, Originator | — |
| APPROVED → IMPLEMENTED | DC, Originator, all approvers | — |
| IMPLEMENTED → CLOSED | Originator, all approvers, observer roles RD/TE/MQ | — (automatic — no DC action) |
| Any → REJECTED | Originator + all prior approvers | — |
| Any → ON_HOLD | Originator, all pending approvers | — |
| Movex write failure (outbox attempt 3) | DC | Attempt 10 — ABANDONED: EM added |

### Email Mechanics

- **Sender:** Acting user's email — looked up via `LDAPIdentityProvider.get_email(username)`
- **`get_email()`** must be added to `IdentityProvider` Protocol in `src/auth/providers.py` (Phase 2 gate F-3)
- **Escalation timer:** Celery beat task checks `ecn_approval_steps.assigned_at` at 48h and 96h intervals
- **Rejection subject:** `"Rejection {rejection_number} created for ECN {ecn_id}."`
- **Rejection body:** Content of `ecn_rejections.description`

Observer roles (RD, TE, MQ) receive a read-only summary at CLOSED only. No work items. No escalation.

---

## 8. Rejection Flows

Two paths inherited from Stargile `RejectECN.awf`, both preserved in OSKAR.

**Path 1 — Restart:** All `ecn_approval_steps` reset. ECN returns to ENGINEERING_REVIEW. ECN revision number incremented. Used when the rejection indicates the ECN needs fundamental rework.

**Path 2 — Proceed:** Only the rejecting role's step resets. All other approvals preserved. ECN returns to the stage where rejection occurred. Used when only the rejecting role's specific concern needs addressing.

Originator chooses the path on resubmit. Choice is stored on the `ecn_rejections` record (`resolution: restart | proceed`).

---

## 9. API Contract — ECN Transitions

All under `/api/v1/ecn/`. All require valid JWT. RBAC enforced via JWT group claim + live DB role lookup.

### Core CRUD

```
POST   /api/v1/ecn/                          Create ECN (→ DRAFT)
GET    /api/v1/ecn/                          List ECNs (filter: status, role, originator, date)
GET    /api/v1/ecn/{ecn_id}                  Get ECN detail
PATCH  /api/v1/ecn/{ecn_id}                  Update header fields (DRAFT only)
```

### Transition Endpoints

```
POST   /api/v1/ecn/{ecn_id}/submit           DRAFT → ENGINEERING_REVIEW       Role: OR
POST   /api/v1/ecn/{ecn_id}/approve          Role-specific approval            Role: current stage role
POST   /api/v1/ecn/{ecn_id}/dc_approve       DC_APPROVED → APPROVED            Role: DC
POST   /api/v1/ecn/{ecn_id}/reject           Any active stage → REJECTED       Role: current stage role
POST   /api/v1/ecn/{ecn_id}/resubmit         REJECTED → ENGINEERING_REVIEW     Role: OR
POST   /api/v1/ecn/{ecn_id}/cancel           → CANCELLED                       Role: OR or AD
POST   /api/v1/ecn/{ecn_id}/hold             → ON_HOLD                         Role: DC or AD
POST   /api/v1/ecn/{ecn_id}/resume           ON_HOLD → prior status            Role: DC or AD
```
> **Note (ADR-009):** `accept` (SUBMITTED→DC_REVIEW) and `pass` (DC_REVIEW→ENGINEERING_REVIEW) endpoints removed.
> `close` (IMPLEMENTED→CLOSED) replaced by `auto_close` — Celery-triggered, no HTTP endpoint.

### Standard Request Body

```json
{ "notes": "optional", "rejection_reason": "mandatory on /reject", "restart": true }
```

### Standard Response

```json
{
  "ecn_id": "uuid",
  "previous_status": "DC_APPROVED",
  "new_status": "APPROVED",
  "transitioned_by": "username",
  "transitioned_at": "2026-04-13T10:00:00Z",
  "audit_record_id": "uuid"
}
```

### ECN Line Item Endpoints

```
POST/GET/PATCH/DELETE   /api/v1/ecn/{ecn_id}/items                      ECN item lines (DRAFT only for write)
POST/GET/PATCH/DELETE   /api/v1/ecn/{ecn_id}/items/{item_id}/mpns       MPN aliases (DRAFT only for write)
POST/GET/PATCH/DELETE   /api/v1/ecn/{ecn_id}/bom-changes                BOM change lines (DRAFT only for write)
```

### DC Recovery Endpoints

```
GET    /api/v1/ecn/{ecn_id}/movex-errors    Movex outbox errors with status (DC recovery panel)
POST   /api/v1/ecn/{ecn_id}/movex-retry     Retry failed outbox entries   Role: DC
```

---

## 10. BOM Concurrency Detection

Before each `PDS002MI` Movex write at APPROVED:

1. Fetch current Movex BOM state for the affected product via `movex-rest-api`
2. Compare against the BOM snapshot captured at DC_APPROVED (`ecn_bom_changes.movex_snapshot_at_review` JSONB)
3. If any component or sequence has changed since snapshot: abort write, set outbox entry to `failed`, surface diff to DC recovery panel
4. DC resolves (update ECN or explicit override) before retry

---

## 11. Customer / Regulatory Approval Flag (ISO 13485 §7.3.9)

| Field on `ecn_instances` | Type | Notes |
|--------------------------|------|-------|
| `requires_customer_approval` | BOOLEAN | Default FALSE. Set by QM at MANAGEMENT_REVIEW. |
| `customer_approval_reference` | VARCHAR(50) | Customer ECR / approval document reference. |
| `customer_approved_at` | TIMESTAMPTZ | Date customer approval received. |
| `regulatory_impact` | BOOLEAN | Default FALSE. Triggers additional QM confirmation gate before CLOSED. |

APPROVED → IMPLEMENTED blocked by `ecn_step_conditions` when `requires_customer_approval=TRUE` and `customer_approved_at` is NULL. Sprint 2+.

---

## 12. Training Record Trigger (ISO 13485 §6.2)

On IMPLEMENTED → CLOSED:

1. System notifies all ECN participants (all role assignments for this ECN)
2. Notification includes: ECN ID, change summary, effective date
3. Each user acknowledges in their OSKAR work queue
4. Acknowledgements stored in `ecn_training_acknowledgements` table

Table schema reserved in Sprint 1. Feature active Sprint 2+. Stargile has no equivalent.

---

## 13. Open ECN Digest — Replacing DBCHK_OpenECN

**Scope added:** 2026-04-14 (Karen email). The SQL Server Agent job `[DBSRV].[SRX_Apps].[dbo].[DBCHK_OpenECN]` must be decommissioned at OSKAR go-live. OSKAR provides the replacement.

### Current job — key facts

- Queries replicated Stargile/ComActivity tables on `DBSRV` (SQL Server), not live DB2
- Sends HTML email to `karen.lewin@srxglobal.com` (hardcoded — parameter `@email_to` is unused)
- Filters: `EHCONO = '100'`, `EHFACI = 'D'`, `EHZECNST < 95`
- "Next Action Person" is claimed in the proc comment but not implemented — `EHRESP` (initiator) is used as proxy; true next action requires joining to `ZECNPRCS`/`ZECNUSRL`
- Known cursor bug: Created date column displays ECN ID instead (duplicate fetch)

### OSKAR replacement — two components

#### Component A: Open ECN List endpoint (Sprint 1)

`GET /api/v1/ecn/` already planned. Must support:

| Filter param | Values | Notes |
|-------------|--------|-------|
| `status` | `DRAFT`, `ENGINEERING_REVIEW`, etc. | Multi-value; `open` = all except CLOSED/CANCELLED/ARCHIVED |
| `facility` | `D`, `M`, etc. | From `ecn_instances.facility` field (add to schema in F-1) |
| `assignee` | username | Current work item holder — the true "Next Action Person" |
| `overdue` | boolean | `ecn_approval_steps.assigned_at` > 48h without action |
| `age_days` | integer | ECNs older than N days |

**"Next Action Person" implementation:** Derived from `ecn_approval_steps` — the user(s) with `status='pending'` for the current ECN status. Exposed as `next_action_users[]` on the ECN list response. This is what Stargile promised but never delivered.

Add `facility` column to `ecn_instances` in F-1 schema work. Default `'D'` for initial deployment.

#### Component B: Scheduled email digest (Sprint 2)

Celery beat task — `tasks/ecn_digest.py`:

| Attribute | Detail |
|-----------|--------|
| Schedule | Configurable via `ECN_DIGEST_SCHEDULE` env var (default: daily 07:00 APAC) |
| Recipients | `ECN_DIGEST_RECIPIENTS` env var (comma-separated) — not hardcoded |
| Scope | All facilities where OSKAR is active |
| Content | Open ECNs with: ID, Title, Status, Created date, Originator, Next Action Person(s), Age (days) |
| Format | HTML table matching existing email style for continuity |
| Trigger | Celery beat; can also be triggered on-demand via `POST /api/v1/admin/ecn-digest` (DC/Admin role) |

**Decommission gate:** `DBCHK_OpenECN` SQL Server job is disabled on OSKAR go-live day. Confirm with Infrastructure (whoever manages DBSRV SQL Server Agent). Add to go-live checklist.

### API addition

```
GET  /api/v1/ecn/?status=open&overdue=true      Open overdue ECNs (DC dashboard)
GET  /api/v1/ecn/?assignee={username}           My pending ECNs (personal work queue)
POST /api/v1/admin/ecn-digest                   Trigger digest on demand (DC/Admin)
```

---

## 14. Open Items — Confirm with Branko Post-POC

| # | Item | Risk if wrong |
|---|------|--------------|
| 1 | ZQ01–ZQ18 field meanings | Low — JSONB fallback; UI deferred |
| 2 | MPDDOC `#TEMPLATE` record exact structure | Medium — MPDDOC gap resolution |
| 3 | Cost threshold for FN gate (WAPC delta %) | Low — stored in `ecn_step_conditions`; no code change |
| 4 | PM involvement conditions beyond routing changes | Low — `ecn_step_conditions` row update only |
| 5 | RD / TE / MQ AD groups existence and population | Medium — notification delivery |
| 6 | Multi-facility item warehouse status scope | Low — documented v1 limitation |
| 7 | Restart vs proceed as default path | Low — originator chooses; no forced default |
