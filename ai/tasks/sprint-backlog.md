# OSKAR — Sprint Backlog
# Source of truth for all work status.
# oskar-state.md (gitignored) is for next-session notes only — not for tracking status.
# Last synced: 2026-07-09 (Sprint 7 complete; Sprint 8 planned)

---

## Phase 0 — Harness

### Completed ✅
- [x] `ai/` structure created (01–05 + 00-skills-audit.md)
- [x] `.providers/claude/CLAUDE.md` — full rewrite from SRX template v3.0
- [x] `ai/memory/05-stargile-ecn-reference.md` — ECN data model, 13 statuses, 16 roles, Movex calls + Section 8 graph analysis
- [x] `ai/memory/00-skills-audit.md` — 60+ skills, 18 agents, security + design sections
- [x] `.providers/claude/skills/Tier1/oskar-ecn-rules.md` — state machine from IECNStatus.java
- [x] `decisions/ADR-001` — SM-Portal navigation link, no auth coupling
- [x] `decisions/PRE-1` through `PRE-12` — Phase 0 architectural decisions
- [x] `ai/evidence/decision-log.md` — lightweight decision index
- [x] `Dockerfile` — Python 3.12-slim, non-root user, healthcheck
- [x] `requirements.txt` — FastAPI, SQLAlchemy, Celery, Redis, LDAP3, aiosmtplib, tenacity, pybreaker, transitions
- [x] `src/main.py` — FastAPI app, CORS, health endpoint, v1_router stub
- [x] `oskar-state.md` — session state (gitignored)
- [x] `.gitignore` — secrets, Python cache, Docker data
- [x] Expert review: @architect-system-design + @expert-cybersecurity + @expert-manufacturing-engineering (2026-04-10)
- [x] **P0-3:** `scripts/setup-server-secrets.sh` + `.env.example` ✅ 2026-04-14
- [x] **P0-4:** `src/logging_config.py` + `src/middleware/correlation.py` + `src/routers/health.py` ✅ 2026-04-14
- [x] **PRE-12:** CONO environment mapping — CONO=300 dev/UAT, CONO=100 production ✅ 2026-04-15

### Remaining ⏳
- [x] **P0-1:** `git init` + first commit — ✅ 2026-04-21 (commit 8d18f81)
- [x] **P0-2:** Add to Knowledge Vault post-commit hook ✅ 2026-04-21

---

## Phase 1 — Discovery

### Track A: MI Gap Analysis ✅ Complete
- [x] A-1 through A-6 — gap matrix, Sprint 2 blockers flagged, endpoint spec for @developer-dotnet

### Track B: ECN Behavioural Spec ✅ Complete
- [x] B-1 through B-9 — `ai/memory/06-ecn-requirements.md` written

### Track C: Compliance Foundation
- [x] C-1 `ai/memory/07-compliance-requirements.md` written ✅
- [ ] C-2 IQ/OQ/PQ sign-off chain confirmation ⏳
  - IQ author: Manal | OQ/PQ author: Mihai | Approver: hsalazar | QM: Divya (Melbourne) | Final: Karen
  - Sign-off owner per section depends on matter — Karen (system/process), Divya (quality), Manal (infrastructure)
- [x] C-3 Training record trigger + customer approval flag documented ✅

### Track D: Risk + Security Baseline ✅ Complete
- [x] D-1 through D-4 — risk register, STRIDE, security controls, incident runbook

### Track E: Testing Strategy ✅ Complete
- [x] E-1 `ai/memory/10-testing-strategy.md` written

---

## Phase 2 — Architecture pre-gates

| # | Task | File | Status |
|---|------|------|--------|
| F-1 | PostgreSQL schema — 13 tables | `ai/memory/12-data-model.md` + migrations 0001–0003 | ✅ 2026-04-16 |
| F-2 | ERPAdapter ABC — all 7 write methods + `get_item_facility` | `src/adapters/erp/base.py` | ✅ 2026-04-16 |
| F-3 | `get_email()` on IdentityProvider Protocol | `src/auth/providers.py` | ✅ 2026-04-16 |
| F-4 | MovexRestAdapter — shared `httpx.AsyncClient` connection pool | `src/adapters/erp/movex.py` | ✅ 2026-04-16 |
| F-5 | `tenacity` retry + `pybreaker` circuit breaker on ERP adapter | `src/adapters/erp/movex.py` | ✅ 2026-04-16 |
| F-6 | ~~Redis DB2 event envelope schema~~ — **Superseded by ADR-007**. `schema_version` envelope concept retained for future `LISTEN/NOTIFY` path. See `ai/memory/03-oskar-architecture.md §15` | `ai/memory/03-oskar-architecture.md §15` | ✅ 2026-04-17 (ADR-007) |
| F-7 | `transitions` in requirements.txt | `requirements.txt` | ✅ |

---

## Scope Addition — DBCHK_OpenECN Replacement

| # | Task | Sprint | Status |
|---|------|--------|--------|
| G-1 | `facility` column on `ecn_instances` (default `'D'` = Melbourne) | F-1 | ✅ included in 0001_initial_schema.py; default updated in 0013 |
| G-2 | `next_action_users[]` on ECN list response | Sprint 1 | ✅ 2026-04-21 |
| G-3 | ECN list filters: status, overdue, assignee, facility, age_days | Sprint 1 | ✅ 2026-04-21 |
| G-4 | Celery beat task `tasks/ecn_digest.py` — daily HTML email | Sprint 2 | ✅ `src/tasks/ecn_notifications.py:288-347` |
| G-5 | `POST /api/v1/admin/ecn-digest` — on-demand digest trigger | Sprint 2 | ✅ `src/routers/admin.py:24-43` |
| G-6 | Go-live: disable `DBCHK_OpenECN` SQL Server Agent job on DBSRV | Go-live | ⏳ |

---

## Sprint 1 — Platform Foundation

### Pre-conditions
| Pre-condition | Status |
|--------------|--------|
| P0-1: git init | ✅ 2026-04-21 |
| LDAPS confirmed with Devian/Manal | ⏳ Not a priority; details expected next week (~2026-05-08) |
| `/etc/oskar/secrets.env` on VM | ⏳ VM provisioned ✅ (4 CPUs / 16 GB RAM / 100 GB storage — 2026-05-01). Docker + Harbor install: Lead Engineer responsibility. |
| structlog + correlation ID (P0-4) | ✅ |
| JWT TTL 60min/8h in .env.example + ADR-006 | ✅ |
| PostgreSQL schema (F-1) | ✅ |
| ERPAdapter ABC (F-2) | ✅ |
| transitions in requirements.txt (F-7) | ✅ |

### Sprint 1 Tasks

