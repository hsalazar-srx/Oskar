# Skill: /oskar-ecn-rules
**Tier:** 1 — Domain rules
**MAS skill:** `manufacturing/ecn-workflow`

## Purpose
OSKAR-specific ECN business rules and workflow constraints derived from Stargile source code
analysis and the 2016–2018 Branko/Nick sessions. Applies to Iteration 1 (ECN module) design
and implementation. See `ai/memory/05-stargile-ecn-reference.md` for the full data model.

---

## ECN Lifecycle — Confirmed from Stargile Source (`IECNStatus.java`)

```
5  PRELIMINARY
10 INITIATION
15 PRELIMINARY_REVIEW_PENDING
20 PRE_APPROVAL_PENDING
25 DC_CHECK_PENDING
30 APPROVAL_PENDING
35 DC_APPROVAL_PENDING
50 MOVEX_UPDATED_PENDING   ← only point Stargile touches Movex
55 COST_REVIEW_PENDING
60 ACTION_NOTIFICATION_PENDING
65 FINAL_APPROVAL_PENDING
90 ECN_COMPLETE
99 ECN_CANCELLED
```

OSKAR v1 maps these to a clean set of named states — do not expose raw integer statuses in
the OSKAR API. Map in the service layer; keep integers in DB for migration compatibility.

---

## Approval Roles — Confirmed from Stargile Source (`IECNRoles.java`)

| ID | Role | Mandatory? | Trigger |
|----|------|-----------|---------|
| 5  | INITIATOR | Always | ECN creator |
| 10 | QUOTATIONS | Conditional | Preliminary review step |
| 15 | PRODUCTION_ENGINEER | Conditional | ECN affects production process |
| 20 | PROGRAM_MANAGER | Conditional | Scope/cost impact |
| 25 | SMT_ENGINEER | Conditional | ECN affects SMT components or programmes |
| 30 | PURCHASING | Conditional | PPV or supplier sourcing impact |
| 35 | TEST_ENGINEER | Conditional | Firmware or test procedure change required |
| 40 | ENGINEERING_MANAGER | Always (final) | Final sign-off before Status 90 |
| 45 | DOCUMENT_CONTROLLER | **Always (mandatory gate)** | Gatekeeper — ISO compliance |
| 50 | COST_ACCOUNTANT | Conditional | NRC/cost change |
| 55 | PRODUCTION_MANAGER | Conditional | Production impact |
| 60 | QUALITY_MANAGER | Conditional | Quality/compliance scope |
| 65 | PROGRAM_ADMINISTRATOR | Conditional | |
| 70 | IT_ANALYST | Conditional | |
| 75 | SCHEDULER | Conditional | |
| 80 | MISCELLANEOUS | Conditional | |

**Design rule:** Role assignments are per-ECN (stored in `ZECNUSRL`). OSKAR must support
dynamic role assignment at ECN creation, not a fixed global chain.

---

## Non-Negotiable Rules

1. **No ECN may reach Status 50 (Movex push) without Document Controller approval.** This is the mandatory gate — no bypass path exists in Stargile and none will exist in OSKAR.
2. **Every status transition must produce a SHA-256 audit chain entry.**
3. **Human approval is required before any Movex commit** — the system must never auto-commit.
4. **Effectivity dates must be validated** — Movex rejects BOM changes if a component already exists with the same from-date. Pre-validate before Status 50 push.
5. **Status 50 is the only Movex write point.** All reads (item lookup, BOM display) happen outside this status. Writes (PDS001MI, PDS002MI) happen only at Status 50.
6. **Rejection returns ECN to initiator with reason code** — OSKAR must support re-submission without re-creating the ECN.
7. **MPN records are OSKAR-owned, not Movex.** Movex has no native MPN field. OSKAR maintains the MPN table; a default flag (`CMZDEFFL`) identifies purchasing preference.

---

## Movex Integration — Confirmed API Calls

From Stargile `BOMService.java` and `ZECNMELG` error log table:

| Call | Operation | When |
|------|-----------|------|
| `PDS001MI / AddProduct` | Create new product header | Status 50 — new item |
| `PDS002MI / AddComponent` | Add BOM line (component) | Status 50 — BOM add |
| `PDS002MI / DeleteComponent` | Remove BOM line | Status 50 — BOM delete |
| `PDS002MI / UpdateOperation` | Modify routing operation | Status 50 — route change |
| `PDS002MI / AddOperation` | Add routing operation | Status 50 — new route step |

Errors are logged per-line with program name + message (replicate `ZECNMELG` as `ecn_movex_errors`
in OSKAR PostgreSQL). Document Controller must be able to view errors and retry the push.

---

## BOM Change Action Flags (from `ZECNBOMS`)

| Flag | Meaning |
|------|---------|
| 1 | Add new component |
| 3 | Change existing component (quantity, reference) |
| (delete) | Separate PDS002MI DeleteComponent call |

