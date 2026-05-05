# OSKAR — Platform Architecture Reference

> **PROVIDER-AGNOSTIC — Non-Negotiable #12**
> No tool-specific syntax. Readable by any LLM tool or none.
>
> Diagrams use Mermaid — renders in VS Code (Markdown Preview), GitHub, and Obsidian
> (requires Mermaid plugin). Run `Ctrl+Shift+V` in VS Code to preview.

**Version:** 2.1 — 2026-05-01
**Changes:** §7 updated (SSE implemented); §10 updated (SSE row); §14 updated (ADR-009: DC single gate, 10-status machine, diagrams redrawn); §17–20 added (AIProvider, Agent Action Outbox, SSE flow, extended platform diagram)

---

## 1. What OSKAR Is

OSKAR is the Engineering Intelligence Platform for Scanfil APAC (JB, Malaysia).
It replaces Stargile (ECN) and PLMServer (BOM + Supplier Intelligence) with a
modern, extensible platform that serves as the engineering workflow and intelligence
pillar of the Dream Factory programme.

**Three iterations:**
- **Iteration 1 (~12 weeks):** ECN module — Engineering Change Notice workflow
- **Iteration 2 (~8 weeks):** BOM module — Bill of Materials management
- **Iteration 3 (~8–10 weeks):** Supplier Intelligence module

---

## 2. System Context — How OSKAR Fits in the Landscape

```mermaid
---
config:
  theme: light
  layout: elk
  look: classic
---
graph TB
  classDef person    fill:#08427b,color:#fff,stroke:#052e56
  classDef system    fill:#1168bd,color:#fff,stroke:#0b4884
  classDef external  fill:#666,color:#fff,stroke:#444
  classDef shared    fill:#2d6a4f,color:#fff,stroke:#1b4332

  E(["👤 Engineer / Approver<br/>~50 users"])

  subgraph Scanfil_APAC["Scanfil APAC"]
    OSKAR["OSKAR Platform<br/>─────────────────<br/>ECN · BOM · Supplier Intelligence<br/>FastAPI · PostgreSQL · Celery<br/>Linux VM <br/>"]:::system
    OSKAR["OSKAR Platform<br/>─────────────────<br/>ECN · BOM · Supplier Intelligence<br/>FastAPI · PostgreSQL · Celery<br/>Linux VM <br/><br/>"]:::system
    SMP["SM-Portal<br/>─────────────────<br/>M3 data · <br/>.NET 8 · React<br/>SRXWEBAPP1"]:::system
    MAPI["movex-rest-api<br/>─────────────────<br/>.NET 8 M3 MI adapter<br/>Shared by OSKAR + SM-Portal<br/>SRXWEBAPP1"]:::shared
  end

  MOVEX[("Movex / M3<br/>─────────────────<br/>ERP — Single Source of Truth<br/>IBM i · DB2 · CONO 100<br/>MVXCOBJ")]:::external
  AD["Active Directory<br/>─────────────────<br/>On-prem LDAP<br/>Engineer authentication"]:::external
  SUPPLIERS["Supplier APIs<br/>─────────────────<br/>DigiKey (Phase 1 — real)<br/>Mouser · RS · Arrow · Avnet<br/>(Phase 3 — stubs)"]:::external

  E -->|"ECN workflow, BOM, Supplier signals<br/>HTTPS / JWT"| OSKAR
  E -->|"M3 data, invoices, exchange rates<br/>HTTPS / Windows Auth"| SMP

  OSKAR -->|"Read item/BOM/ECN<br/>Write on human approval only"| MAPI
  SMP   -->|"Read M3 data"| MAPI
  MAPI  -->|"M3 MI transactions / DB2 queries"| MOVEX

  OSKAR -->|"LDAPS bind — auth engineers<br/>port 636"| AD
  SMP   -->|"Windows Negotiate<br/>NTLM/Kerberos"| AD

  OSKAR -->|"Part search, pricing, availability<br/>HTTPS / OAuth2"| SUPPLIERS
```

---

## 3. Infrastructure Deployment Diagram

```mermaid
---
config:
  theme: light
  layout: elk
  look: classic
---
graph TB
  subgraph Internet["External"]
    digikey["DigiKey API<br/>api.digikey.com"]
    suppliers_ext["Supplier APIs x5<br/>(Phase 3 stubs)"]
  end

  subgraph SRXWEBAPP1["SRXWEBAPP1 — Windows Server"]
    direction TB
    IIS["IIS — Port 443<br/>ADCS Certificate"]

    subgraph WSL2["WSL2 — Existing Services"]
      movexapi_svc["movex-rest-api<br/>.NET 8 — /api"]
    end

    subgraph SMPortal["SM-Portal"]
      smportal_be["SM-Portal Backend<br/>.NET 8<br/>Windows Negotiate Auth"]
      smportal_fe["SM-Portal Frontend<br/>React / TypeScript"]
    end
  end

  subgraph OskarVM["OSKAR Linux VM — VMware, Ubuntu 24.04 LTS<br/>apac-plm-ops.srxglobal.local | 2 vCPU / 4 GB"]
    direction TB
    Harbor["Harbor Registry<br/>apac-plm-ops.srxglobal.local"]

    subgraph DockerProd["Docker Compose — Production"]
      oskar_fe["oskar-frontend<br/>React/TS — :3000"]
      oskar_app["oskar-app<br/>FastAPI — :8000<br/>/api/v1/"]
      oskar_worker["oskar-worker<br/>Celery (PostgreSQL broker)"]
      oskar_db["oskar-db<br/>PostgreSQL 16<br/>broker · session · audit · outbox"]
    end

    subgraph DockerStaging["Docker Compose — Staging (Phase 2)"]
      staging["Staging Stack<br/>Port 8001"]
    end
  end

  subgraph OnPrem["On-Premises Infrastructure"]
    IBMI["IBM i / AS400<br/>Movex / M3<br/>CONO 100 — MVXCOBJ"]
    AD["Active Directory<br/>LDAPS :636"]
  end

  IIS -->|"reverse proxy :8000/:3000"| oskar_app
  IIS -->|"serves"| smportal_fe
  IIS -->|"reverse proxy"| smportal_be

  oskar_fe -->|"/api/v1/ calls (polling every 15-30s)"| oskar_app
  oskar_app --> oskar_db
  oskar_worker --> oskar_db

  oskar_app -->|"LDAPS bind :636"| AD
  oskar_app -->|"HTTP/JSON"| movexapi_svc
  oskar_worker -->|"OAuth2 / REST"| digikey
  oskar_worker -.->|"stubs — Phase 3"| suppliers_ext

  smportal_be -->|"HTTP/JSON"| movexapi_svc
  smportal_be -->|"Windows Negotiate"| AD

  movexapi_svc -->|"DB2 / IBM i socket"| IBMI
```

---

## 4. OSKAR ↔ Movex Data Flow

