# OSKAR — Sprint Backlog
# Source of truth for all work status.
# oskar-state.md (gitignored) is for next-session notes only — not for tracking status.
# Last synced: 2026-05-11 (MCP Server moved to Future Improvements — BOM + Supplier Intelligence take priority as Iterations 2 & 3)

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
| G-1 | `facility` column on `ecn_instances` (default `'L'` = Melbourne) | F-1 | ✅ included in 0001_initial_schema.py |
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
- [ ] movex-rest-api: `GET /api/mitpop/search` custom DB2 endpoint deployed (@developer-dotnet) — **S3-1 blocker**

**Key finding (2026-05-11):** No M3 MI program supports reverse alias lookup (POPN→ITNO).
MMS025MI.GetAlias requires CONO+ALWT+ITNO+ALWQ+E0PA+VFDT (ITNO-first). MMS025MI.LstAlias
requires CONO+ITNO (also ITNO-first). MMS001MI not enabled at Scanfil APAC.
Stargile never solved this — `RequestECNDBHelper.java:313` has a TODO comment from 2008.
Solution: custom parameterised DB2 query against `MVXCDTA.MITPOP WHERE MPPOPN=@popn`.
Full endpoint spec in `ai/memory/02-movex-erp-authority.md §7`.

### Sprint 3 Tasks

| # | Task | File | Status |
|---|------|------|--------|
| S3-1 | Part number reverse alias lookup — `GET /api/v1/parts/alias?popn=&cuno=`; queries `MVXCDTA.MITPOP` via custom DB2 endpoint on movex-rest-api; returns `full_match`/`partial_match`/`no_match`. `app.state.erp_adapter` lifespan wired. 34 tests passing. Replaces manual MOVEX search (30 min → seconds). Source: Nick 42:56–44:27. | `src/routers/parts.py` + `src/adapters/erp/movex.py` + `src/adapters/erp/base.py` + `src/main.py` | ✅ 2026-05-11 — awaiting `GET /api/mitpop/search` from @developer-dotnet to go live |
| S3-2 | Auto Scanfil APAC part number generation — `GET /api/v1/parts/suggest-pn?prgp=&itcl=&cuno=[&commodity_override=]`; resolves commodity code from Nick's full matrix (50 rows, 11 multi-code pairs); queries `MVXCDTA.MITMAS` for next sequence via `GET /api/mitmas/next-sequence`. 'LF' prefix is the company identifier (not lead-free marker). `TEM/TEMP`=4 codes (66/76/81/90), `PLA/INJEC`+`PLA/PLAMC`=2 codes (65/67) — corrected from initial spec after cross-check against CSV. 50 tests passing. | `src/routers/parts.py` + `src/services/ecn/commodity_codes.py` + `src/adapters/erp/` | ✅ 2026-05-12 — awaiting `GET /api/mitmas/next-sequence` from @developer-dotnet to go live |
| S3-3 | Stock code population — auto-populate `ecn_items` stock code fields from Movex lookup on full/partial match. Eliminates copy-paste from MOVEX screens. Source: Hector 1:01:32. | `src/services/ecn/items.py` | ⏳ |
| S3-4 | Proc & Product Group auto-population — derive `procurement_group` + `product_group` from MPN commodity type using Nick's matrix (50 rows, `_Proc_Prod_Grp_Matrix.csv`); dropdown + auto-suggest in ECN item UI. Source: VSM p.6, Nick matrix. | `src/services/ecn/items.py` + frontend | ⏳ |
| S3-5 | SRX item description normalisation — enforce ≤30 char (Movex hard limit); propose standard description from Nick's template names; pull from DigiKey description and truncate/map. Source: VSM p.6. | `src/services/ecn/items.py` | ⏳ |

**Explicitly out of scope for Iteration 1 (Karen, 1:10:42):**
- BOM scrubbing as standalone tool (Nick 24:33) — Iteration 3
- Customer BOM vs Quoted BOM comparison (Nick 34:37) — Iteration 2/3
- AI/MCP integration (Nick, Hector 54:40) — gated on Scanfil group AI policy

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
