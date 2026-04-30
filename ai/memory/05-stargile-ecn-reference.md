# OSKAR — Stargile ECN Reference (Ground Truth)

> **PROVIDER-AGNOSTIC — Non-Negotiable #12**
> No tool-specific syntax. Readable by any LLM tool or none.

This file documents the Stargile ECN data model, workflow, and Movex integration as
recovered directly from the Stargile source code (`c:/Projects/SuperTool/Stargile_Source_Code/` — SuperTool is the archived predecessor workspace; source code stays there).
It is the authoritative reference for OSKAR ECN module design decisions.

**Sources analysed:**
- `Startronics/Docs/ZECN*.sql` — all ECN table DDL
- `Startronics/Processes/RequestECN.awf`, `RejectECN.awf` — XPDL workflow definitions
- `Startronics/src/java/com/startronics/ecn/` — business logic, rules, service classes
- `2016-12-22 Branko/Nick kick-off transcript`
- `2018-04-17 Branko session (items, BOMs, routes)`
- `c:/Projects/SuperTool/graphify-out2/GRAPH_REPORT.md` — AST graph analysis: 424 files, 4146 nodes, 5057 edges, 173 communities (2026-04-10)

---

## 1. ECN Data Model

### ZECNHEAD — ECN Master Record

Primary key: `(EHCONO, EHZECNID)`

| Field | Type | Meaning |
|-------|------|---------|
| EHCONO | INT | Company number (CONO=100) |
| EHZECNID | INT | ECN ID (primary key) |
| EHZECNTL | VARCHAR(20) | ECN Title |
| EHZECNST | INT | Status (see status table below) |
| EHZECNTP | CHAR | ECN Type: `ECO` or `MCO` |
| EHRESP | VARCHAR(10) | Responsible user (initiator) |
| EHCUNO | VARCHAR(10) | Customer number |
| EHZECNRF | VARCHAR(20) | Customer ECR / reference number |
| EHFACI | CHAR(3) | Facility |
| EHPRNO | VARCHAR(15) | Product number |
| EHFDAT | DATE | Effective from-date |
| EHRGDT / EHRGTM | DATE/TIME | Record entry date/time |
| EHLMDT / EHCHNO / EHCHID | — | Audit: last modified date, change number, changed by |
| EHZECNTX | CLOB | ECN description (free text) |

**Change scope flags (BOOLEAN — drive conditional approver routing):**

| Field | Meaning |
|-------|---------|
| EHZNEWPR | New Parts Required |
| EHZNEWMR | New MPNs Required |
| EHZNEWBR | New BOMs Required |
| EHZNEWRR | New Routings Required |
| EHZCHGPR | Change Parts Required |
| EHZCHGBR | Change BOMs Required |
| EHZCHGRR | Change Routings Required |
| EHZCHGDC | Change to Documents |
| EHZCHGSW | Change to Software |
| EHZCHGTX | CLOB | Document changes description |

**Questionnaire fields ZQ01–ZQ18:** Yes/No (`YN`) and Complete (`CM`) flags, supporting
text fields. Purpose of each field: confirm with Branko post-POC before building UI.

**Cost fields (ZQ19–ZQ23):**

| Field | Meaning |
|-------|---------|
| EHZQ19TC | Total Non-Recurring Costs (Engineering) |
| EHZQ20TC | Total Non-Recurring Material Costs (Program Manager) |
| EHZQ21TC | Total Implementation Cost |
| EHZQ22CC | Change to Ongoing Unit Costs |
| EHZQ23TC | Total Cost of Implementation |

---

### ZECNITMN — Item Changes per ECN Line

Primary key: `(NICONO, NIZECNID, NIZECNLN)`

| Field | Meaning |
|-------|---------|
| NIZNWITF | New item flag (BOOLEAN) |
| NIITNO | Item number (VARCHAR 15) |
| NISTAT | Status (CHAR 2) — 20=active, 90=inactive |
| NIITDS | Item name (VARCHAR 30) |
| NIFUDS | Description 2 (VARCHAR 60) |
| NIDWNO | Drawing number |
| NIPRGP | Procurement group |
| NIITCL | Product group |
| NIUNMS | Unit of measure |
| NIECVE | Revision number (CHAR 4) |
| NIATPL | Item template |
| NISUNO | Supplier number |
| NIRESP | Responsible engineer |
| NIBUYE | Buyer |
| NIPUPR | Purchase price (DECIMAL 17,6) |
| NILEA1 | Supply lead time (days) |