```mermaid
---
config:
  theme: light
  layout: elk
  look: classic
---
sequenceDiagram
  participant E as Engineer
  participant FE as OSKAR Frontend
  participant API as oskar-app (FastAPI)
  participant Adapter as MovexRestAdapter
  participant MAPI as movex-rest-api
  participant DB2 as IBM i / DB2

  Note over E,DB2: READ PATH — item/BOM/ECN lookup

  E->>FE: Open ECN form
  FE->>API: GET /api/v1/items?q=SRX-10045
  API->>Adapter: search_items("SRX-10045")
  Adapter->>MAPI: GET /api/items?q=SRX-10045
  MAPI->>DB2: SELECT TRIM(MMITNO), TRIM(MMITDS) FROM MVXCOBJ.MITMAS WHERE CONO=100
  DB2-->>MAPI: rows
  MAPI-->>Adapter: JSON
  Adapter-->>API: list[dict]
  API-->>FE: 200 OK — item list
  FE-->>E: Display results

  Note over E,DB2: WRITE PATH — ECN approval (Transactional Outbox, ADR-005)

  E->>FE: Click "Approve" (e.g. QM approves at MANAGEMENT_REVIEW)
  FE->>API: POST /api/v1/ecn/{id}/approve-role {role_id: "QM"}
  API->>API: Verify JWT — check OSKAR-Approvers group
  API->>API: ECNWorkflowMachine.approve_role() — guard conditions
  API->>API: BEGIN transaction
  API->>API: UPDATE ecn_instances SET status=... (if block complete → APPROVED)
  API->>API: INSERT movex_outbox (state='pending', idempotency_key=...)
  API->>API: INSERT ecn_transition_history (sha256_self=compute_transition_hash(...))
  API->>API: COMMIT
  API->>API: dispatch Celery notify task (after commit, fire-and-forget)
  API-->>FE: 200 OK — step approved
  FE-->>E: ECN status updated ✓

  Note over E,DB2: Celery worker picks up outbox (async, after commit)
  API->>Adapter: add_bom_component(..., idempotency_key=...) [Celery — not FastAPI]
  Adapter->>MAPI: POST /mi/PDS002MI/AddComponent {cono: 100, ...}
  MAPI->>DB2: INSERT MVXCOBJ.PDSMLS WHERE CONO=100 ...
  DB2-->>MAPI: OK (MSID blank = success)
  MAPI-->>Adapter: 200 OK
  Adapter-->>API: success → outbox entry → completed → ECN → IMPLEMENTED
```

---

## 5. OSKAR ↔ SM-Portal Relationship (ADR-001)

```mermaid
---
config:
  theme: light
  layout: elk
  look: classic
---
graph LR
  subgraph Shared["Shared Infrastructure"]
    AD["Active Directory<br/>(on-prem)"]
    MAPI["movex-rest-api<br/>.NET 8 — shared"]
    IBMI["Movex / M3<br/>IBM i — SSoT"]
  end

  subgraph SMP["SM-Portal (SRXWEBAPP1 / WSL2)"]
    smp_be[".NET 8 Backend<br/>Windows Negotiate Auth<br/>/api — unversioned ⚠️"]
    smp_fe["React Frontend<br/>Windows Auth UI"]
  end

  subgraph NX["OSKAR (Linux VM)"]
    nx_be["FastAPI Backend<br/>JWT + LDAP Auth<br/>/api/v1/ — versioned ✅"]
    nx_fe["React Frontend<br/>Standalone IIS vhost"]
  end

  smp_fe -->|"Navigation tile — opens new tab<br/>oskar.srxglobal.local (ADR-024)"| nx_fe

  smp_be -->|"Windows Negotiate<br/>NTLM/Kerberos"| AD
  nx_be  -->|"LDAPS bind — same AD credentials<br/>port 636 → JWT issued"| AD

  smp_be --> MAPI
  nx_be  --> MAPI
  MAPI   --> IBMI

  Note1["ADR-001: SM-Portal → OSKAR navigation via link only (Option A).<br/>No auth coupling. SM-Portal tile opens oskar.srxglobal.local in new tab.<br/>Engineers use same Windows AD credentials — OSKAR authenticates independently via LDAP.<br/>Shared Tailwind design tokens for visual coherence."]
```

---

## 6. Authentication Flow

```mermaid
---
config:
  theme: light
  layout: elk
  look: classic
---
sequenceDiagram
  participant E as Engineer
  participant FE as OSKAR Frontend
  participant API as oskar-app (FastAPI)
  participant LDAP as Active Directory (LDAP)

  E->>FE: Enter Windows credentials
  FE->>API: POST /api/v1/auth/login {username, password}
  API->>LDAP: ldap3 bind — CN=username,DC=srxglobal,DC=local
  LDAP-->>API: bind success / failure

  alt Authentication failed
    API-->>FE: 401 Unauthorized
    FE-->>E: Invalid credentials
  else Authentication succeeded
    API->>LDAP: get_groups(username) — memberOf query
    LDAP-->>API: [OSKAR-Engineers, OSKAR-Approvers]
    API->>API: Issue JWT access token (60min) + HttpOnly refresh cookie (8h), groups claim
    API-->>FE: 200 OK — JWT token
    FE->>FE: Store JWT in memory (not localStorage)
    FE-->>E: Logged in — role-based UI rendered
  end

  Note over E,LDAP: Subsequent requests
  E->>FE: Any action
  FE->>API: Authorization: Bearer JWT
  API->>API: Verify signature + expiry + groups
  API-->>FE: Response based on RBAC
```

---

## 7. Event Notification (ADR-007 — Redis Eliminated)

> **ADR-007** (2026-04-17) removed Redis. The former Redis Streams design (F-6) is superseded.
> SSE endpoint `GET /api/v1/ecn/{id}/stream` implemented in Sprint 2 via PostgreSQL
> LISTEN/NOTIFY (migration 0007 trigger `trg_ecn_instances_notify`). Frontend polling
> (15–30s) retained as automatic fallback on SSE disconnect. See §19 for full SSE sequence.

```mermaid
---
config:
  theme: light
  layout: elk
  look: classic
---
graph LR
  subgraph Services["oskar-app (FastAPI)"]
    ecn_svc["ECN Service<br/>status transition"]
    bom_svc["BOM Service"]
    sup_svc["Supplier Worker<br/>oskar-worker (Celery)"]
    sse_ep["SSE endpoint<br/>GET /ecn/{id}/stream<br/>Sprint 2"]
  end

  subgraph Notify["Notification — Celery tasks"]
    smtp["aiosmtplib<br/>SMTP 10.10.0.155:25"]
  end

  subgraph FE["OSKAR Frontend"]
    poll["HTTP polling<br/>GET /api/v1/ecn/{id}<br/>every 15–30 s (fallback)"]
    sse_client["SSE listener<br/>Sprint 2"]
  end

  subgraph PG["PostgreSQL"]
    trigger["trg_ecn_instances_notify<br/>AFTER UPDATE → pg_notify"]
  end

  ecn_svc -->|"dispatch Celery task\n(after DB commit)"| smtp
  bom_svc -->|"dispatch Celery task"| smtp
  sup_svc -->|"dispatch Celery task"| smtp

  ecn_svc -->|"UPDATE ecn_instances"| trigger
  trigger -->|"LISTEN ecn_{id}"| sse_ep
  sse_ep -.->|"text/event-stream"| sse_client

  poll -->|"reads current status"| ecn_svc
  smtp -->|"email to approvers\n/ originator"| ext["Approvers / Originator<br/>email inbox"]
```