---

## Change Scope Flags (from `ZECNHEAD`)

ECN header carries boolean scope flags that drive conditional approver routing:

```
EHZNEWPR  New Parts Required
EHZNEWMR  New MPNs Required
EHZNEWBR  New BOMs Required
EHZNEWRR  New Routings Required
EHZCHGPR  Change Parts Required
EHZCHGBR  Change BOMs Required
EHZCHGRR  Change Routings Required
EHZCHGDC  Change to Documents
EHZCHGSW  Change to Software
```

OSKAR must expose these as a structured checklist at ECN creation — they drive which
conditional approvers are added to `ZECNUSRL` / OSKAR equivalent.

---

## ECN Types

From `ZECNHEAD.EHZECNTP`:
- **ECO** — Engineering Change Order (standard)
- **MCO** — Manufacturing Change Order

---

## Cost Fields (from `ZECNHEAD` questionnaire ZQ19–ZQ23)

| Field | Meaning |
|-------|---------|
| EHZQ19TC | Total Non-Recurring Costs (Engineering) |
| EHZQ20TC | Total Non-Recurring Material Costs (Program Manager) |
| EHZQ21TC | Total Implementation Cost |
| EHZQ22CC | Change to Ongoing Unit Costs |
| EHZQ23TC | Total Cost of Implementation |

**Open item:** Questionnaire fields ZQ01–ZQ18 (18 Yes/No + text fields) exist in Stargile.
Confirm with Branko post-POC which are still actively used — do not build UI for all 18
before validation.

---

## Known Pain Points (design to fix, not replicate)

| Pain Point | Root Cause | OSKAR Fix |
|------------|-----------|-----------|
| Status 50 timeout with no confirmation | No async feedback; push is synchronous | Celery async push; frontend polls `GET /api/v1/ecn/{id}` every 15–30s for status (ADR-007) |
| Date-from conflicts only discovered at push | No pre-validation | Validate from-date against Movex BOM before Status 50 |
| Multi-facility item status (Melbourne vs JB) | Item warehouse table not managed by Stargile | Phase 2 scope — flag as known limitation in v1 |
| MPN ordering unclear to purchasing | No default flag visible | Expose `default_mpn` flag in OSKAR UI and API |
| Stuck ECNs discovered only by weekly report | No real-time dashboard | OSKAR ECN list with age + status filter; no "Monday job" needed |
| IE9 dependency | Legacy Java webapp | Not a concern — OSKAR is a modern React/FastAPI stack |
| Username case sensitivity | Stargile bug | LDAP bind is case-insensitive by design |

---

## Data Migration Approach

- Export Stargile `ZECNHEAD` + child tables to CSV/JSON before decommission (Manal owns export)
- Import as `status=closed` records in OSKAR — read-only, no re-approval required
- MPN records (`ZECNMPNI`) migrate to OSKAR MPN table
- Historical audit trail: preserve SHA-256 chain integrity on import (hash each imported record)
- **2-week drain period before cutover:** engineers push open Stargile ECNs to completion;
  any remaining open ECNs are cancelled in Stargile and re-raised in OSKAR
- New ECNs created in OSKAR from go-live day forward

---

## API Endpoints (Sprint 1, /api/v1/)

```
POST   /api/v1/ecn/                         Create ECN (Draft — status 5)
GET    /api/v1/ecn/                          List ECNs (filter: status, assignee, type)
GET    /api/v1/ecn/{id}                      Get ECN detail + current status
PATCH  /api/v1/ecn/{id}/submit              Submit for review (5→10)
POST   /api/v1/ecn/{id}/approve             Approver action (approve/reject/comment)
GET    /api/v1/ecn/{id}/audit               Full SHA-256 audit chain
GET    /api/v1/ecn/{id}/movex-errors        Movex push error log (for DC retry workflow)
POST   /api/v1/ecn/{id}/movex-push          Retry Movex push (Document Controller only)
GET    /api/v1/ecn/{id}/bom                 Current BOM lines for this ECN
POST   /api/v1/ecn/{id}/bom                 Add/change BOM line
DELETE /api/v1/ecn/{id}/bom/{line}          Remove BOM line
GET    /api/v1/ecn/{id}/mpn                 MPN records for ECN items
POST   /api/v1/ecn/{id}/mpn                 Add MPN record
```

---

## What NOT to Approach Branko/Nick For Yet

All ECN process knowledge has been recovered from Stargile source code and prior session
transcripts (2016, 2018). Do not initiate external requirements sessions until:

1. A working POC exists (ECN lifecycle end-to-end against Movex)
2. The following specific questions arise from POC testing that cannot be answered from code:
   - Which ZQ01–ZQ18 questionnaire fields are still actively used
   - Notification recipient list per status transition
   - Multi-facility item warehouse handling intent for v1

Branko and Nick validate a working system — they do not provide requirements for a blank page.