---

### ZECNBOMS — BOM Changes per ECN Line

Primary key: `(BMCONO, BMZECNID, BMZECNLN)`
Indexes on `(BMPRNO, BMZECNID, BMZECNLN)` and `(BMMTNO, BMZECNID, BMZECNLN)`

| Field | Meaning |
|-------|---------|
| BMZNWBMF | New BOM flag (BOOLEAN) |
| BMPRNO | Parent product number (VARCHAR 15) |
| BMSTRT | Product structure type (CHAR 3) |
| BMMSEQ | Sequence number (INT) |
| BMZACTFL | **Action flag: 1=Add, 3=Change** |
| BMOPNO | Operation number (links to routing) |
| BMMTNO | Component / material number (VARCHAR 15) |
| BMZNWQTY | New quantity (DECIMAL 15,6) |
| BMZCIRRF | Circuit reference (CLOB — PCB assembly) |
| BMZBOMNT | BOM notes (CLOB) |
| BMSTA1 | Update status (CHAR 2) |

Delete operations use a separate PDS002MI `DeleteComponent` call — no action flag 2.

---

### ZECNMPNI — Manufacturer Part Numbers

Primary key: `(CMCONO, CMZECNID, CMITNO, CMMSEQ)`

| Field | Meaning |
|-------|---------|
| CMZECNID | ECN reference |
| CMITNO | Item number |
| CMMSEQ | Sequence (ordering) |
| CMZACTFL | Action flag: 1=Add, 3=Change |
| CMZMANPN | Manufacturer part number |
| CMSUNO | Supplier number |
| **CMZDEFFL** | **Default flag — purchasing preference** |
| CMZEEFDT | Effective date |

**Key fact:** Movex has no native MPN field. MPNs are owned by OSKAR (previously Stargile).
`CMZDEFFL` resolves the ambiguity of which MPN purchasing should buy when multiple exist.

---

### ZECNCIRF — Circuit References

Tracks PCB circuit references associated with BOM changes.
Key fields: `CRZCIRRF` (CLOB), `CRZECNID`.

---

### ZECNMELG — Movex Error Log

Primary key: `(ZECONO, ZEZECNID, ZEZECNLN, ...)`

| Field | Meaning |
|-------|---------|
| ZEZECNID | ECN reference |
| ZEZECNLN | Line number |
| ZEPGNM | Program name (e.g. `PDS001MI`, `PDS002MI`) |
| ZEMSGT | Error message (VARCHAR 180) |
| ZESTAT | Status |

Document Controller views this log to diagnose Status 50 failures and retry the push.
OSKAR must replicate this as `ecn_movex_errors` in PostgreSQL.

---

### ZECNRJCT — Rejections

| Field | Meaning |
|-------|---------|
| RJZECNID | ECN reference |
| RJZREJNO | Rejection sequence number |
| RJZCAUSR | User who rejected |
| RJZRSNCD | Reason code (1, 2, 3 — configurable) |
| RJZDSC | Description (CLOB) |

---

### ZECNAUTH / ZECNUSRL — Approver Assignments

`ZECNAUTH`: maps ECN approval responsibility to users by role.
`ZECNUSRL`: links role IDs (5–80) to actual users per ECN.

Role assignment happens at ECN creation (`ProcessAssignUsersToRolesRule.java`).
Assignments are per-ECN — not a global static chain.

---

### ZECNPRCS — Process Sign-off Tracking

Primary key: `(PRZECONO, PRZECNID, PRZECNST, PRZECNRL)`

Tracks which roles have signed off at each status level. OSKAR equivalent: `ecn_approvals` table.

---

## 2. Workflow States

From `IECNStatus.java`:

| Integer | Constant | Description |
|---------|----------|-------------|
| 5 | PRELIMINARY | ECN created |
| 10 | INITIATION | Initiator completing header |
| 15 | PRELIMINARY_REVIEW_PENDING | Awaiting preliminary review |
| 20 | PRE_APPROVAL_PENDING | Pre-approval phase |
| 25 | DC_CHECK_PENDING | Document Control checks |
| 30 | APPROVAL_PENDING | Multi-role approval |
| 35 | DC_APPROVAL_PENDING | Document Controller approval (mandatory gate) |
| **50** | **MOVEX_UPDATED_PENDING** | **Only Movex write point** |
| 55 | COST_REVIEW_PENDING | Cost accountant review |
| 60 | ACTION_NOTIFICATION_PENDING | Notification phase |
| 65 | FINAL_APPROVAL_PENDING | Engineering Manager final sign-off |
| 90 | ECN_COMPLETE | Closed |
| 99 | ECN_CANCELLED | Cancelled |