---

## 8. Supplier Intelligence Fan-out (Iteration 3)

```mermaid
---
config:
  theme: light
  layout: elk
  look: classic
---
graph TB
  trigger["Engineer searches part<br/>e.g. SRX-10045"]
  worker["oskar-worker (Celery)<br/>asyncio.gather — all suppliers in parallel"]

  trigger --> worker

  worker -->|"OAuth2 — Phase 1 real"| dk["DigiKeyAdapter<br/>api.digikey.com"]
  worker -.->|"stub — Phase 3"| mo["MouserAdapter<br/>api.mouser.com"]
  worker -.->|"stub — Phase 3"| rs["RSComponentsAdapter<br/>api.rs-online.com"]
  worker -.->|"stub — Phase 3"| ar["ArrowAdapter<br/>api.arrow.com"]
  worker -.->|"stub — Phase 3"| av["AvnetAdapter<br/>api.avnet.com"]

  dk --> agg["Result aggregation<br/>(Celery task)"]
  mo --> agg
  rs --> agg
  ar --> agg
  av --> agg

  agg --> api["oskar-app<br/>GET /api/v1/supplier/search/{part}"]
  api --> frontend["OSKAR Frontend<br/>Price / availability panel"]
```

---

## 9. Technology Stack

| Layer | Technology | Key Decision |
|-------|-----------|-------------|
| Backend | Python 3.12 / FastAPI | Async-first; aligns with ML/AI direction |
| API versioning | `/api/v1/` prefix — Sprint 1 Day 1 | Non-Negotiable #13 — never omit |
| Database | PostgreSQL 16 | Enterprise-grade; future Data Warehouse integration |
| Session store | PostgreSQL — `jti_blocklist` + `refresh_tokens` tables | JTI blocklist + refresh token hashes; 50-user scale, PK lookup sub-ms |
| Event bus | HTTP polling on `GET /api/v1/ecn/{id}` | Human-paced workflow — steps take hours; polling adequate. `LISTEN/NOTIFY` reserved if live-push ever required |
| Task broker | Celery + PostgreSQL (`celery[sqlalchemy]`) | Supplier fan-out (6+ APIs), retry, aggregation — PostgreSQL broker adequate at this volume; Redis eliminated |
| Auth | JWT + `IdentityProvider` protocol | `LDAPIdentityProvider` (on-prem AD); `EntraIDProvider` stub |
| Frontend | React / TypeScript — **standalone** | Separate IIS vhost; incompatible auth with SM-Portal |
| Supplier adapters | `SupplierAdapter` ABC | Per-adapter circuit breaker; 1 real + 5 stubs in Phase 1 |
| ERP adapters | `ERPAdapter` ABC | `MovexRestAdapter` (prod); `IFSAdapter` (stub, v1 only) |
| Deployment | Docker Compose on Linux VM (VMware, Ubuntu 24.04 LTS) | VMware confirmed — 2 vCPU / 4 GB |
| Container registry | Harbor (self-hosted on OSKAR VM) — Manal owns | Provisioned by 2026-04-17 |
| Reverse proxy | IIS (HTTPS, ADCS certificate — Manal) | Windows Server standard |
| LLM context | `ai/` folder — provider-agnostic markdown | Non-Negotiable #12 |
| LLM adapters | `.providers/claude/`, `.providers/openai-compatible/` | Thin, swappable |

---

## 10. Redis Elimination (ADR-007)

> **Decision:** ADR-007 (`decisions/ADR-007-redis-elimination-postgresql-broker.md`) — accepted 2026-04-17.
> **Supersedes:** PRE-2 (Redis three-DB logical separation).

Redis has been removed from the OSKAR stack. All three former Redis jobs are served by PostgreSQL:

| Former Redis role | Replacement | Decision rationale |
|------------------|-------------|--------------------|
| Celery broker (DB0) | `celery[sqlalchemy]` — PostgreSQL transport | Tens of tasks/day; PG broker adequate at this volume |
| JTI blocklist + refresh tokens (DB1) | `jti_blocklist` + `refresh_tokens` tables | 50-user scale; UUID PK lookup sub-ms |
| Event stream (DB2) | HTTP polling (fallback) + **SSE via pg_notify** (`GET /api/v1/ecn/{id}/stream`, Sprint 2) | **SSE implemented** — migration 0007 trigger fires AFTER UPDATE on ecn_instances |

**Docker Compose stack (production):** `oskar-db` · `oskar-app` · `oskar-worker` · `oskar-frontend` — no `oskar-redis`.

---

## 11. SHA-256 Audit Chain

> **Decision:** ADR-004. **Implementation:** `ecn_transition_history` table (migration `0001_initial_schema.py`); hash computed in `ECNWorkflowMachine.compute_transition_hash()`.

Every ECN transition is recorded as an immutable row in `ecn_transition_history`. Rows form a per-ECN linked chain via `sha256_prev` — tamper-evident without a blockchain.

**Fields included in hash** (canonical JSON, sorted keys, SHA-256):

```json
{
  "id":               "uuid4 — row PK",
  "ecn_id":           "uuid — FK to ecn_instances",
  "from_status":      "integer | null (null for chain head)",
  "to_status":        "integer",
  "action":           "submit | approve_role | dc_approve | complete_management_review | role_assigned | ...",
  "actor_username":   "sAMAccountName (LDAP-verified) | 'system' for Celery transitions",
  "actor_role":       "DC | QM | ... | null",
  "notes":            "free text | null",
  "movex_payload":    "JSONB — MI call payloads (Sprint 2) | null",
  "agent_provenance": "JSONB — AI suggestion accepted by engineer | null",
  "sha256_prev":      "hex string | null (chain head)",
  "created_at":       "ISO 8601 UTC"
}
```

**Rules:**
- `sha256_self` is computed in Python (`hashlib.sha256`) before INSERT — never in a DB trigger
- `sha256_prev` is `NULL` for the first row per ECN (chain head); unique index enforces exactly one head per ECN
- `ecn_transition_history` is INSERT + SELECT only for `oskar_app` — RLS enforced in migration `0003_rls_policies.py`
- To verify chain integrity: see `ai/memory/12-data-model.md §6.4`

