# OSKAR — Sprint Backlog
# Source of truth for all work status.
# oskar-state.md (gitignored) is for next-session notes only — not for tracking status.
# Last synced: 2026-05-05 (Sprint 3 added — 820-min scope gaps H-1/H-2/H-3; MPN extended fields added to Sprint 2)

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
| G-4 | Celery beat task `tasks/ecn_digest.py` — daily HTML email | Sprint 2 | ⏳ |
| G-5 | `POST /api/v1/admin/ecn-digest` — on-demand digest trigger | Sprint 2 | ⏳ |
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

**Sprint 2 pre-gate design decisions (completed before code):**
- ✅ **ADR-009** (2026-05-01): DC single gate — SUBMITTED+DC_REVIEW removed; DC_APPROVED (25) added before Movex write; IMPLEMENTED→CLOSED automatic. `decisions/ADR-009-dc-single-gate-role-customisation.md`
- ✅ **Migration 0006** (2026-05-01): `ecn_items.item_group VARCHAR(3)` + `ecn_items.customer_alias VARCHAR(30)` promoted from JSONB; `ecn_instances` CHECK constraint updated for ADR-009.
- ✅ **Risk R-19** (2026-05-01): BOM-level IP inference via DigiKey/Octopart API query patterns. Scanfil management approval gate required before Stage 3 BOM tools. `ai/memory/09-known-risks-and-pitfalls.md`.

**Sprint 2 scope (all ⏳):**
- **Optimistic locking (ADR-008):** `If-Unmodified-Since` check in `ECNService.update_ecn` + `transition_ecn`; 428 if header absent, 409 if stale; OQ-40 through OQ-45 ✅ 2026-04-24
- **Transactional Outbox:** `src/tasks/celery_app.py` + `src/tasks/movex_outbox.py`; retry 30s → 5min → 30min; DC alert attempt 3; ABANDONED + EM alert attempt 10; `advance_ecn_to_implemented` task; 23 tests ✅ 2026-04-24
- ECN write gate: DB-layer `oskar_worker` REVOKE INSERT on `movex_outbox` + RLS on `ecn_instances` ✅ 2026-04-24 (migration 0005 — HMAC token approach superseded)
- **Workflow machine update (ADR-009):** remove SUBMITTED/DC_REVIEW from ECNStatus; add DC_APPROVED=25; update _TRANSITIONS (remove accept/pass_to_engineering; add dc_approve + auto_close); update all guard conditions and tests ✅ 2026-05-04
- **Per-ECN role customisation (ADR-009):** `POST /api/v1/ecn/{id}/role-assignments`; DC-authority guard; supersede-and-insert pattern; transition history record ✅ 2026-05-04
- Rejection flows: restart vs proceed
- Drawing number workflow: DC confirmation at DC_APPROVED gate (replaces DC_REVIEW gate)
- MPN alias: automatic `MMS025MI.AddAlias` at IMPLEMENTED (uses `ecn_items.customer_alias` + `ecn_items.item_group` as ALWQ)
- **MPN extended fields (820-min scope — Nick, 2026-04-29):** `ecn_mpns` columns for `lifecycle` (active/eol/nrnd), `eol_date`, `lead_time_weeks`, `msl_level` (1–6), `packaging_type`, `do_not_buy`, `alt_mpn`; surfaced in ECN item UI. Schema pre-created in migration 0007 (AI/Agent groundwork plan). Blocker for Iteration 1 sign-off — Nick explicitly requested these fields.
- Parallel approval block: Management Review (EM + PM + QM + SC + FN simultaneous)
- Overdue escalation: 48h → role + manager; 96h → EM added (DC escalation now triggers at DC_APPROVED, not SUBMITTED)
- DC recovery UI: Movex Write Status Panel
- Effectivity date fields on ECNItems
- BOM concurrency detection before Movex write
- Email notifications via `get_email()` + SMTP (10.10.0.155, port 25)
- ECN version/revision lineage on rejection+resubmit
- DBCHK replacement: G-4 Celery digest + G-5 on-demand endpoint

---

## Sprint 3 — Part Number Intelligence (820-Minute Scope Gap)

> **Source:** Engineers meeting 2026-04-29 (Branko, Nick, Karen). Karen confirmed scope:
> *"if this tool is ECN focused and it replaces that 820 minutes with 30 minutes, there's a win."*
> These items were identified as the primary remaining time sinks not covered by Sprint 2.

**Pre-conditions:**
- [ ] Sprint 2 complete
- [x] Nick's methodology documentation received ✅ — `context/ecn-history/Initial_Meeting_Nick_and_Branko_290426/`

| # | Task | Source | Status |
|---|------|--------|--------|
| H-1 | **Part number lookup UI** — alias check against Movex on ECN item entry: full match / partial match / no match result surfaced to engineer. Replaces manual MOVEX search (Step 4 — identified by Hector as single biggest time sink: 30 min on tasks that should take seconds, 1:01:32). | Nick 42:56–44:27 | ⏳ |
| H-2 | **Auto SRX part number generation** — "no match" path: generate new SRX PN using Nick's methodology (`LF` + customer code + commodity code + next available 4-digit sequence from `MITMAS`). Commodity→Proc/Prod Group lookup from Nick's matrix (50 rows). Calls `PDS001MI.AddProduct` via outbox. **Methodology doc received** — `context/ecn-history/Initial_Meeting_Nick_and_Branko_290426/ecn xxxx_item_upload_v13_ecn_item_upload.csv` + `_Proc_Prod_Grp_Matrix.csv`. | Nick 42:56–44:27 | ⏳ | 
| H-3 | **Stock code population** — auto-populate `ecn_items` stock code fields from Movex lookup result on full/partial match. Eliminates manual copy-paste from MOVEX screens. | Hector 1:01:32 | ⏳ |
| H-4 | **Proc & Product Group auto-population** — on new item entry, derive `procurement_group` + `product_group` from MPN commodity type using Nick's matrix (currently 120 min manual lookup). Matrix is fully documented in `_Proc_Prod_Grp_Matrix.csv` (50 commodity rows). Exposed as dropdown + auto-suggest in ECN item UI. | VSM p.6, Nick matrix | ⏳ |
| H-5 | **SRX item description normalisation** — enforce ≤30 char limit (Movex hard constraint); propose standard description from Nick's template names (e.g. "RESISTOR SMD", "IC TH"); pull candidate from DigiKey description and truncate/map. Eliminates 120-min manual sanitisation task. | VSM p.6 + template | ⏳ |

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
| LDAPS confirmation | Manal | S1-9 live test | Not a priority; expected ~2026-05-08 |
| Harbor hostname (final) | Lead Engineer (Manal provides hostname) | `scripts/push-image.sh` | Blocked on Docker install |
| Linux VM provisioned | ✅ Resolved 2026-05-01 | — | 4 CPUs / 16 GB RAM / 100 GB storage. Docker + Harbor install: Lead Engineer. |
| ~~movex-rest-api: MMS025MI.AddAlias~~ | ✅ Resolved 2026-05-01 | — | MMS025MI.json present; generic routing sufficient. No dotnet work needed. |
| movex-rest-api: MPDDOC drawing creation | @developer-dotnet | Sprint 2 design | |
| DBCHK_OpenECN disable at go-live | Infrastructure | G-6 | |
| MPDDOC — MI program or direct DB2? | @developer-dotnet | Sprint 2 design | |