**Status progression** (`ProcessUpgradeECNStatusRule.java`): linear array traversal.
`getNextECNStatus()` advances through the sequence. No branching — conditional approvers
are skipped via `ProcessSkipWorkItemRule`, not by skipping statuses.

---

## 3. Workflow Definition

From `RequestECN.awf` (XPDL 1.0):

```
Entry Point
  → Assign Users to Roles
  → Initiation (work item to Initiator)
  → Preliminary Review (Quotations role)
  → Production Engineer review
  → Program Manager review
  → SMT Engineer review
  → Purchasing review
  → Test Engineer review
  → Document Controller (mandatory)
  → Cost Review (Cost Accountant)
  → Final Approval (Engineering Manager)
  → ECN Complete (Status 90)
```

Rejection path (`RejectECN.awf`):
```
Rejection triggered → Create ZECNRJCT record → Notify Initiator → Wait for response
  → restartECN  → re-enters workflow from beginning
  → proceedWithECN → re-enters at point of rejection
```

---

## 4. Movex Integration

**API calls confirmed** (`BOMService.java`, `ZECNMELG` error log patterns):

| MI Program | Transaction | Purpose |
|------------|-------------|---------|
| PDS001MI | AddProduct | Create new product header in Movex |
| PDS002MI | AddComponent | Add BOM line (component + quantity + operation) |
| PDS002MI | DeleteComponent | Remove BOM line |
| PDS002MI | UpdateOperation | Modify routing operation |
| PDS002MI | AddOperation | Add new routing step |

**Read operations** (any status, for display):
- `MPDHED` (Product Header) — validate product structure exists
- `MPDMAT` (Product Material) — display current BOM for editing
- `CITMAS` (Item Master) — validate components exist before adding

**Write rule:** Writes to Movex happen **at Status 50 only**. All earlier statuses are
OSKAR-internal. This is the boundary between OSKAR workflow and Movex SSoT.

**Field references:**
- Schema: `MVXCDTA.MPDMAT` (PreparedStatementHelper pattern)
- Company filter: `SessionValues.getValue("CONO")` → CONO=100
- Audit: `SessionValues.getValue("MVXUSERID")`

---

## 5. Known Pain Points (design decisions for OSKAR)

| Pain Point | Stargile Behaviour | OSKAR Decision |
|------------|-------------------|---------------|
| Status 50 timeout — no confirmation | Synchronous push; no feedback | Celery async task; frontend polls `GET /api/v1/ecn/{id}` every 15–30s for status (ADR-007) |
| Date-from conflicts found only at push | No pre-validation | Pre-validate component from-dates against Movex BOM before Status 50 |
| Stuck ECNs — weekly manual report | No live dashboard | ECN list with age + status filter; overdue highlighting |
| Multi-facility item status (Melbourne/JB) | Item warehouse table not managed by ECN | **Known v1 limitation** — document and defer to Phase 2 |
| MPN default unclear to purchasing | No default field surfaced to users | Expose `default_mpn` flag in UI; map from `CMZDEFFL` |
| Retry after Movex failure — admin-only button | Limited access to push button | DC role can trigger retry via API; full error detail visible |
| IE9 dependency | Hardcoded browser target | Not applicable — OSKAR is React/FastAPI |
| Username case sensitivity | Stargile bug (lowercase required) | LDAP bind normalises username; not replicated |

---

## 6. Multi-facility Note

Item master has two levels:
- **Main item master** (`CITMAS`): global status (20=active, 90=inactive)
- **Item warehouse table**: facility-specific status (Melbourne vs JB can differ)

Stargile can update main item master status but **cannot** update item warehouse status.
Workaround in use: direct SQL updates by admin. No audit trail.

**OSKAR v1:** Treat this as a known limitation. Note it in IQ documentation. Do not build
facility-level item warehouse management in Iteration 1 — this is Phase 2 scope.

---

## 7. Cutover Plan

- **2-week drain period** before go-live: engineers push open Stargile ECNs to completion
  or cancellation. Target: zero open ECNs in Stargile on go-live day.
- **Go-live day:** All new ECNs created in OSKAR. Stargile read-only.
- **In-flight rule:** Any Stargile ECN not closed by go-live is cancelled in Stargile and
  re-raised in OSKAR by the initiator. No mid-workflow migration.