**Chain integrity check (returns 0 rows if intact):**
```sql
SELECT id, sha256_self
FROM ecn_transition_history t1
WHERE sha256_prev != (
    SELECT sha256_self FROM ecn_transition_history t2
    WHERE t2.ecn_id = t1.ecn_id
      AND t2.created_at < t1.created_at
    ORDER BY t2.created_at DESC LIMIT 1
);
```

---

## 12. ECN Workflow Engine Design

> **Decision:** Celery + PostgreSQL + `transitions` library. See `decisions/ADR-002-workflow-engine-celery-postgresql-transitions.md`.
> **Implementation:** `src/workflow/machine.py` — `ECNWorkflowMachine` + `ECNStatus` IntEnum (2026-04-16).

### Layered responsibility

| Layer | Technology | Location | Owns |
|---|---|---|---|
| State machine | `transitions` library (`ECNWorkflowMachine`) | `src/workflow/machine.py` | Legal transitions, guard conditions, SHA-256 hash computation |
| Workflow state | PostgreSQL (13 tables) | `ecn_instances.status` | All ECN state — single source of truth; never in Celery or Redis |
| Side-effect execution | Celery (async workers) | `src/workers/` (Sprint 2) | Movex MI calls, email dispatch, Redis stream publish |

**Critical rule:** Workflow state lives in PostgreSQL. Celery executes side effects only. A Redis restart or worker crash must never leave an ECN in an unknown state.

**Machine is DB-agnostic.** `ECNModel` and `TransitionContext` are plain dataclasses — no SQLAlchemy ORM objects enter the machine. The caller (FastAPI service layer) reads from DB, constructs the dataclasses, triggers the machine, then persists the result inside a DB transaction.

### Transactional Outbox Pattern (replaces Stargile LogicalUnitOfWork)

Every Movex write follows this sequence:

1. **Human confirms** (FastAPI, synchronous) → DB transaction commits atomically: `ecn_instances.status` advance + `movex_outbox` entry + `ecn_transition_history` record (SHA-256 chain)
2. **Celery picks up** outbox entry → executes MI calls in declared order, idempotent (`acks_late=True`, `idempotency_key` on outbox row)
3. **On MI failure** → exponential retry (30s → 5min → 30min); ECN stays at APPROVED (correct — Movex write pending); `ecn_movex_errors` updated; DC alerted via Celery email task at attempt 3; ABANDONED + EM alerted at attempt 10
4. **On success** → ECN advances to IMPLEMENTED via `movex_write_complete` trigger; Celery dispatches `ecn.implemented` email notification

This eliminates Stargile's stuck-ECN problem: APPROVED = Movex pending (correct), IMPLEMENTED = Movex confirmed (correct). The DC sees per-MI-call error state via the DC Recovery UI panel.

### PostgreSQL Schema — 13 Tables

**Migrations:** `alembic upgrade head` — three files in `alembic/versions/`.

**Core tables:**

| Table | Replaces (Stargile) | Purpose |
|---|---|---|
| `ecn_instances` | ZECNHEAD + ProcessInst | ECN header, 11 statuses, change scope flags, cost fields, `extra_data JSONB` safety valve |
| `ecn_role_assignments` | ProcessInstAssignment + System.rolemap XML | Per-ECN role assignments; INSERT-only; RLS enforced |
| `ecn_approval_steps` | WorkItem + WorkItemAssignment | Per-step approval records with `skipped` state for conditional roles; `at_status` column |
| `ecn_transition_history` | ProcessInstControl | SHA-256 audit chain; INSERT-only; RLS enforced |
| `ecn_rejections` | ZECNRJCT | Rejection records with restart/proceed resolution |
| `ecn_movex_errors` | ZECNMELG | Per-MI-call error log (MSID field); visible to DC recovery UI |
| `movex_outbox` | LogicalUnitOfWork | Transactional outbox; idempotency key; states: pending/processing/completed/failed/abandoned |

**ECN line tables:**

| Table | Replaces (Stargile) | Purpose |
|---|---|---|
| `ecn_items` | ZECNITMN | ECNItem equivalent; `drawing_created` flag; `alias_written` flag; `questionnaire_data JSONB` |
| `ecn_mpns` | ZECNMPNI | MPN aliases per item; normalised (no ecn_id — join via ecn_items) |
| `ecn_bom_changes` | ZECNBOMS | BOM add/change/delete records; `movex_snapshot_at_review JSONB` for concurrency detection |

**System tables:**

| Table | Replaces (Stargile) | Purpose |
|---|---|---|
| `system_role_users` | System.rolemap XML | Global role-to-user mapping; facility-scoped; source for auto-assignment |
| `ecn_step_conditions` | Hardcoded `isRoleChecked()` | Data-driven approval routing (7 seed rows for facility='L') |
| `ecn_training_acknowledgements` | — | ISO 13485 §6.2 training records; created on ECN CLOSED |

**Deferred (not Sprint 1):** `ecn_circuit_refs` (ZECNCIRF), threaded comments table, ZQ01–ZQ18 questionnaire UI (JSONB safety valve present).

---

## 13. RBAC Hybrid Model

> **Decision:** AD groups (coarse) + PostgreSQL per-ECN assignments (fine). See `decisions/ADR-003-rbac-hybrid.md`.

### Four-layer model

| Layer | Store | Question answered | Who manages |
|---|---|---|---|
| Authentication | Active Directory (LDAPS bind port 636) | Is this a valid Scanfil APAC user? | IT (Manal) |
| Platform access | AD groups (`OSKAR-Engineers`, `OSKAR-Approvers`) | Can this user log into OSKAR? | IT (Manal) |
| System role | `system_role_users` (PostgreSQL) | Is this user a DC / EM / QM system-wide? | OSKAR Admin |
| Per-ECN role | `ecn_role_assignments` (PostgreSQL) | Who is the DC for ECN-2026-0042? | Auto-assigned at creation; overrideable by Admin |

### Rules

- **JWT carries AD groups only** — never per-ECN roles (those are mutable; always query DB)
- **Every approval gate** checks both: JWT group (coarse, stateless) then `ecn_role_assignments` (fine, live DB query)
- **`ecn_step_conditions`** table drives which roles are required per ECN based on change scope flags — no conditionals in Python code
- **Role assignments are INSERT-only** — never UPDATE; assignment history is immutable
- **Self-approval is prohibited** at the application layer: originator cannot approve any stage of their own ECN regardless of role membership

### Auto-assignment logic

At ECN creation, for each required role: query `system_role_users` for active users in that role. If exactly 1 user → auto-assign with `is_auto_assigned=TRUE`. If 0 users → ECN creation fails (surface error before submission). If >1 users → assignment stays unallocated; DC assigns manually.

---

## 14. ECN Status Machine