| # | Task | File | Status |
|---|------|------|--------|
| S1-1 | IFSAdapter — stubs satisfying ABC contract | `src/adapters/erp/ifs.py` | ✅ 2026-04-16 |
| S1-2 | Alembic scaffold + migrations 0001–0003 | `alembic/` | ✅ 2026-04-16 |
| S1-3 | ECNWorkflowMachine — 11 statuses, all guards, ON_HOLD, SHA-256 chain | `src/workflow/machine.py` | ✅ 2026-04-16 |
| S1-4 | Workflow unit tests — 30+ cases | `tests/workflow/test_machine.py` | ✅ 2026-04-16 |
| S1-5  | Auth — JWT module: access/refresh token creation+validation, JTI helpers (HS256, alg:none block) | `src/auth/jwt.py` | ✅ 2026-04-20 |
| S1-5a | Auth — DB session factory (`get_session` FastAPI dep) | `src/db.py` | ✅ 2026-04-20 |
| S1-6  | ~~Auth — Redis client factory~~ | _Eliminated — ADR-007_ | ✅ N/A |
| S1-7  | Auth — Alembic migration `0004_auth_tables` — `jti_blocklist` + `refresh_tokens` | `alembic/versions/0004_auth_tables.py` | ✅ 2026-04-17 |
| S1-8  | Auth — FastAPI deps: `get_current_user` (DB JTI check), `require_group`, convenience aliases | `src/auth/dependencies.py` | ✅ 2026-04-20 |
| S1-9  | Auth — endpoints: login / refresh (rotation + family detection) / logout | `src/routers/auth.py` | ✅ 2026-04-20 |
| S1-10 | Auth — LDAPS TLS hardening: `_make_server()` with `CERT_REQUIRED`, CA from Docker secret | `src/auth/providers.py` | ✅ 2026-04-20 |
| S1-11 | Auth — wire auth router into v1_router | `src/routers/__init__.py` | ✅ 2026-04-20 |
| S1-12 | Auth — unit tests: 19 passed, 2 skipped (alg:none — jose doesn't expose encoding path) | `tests/auth/test_jwt.py` | ✅ 2026-04-20 |
| S1-13 | ECN CRUD — `POST /api/v1/ecn/` | `src/routers/ecn.py` + `src/services/ecn.py` | ✅ 2026-04-21 |
| S1-14 | ECN CRUD — `GET /api/v1/ecn/{id}` | `src/routers/ecn.py` + `src/services/ecn.py` | ✅ 2026-04-21 |
| S1-15 | ECN CRUD — `PATCH /api/v1/ecn/{id}/status` (wires machine to API) | `src/routers/ecn.py` + `src/services/ecn.py` | ✅ 2026-04-21 |
| S1-16 | ECN list — `GET /api/v1/ecn/` with G-2/G-3 filters + `next_action_users[]` | `src/routers/ecn.py` + `src/services/ecn.py` | ✅ 2026-04-21 |
| S1-16a | ECN router tests — 29 passed | `tests/routers/test_ecn.py` + `tests/conftest.py` | ✅ 2026-04-21 |
| S1-17 | Docker hardening — read-only filesystem, no Redis container | `docker/` + compose files | ✅ 2026-04-22 |
| S1-18 | CI — gitleaks pre-commit + pip-audit | `.pre-commit-config.yaml` | ✅ 2026-04-22 |

---

## Sprint 2 — ECN Workflow

**Pre-conditions:**
- [x] ~~MMS025MI.AddAlias added to movex-rest-api~~ ✅ 2026-05-01 — MMS025MI.json confirmed present; generic routing exposes `POST /api/MMS025MI/AddAlias` automatically. No additional dotnet work needed.
- [ ] MPDDOC drawing creation added to movex-rest-api (@developer-dotnet)
- [ ] Sprint 1 complete

**Routing operations ground truth (2026-05-08, verified):**
- MI program: `PDS002MI.AddOperation` / `UpdateOperation` → MPDOPE (`MVXCDTA`)
- `LstOperation` works correctly when called without `FDAT`/`OPNO` (4-field key, confirmed by RPG source + live MITEST)
- Pre-flight read must use direct DB2 query against MPDOPE (safer for automated calls — no cursor seek risk)
- Product `LFRMR241-7278` ground truth: 2 ops in Movex (SMTTS/50, MANASY/100) vs 8 in Labour Routing template → 6 × AddOperation + 2 × UpdateOperation required
- Full analysis: `movex-rest-api/analysis/PDS002MI-routing-analysis.md`

**Sprint 2 pre-gate design decisions (completed before code):**
- ✅ **ADR-009** (2026-05-01): DC single gate — SUBMITTED+DC_REVIEW removed; DC_APPROVED (25) added before Movex write; IMPLEMENTED→CLOSED automatic. `decisions/ADR-009-dc-single-gate-role-customisation.md`
- ✅ **Migration 0006** (2026-05-01): `ecn_items.item_group VARCHAR(3)` + `ecn_items.customer_alias VARCHAR(30)` promoted from JSONB; `ecn_instances` CHECK constraint updated for ADR-009.
- ✅ **Risk R-19** (2026-05-01): BOM-level IP inference via DigiKey/Octopart API query patterns. Scanfil management approval gate required before Stage 3 BOM tools. `ai/memory/09-known-risks-and-pitfalls.md`.

### Sprint 2 Tasks

| # | Task | File | Status |
|---|------|------|--------|
| S2-1 | Optimistic locking (ADR-008) — `If-Unmodified-Since`; 428 if absent, 409 if stale | `src/services/ecn/helpers.py:322-346` | ✅ 2026-04-24 |
| S2-2 | Transactional Outbox — retry 30s→5min→30min; DC alert attempt 3; ABANDONED+EM attempt 10; 23 tests | `src/tasks/movex_outbox.py` | ✅ 2026-04-24 |
| S2-3 | ECN write gate — `oskar_worker` REVOKE INSERT on `movex_outbox` + RLS on `ecn_instances` | migration 0005 | ✅ 2026-04-24 |
| S2-4 | Workflow machine (ADR-009) — SUBMITTED/DC_REVIEW removed; DC_APPROVED=25; guards + tests updated | `src/workflow/machine.py` | ✅ 2026-05-04 |
| S2-5 | Per-ECN role customisation (ADR-009) — `POST /api/v1/ecn/{id}/role-assignments`; DC-authority guard; supersede-and-insert | `src/services/ecn/workflow.py:555-645` | ✅ 2026-05-04 |
| S2-6 | Rejection flows — `reject` trigger → REJECTED; `resubmit` → ENGINEERING_REVIEW; originator-only guard | `src/workflow/machine.py:250-266` | ✅ |
| S2-7 | MPN alias — `_queue_alias_outbox()` at IMPLEMENTED→CLOSED; `MMS025MI.AddAlias` with `customer_alias`+`item_group` as ALWQ | `src/services/ecn/workflow.py:526-551` | ✅ |
| S2-8 | Parallel approval block — `approve_role` per-role; `complete_management_review` auto-advances when all required roles approved | `src/workflow/machine.py:206-222` | ✅ |
| S2-9 | Overdue escalation — Celery beat 6h; 48h → assignee+EM email; 96h → DC added | `src/tasks/ecn_notifications.py:124-285` | ✅ |
| S2-10 | Email notifications — `ECNEmailService` async SMTP (10.10.0.155:25); digest + escalation + rejection | `src/tasks/ecn_notifications.py:53-88` | ✅ |
| S2-11 | Effectivity date fields on ECNItems — `effectivity_type` + `effectivity_from` | migration 0001 | ✅ |
| S2-12 | DBCHK replacement G-4 — `send_ecn_digest()` Celery beat daily | `src/tasks/ecn_notifications.py:288-347` | ✅ |
| S2-13 | DBCHK replacement G-5 — `POST /api/v1/admin/ecn-digest` (DC-only, 202 Accepted) | `src/routers/admin.py:24-43` | ✅ |
| S2-14 | Drawing number workflow — `_queue_drawing_outbox()` at DC_APPROVED; guard on `is_new_item=TRUE` items | `src/services/ecn/workflow.py:501-524` | ⚠️ OSKAR done — blocked on MPDDOC endpoint (@developer-dotnet) |
| S2-15 | MPN extended fields (Nick, 2026-04-29) — schema: `lifecycle`, `eol_date`, `lead_time_weeks`, `msl_level`, `packaging_type`, `do_not_buy`, `alt_mpn` | migration 0007 | ⚠️ Schema ✅ — Pydantic models + ECN item UI pending |
| S2-16 | DC recovery UI — Movex Write Status Panel | `src/routers/sse.py` + migration 0007 | ⚠️ SSE infra + pg_notify ✅ — display logic pending |
| S2-17 | ECN version/revision lineage — SHA-256 audit chain per transition; revision_number preserved on resubmit | `src/services/ecn/helpers.py:138-192` | ⚠️ Audit chain ✅ — UI lineage display pending |
| S2-18 | BOM concurrency detection before Movex write — delta detection at DC_APPROVED gate | `src/services/ecn/workflow.py` | ⚠️ Schema ✅ — delta logic pending |
| S2-19 | Routing ops — `ecn_routing_operations` migration (0009) — `ecn_item_id FK`, `operation_number`, `operation_description`, `work_centre`, `run_time` (POPITI), `setup_time` (POSETI), `change_type` (ADD/UPDATE), `movex_snapshot JSONB` | `alembic/versions/0009_ecn_routing_operations.py` | ✅ 2026-05-08 |
| S2-20 | Routing ops — DTO models — `RoutingOperationRequest` + `RoutingOperationResponse`; mirror MPDOPE key fields | `src/services/ecn/models.py` | ✅ 2026-05-08 |
| S2-21 | Routing ops — ERP adapter pre-flight read — `get_routing_operations(item, faci, strt)` abstract + movex impl; `PDS002MI.LstOperation` GET (no FDAT/OPNO — 4-field key confirmed) | `src/adapters/erp/base.py` + `movex.py` | ✅ 2026-05-08 |
| S2-22 | Routing ops — outbox queue method — `_queue_routing_operations_outbox()`; `PDS002MI.AddOperation` or `UpdateOperation` per row at DC_APPROVED gate; `_mi_verb` maps ADD/UPDATE → Add/Update | `src/services/ecn/workflow.py` | ✅ 2026-05-08 |
| S2-23 | Routing ops — items service CRUD — `GET/POST/PATCH/DELETE /api/v1/ecn/{id}/items/{item_id}/routing`; 15 tests passing | `src/routers/ecn.py` + `src/services/ecn/items.py` + `tests/routers/test_routing_operations.py` | ✅ 2026-05-08 |

---

## Sprint 3 — Part Number Intelligence (820-Minute Scope Gap)

> **Source:** Engineers meeting 2026-04-29 (Branko, Nick, Karen). Karen confirmed scope:
> *"if this tool is ECN focused and it replaces that 820 minutes with 30 minutes, there's a win."*
> These items were identified as the primary remaining time sinks not covered by Sprint 2.

**Pre-conditions:**
- [ ] Sprint 2 complete
- [x] Engineering Team's methodology documentation received ✅ — `context/ecn-history/Initial_Meeting_Nick_and_Branko_290426/`
- [x] movex-rest-api: `GET /api/mitpop/search` custom DB2 endpoint deployed (@developer-dotnet) — **S3-1 blocker**. Renamed to `/api/parts/search-alias` 2026-06-16.

**Key finding (2026-05-11):** No M3 MI program supports reverse alias lookup (POPN→ITNO).
MMS025MI.GetAlias requires CONO+ALWT+ITNO+ALWQ+E0PA+VFDT (ITNO-first). MMS025MI.LstAlias
requires CONO+ITNO (also ITNO-first). MMS001MI not enabled at Scanfil APAC.
Stargile never solved this — `RequestECNDBHelper.java:313` has a TODO comment from 2008.
Solution: custom parameterised DB2 query against `MVXCDTA.MITPOP WHERE MPPOPN=@popn`.
Full endpoint spec in `ai/memory/02-movex-erp-authority.md §7`.

### Sprint 3 Tasks

| # | Task | File | Status |
|---|------|------|--------|
| S3-1 | Part number reverse alias lookup — `GET /api/v1/parts/alias?popn=&cuno=`; queries `MVXCDTA.MITPOP` via custom DB2 endpoint on movex-rest-api; returns `full_match`/`partial_match`/`no_match`. `app.state.erp_adapter` lifespan wired. 34 tests passing. Replaces manual MOVEX search (30 min → seconds). Source: Nick 42:56–44:27. | `src/routers/parts.py` + `src/adapters/erp/movex.py` + `src/adapters/erp/base.py` + `src/main.py` | ✅ LIVE 2026-06-09 — validated end-to-end vs IBM i CONO 300 |
| S3-2 | Auto Scanfil APAC part number generation — `GET /api/v1/parts/suggest-pn?prgp=&itcl=&cuno=[&commodity_override=]`; resolves commodity code from Engineering Team's full matrix (50 rows, 11 multi-code pairs); queries `MVXCDTA.MITMAS` for next sequence via `GET /api/mitmas/next-sequence`. 'LF' prefix is the company identifier (not lead-free marker). `TEM/TEMP`=4 codes (66/76/81/90), `PLA/INJEC`+`PLA/PLAMC`=2 codes (65/67) — corrected from initial spec after cross-check against CSV. 50 tests passing. | `src/routers/parts.py` + `src/services/ecn/commodity_codes.py` + `src/adapters/erp/` | ✅ LIVE 2026-06-09 — validated end-to-end vs IBM i CONO 300 |
| S3-3 | Stock code autofill — `POST /api/v1/parts/autofill`; enriches `ecn_items` row: (1) supplier chain DigiKey→Nexar→stubs → AI smart truncation (`AIProvider.suggest_description`) → `item_name` ≤30 chars; (2) `MMS200MI.GetItmBasic` → `unit_of_measure` (skipped for `is_new_item=True`). 26/26 tests passing. `supplier_part_cache` PostgreSQL cache (migration 0010, 30-day TTL). `DigiKeyAdapter` + `NexarAdapter` wired in lifespan (skip gracefully when `CLIENT_ID` unset). Source: Hector 1:01:32. | `src/routers/parts.py` + `src/adapters/suppliers/` + `src/adapters/erp/movex.py` + `alembic/versions/0010_supplier_part_cache.py` + `src/main.py` | ✅ 2026-05-13 |
| S3-4 | Proc & Product Group auto-population — `GET /api/v1/parts/groups` returns all valid (prgp, itcl) pairs with commodity codes for ECN item dropdowns (no auth, filterable by ?prgp=&itcl=). `POST /api/v1/parts/autofill-groups` writes validated prgp+itcl onto ecn_items row, returns updated item + commodity_codes list for immediate suggest-pn wiring. Pair validated against Engineering Team's matrix before write — unknown pairs rejected 422. 31 tests passing. Eliminates manual datasheet lookup (~30 min/part, VSM p.6). | `src/routers/parts.py` + `tests/routers/test_proc_prod_groups.py` | ✅ 2026-05-15 |
| S3-5 | Scanfil APAC item description normalisation — `GET /api/v1/parts/suggest-description?prgp=&itcl=&commodity_code=` returns Engineering Team's canonical template names (69 entries, all pre-validated ≤30 chars, multiple templates per code e.g. HWR/HARDW/69 → SCREW/WASHER/NUT/CRIMP). `POST /api/v1/parts/validate-description` enforces Movex MITMAS.MMITDS rules: ≤30 chars, no tab/pipe/null/control chars; optional write-back to ecn_items when valid. `DESCRIPTION_TEMPLATES` map added to `commodity_codes.py` with import-time length guard. 49 tests passing. Eliminates silent upload rejection from Stargile (VSM p.6). | `src/routers/parts.py` + `src/services/ecn/commodity_codes.py` + `tests/routers/test_description_normalisation.py` | ✅ 2026-05-15 |

**Explicitly out of scope for Iteration 1 (Karen, 1:10:42):**
- BOM scrubbing as standalone tool (Nick 24:33) — Iteration 3
- Customer BOM vs Quoted BOM comparison (Nick 34:37) — Iteration 2/3
- AI/MCP integration (Nick, Hector 54:40) — gated on Scanfil group AI policy

---

## Sprint 4 — Local Stand-Up + React Frontend ✅ COMPLETE (2026-05-28)

> **Result:** Backend running locally in Docker. Full React frontend built and working against live API.
> ECN workflow demonstrated end-to-end: create → submit → eng review → approve → on hold → reject → resubmit.
> POC assessed as covering ~85% of the 820-minute scope (Karen's Stage 1 target).

### Local Backend Stand-Up ✅

| # | Task | File | Status |
|---|------|------|--------|
| S4-1 | Local `.env` file — dev values, `AUTH_PROVIDER=dev`, `SECURE_COOKIE=false` | `.env` (gitignored) | ✅ 2026-05-18 |
| S4-2 | `docker-compose.dev.yml` — dev auth, healthchecks, correct DB name `oskar` | `docker/docker-compose.dev.yml` | ✅ 2026-05-18 |
| S4-3 | `DevIdentityProvider` — `AUTH_PROVIDER=dev` bypasses LDAP; `DEV_USERS` allowlist | `src/auth/providers.py` | ✅ 2026-05-18 |
| S4-4 | `scripts/seed-dev-data.sql` — all roles seeded for facility='L'; idempotent | `scripts/seed-dev-data.sql` | ✅ 2026-05-18 |
| S4-5 | Docker up, Alembic migrations, seed data running | Local | ✅ |
| S4-6 | Smoke-test: health, login, create ECN, submit, transitions all verified | Local | ✅ |
| S4-7 | `scripts/seed_demo.py` — demo ECNs seeded at all workflow stages | `scripts/seed_demo.py` | ✅ |

**Demo users** (any password works in dev): `hsalazar` (OR+DC), `eng_user` (SE), `qm_user` (QM), `dc_user` (DC)

### React Frontend — Core Screens ✅

Stack: Vite + React 18 + TypeScript + Tailwind v4 + shadcn/ui + React Hook Form + Zod + TanStack Query + Zustand + Axios

| # | Task | File | Status |
|---|------|------|--------|
| S4-8 | Vite + React + TypeScript scaffold; full dependency install | `frontend/` | ✅ |
| S4-9 | Custom Axios instance: Bearer token attach, 401 auto-refresh, redirect on refresh failure | `frontend/src/api/axios.ts` | ✅ |
| S4-10 | Zustand auth store: `{ user, login, logout }`; JWT decode on load; session storage | `frontend/src/store/auth.ts` | ✅ |
| S4-11 | Login page: credentials → `POST /api/v1/auth/login`; token stored, redirect to `/ecn` | `frontend/src/pages/LoginPage.tsx` | ✅ |
| S4-12 | ECN list page: stats cards (total/draft/review/overdue), data table with status badges, age, next-action user, filters | `frontend/src/pages/ECNListPage.tsx` | ✅ |
| S4-13 | ECN create page: RHF+Zod; title, description, facility select, change scope checkboxes | `frontend/src/pages/ECNCreatePage.tsx` | ✅ |
| S4-14 | ECN detail page: status badge, role-aware action bar, approval steps panel, role assignment editing (DC only), inline toast on transition, reject/hold modals | `frontend/src/pages/ECNDetailPage.tsx` | ✅ |
| S4-15 | ECN item panel (shadcn Sheet): item fields, effectivity type+date, proc/product group, 30-char name counter; create + edit | `frontend/src/components/ECNItemPanel.tsx` | ✅ |
| S4-16 | Vite dev proxy: `/api → http://localhost:8000`; SM Portal design tokens in Tailwind | `frontend/vite.config.ts` | ✅ |

### Frontend Bug Fixes Applied (2026-05-27 session)

| Bug | Fix |
|-----|-----|
| 422 on item create — `line_number`, `item_number`, `effectivity_type` missing | Added all three to schema + API call |
| 500 on item PATCH — empty string sent to Postgres DATE column | `stripEmpty()` helper filters `""` and `undefined` before send |
| 500 on DATE effectivity — asyncpg rejects ISO string for DATE column | Backend: `date.fromisoformat()` in `items.py` |
| 422 on Submit for Review — `defaultRole()` derived `"Engineers"` from AD group name | Removed group-name derivation; explicit `role` on every `ActionDef` |
| "Transition failed" on Reject/Place on Hold — missing `rejection_reason` / `hold_reason` | `needsModal` pattern routes to structured modal dialogs |
| Toast shown at bottom, 2s duration | Repositioned top-center fixed; increased to 5s |

### Frontend Refactor (2026-05-28 — committed c1c0d20)

| Component | Before | After |
|-----------|--------|-------|
| `pages/ECNDetailPage.tsx` | 873 lines | ~200 lines (container only) |
| `components/ECNItemPanel.tsx` | 442 lines | 1-line shim |
| `components/ecn/ECNItemPanel.tsx` | — | ~400 lines |
| `components/ecn/WorkflowPanel.tsx` | — | ~220 lines |
| `components/ecn/RoleRow.tsx` | — | ~80 lines |
| `components/ecn/ActionModal.tsx` | — | ~120 lines |
| `components/ecn/ECNCard.tsx` | — | ~80 lines |
| `lib/ecn-workflow.ts` | — | ~90 lines (domain constants) |
| `api/ecn.ts` | — | ~90 lines (all ECN API functions) |

Also fixed: `ECNCreatePage` POST `/api/v1/ecn` missing trailing slash → 401 (FastAPI 307 redirect drops Auth header).

### What's Deferred Post-POC

| Feature | Current state | Unblocked by |
|---------|--------------|--------------|
| PN alias duplicate check (S3-1 live) | ✅ LIVE 2026-06-09 | — |
| PN auto-suggest (S3-2 live) | ✅ LIVE 2026-06-09 | — |
| Stock code autofill — DigiKey/Nexar (S3-3) | Backend ✅; adapters wired | DigiKey/Nexar API creds |
| MPN extended fields UI (S2-15) | Schema ✅ in DB | UI build |
| DC recovery panel / Movex write status (S2-16) | SSE infra + pg_notify ✅ | Display panel UI build |
| Drawing number outbox (S2-14) | Backend ✅ | MPDDOC endpoint from @developer-dotnet |
| Routing operations UI | Schema + CRUD API ✅ | UI build |
| Email notifications | `ECNEmailService` + digest ✅ | SMTP reachable from VM; needs VM deployment |
| Celery worker/beat | Code ✅ | VM deployment |
| VM deployment | VM provisioned (2026-05-01) | ➜ **Sprint 5** |

---

## Sprint 5 — VM Deployment (staging) ✅ CORE COMPLETE (2026-06-02)

> **Result:** Staging stack live on `apac-plm-ops.srxglobal.local` (10.131.1.10).
> All 5 containers healthy. 12 Alembic migrations applied. 7 demo ECNs seeded.
> Corporate proxy blocked Windows→VM Docker push — images built on VM directly (see LL-002).
> Remaining: IIS proxy, systemd auto-start, LDAP switchover (Manal dependency).

**Pre-conditions:**
- [x] VM provisioned (2026-05-01): 4 CPUs / 16 GB RAM / 100 GB storage ✅
- [x] Harbor v2.15.0 installed on VM — HTTP mode, `oskar` project created ✅
- [x] SSH enabled on VM (openssh-server installed 2026-06-02) ✅
- [x] Node.js 20 LTS installed on VM (for npm lock file regen) ✅
- [ ] DNS A record `apac-plm-ops.srxglobal.local` → VM IP (Manal) ⏳
- [ ] IIS reverse proxy rule on SRXWEBAPP1 for Oskar vhost (Lead Engineer) ⏳

**Deployment runbook:** `docs/runbooks/vm-deployment.md`

### Sprint 5 Tasks

| # | Task | File | Status |
|---|------|------|--------|
| S5-1 | Harbor install on VM — Docker Engine + HTTP mode + `oskar` project | `docs/runbooks/harbor-installation.md` | ✅ 2026-06-02 |
| S5-2 | Configure insecure registry on VM + `docker login 10.131.1.10` | `/etc/docker/daemon.json` on VM | ✅ 2026-06-02 |
| S5-3 | Download source zip from GitHub onto VM, extract to `/opt/oskar-src` | VM filesystem | ✅ 2026-06-02 |
| S5-4 | Build `oskar-app:v0.1.0` and `oskar-frontend:v0.1.0` on VM, push to Harbor | `Dockerfile`, `frontend/Dockerfile` | ✅ 2026-06-02 |
| S5-5 | Create `/opt/oskar/.env.staging`; copy `docker-compose.staging.yml`; `docker compose up -d` | `docker/docker-compose.staging.yml` | ✅ 2026-06-02 |
| S5-6 | Run Alembic migrations — 12 revisions applied (0001→0012) | `alembic/versions/` | ✅ 2026-06-02 |
| S5-7 | Run demo seed — 7 ECNs across all workflow stages | `scripts/seed_demo.py` | ✅ 2026-06-02 |
| S5-8 | Smoke test API — health + login + ECN list from VM | `curl http://localhost:8001/health` | ✅ 2026-06-02 |
| S5-9 | IIS reverse proxy: `oskar.srxglobal.local` → ports 8001/3001 | IIS on SRXWEBAPP1 | ⏳ Lead Engineer |
| S5-10 | Validate SMTP → 10.10.0.155:25 from staging container | — | ⏳ |
| S5-11 | Switch `AUTH_PROVIDER=ldap` once Manal confirms LDAPS service account | `.env.staging` on VM | ⏳ Blocked on Manal |
| S5-12 | Enable `oskar-staging.service` systemd unit for auto-start on reboot | `/etc/systemd/system/` on VM | ⏳ |

### Dockerfile Fixes Applied During Sprint 5

| Fix | Before | After |
|-----|--------|-------|
| `Dockerfile` missing alembic | Only copied `src/` | Also copies `alembic/`, `alembic.ini`, `scripts/` |
| Frontend nginx image | `nginx:alpine` (root required) | `nginxinc/nginx-unprivileged:alpine` (non-root, port 8080) |
| Frontend compose port | `3001:80` | `3001:8080` |

### Sprint 5 Acceptance Checklist

- [x] Harbor UI accessible at `http://10.131.1.10`
- [x] `docker login 10.131.1.10` succeeds from VM
- [x] `oskar-app:v0.1.0` and `oskar-frontend:v0.1.0` in Harbor
- [x] All 5 staging containers Up (app healthy, worker/beat running, frontend up, db healthy)
- [x] 12 Alembic migrations applied cleanly
- [x] 7 demo ECNs seeded across all workflow stages
- [x] `curl http://localhost:8001/health` → `{"status":"ok"}`
- [ ] Login from LAN browser works
- [ ] ECN list loads in browser with ≥5 seed ECNs
- [ ] ECN transition fires in browser
- [ ] `oskar-staging.service` enabled in systemd
- [ ] IIS vhost routes correctly
- [ ] LDAP auth confirmed (Manal dependency)

---

## Sprint 6 — ECN List & Detail UX Enhancements ✅ COMPLETE (2026-07-02)

> **Result:** 667 tests passing (2 skipped, 17 warnings). All Tier 1 plan items shipped.
> UAT DB password mismatch diagnosed and resolved. 502 Bad Gateway after CORS update resolved
> (nginx stale IP — frontend container restart). Sprint plan: `ai/plans/regarding-the-oskar-project-eager-dolphin.md`

### Backend

| # | Task | File | Status |
|---|------|------|--------|
| S6-1 | Migration 0017 — `customer_ecn_refs VARCHAR(500)` on `ecn_instances` + GIN FTS index covering `ecn_number, title, description, customer_number, customer_ecn_refs` | `alembic/versions/0017_customer_ecn_refs_and_fts.py` | ✅ |
| S6-2 | Migration 0018 — `ecn_comments` table (`id, ecn_id, author_username, body, created_at, updated_at`) with cascade delete and `(ecn_id, created_at)` index | `alembic/versions/0018_ecn_comments.py` | ✅ |
| S6-3 | ECN list endpoint — `sort_by` + `sort_dir` params; `customer_name` join via Movex cache; `customer` + `originator` filter params; FTS search replaces ILIKE | `src/routers/ecn.py` + `src/services/ecn/` | ✅ |
| S6-4 | `ECNSummary` + `ECNDetail` schemas — add `customer_name`, `customer_ecn_refs` | `src/services/ecn/models.py` | ✅ |
| S6-5 | `ecn_comments` router — `GET/POST/PATCH/DELETE /api/v1/ecn/{ecn_id}/comments`; author-only edit; DC or author delete; no status restriction | `src/routers/ecn_comments.py` | ✅ |
| S6-6 | Migration 0015 dedup fix — CTE DELETE before `uq_ecn_items_ecn_id_item_number` unique constraint (dev data had duplicates) | `alembic/versions/0015_ecn_items_unique_item_number.py` | ✅ |
| S6-7 | Migration 0017 asyncpg apostrophe fix — removed escaped apostrophe from `COMMENT ON COLUMN` string | `alembic/versions/0017_customer_ecn_refs_and_fts.py` | ✅ |
| S6-8 | `ecn_comments.py` DELETE 204 fix — added `response_model=None` to prevent FastAPI startup `AssertionError` crash-loop | `src/routers/ecn_comments.py` | ✅ |

### Frontend

| # | Task | File | Status |
|---|------|------|--------|
| S6-9 | `ECNListPage` — Entry Date column, sortable column headers, Customer column reordered, Cust. ECN column | `frontend/src/pages/ECNListPage.tsx` | ✅ |
| S6-10 | `ECNListPage` — column-level dropdowns: Customer, Originator, Next Action (client-side from loaded data) | `frontend/src/pages/ECNListPage.tsx` | ✅ |
| S6-11 | `ECNListPage` — stat cards converted to clickable filter toggles: Active ECNs, Require My Action, Overdue (>7 days); mutual exclusion; client-side filtering on `next_action_users` and `ageDays()` | `frontend/src/pages/ECNListPage.tsx` | ✅ |
| S6-12 | `ECNCreatePage` — customer combobox: name-first search, "Customer Name (CODE)" labels, AC shown first | `frontend/src/pages/ECNCreatePage.tsx` | ✅ |
| S6-13 | `ECNCreatePage` — Customer ECN Refs text field (comma-separated) | `frontend/src/pages/ECNCreatePage.tsx` | ✅ |
| S6-14 | `ECNDetailPage` — customer name shown as "Name (CODE)"; CustomerECN refs as tag chips; customer alias in items list; item count footer | `frontend/src/pages/ECNDetailPage.tsx` | ✅ |
| S6-15 | `ECNDetailPage` — Import button visible (greyed with tooltip) in non-DRAFT states | `frontend/src/pages/ECNDetailPage.tsx` | ✅ |
| S6-16 | `ECNCommentsPanel` — chronological comment thread, inline textarea, Ctrl+Enter submit, optimistic update | `frontend/src/components/ecn/ECNCommentsPanel.tsx` | ✅ |
| S6-17 | `ItemUploadDrawer` + item editor — 30-char truncation warning badge + live `{n}/30` character counter | `frontend/src/components/ecn/ItemUploadDrawer.tsx` | ✅ |

### Fixes & Bug Squashes

| Bug | Root cause | Fix |
|-----|-----------|-----|
| Login hang on UAT | `ecn_comments.py` DELETE endpoint missing `response_model=None` → FastAPI startup `AssertionError` → container crash-loop | Added `response_model=None` to DELETE |
| `ECNCommentsPanel.tsx` build error | Unused `useEffect` in import | Removed from import |
| `ECNCreatePage.tsx` build error | `CustomerEntry` type import not using `import type` — `verbatimModuleSyntax` violation | Changed to `import { fetchCustomers, type CustomerEntry }` |
| Stat cards not filtering | `needs_my_action` SQL queried `ecn_role_assignments` (too broad); `next_action_users` is computed post-query and cannot be used as SQL WHERE | Moved all three toggles to client-side filtering on enriched result set |
| Test `test_invalid_change_type_returns_422` broken | Was using `"DELETE"` which is in `VALID_CHANGE_TYPES` — test was testing a valid value | Changed to `"REMOVE"` (genuinely invalid) |
| UAT `InvalidPasswordError` | `.env.staging` had `oskar_dev` password; actual DB password was `oskar_staging` | Reset DB password via `ALTER USER oskar WITH PASSWORD 'oskar_staging'`; updated `.env.staging`; runbook updated |
| UAT 502 Bad Gateway after CORS update | nginx in frontend container had stale IP for `oskar-app-staging` after app container restart | Restarted frontend container; runbook updated |

### UAT Infrastructure Notes (2026-06-29)

- PostgreSQL superuser is `oskar` (not `postgres` — container was initialized with `POSTGRES_USER=oskar`)
- Database name: `oskar_staging` (not `oskar`)
- Host port: `5433` (not `5432` — app container connects on `5432` via internal Docker network)
- All `psql` commands on VM host must use `-U oskar -d oskar_staging -p 5433`
- Run Alembic migrations from inside the app container, not from VM host: `docker exec oskar-app-staging alembic upgrade head`
- Full troubleshooting procedure: `docs/runbooks/vm-deployment.md §T-12`

---

## Sprint 7 — ECN Workflow Completions + Administration ✅ COMPLETE (2026-07-09)

> **Result:** 711 tests passing (2 skipped). All sprint items shipped. Browser cache stale-page
> bug resolved via `NoCacheMiddleware`. Drawing number Movex constraint removed (drawings are
> DMR files, not Movex records). Outbox dispatch wired end-to-end (BackgroundTasks + Celery).
> Admin page upgraded from read-only to full CRUD.

### D — Cancel ECN with Note ✅

| # | Task | File | Status |
|---|------|------|--------|
| S7-D1 | New workflow trigger `cancel` → status 80 (CANCELLED); allowed from DRAFT / ENG_REVIEW / MGMT_REVIEW / ON_HOLD; terminal | `src/workflow/machine.py` | ✅ |
| S7-D2 | Cancel modal — "Reason for cancellation" (required); stored in `ecn_transition_history.notes`; triggered from action bar | `frontend/src/components/ecn/ActionModal.tsx` + `ECNDetailPage.tsx` | ✅ |
| S7-D3 | Guard `_guard_cancel`: originator, DC, or Admin only; notes mandatory; blocked from IMPLEMENTED/CLOSED | `src/workflow/machine.py` | ✅ |
| S7-D4 | CANCELLED badge + status in list and detail | `frontend/src/lib/ecn-status.ts` | ✅ |
| S7-D5 | Tests: cancel transitions + guard violations in `test_machine.py` | `tests/workflow/test_machine.py` | ✅ |

### B — Administration Page ✅

| # | Task | File | Status |
|---|------|------|--------|
| S7-B1 | `GET/POST/DELETE /api/v1/admin/roles` — plant role defaults CRUD; DC-only; backed by `system_role_users` | `src/routers/admin.py` + `src/services/admin.py` | ✅ |
| S7-B2 | Admin UI — all 14 role cards shown; `+ Add` inline form per role (username + facility); hover-reveal × remove button + confirmation modal | `frontend/src/pages/AdminPage.tsx` | ✅ 2026-07-09 |
| S7-B3 | PN Categories tab — explicitly removed from scope (Engineering Team matrix is the source of truth; no admin UI needed) | — | ✅ removed |
| S7-B4 | Tests: 14 tests in `test_admin_roles.py` — list (with facility/role_id filter), add (201/403/409/422), remove (204/403/404) | `tests/routers/test_admin_roles.py` | ✅ |

### A — DMR/SharePoint Link ✅

| # | Task | File | Status |
|---|------|------|--------|
| S7-A1 | Migration 0022 — `dmr_url VARCHAR(1000)` on `ecn_instances`; nullable | `alembic/versions/0022_ecn_add_dmr_url.py` | ✅ |
| S7-A2 | `PATCH /api/v1/ecn/{id}` accepts `dmr_url`; DC or originator via existing field-update guard | `src/routers/ecn_core.py` | ✅ |
| S7-A3 | ECNCard — DMR URL shown as clickable link in metadata card; inline edit for DC/originator; accepts SharePoint HTTPS or UNC path | `frontend/src/components/ecn/ECNCard.tsx` | ✅ |

### F — Implementation Schedule ✅

> Checklist stored in `ecn_instances.extra_data.impl_checklist JSONB` — no migration needed.
> Section labels: Engineering (section 1), Program Manager — WIP Impact (section 2). Section 3 omitted (never used in Stargile).
> Power user validation questions filed in memory (`project_oskar_power_user_questions.md`).

| # | Task | File | Status |
|---|------|------|--------|
| S7-F1 | Checklist schema in `extra_data JSONB`; `_seed_impl_checklist()` called at `movex_write_complete` transition; 8 default items across 2 sections | `src/services/ecn/workflow.py` | ✅ |
| S7-F2 | Default items: (1) MES update, (2) AOI programs, (3) New wave pallets, (4) Valor MSS update, (5) PDS001/G routing text, (6) Documents to shopfloor, (7) Re-validation (medical), (8) Production First Article; each has `applicable/completed/completed_by/completed_at/notes` | `src/services/ecn/workflow.py` | ✅ |
| S7-F3 | `PATCH /api/v1/ecn/{id}/checklist` — toggle `applicable` (null/true/false) + `completed` + `notes`; DC or originator only | `src/routers/ecn_core.py` + `src/services/ecn/service.py` | ✅ |
| S7-F4 | Open Orders — `GET /api/v1/ecn/{id}/open-orders`; `MMS100MI.LstMO` via movex-rest-api per ECN item; returns MO number, item, qty, due date, facility | `src/routers/ecn_core.py` + `src/adapters/erp/movex.py` | ✅ |
| S7-F5 | `ImplementationSchedulePanel` — animated progress ring, section cards, `ApplicableToggle` (null→true→false cycle), `NotesField` inline edit, completion banner; visible at status ≥ 60 | `frontend/src/components/ecn/ImplementationSchedulePanel.tsx` | ✅ |
| S7-F6 | Open Orders drawer in panel — right-slide drawer with MO list; shows MO number, item, qty, due date, facility per order; empty state if none | `frontend/src/components/ecn/ImplementationSchedulePanel.tsx` | ✅ |

### Additional Sprint 7 Work

| # | Item | Status |
|---|------|--------|
| S7-X1 | Migration 0019 — `change_parts` + `bom_changes` change scope flags; migration 0020 — `pn_categories` table (seed only); migration 0021 — `add_mpn` scope flag (triggers SC review) | ✅ |
| S7-X2 | `NoCacheMiddleware` — `Cache-Control: no-store` on all `/api/` responses; fixes browser disk-cache stale ECN detail page (Ctrl+Shift+R was required before) | `src/middleware/no_cache.py` | ✅ |
| S7-X3 | Drawing number constraint removed — `_guard_dc_approve` no longer blocks on missing drawing numbers (drawings stored in DMR/SharePoint, not Movex); UI field retained as optional | `src/workflow/machine.py` + `src/services/ecn/workflow.py` | ✅ |
| S7-X4 | `MPDDOC.CreateDrawing` removed from entire pipeline — endpoint does not exist in movex-rest-api; drawings are DMR files | `src/tasks/movex_outbox.py` + `src/adapters/erp/` | ✅ |
| S7-X5 | Outbox dispatch wired end-to-end — `transition()` returns `(ECNDetail, list[str])` of inserted IDs (via `RETURNING id`); `BackgroundTasks` dispatches `process_outbox_entry.apply_async` post-commit | `src/routers/ecn_core.py` + `src/services/ecn/workflow.py` | ✅ |
| S7-X6 | `MovexRestAdapter.open()` called in Celery worker before dispatch; `close()` in `finally` block | `src/tasks/movex_outbox.py` | ✅ |
| S7-X7 | AD group CN alignment — all `ecn-*` group CNs updated to match real `srxglobal.com` directory structure | `src/auth/providers.py` + `docs/srxglobal-active-directory-groups-structure.md` | ✅ |
| S7-X8 | UX fixes (meeting feedback 2026-07-02): ECN list cache clear on transition, item-count gate removed from submit, status label "Implemented" → "Movex Updated", checklist strikethrough removed, `add_mpn` scope checkbox added | `frontend/src/` + `src/` | ✅ |
| S7-X9 | Bug fix — `_auto_assign_roles` skips INSERT when multiple users exist for a role (was hitting NOT NULL constraint with `username=None`; now leaves manual assignment to DC) | `src/services/ecn/workflow.py` | ✅ |

### Fixes

| Bug | Root cause | Fix |
|-----|-----------|-----|
| Stale ECN detail page — Ctrl+Shift+R required | Browser HTTP disk cache on `GET /api/v1/ecn/{id}` — no `Cache-Control` header | `NoCacheMiddleware` sets `Cache-Control: no-store` on all `/api/` responses |
| `MovexRestAdapter not initialised` in Celery | `open()` never called before dispatching MI call | Added `await adapter.open()` + `finally: await adapter.close()` |
| Outbox rows queued but never dispatched | `apply_async` not called after INSERT | `BackgroundTasks` dispatches post-commit; IDs returned via `RETURNING id` |
| `seed_demo.py` failure on staging (DC has 3 users) | `_auto_assign_roles` inserted `username=None` row, hitting NOT NULL | Skip INSERT when multiple candidates exist — DC assigns manually |
| 30 router test failures after `transition()` tuple change | Mocks returned `ECNDetail` directly; router unpacks `(detail, list[str])` | All 4 test files updated; `set_drawing_number` mocks correctly not wrapped |

### Deferred from Sprint 7

| Item | Reason |
|------|--------|
| I — Originator reassignment | OR reassignment is a low-frequency edge case; moved to Iteration 2 (I2-14) |
| C — Role assignment by customer (allocation page scraping) | Await direct DB access to allocation data; scraping approach too fragile |
| CRS620 manufacturer ID auto-resolve | Sprint 8 — alongside mounting type (J) |
| E — Notification template management | Sprint 8 |
| PDS001/G routing text helper (S7-F6) | Dropped — team confirmed free-form notes in checklist row is sufficient |

---

## Sprint 8 — Routing Operations UI + UAT Hardening ⏳ IN PROGRESS

> **Priority order:** Routing ops UI → MPN fields UI → UAT deployment update → IQ/OQ/PQ preparation.
> Power user session week of 2026-07-07 to validate checklist items and open questions
> (see `memory/project_oskar_power_user_questions.md`).

### Pre-conditions

| Pre-condition | Status |
|---|---|
| Sprint 7 complete | ✅ 2026-07-09 |
| Power user session (week of 2026-07-07) — checklist items, MES scope, PDS001/G owner | ⏳ |
| UAT database migration 0019–0022 applied on staging VM | ⏳ |
| LDAPS confirmed with Manal (`AUTH_PROVIDER=ldap` switchover) | ⏳ |

### A — Routing Operations UI ✅ DONE 2026-07-10

| # | Task | File | Status |
|---|------|------|--------|
| S8-A1 | Routing operations section — list of ops with op number, description, work centre, run time, change type badge (ADD/UPDATE/DELETE) | `frontend/src/components/ecn/RoutingOpsPanel.tsx` | ✅ |
| S8-A2 | Add/edit routing op form — inline; wires to `POST/PATCH /api/v1/ecn/{id}/items/{item_id}/routing` | `frontend/src/components/ecn/RoutingOpsPanel.tsx` | ✅ |
| S8-A3 | Delete routing op — confirm-then-`DELETE` | `frontend/src/components/ecn/RoutingOpsPanel.tsx` | ✅ |
| S8-A4 | Movex snapshot diff view | — | ⏸ Deferred, not requested during build |

### B — MPN Extended Fields UI ✅ DONE 2026-07-10

| # | Task | File | Status |
|---|------|------|--------|
| S8-B1 | MPN panel — `lifecycle`, `eol_date`, `lead_time_weeks`, `msl_level`, `packaging_type`, `do_not_buy`, `alt_mpn`; editable in DRAFT/DC_APPROVED | `frontend/src/components/ecn/ECNItemPanel.tsx` | ✅ |
| S8-B2 | `do_not_buy` flag — red badge in item list/detail | `frontend/src/components/ecn/ECNItemPanel.tsx` | ✅ |

### C — UAT Deployment Update

| # | Task | File | Status |
|---|------|------|--------|
| S8-C1 | Rebuild `oskar-app` + `oskar-frontend` images on staging VM with Sprint 7 + 8 changes | VM | ⏳ |
| S8-C2 | Apply migrations 0019–0023 on staging: `docker exec oskar-app-staging alembic upgrade head` | VM | ⏳ |
| S8-C3 | Re-seed demo data — run `seed_demo.py` (now handles DC multi-user correctly) | VM | ⏳ |
| S8-C4 | Validate: DMR URL field, Implementation Schedule, Cancel ECN, Admin CRUD, routing ops, MPN fields, customer role defaults from browser on staging | UAT | ⏳ |
| S8-C5 | Switch `AUTH_PROVIDER=ldap` (Manal dependency — LDAPS service account) | `.env.staging` on VM | ⏳ Manal |
| S8-C6 | Enable `systemd` auto-start unit for staging | VM | ⏳ |

### D — IQ/OQ Preparation

| # | Task | Status |
|---|------|--------|
| S8-D1 | IQ document — infrastructure qualification: VM, Docker, Harbor, PostgreSQL, network controls | ⏳ Manal (infra sections) |
| S8-D2 | OQ document — operational qualification: all workflow transitions, guard conditions, audit chain, email notifications, LDAP auth | ⏳ Mihai |
| S8-D3 | Test trace: map existing `pytest` test IDs to IQ/OQ requirements | ⏳ hsalazar |

### E — Customer Role Defaults (SE/PM) ✅ DONE 2026-07-10

Added mid-sprint, not originally scoped — DC asked how to adjust which users are assigned to
each ECN based on customer. Built as a per-customer SE/PM candidate table, seeded from Stargile
`srx_allocation` (MySQL, 10.40.10.32) via fuzzy name match against live MOVEX customers.

| # | Task | File | Status |
|---|------|------|--------|
| S8-E1 | Migration — `customer_role_defaults` table (cuno, role_id ∈ {SE,PM}, username, is_default, source, soft-delete) | `alembic/versions/0023_customer_role_defaults.py` | ✅ |
| S8-E2 | One-time import script — Stargile `tbl_Allocation`/`tbl_people` fuzzy-matched to MOVEX CUNOs; 315 candidate rows imported across 48 customers, 8 unmatched left for manual review (left as-is per DC decision 2026-07-10) | one-off script, not committed | ✅ |
| S8-E3 | Admin service + endpoints — list/add/set-default/remove candidates (DC-only) | `src/services/admin.py`, `src/routers/admin.py` | ✅ |
| S8-E4 | ECN auto-assign override — customer-scoped SE/PM default wins over facility-wide `system_role_users` when creating an ECN | `src/services/ecn/helpers.py` (`_auto_assign_roles`) | ✅ |
| S8-E5 | Admin UI — "Customer — SE / PM Defaults" section: customer picker, per-role candidates, make-default/remove | `frontend/src/pages/AdminPage.tsx` | ✅ |

---

## Sprint 9 — Digest, Lineage, Mounting Type, Recovery Panel, Reassignment ⏳ PLANNED

> Scope locked 2026-07-10. Ordered quick-wins-first: S9-1 and S9-2 are backend/frontend-only
> against existing data; S9-4 and S9-5 need new backend (endpoint/trigger) design.

| # | Task | Scope | File(s) | Est. |
|---|------|-------|---------|------|
| S9-1 | Facility-scoped ECN digest — add `facility` filter to `_fetch_open_ecns()` and join DC's `system_role_users.facility` in `_fetch_digest_recipients()`; send one digest per facility instead of one global digest to all DCs | Backend only | `src/tasks/ecn_notifications.py` | 2-3 hrs |
| S9-2 | ECN revision lineage UI — new read-only panel/tab showing `ecn_transition_history` (already has `revision_number`, `sha256_prev`, `sha256`) as a chain; needs a small new GET endpoint | Backend (thin) + Frontend | new router endpoint + `frontend/src/components/ecn/` | 1 day |
| S9-3 | Part TH/SMD mounting type — add `mounting_type` column to `ecn_items`, extend DigiKey adapter to return it, add dropdown to item form | Migration + Backend + Frontend | new migration, DigiKey adapter, item form | 1 day |
| S9-4 | DC recovery panel for failed Movex writes — **no listing endpoint exists yet**; add `GET /api/v1/admin/movex-outbox?state=failed` + retry action, then a DC-facing panel | Backend (new) + Frontend | `src/routers/admin.py`, `frontend/src/pages/AdminPage.tsx` | 1.5-2 days |
| S9-5 | Originator reassignment — **no backend exists**; new `reassign_originator` workflow trigger, DC-only endpoint, transition history entry, DC-only modal | Backend (new) + Frontend | `src/workflow/machine.py`, `src/routers/ecn_core.py`, frontend modal | 1.5 days |

**Total estimate:** ~6-7 dev days, single sprint.

---

## Post-Go-Live — OpenBao Secrets Vault

**Pre-conditions:** Production stable ≥30 days, Devian + Manal available.

| # | Task | Status |
|---|------|--------|
| V-1 | ADR-008: OpenBao KV v2 + Vault Agent sidecar | ⏳ |
| V-2 | `oskar-vault` service in `docker-compose.prod.yml` | ⏳ |
| V-3 | Rewrite `setup-server-secrets.sh` for Bao KV | ⏳ |
| V-4 | Bao policies: oskar-app + oskar-worker | ⏳ |
| V-5 | Shamir 3-of-5 unseal key custody (Devian) | ⏳ |
| V-6 | Rotation schedule: JWT 90d, DB PW 180d, LDAP PW 90d | ⏳ |
| V-7 | Update IQ-09 for Bao-based flow | ⏳ |

---

## Open Items (Blocking / Tracked)

| Item | Owner | Blocks | Notes |
|------|-------|--------|-------|
| ~~Project name confirmation~~ | ✅ Resolved | — | Confirmed **OSKAR** 2026-04-21 |
| IQ/OQ/PQ sign-off per section | Karen / Divya / Manal | C-2 | Karen=system, Divya=quality, Manal=infra |
| LDAPS confirmation | Manal | S1-9 live test | Expected 2026-05-08 — confirm with Manal |
| Harbor hostname (final) | Lead Engineer (Manal provides hostname) | `scripts/push-image.sh` | Blocked on Docker install |
| Linux VM provisioned | ✅ Resolved 2026-05-01 | — | 4 CPUs / 16 GB RAM / 100 GB storage. Docker + Harbor install: Lead Engineer. |
| ~~movex-rest-api: MMS025MI.AddAlias~~ | ✅ Resolved 2026-05-01 | — | MMS025MI.json present; generic routing sufficient. No dotnet work needed. |
| movex-rest-api: MPDDOC drawing creation | @developer-dotnet | Sprint 2 design | |
| DBCHK_OpenECN disable at go-live | Infrastructure | G-6 | |
| MPDDOC — MI program or direct DB2? | @developer-dotnet | Sprint 2 design | |

---

## Iteration 2 — Backlog (Post-PoC)

> Items confirmed as out of scope for Iteration 1 and queued for Iteration 2 planning.
> Last updated 2026-07-09: Sprint 7 shipped DMR, Implementation Schedule, Admin CRUD, Cancel ECN.
> I2-7 (routing ops UI) and I2-3 (MPN extended fields) pulled into Sprint 8.
> I2-14 (originator reassignment) remains Iteration 2.

| # | Item | Source | Notes |
|---|------|--------|-------|
| I2-1 | Facility-scoped ECN digest — send per-facility digest emails so JB DCs only see JB ECNs and Melbourne DCs only see Melbourne ECNs. Current `_fetch_open_ecns()` has no facility filter — when both facilities go live, DC recipients will see cross-facility ECNs. Fix: filter digest query by `facility` and dispatch one email per facility group, or add a facility column + filter UI on the digest. | Gap analysis vs `ECN-Open-NextAction-Johor.xls` 2026-06-22 | `src/tasks/ecn_notifications.py:132-156` |
| I2-2 | Customer BOM vs Quoted BOM comparison | Karen/Nick 2026-04-29 meeting (1:10:42) | Iteration 2/3 per Karen |
| I2-3 | MPN extended fields UI — `lifecycle`, `eol_date`, `lead_time_weeks`, `msl_level`, `packaging_type`, `do_not_buy`, `alt_mpn` display in ECN item panel | S2-15 deferred | → Sprint 8 (S8-B) |
| I2-4 | DC recovery panel — Movex write status display (SSE infra + pg_notify ✅) | S2-16 deferred | Display panel UI build |
| I2-5 | ECN version/revision lineage — UI display of SHA-256 audit chain | S2-17 deferred | Audit chain ✅ in DB |
| I2-6 | BOM concurrency detection — delta detection at DC_APPROVED gate | S2-18 deferred | Schema ✅ |
| I2-7 | Routing operations UI | S2-23 deferred | → Sprint 8 (S8-A) |
| I2-8 | CRS620 manufacturer ID auto-resolve — when MPN entered, auto-lookup Manufacturer Code (status 30) via `CRS620MI` and pre-fill; eliminates manual lookup. Depends on movex-rest-api extension. | Sprint 7 analysis | Alongside S8-J (mounting type) |
| I2-9 | E — Notification template management — admin page `/admin/notifications`; Jinja2 templates in `notification_templates` DB table; migrate hardcoded templates from `src/tasks/ecn_notifications.py` | Sprint 8 | `notification_templates` table new |
| I2-10 | J — Part TH/SMD mounting type — `mounting_type (TH\|SMD\|OTHER)` on `ecn_items`; auto-populate from DigiKey via `/parts/autofill` extension | Sprint 8 | Schema change + DigiKey adapter extension |
| I2-11 | K — Quotation Team bulk price/lead-time update — two-phase upload (Engineering template then QT template); QT updates allowed on APPROVED/IMPLEMENTED for protected fields only | Iteration 2 | New upload template |
| I2-12 | G — BOM enhancements — TXT format export, cross-reference ECN deletion vs active BOM, DigiKey attribute lookup, MPN not-found flow → new ECN | Iteration 2/3 | Full analysis in plan file |
| I2-13 | H — Transmittal & SharePoint document management — Oskar-native PDF transmittal generation; email distribution; legacy DMR path redirect | Iteration 2/3 | Requires SharePoint Graph API |
| I2-14 | I — Originator reassignment — `PATCH /api/v1/ecn/{id}/reassign`; DC-only; bypasses OR lock; transition history entry; notification email. Low-frequency edge case (user leaves, handover). | Moved from Sprint 7 | OR role is explicitly blocked from `assign_role`; needs dedicated endpoint |

---

## Future Improvements — Oskar MCP Server (Engineering Intelligence Layer)

> **Decision:** 2026-05-11. Deferred from active sprint planning — BOM (Iteration 2) and Supplier
> Intelligence (Iteration 3) take priority. MCP layer is a post-production enhancement, not a
> core iteration deliverable.
> Full analysis and council report: `ai/council-transcript-20260511-103622.md`

**Architecture decision (locked):** MCP Apps are a complementary intelligence layer on top of the
web UI — not a replacement. Write operations (approvals, ECN creation, status transitions) must
remain web-UI-only for LDAP auth, SHA-256 audit chain, and IQ/OQ/PQ compliance reasons.

**Pre-conditions before picking this up:**
- Production stable ≥ 30 days post go-live
- Iterations 2 (BOM) and 3 (Supplier Intelligence) complete or in steady state
- Scanfil group AI policy confirmed (required for multi-user rollout)
- Lead Engineer Claude Code usage can start earlier without policy gate (internal only)

| # | Task | Notes |
|---|------|-------|
| MCP-1 | MCP server scaffold — `mcp/` folder in monorepo; FastMCP; internal HTTP to Oskar FastAPI; read-only tools only | `mcp/server.py` |
| MCP-2 | `get_ecn_status` tool — ECN header, current status, pending approvers, overdue flag; wraps `GET /api/v1/ecn/{id}` | `mcp/tools/ecn.py` |
| MCP-3 | `list_ecns` tool — filterable by status, assignee, overdue, facility; wraps `GET /api/v1/ecn/` | `mcp/tools/ecn.py` |
| MCP-4 | `get_outbox_status` tool — DC recovery diagnostics; surfaces failed Movex writes with retry count + last error | `mcp/tools/outbox.py` |
| MCP-5 | `lookup_part` tool — alias + stock code check against Movex; wraps Sprint 3 part lookup logic for Claude Code context | `mcp/tools/parts.py` |
| MCP-6 | MCP App — ECN status dashboard; workflow state + approval timeline inline in Claude/VS Code; read-only; `ui://` resource | `mcp/apps/ecn-status/` |
| MCP-7 | MCP App — DC recovery panel; live-updating outbox error display for incident response in Claude Code | `mcp/apps/dc-recovery/` |
| MCP-8 | MCP server Docker service — `mcp-server` container; internal network only; auth via API key to Oskar FastAPI | `docker/docker-compose.prod.yml` |
| MCP-9 | Claude Code MCP config — `.mcp.json` in repo root; enables Lead Engineer to query Oskar from Claude Code | `.mcp.json` |

**Permanently out of scope for MCP layer:**
- Write operations (approvals, ECN creation, status transitions) — web UI only
- External / supplier-facing MCP exposure — security review required separately