- **Historical data:** Export `ZECNHEAD` + child tables → import as `status=closed` records
  in OSKAR (read-only). Manal owns the Stargile export.
- Karen to endorse cutover plan before go-live date is communicated to engineering team.

---
## 8. Graph Analysis Findings (2026-04-10)

Source: `c:/Projects/SuperTool/graphify-out2/GRAPH_REPORT.md` — AST analysis of full 424-file Stargile codebase.
These findings extend and correct the earlier static source analysis in Sections 1–7.

---

### 8.1 ECNItem — Upload DTO (not a service)

`ECNItem.java` is the most connected ECN class (76 edges, 6th in entire codebase). It is a **data transfer object** used across all upload rules, processors, and services — not a service class.

**Additional fields not captured in `ZECNITMN` DDL analysis:**

| Field | Movex Column | Meaning | OSKAR implication |
|-------|-------------|---------|-------------------|
| `znwitf` | ZNWITF | New item flag (Boolean) | Drive "new vs. change" UI routing |
| `dwno` | DWNO | Drawing number | Link to MPDDOC; auto-created by `ItemService.createDwno()` |
| `ecve` | ECVE | ECN version on item | Track which ECN version introduced/modified item |
| `popn` | POPN | Manufacturer part number alias | Created in Movex `MITPOP` via MMS025MI |
| `wapc` | WAPC | Weighted average purchase cost | Populated from Purchasing; displayed in Cost Review step |
| `buar` | BUAR | Business area | Routing/costing scope |
| `lea1` | LEA1 | Lead time 1 (purchasing) | Supplier intelligence input in Iteration 3 |
| `lea4` | LEA4 | Lead time 4 (internal) | Manufacturing planning |
| `satd` | SATD | Safety lead time (days) | Planning buffer |

**Drawing number auto-creation:** `ItemService.createDwno()` copies a `#TEMPLATE` record from `MPDDOC` table. OSKAR must replicate this or provide an equivalent document number registry.

---

### 8.2 MMS025MI — Sixth Movex MI Call (Item Alias / MPN Registration)

**Not in ai/05 Section 4 Movex integration table.** Now confirmed:

| MI Program | Transaction | Purpose | When |
|------------|-------------|---------|------|
| MMS025MI | AddAlias | Register MPN (POPN) as alias against item (ITNO) in Movex `MITPOP` | During item processing when `znwitf=true` (new item) |

**Call sequence in `ItemService.addItemAlias()`:**
1. Check `MITPOP` — does alias already exist? (`checkItemAlias()` — direct SQL on `MITPOP`)
2. If not: call `MMS025MI.AddAlias(cono, alwt, alwq, itno, popn, e0pa)`
3. If success: write `AuditTrailService` entry for the new `MITPOP` row

**Fields:**
- `ALWT` — alias type (qualifier category)
- `ALWQ` — alias qualifier
- `ITNO` — item number
- `POPN` — manufacturer part number
- `E0PA` — partner (supplier) alias type

**OSKAR implication:** The movex-rest-api must expose `MMS025MI.AddAlias`. This is a Track A gap — not currently configured in any `transactions/*.json` file.

---

### 8.3 AsynchControl — Full BPMN Workflow Engine

`AsynchControl` is not a simple async helper (143 edges, most connected node in the entire codebase). It is a **complete process instance engine** that drives all ECN status transitions.

**DB tables it manages** (beyond ZECN* tables):

| Table | Purpose |
|-------|---------|
| `ProcessInst` | One row per active ECN workflow instance. Fields: `ProcessInstId`, `ProcessName`, `RunningState` (default 11), `Archived`. |
| `ProcessInstControl` | Activity state per instance — tracks current position in the workflow |
| `ProcessInstAssignment` | Role-to-user assignments per instance |
| `ProcessInstAssignmentMulti` | Multi-user assignments per role |
| `WorkItem` | Individual approval tasks sent to users |
| `WorkItemWorkspace` | Workspace context for each work item |
| `WorkItemText` | Text/comments attached to work items |
| `WorkItemAssignment` | Which user owns which work item |
| `ProcessInstData` | Key-value store for process variables |
| `ProcessInstIdMap` | Maps external IDs (ECN ID) to process instance ID |

**Role auto-assignment:** On process creation, `AsynchControl` queries `AuthorizationManager.getRoleManager().getUsers(role)`. If a role has exactly one user, it is auto-assigned. Otherwise, a human assignment step fires.