> **Implementation:** `src/workflow/machine.py` — `ECNWorkflowMachine` + `ECNStatus` IntEnum.
> **Decision rationale:** `decisions/ADR-002-workflow-engine-celery-postgresql-transitions.md`.
> **ADR-009 (2026-05-01):** DC single gate. SUBMITTED(10) and DC_REVIEW(20) removed; DC_APPROVED(25) added
> between MANAGEMENT_REVIEW and APPROVED. IMPLEMENTED→CLOSED is now automatic (Celery). 10 active statuses.
> ARCHIVED is a flag (`is_archived=TRUE`), not a status — no state machine transition involved.

### 14.1 Status Reference

| Code | Name | Terminal? | Description |
|------|------|-----------|-------------|
| 0 | DRAFT | No | Being authored; not yet submitted |
| 25 | DC_APPROVED | No | DC final sign-off before Movex write; customer approval gate here |
| 30 | ENGINEERING_REVIEW | No | SE/CE technical review in progress |
| 40 | MANAGEMENT_REVIEW | No | Parallel approval block: EM + QM always; PM/SC/FN conditional |
| 50 | APPROVED | No | All human approvals complete; Movex writes queued in outbox |
| 60 | IMPLEMENTED | No | All Movex writes confirmed successful by Celery |
| 65 | REJECTED | No | Rejected at any stage; routed to originator with mandatory reason |
| 70 | CLOSED | **Yes** | Post-implementation complete; automatic via Celery (ADR-009) |
| 80 | CANCELLED | **Yes** | Withdrawn before approval; no Movex writes made |
| 90 | ON_HOLD | No | Suspended pending external input; pre_hold_status saves prior status |
| — | ARCHIVED | Flag only | `is_archived=TRUE` on CLOSED records; not a transition |

**Tombstoned integers:** 10 (SUBMITTED) and 20 (DC_REVIEW) removed by ADR-009. Must never be reused.

### 14.2 Full Transition Diagram

```mermaid
stateDiagram-v2
    [*] --> DRAFT : ECN created

    DRAFT --> ENGINEERING_REVIEW : submit<br>[originator only · ≥1 item · title set]
    DRAFT --> CANCELLED : cancel<br>[originator or Admin]
    DRAFT --> ON_HOLD : place_on_hold<br>[DC or Admin · reason + resume date]

    ENGINEERING_REVIEW --> MANAGEMENT_REVIEW : approve_engineering<br>[SE or CE]
    ENGINEERING_REVIEW --> REJECTED : reject<br>[SE or CE · reason mandatory]
    ENGINEERING_REVIEW --> ON_HOLD : place_on_hold<br>[DC or Admin]

    MANAGEMENT_REVIEW --> MANAGEMENT_REVIEW : approve_role<br>[EM/QM/PM/SC/FN/CE/CA · no self-approval]
    MANAGEMENT_REVIEW --> DC_APPROVED : complete_management_review<br>[system — all required roles approved]
    MANAGEMENT_REVIEW --> REJECTED : reject<br>[any required role · reason mandatory]
    MANAGEMENT_REVIEW --> ON_HOLD : place_on_hold<br>[DC or Admin]

    DC_APPROVED --> APPROVED : dc_approve<br>[DC only · ISO 13485 customer approval gate]
    DC_APPROVED --> REJECTED : reject<br>[DC only · reason mandatory]
    DC_APPROVED --> ON_HOLD : place_on_hold<br>[DC or Admin]

    APPROVED --> IMPLEMENTED : movex_write_complete<br>[Celery — all outbox entries completed]
    APPROVED --> ON_HOLD : place_on_hold<br>[DC or Admin]

    IMPLEMENTED --> CLOSED : auto_close<br>[Celery — automatic · no human action required]
    IMPLEMENTED --> ON_HOLD : place_on_hold<br>[DC or Admin]

    REJECTED --> ENGINEERING_REVIEW : resubmit<br>[originator only]
    REJECTED --> CANCELLED : withdraw<br>[originator only]
    REJECTED --> ON_HOLD : place_on_hold<br>[DC or Admin]

    ON_HOLD --> DRAFT : resume [pre_hold=0]
    ON_HOLD --> ENGINEERING_REVIEW : resume [pre_hold=30]
    ON_HOLD --> MANAGEMENT_REVIEW : resume [pre_hold=40]
    ON_HOLD --> DC_APPROVED : resume [pre_hold=25]
    ON_HOLD --> APPROVED : resume [pre_hold=50]
    ON_HOLD --> IMPLEMENTED : resume [pre_hold=60]
    ON_HOLD --> REJECTED : resume [pre_hold=65]

    CLOSED --> [*]
    CANCELLED --> [*]
```

### 14.3 Normal Workflow (Happy Path)

```mermaid
---
config:
  theme: light
  layout: elk
  look: classic
---
sequenceDiagram
    participant OR as Originator
    participant DC as Document Controller
    participant SE as SE / CE
    participant MG as Mgmt Block\n(EM · QM · PM · SC · FN)
    participant SYS as System (Celery)

    OR->>SE: submit — DRAFT → ENGINEERING_REVIEW
    Note over OR,SE: Guard: ≥1 item, title set, originator only\nNo DC gate at submission (ADR-009)

    SE->>MG: approve_engineering\nENGINEERING_REVIEW → MANAGEMENT_REVIEW
    Note over MG: Parallel block opens\nAll required roles notified simultaneously

    par Parallel approvals (any order)
        MG->>MG: approve_role [EM]
    and
        MG->>MG: approve_role [QM]
    and
        MG-->>MG: approve_role [PM] (if routing/operation changes)
    and
        MG-->>MG: approve_role [SC] (if new_parts or lead_time_changes)
    and
        MG-->>MG: approve_role [FN] (if wapc_delta_pct > threshold)
    end

    MG->>DC: complete_management_review\nMANAGEMENT_REVIEW → DC_APPROVED
    Note over DC: DC_APPROVED — single gate before Movex write (ADR-009)

    DC->>SYS: dc_approve — DC_APPROVED → APPROVED
    Note over SYS:  movex_outbox entries created atomically<br>with status advance (Transactional Outbox)

    SYS->>SYS: movex_write_complete\nAPPROVED → IMPLEMENTED
    Note over SYS: All MI calls confirmed<br>Celery dispatches email notification

    SYS->>SYS: auto_close — IMPLEMENTED → CLOSED
    Note over SYS: Celery-triggered — no DC action required (ADR-009)
```

### 14.4 Rejection and Recovery Paths

```mermaid
---
config:
  theme: light
  layout: elk
  look: classic
---
flowchart TD
    classDef active  fill:#1168bd,color:#fff,stroke:#0b4884
    classDef reject  fill:#c0392b,color:#fff,stroke:#922b21
    classDef hold    fill:#d68910,color:#fff,stroke:#9a6109
    classDef term    fill:#2d6a4f,color:#fff,stroke:#1b4332

    DR([DRAFT]):::active
    ER([ENGINEERING_REVIEW]):::active
    MR([MANAGEMENT_REVIEW]):::active
    DA([DC_APPROVED]):::active
    AP([APPROVED]):::active
    IM([IMPLEMENTED]):::active
    RJ([REJECTED]):::reject
    CL([CLOSED]):::term
    CA([CANCELLED]):::term
    OH([ON_HOLD]):::hold

    DR -->|"submit [originator]"| ER
    ER -->|"approve_engineering [SE/CE]"| MR
    MR -->|"complete_management_review\n[system — auto]"| DA
    DA -->|"dc_approve [DC]\ncustomer approval gate"| AP
    AP -->|"movex_write_complete\n[Celery]"| IM
    IM -->|"auto_close [Celery]"| CL

    ER -->|"reject [SE/CE]\nreason mandatory"| RJ
    MR -->|"reject [any role]\nreason mandatory"| RJ
    DA -->|"reject [DC]\nreason mandatory"| RJ

    RJ -->|"resubmit [originator]"| ER
    RJ -->|"withdraw [originator]"| CA
    DR -->|"cancel [originator/Admin]"| CA

    DR & ER & MR & DA & AP & IM & RJ -->|"place_on_hold\n[DC/Admin]\nreason + resume date"| OH
    OH -->|"resume [DC/Admin]\nrestores pre_hold_status"| DR
    OH -->|"resume"| ER
    OH -->|"resume"| MR
    OH -->|"resume"| DA
    OH -->|"resume"| AP
    OH -->|"resume"| IM
    OH -->|"resume"| RJ
```

### 14.5 Parallel Approval Block — MANAGEMENT_REVIEW Detail

```mermaid
---
config:
  theme: light
  layout: elk
  look: classic
---
flowchart TD
    classDef always   fill:#1168bd,color:#fff,stroke:#0b4884
    classDef cond     fill:#5d6d7e,color:#fff,stroke:#424949
    classDef approved fill:#2d6a4f,color:#fff,stroke:#1b4332
    classDef rejected fill:#c0392b,color:#fff,stroke:#922b21
    classDef skip     fill:#aab7b8,color:#333,stroke:#717d7e

    enter(["Enter MANAGEMENT_REVIEW\n(from ENGINEERING_REVIEW)"])

    enter --> eval["Evaluate ecn_step_conditions\nfor facility + change scope flags"]

    eval --> EM["EM\n(always required)"]:::always
    eval --> QM["QM\n(always required — ISO 13485)"]:::always
    eval --> PM{"routing_changes=TRUE\nor operation_changes=TRUE?"}
    eval --> SC{"new_parts=TRUE\nor lead_time_changes=TRUE?"}
    eval --> FN{"wapc_delta_pct > FN_THRESHOLD_PCT?"}

    PM -->|Yes| PM_step["PM approval step\n(pending)"]:::cond
    PM -->|No| PM_skip["PM skipped\nskip_reason set"]:::skip

    SC -->|Yes| SC_step["SC approval step\n(pending)"]:::cond
    SC -->|No| SC_skip["SC skipped"]:::skip

    FN -->|Yes| FN_step["FN approval step\n(pending)"]:::cond
    FN -->|No| FN_skip["FN skipped"]:::skip

    EM --> EM_dec{approved?}
    QM --> QM_dec{approved?}
    PM_step --> PM_dec{approved?}
    SC_step --> SC_dec{approved?}
    FN_step --> FN_dec{approved?}

    EM_dec -->|Yes| check["All non-skipped\napproval steps = approved?"]:::approved
    QM_dec -->|Yes| check
    PM_dec -->|Yes| check
    SC_dec -->|Yes| check
    FN_dec -->|Yes| check

    EM_dec -->|No / Reject| reject(["→ REJECTED\nremaining steps → superseded"]):::rejected
    QM_dec -->|No / Reject| reject
    PM_dec -->|No / Reject| reject
    SC_dec -->|No / Reject| reject
    FN_dec -->|No / Reject| reject

    check -->|"All approved\n(pending count = 0)"| advance(["→ APPROVED\nmovex_outbox entries created"]):::approved
    check -->|"Still pending"| wait["Wait for remaining\napprovers"]
    wait --> check
```

### 14.6 Movex Write State Machine (APPROVED → IMPLEMENTED)

```mermaid
---
config:
  theme: light
  layout: elk
  look: classic
---
sequenceDiagram
    participant API as oskar-app (FastAPI)
    participant DB as PostgreSQL
    participant Celery as oskar-worker (Celery)
    participant MAPI as movex-rest-api
    participant DC as Document Controller

    Note over API,DB: Human approves final step (atomic transaction)
    API->>DB: BEGIN
    API->>DB: UPDATE ecn_instances SET status=50 (APPROVED)
    API->>DB: INSERT movex_outbox (state='pending', idempotency_key=...)
    API->>DB: INSERT ecn_transition_history (sha256_self=...)
    API->>DB: COMMIT

    API->>Celery: dispatch task (fire-and-forget, after commit)

    loop For each outbox entry (in order)
        Celery->>DB: SELECT outbox WHERE state='pending' ORDER BY created_at
        Celery->>DB: UPDATE outbox SET state='processing'
        Celery->>MAPI: POST /mi/PDS001MI/AddProduct {Idempotency-Key: ...}
        alt MI success (MSID blank)
            MAPI-->>Celery: 200 OK
            Celery->>DB: UPDATE outbox SET state='completed'
        else MI failure (MSID non-blank or 5xx)
            MAPI-->>Celery: error
            Celery->>DB: INSERT ecn_movex_errors (attempt_number, error_code)
            Celery->>DB: UPDATE outbox SET state='failed', next_retry_at=+30s/5m/30m
            Note over Celery,DC: attempt=3 → alert DC via Celery email task\nattempt=10 → state='abandoned', alert EM
        end
    end

    Note over Celery,DB: All entries completed
    Celery->>DB: BEGIN
    Celery->>DB: UPDATE ecn_instances SET status=60 (IMPLEMENTED)
    Celery->>DB: INSERT ecn_transition_history (actor='system', sha256_self=...)
    Celery->>DB: COMMIT
    Celery->>smtp: dispatch ecn.implemented email notification (aiosmtplib)
```

### 14.7 Guard Conditions Reference