**Transaction model:** `LogicalUnitOfWork` wraps each state transition. If a Movex push fails at Status 50, the `luow` is rolled back — ECN stays at status 49/50 pending. This is the mechanism behind "stuck ECNs."

**OSKAR implication:** OSKAR replaces `AsynchControl` with Celery tasks + PostgreSQL state machine. The `ProcessInst`/`WorkItem` table pattern maps directly to OSKAR `ecn_workflow_instances` and `approval_tasks` tables. Celery email tasks + HTTP polling replace `WorkItemWorkspace` event propagation (ADR-007: Redis eliminated).

---

### 8.4 FileRoleManagement — XML-Based RBAC (Critical Pain Point)

Stargile stores role-to-user mappings in `System/System.rolemap` — an **XML file** with in-memory caching (`SimpleCacheManager`).

**Methods:**
- `getUsers(role)` — returns all users assigned to a role (direct + via group)
- `getRolesForUser(userId)` — returns all roles for a user (direct + via group membership)
- `addUserToRole(role, user)` — writes to XML file, clears cache
- `removeUserFromRole(role, user)` — writes to XML file, clears cache
- `canActInRole(userId, roleId)` — used at every approval gate

**Why this is a pain point:**
- Role assignments are in a flat XML file — no DB query, no audit trail, no transaction
- Cached in memory — stale after file change without server restart
- Group membership delegated to `AuthorizationManager.getGroupManager()` — separate system

**OSKAR replacement:** PostgreSQL `user_ecn_roles` table with columns `(user_id, role_id, ecn_id, assigned_by, assigned_at)`. Supports per-ECN role assignment (Stargile assigns globally; OSKAR can scope per-ECN). Full audit trail. No file system dependency.

---

### 8.5 Email Notification Logic (Exact Recipient Rules)

From `ECNRejectProcessSendMessageRule.java` — the most complete notification source found.

**Rejection notification rules (confirmed from source):**

| Condition | Recipients |
|-----------|-----------|
| Rejection at status ≤ 50 (MOVEX_UPDATED_PENDING) | All users who approved at any status > 50 — via `getUniqueUsersInECNStatusGreaterThan()` |
| Rejection at status 65 (FINAL_APPROVAL_PENDING) | Document Controller (always) + Engineering Manager (if role was checked) + Production Manager (if role was checked) + Quality Manager (if role was checked) |

**Email mechanism:**
- `ProcessECNHelper.getUserEmail(processData, userId)` — looks up email from user record
- `EmailHelper.sendEmail(sender, recipient, subject, body)` — SMTP via corporate relay
- Sender = rejecting user's email address
- Subject = `"Rejection {zrejno} created for ECN {zecnid}."`
- Body = `RJZDSC` (rejection description from `ZECNRJCT`)

**OSKAR implication for Track B:**
- Email notification on rejection is per-role, conditional on role check state
- The `isRoleChecked()` pattern means OSKAR must track per-role approval state in `ecn_role_approvals` table
- Sender identity must be the acting user's email, not a system address

---

### 8.6 Updated Movex MI Call Table (Complete)

Replaces Section 4 table — includes MMS025MI (graph analysis §8.2) and MMS200MI Add* transactions (2026-04-22, confirmed from 2018-04-17 Branko session):

| MI Program | Transaction | Purpose | When | `is_new_item` gate |
|------------|-------------|---------|------|--------------------|
| MMS200MI | AddItmViaItmTyp | Create item master record (MITMAS) via item type template — preferred | Status 50 — new items only | `TRUE` only |
| MMS200MI | AddItmBasic | Create item master record (MITMAS) without template — fallback | Status 50 — new items only | `TRUE` only |
| MMS200MI | AddItmFac | Create facility-level record (MITFAC) | Status 50 — new items only, after AddItm* | `TRUE` only |
| MMS200MI | AddItmWhs | Create warehouse-level record (MITWHL) | Status 50 — new items only, after AddItmFac | `TRUE` only |
| PDS001MI | AddProduct | Create product structure header (MPDHED) | Status 50 — new items | `TRUE` only |
| PDS002MI | AddComponent | Add BOM line (component + qty + operation) | Status 50 — BOM changes | Either |
| PDS002MI | DeleteComponent | Remove BOM line | Status 50 — BOM changes | Either |
| PDS002MI | UpdateOperation | Modify routing operation | Status 50 — routing changes | Either |
| PDS002MI | AddOperation | Add new routing step | Status 50 — routing changes | Either |
| MMS025MI | AddAlias | Register MPN (POPN) as alias for item in MITPOP | Status 50 — new items with MPN | `TRUE` only |