| Trigger | Source | Guard | Who |
|---------|--------|-------|-----|
| `submit` | DRAFT | ≥1 item; title set; actor = originator | Originator |
| `approve_engineering` | ENGINEERING_REVIEW | actor_role ∈ {`SE`, `CE`} | SE or CE |
| `approve_role` | MANAGEMENT_REVIEW | actor_role ∈ valid mgmt roles; actor ≠ originator | EM/QM/PM/SC/FN/CE/CA |
| `complete_management_review` | MANAGEMENT_REVIEW | all non-skipped steps `approved`; `all_required_approved_fn` registered | System |
| `dc_approve` | DC_APPROVED | actor_role = `DC`; `customer_approved_at` set if `requires_customer_approval=TRUE` (ADR-009) | DC |
| `movex_write_complete` | APPROVED | _(no guard — Celery only)_ | Celery |
| `auto_close` | IMPLEMENTED | _(no guard — Celery only, ADR-009)_ | Celery |
| `reject` | ENGINEERING_REVIEW/MANAGEMENT_REVIEW/DC_APPROVED | rejection_reason non-empty | Role-appropriate |
| `resubmit` | REJECTED | actor = originator | Originator |
| `cancel` | DRAFT | actor = originator or actor_role = `AD` | Originator or Admin |
| `place_on_hold` | any non-terminal/non-hold | actor_role ∈ {`DC`, `AD`}; hold_reason set; expected_resume_date set | DC or Admin |
| `resume` | ON_HOLD | actor_role ∈ {`DC`, `AD`}; `pre_hold_status` not NULL | DC or Admin |
> **ADR-009:** `accept` (SUBMITTED→DC_REVIEW) and `pass_to_engineering` (DC_REVIEW→ENGINEERING_REVIEW) removed. Integers 10 and 20 tombstoned.

**Self-approval prohibition:** Enforced on `approve_role` — actor_username cannot equal ecn.originator_username at any stage, regardless of role membership.

---

## 15. ECN Event Notification (supersedes F-6 Redis Streams design)

> **ADR-007** (2026-04-17) eliminated Redis. The F-6 Redis Streams event schema is superseded.
> The `schema_version` envelope concept and event type taxonomy below are retained — applied to
> future `LISTEN/NOTIFY` payloads if that path is taken (see ADR-007).

### Current approach — Celery + direct SMTP

On each ECN status transition, the FastAPI service layer dispatches a Celery task
(`tasks.notify_ecn_transition`) after the DB transaction commits. The task calls
`aiosmtplib` directly (SMTP 10.10.0.155:25). No stream intermediary.

Frontend status updates: HTTP polling on `GET /api/v1/ecn/{id}` — 15–30s interval, adequate
for a workflow where steps take hours.

### ECN event taxonomy (retained for LISTEN/NOTIFY future path)

These event types are emitted by the service layer. Currently consumed by Celery notification
tasks only. If `LISTEN/NOTIFY` is introduced, this taxonomy becomes the `pg_notify` payload.

| event_type | Trigger | Key fields |
|------------|---------|-----------|
| `ecn.created` | ECN created (DRAFT) | `title`, `originator` |
| `ecn.submitted` | DRAFT → ENGINEERING_REVIEW | — |
| `ecn.approved_by_role` | Parallel approver completes | `role`, `remaining` |
| `ecn.dc_approved` | DC_APPROVED → APPROVED | — |
| `ecn.implemented` | APPROVED → IMPLEMENTED | `mi_calls` count |
| `ecn.closed` | IMPLEMENTED → CLOSED (auto_close) | — |
| `ecn.rejected` | Any stage → REJECTED | `rejection_number`, `reason` |
| `ecn.on_hold` | Any stage → ON_HOLD | `reason`, `resume_by` |
| `ecn.role_assigned` | Role reassigned by DC | `role_id`, `new_username`, `superseded_username` |
> **ADR-009:** `ecn.accepted` and `ecn.passed_to_engineering` events removed (SUBMITTED/DC_REVIEW statuses tombstoned).
| `ecn.resumed` | ON_HOLD → prior status | `resumed_status` |
| `ecn.cancelled` | → CANCELLED | — |
| `ecn.movex_write_failed` | Outbox attempt 3 | `mi_transaction`, `error_code` |
| `ecn.movex_write_abandoned` | Outbox attempt 10 | `mi_transaction` |

### Version history

| Version | Date | Change |
|---------|------|--------|
| 1 | 2026-04-15 | Initial schema — ECN lifecycle events |

---

## 16. Non-Negotiables

Full list of 13 non-negotiables: `context/OSKAR_Integrated_Plan_v5.1.md` Section 3.

Architecture-relevant summary:
1. Movex is SSoT — always, without exception
2. Human-in-the-loop — no Movex commit without explicit approval
3. Immutable SHA-256 audit chain — every engineering event
4. `/api/v1/` prefix from Sprint 1 Day 1
5. `ai/` context layer is LLM-agnostic — no tool syntax inside `ai/` files

---

## 17. AIProvider Abstraction (ADR-010)

`AIProvider` is a `typing.Protocol` in `src/adapters/ai/base.py`. Mirrors `IdentityProvider`,
`ERPAdapter`, and `SupplierAdapter` — swap providers via `AI_PROVIDER_CLASS` env var, no
caller code changes.

| Class | Stage | Trigger |
|-------|-------|---------|
| `NoOpAIProvider` | **1 — Active** | Default (no env var needed) |
| `OllamaProvider` | 2 | AI Lab provisioned on-prem |
| `AnthropicProvider` | 2 | Data boundary approved by Karen/Scanfil Group |
| `AzureOpenAIProvider` | 2 | Azure subscription confirmed with Maarit |

```mermaid
---
config:
  theme: light
  layout: elk
  look: classic
---
classDiagram
  class AIProvider {
    <<Protocol>>
    +suggest_description(raw, max_len) AISuggestion
    +check_mpn_status(mpns) list~MPNStatus~
    +draft_ecn_title(description) AISuggestion
    +detect_bom_risks(items) list~AISuggestion~
  }
  class NoOpAIProvider {
    +suggest_description() AISuggestion
    +check_mpn_status() list~MPNStatus~
    model = "noop"
    confidence = 0.0
  }
  class OllamaProvider {
    <<Stage 2 — AI Lab>>
    +base_url: str
    +model: str
  }
  class AnthropicProvider {
    <<Stage 2 — approved cloud>>
    +api_key: str
    +model: str
  }
  class AISuggestion {
    <<frozen dataclass>>
    +suggestion_type: str
    +content: str
    +confidence: float
    +model: str
    +prompt_hash: str
  }
  class MPNStatus {
    <<frozen dataclass>>
    +mpn: str
    +lifecycle: str
    +eol_date: str
    +suggested_alternative: str
  }
  AIProvider <|.. NoOpAIProvider : implements
  AIProvider <|.. OllamaProvider : implements
  AIProvider <|.. AnthropicProvider : implements
  AIProvider ..> AISuggestion : returns
  AIProvider ..> MPNStatus : returns
```

**Prompt injection defence:** All external text (BOM descriptions, MPN fields from customer
uploads) must be passed through `sanitize_for_prompt()` before inclusion in any AI prompt.
Mandatory for all Stage 2 provider implementations. See ADR-010 for threat model and
defence layers.

---

## 18. Agent Action Outbox

`agent_actions` extends the Transactional Outbox pattern (ADR-002) for AI-proposed write
actions. `requires_human BOOLEAN NOT NULL DEFAULT TRUE` enforces Non-Negotiable #2 at the
schema level — no AI action can bypass human review.

```mermaid
---
config:
  theme: light
  layout: elk
  look: classic
---
stateDiagram-v2
  note right of pending_approval
    Agent proposes action.
    Visible in approval UI (Stage 2).
    Human receives notification.
  end note

  [*] --> pending_approval : Agent proposes\n(authority_level = approval_required)
  [*] --> executing : Agent proposes\n(authority_level = autonomous)

  pending_approval --> approved : Engineer approves\n[reviewed_by set]
  pending_approval --> rejected : Engineer rejects\n[reviewed_by set]

  approved --> executing : Celery picks up
  executing --> completed : Action succeeds\n[result JSONB written]
  executing --> failed : Action fails\n[result JSONB with error]

  rejected --> [*]
  completed --> [*]
  failed --> [*]

  note right of executing
    Stage 1: no Celery task reads agent_actions.
    Table exists — state machine design is locked in.
    Stage 2 adds oskar-agent Celery worker.
  end note
```

| | `movex_outbox` | `agent_actions` |
|---|---|---|
| Who creates | FastAPI (after human approval) | AI agent / MCP tool call |
| Who executes | `oskar-worker` Celery | `oskar-agent` Celery (Stage 2) |
| Human gate | At MANAGEMENT_REVIEW / DC_APPROVED | `pending_approval` state |
| Non-Negotiable #2 | Enforced | Enforced (`requires_human=TRUE`) |
| Audit chain | `ecn_transition_history` | `agent_actions.result JSONB` |

---

## 19. SSE Event Flow

`GET /api/v1/ecn/{ecn_id}/stream` — implemented Sprint 2. Uses raw `asyncpg.connect()`
(SQLAlchemy `AsyncSession` is incompatible with `LISTEN/NOTIFY`). Semaphore cap: 20
concurrent connections. Keepalive ping every 25s (within IIS proxy idle timeout).

```mermaid
---
config:
  theme: light
  layout: elk
  look: classic
---
sequenceDiagram
  participant FE as OSKAR Frontend
  participant API as oskar-app (FastAPI)
  participant PG as PostgreSQL
  participant Worker as oskar-worker (Celery)

  FE->>API: GET /api/v1/ecn/{id}/stream\n[Authorization: Bearer JWT]
  API->>API: Validate JWT → get_current_user()
  API->>PG: SELECT status, ecn_number, updated_at WHERE id = $1
  PG-->>API: current row
  API-->>FE: data: {"type":"ecn_status","status":25,...}\n\n (initial event)
  API->>PG: LISTEN ecn_{id}

  Note over FE,Worker: Engineer approves a step (separate request)
  FE->>API: PATCH /api/v1/ecn/{id}/status {trigger: "approve_role"}
  API->>PG: BEGIN\nUPDATE ecn_instances SET status=30\nINSERT movex_outbox\nINSERT ecn_transition_history\nCOMMIT
  PG->>PG: trg_ecn_instances_notify fires\npg_notify('ecn_{id}', payload)
  PG-->>API: notification received (SSE connection)
  API-->>FE: data: {"type":"ecn_status","status":30,...}\n\n

  Note over API,FE: Every 25s with no changes
  API-->>FE: data: {"ping":true}\n\n (keepalive)

  Note over FE,API: Client disconnects (browser tab closed)
  API->>PG: UNLISTEN ecn_{id}
  API->>PG: close connection
```

---

## 20. Extended Platform Architecture — Future State (Stage 2+)

Orientation diagram for Stage 2 developers. Blue = implemented (Stage 1). Green = Sprint 2.
Grey = Stage 2. Purple = Stage 3.

```mermaid
---
config:
  theme: light
  layout: elk
  look: classic
---
graph TB
  classDef existing fill:#1168bd,color:#fff,stroke:#0b4884
  classDef sprint2  fill:#2d6a4f,color:#fff,stroke:#1b4332
  classDef stage2   fill:#5d6d7e,color:#fff,stroke:#424949
  classDef stage3   fill:#6c3483,color:#fff,stroke:#4a235a
  classDef external fill:#666,color:#fff,stroke:#444

  subgraph Clients["AI Clients (Stage 2+)"]
    mcp_client["Claude Desktop / Cursor\n(MCP client)"]:::stage2
    group_agent["Scanfil Group Agent\n(A2A — Stage 3)"]:::stage3
    i3x_agent["Siemens i3x\n(A2A — Stage 3)"]:::stage3
  end

  subgraph MCP["oskar-mcp container (Stage 2)"]
    mcp_srv["MCP Server\nNo DB — REST only\nservice-account JWT"]:::stage2
  end

  subgraph Frontend["OSKAR Frontend (React/TS)"]
    fe_ecn["ECN forms"]:::existing
    fe_sse["SSE listener"]:::sprint2
    fe_actions["Agent Actions\nApproval UI (Stage 2)"]:::stage2
  end

  subgraph API["oskar-app (FastAPI /api/v1/)"]
    r_ecn["/ecn/ — existing"]:::existing
    r_auth["/auth/ — existing"]:::existing
    r_sse["/ecn/{id}/stream — Sprint 2"]:::sprint2
    r_ai["/ai/ — Stage 2"]:::stage2
    r_events["/events/ingest — Stage 2"]:::stage2
    r_hooks["/webhooks/ — Stage 2"]:::stage2
    r_actions["/agent-actions/ — Stage 2"]:::stage2
  end

  subgraph Adapters["Adapter Layer"]
    erp["ERPAdapter\nMovexRestAdapter · IFSAdapter stub"]:::existing
    sup["SupplierAdapter\nDigiKey · 5 stubs"]:::existing
    ai["AIProvider\nNoOpAIProvider (Stage 1)\nOllama · Anthropic (Stage 2)"]:::sprint2
  end

  subgraph Workers["oskar-worker (Celery)"]
    w_ecn["ecn_tasks"]:::existing
    w_sup["supplier_tasks"]:::existing
    w_ai["ai_tasks — Stage 2"]:::stage2
  end

  subgraph DB["PostgreSQL (oskar-db)"]
    db_core["13 core ECN tables"]:::existing
    db_auth["Auth tables"]:::existing
    db_ai["ai_suggestions\nagent_actions\n(schema Sprint 2)"]:::sprint2
  end

  subgraph External["External Systems"]
    movex["Movex / M3"]:::external
    digikey["DigiKey"]:::external
    ailab["AI Lab · Ollama (Stage 2)"]:::stage2
    i3x_sys["Siemens i3x (Stage 3)"]:::stage3
  end

  mcp_client -->|MCP protocol| mcp_srv
  mcp_srv -->|REST| r_ecn & r_ai & r_actions

  fe_ecn --> r_ecn
  fe_sse -.->|SSE| r_sse
  fe_actions --> r_actions

  r_ecn --> erp & db_core
  r_sse --> db_core
  r_ai --> ai
  r_actions --> db_ai

  w_ai --> ai & db_ai

  ai -.-> ailab
  erp --> movex
  sup --> digikey
```