**Execution order for new items (`is_new_item = TRUE`):**
`AddItmViaItmTyp` → `AddItmFac` → `AddItmWhs` → `AddProduct` → `AddComponent` → `AddAlias`
Each step is a separate `movex_outbox` entry. MITMAS must exist before MITFAC; MITFAC before MITWHL; MITMAS before MPDHED.

**Why Stargile did not automate this:** Engineers manually created the item in Movex first, then referenced it in Stargile. Confirmed in the 2018-04-17 Branko session (timestamp 43:57): *"this is another step where we use a shortcut sometimes by manually creating it in Movex."* This was a normalised workaround, not a named pain point — OSKAR must eliminate this manual step.

**Track A impact:** All MMS200MI Add* transactions added to `transactions/MMS200MI.json` (2026-04-22). PDS001MI, PDS002MI, MMS025MI transaction files still need to be created before Sprint 2.

---

## 9. DBCHK_OpenECN — SQL Server Background Job (2026-04-14)

**Source:** `[DBSRV].[SRX_Apps].[dbo].[DBCHK_OpenECN]` — stored procedure authored by Karen Lewin, 2024-02-21.
**Context:** Added to OSKAR scope by Karen (email 2026-04-14). Must be analysed and replaced by OSKAR.

---

### What it does

Runs as a SQL Server Agent job on `DBSRV`. Queries replicated Stargile/ComActivity tables in `SRX_Apps` and sends an HTML email digest of all open ECNs (status < 95) for facility `D` (Division D / JB).

**Replaced:** A pre-2013 version that used a Linked Server to AS/400 (DB2 OLE DB). That approach failed in Feb 2024 with an OLE DB hotfix error. The 2024 replacement replicates Stargile/ComActivity tables into SQL Server instead of querying AS/400 directly.

### ZECNHEAD fields queried

| Stargile field | Meaning | Note |
|----------------|---------|------|
| `EHZECNID` | ECN ID | |
| `EHZECNTL` | ECN Title | |
| `EHZECNST` | ECN Status | Filter: `< 95` (all non-cancelled) |
| `EHRESP` | Responsible user / initiator | Used twice — once as ECN ID (cursor bug: @str1=EHZECNID, @str4=EHZECNID again), once as resp |
| `EHZECNTP` | ECN Type (ECO/MCO) | |
| `EHCUNO` | Customer number | |
| `EHPRNO` | Product number | |
| `EHCONO` | Company filter | `= '100'` |
| `EHFACI` | Facility filter | `= 'D'` (hardcoded) |

**Cursor bug noted:** The cursor fetches `EHZECNID` twice (`@str1` and `@str4`) — the original intent was `@str4 = EHRGDT` (Created date) per the proc comment. The email header says "Created" but the value displayed is the ECN ID again. This is a known data quality issue in the existing report.

### "Next Action Person" — current state

The proc title and 2024 comment say "adding ToUSER as the Next Action Person" but the cursor does **not** include a `ToUSER` or next-action field. `EHRESP` (initiator/responsible) is used as the closest proxy. The true next action person requires joining to `ZECNPRCS` / `ZECNAUTH` / `ZECNUSRL` — which the proc does not currently do. This is an **incomplete feature in Stargile** that OSKAR must fully implement.

### Email delivery

| Detail | Value |
|--------|-------|
| Recipient | `karen.lewin@srxglobal.com` (hardcoded — `@email_to` parameter is ignored) |
| Sender profile | `DBSRV` mail profile |
| Format | HTML table, styled with inline CSS |
| Trigger | SQL Server Agent job (schedule not in proc — confirm with Infrastructure) |
| Facility scope | Division D only (hardcoded `EHFACI = 'D'`) |

### OSKAR replacement scope

OSKAR must provide:

1. **Open ECN dashboard** — live web view replacing the email digest. Filterable by status, facility, assignee, age. Accessible to DC and EM at minimum.
2. **True "Next Action Person" field** — derived from `ecn_approval_steps` (who currently holds the work item). Not just the originator. This is what Stargile promised but never delivered.
3. **Scheduled digest email (optional)** — configurable Celery beat task. Sends HTML email of open ECNs. Recipients configurable (not hardcoded). Facility-aware (not just `D`). Sprint 2+ scope.
4. **Decommission dependency:** `DBCHK_OpenECN` SQL Server job must be turned off when OSKAR goes live. Until then it continues running — parallel operation during cutover period is acceptable.

---
