# Skills & Agents Audit — OSKAR Platform

**Date:** 2026-04-09
**Phase:** Phase 0
**Auditor:** Lead Engineer — Hector Salazar
**Status:** Phase 0 gates ✅ | Phase 1 gates ⏳ pending

> **PROVIDER-AGNOSTIC — Non-Negotiable #12**
> No tool-specific syntax. Readable by any LLM tool or none.

Mandatory Phase 0 gate. No Sprint 1 code begins without it.
Supersedes the earlier draft at `.github/OSKAR/ai/memory/` — that version
predates the Stargile source analysis and contains stale/fabricated assumptions.

---

## 1. Skills in Scope

**Registry:** `C:\Projects\.github\skills\manifest.json`

### Integration Skills

| Skill ID | Ver | Applied To | How |
|----------|-----|-----------|-----|
| `integration/m3-transaction-builder` | 1.5 | ERP Adapter — PDS001MI / PDS002MI | Construct MI transactions for Status 50 Movex push |
| `integration/m3-response-parser` | 1.3 | ERP Adapter | Parse PDS MI responses; map errors to `ecn_movex_errors` table |
| `integration/movex-db2-data-source` | 1.0 | Phase 1 Track A | Query which PDS endpoints `movex-rest-api` already exposes |
| `integration/rest-api-design` | 1.0 | FastAPI `/api/v1/` layer | Endpoint design conventions, OpenAPI spec |
| `integration/integration-validator` | 1.0 | ERP Adapter, Supplier Adapters | Validate payloads before Status 50 push; prevent known Movex error patterns |
| `integration/oauth-token-manager` | 1.0 | DigiKey Adapter (Iteration 3) | Proactive OAuth2 token refresh — PLMServer's crash-on-expiry failure mode |
| `integration/api-rate-limiter` | 1.0 | Supplier Adapters (Iteration 3) | Per-supplier rate limits (DigiKey 1000/day, Mouser 1000/hr, Element14 100/min) |

### Architecture Skills

| Skill ID | Ver | Applied To | How |
|----------|-----|-----------|-----|
| `architecture/audit-logging-framework` | 1.0 | Audit chain | SHA-256 hash chain on every ECN status transition — ISO 13485 |
| `architecture/resilience-patterns` | 1.9 | Supplier Adapters, ERP Adapter | Circuit breaker per adapter; retry with backoff on Movex push |
| `architecture/clean-architecture` | 1.2 | Entire codebase | Domain / Application / Infrastructure layer separation |
| `architecture/software-architecture` (design) | 1.0 | Platform design | DDD bounded contexts — ECN, BOM, Supplier domains |
| `architecture/rbac-endpoint-control` | 1.0 | FastAPI endpoints | Role-based access — Document Controller, Engineering Manager, Initiator |
| `architecture/configuration-management` | 1.0 | Settings / `.env` | Pydantic Settings — env vars, `.env`, no hardcoded secrets |
| `architecture/strangler-fig-pattern` | 1.0 | Cutover strategy | 2-week drain period; Stargile read-only post go-live |
| `architecture/ui-ux-best-practices` | 1.0 | React frontend | ECN workflow UI; approval screens; error feedback for Status 50 |

### Security Skills

| Skill ID | Ver | Applied To | How |
|----------|-----|-----------|-----|
| `security/auth-patterns` | 1.0 | JWT + LDAP auth layer | JWT issuance on LDAP bind; 8-hour expiry; `IdentityProvider` protocol |
| `security/api-security` | 1.0 | All `/api/v1/` endpoints | OWASP API Top 10; input validation; RBAC enforcement per endpoint |
| `security/secrets-management` | 1.0 | `.env` / deployment | No secrets in code or logs; `.env.example` pattern; env injection |
| `security/threat-modeling` | 1.0 | Phase 2 / pre-Sprint 1 | STRIDE analysis — ECN approval chain, Movex push, MPN data, JWT |
| `security/security-auditor` | 1.0 | Sprint 4 / IQ gate | ISO 27001-aligned security review before go-live |
| `security/devsecops-pipeline` | 1.0 | CI/CD (future) | SAST, dependency scanning, secret detection in build pipeline |
| `security/llm-ai-security` | 1.0 | MAS agent layer | Prompt injection protection; agent isolation; OWASP LLM Top 10 |

### Design Skills

| Skill ID | Ver | Applied To | How |
|----------|-----|-----------|-----|
| `design/architecture-decision-records` | 1.0 | `decisions/` folder | ADR-001 done; data model ADR, auth ADR pending in Phase 2 |
| `design/architect-review` | 1.0 | Phase 2 | Architecture review gate before Sprint 1 code begins |
| `design/brainstorming` | 1.0 | Phase 1 | ECN Behavioural Spec ideation; edge case discovery |
| `design/software-architecture` | 1.0 | Platform design | Clean architecture; domain boundaries; extensibility for Iterations 2–3 |

### Manufacturing Skills

| Skill ID | Ver | Applied To | How |
|----------|-----|-----------|-----|
| `manufacturing/ecn-workflow` | 1.0 | ECN Module | State machine, approval routing — Tier 1 skill wraps this |
| `manufacturing/bom-management` | 1.0 | BOM Module (Iteration 2) | BOM structures, revision control, MMBILL traversal |
| `manufacturing/bom-comparison` | 1.0 | BOM Module (Iteration 2) | BOM diff UI — progress bars, colour coding, word wrap |

### Migration Skills

| Skill ID | Ver | Applied To | How |
|----------|-----|-----------|-----|
| `migration/legacy-analyzer` | 1.0 | Stargile analysis | **Partially applied** — ground truth in `ai/05`. Java rule class bodies not yet fully extracted. |
| `migration/transaction-mapper` | 1.0 | Phase 2 data model | Map ZECNHEAD/ZECNBOMS fields → OSKAR PostgreSQL schema |
| `migration/data-reconciliation` | 1.0 | Cutover validation | Validate historical archive import (ZECNHEAD → OSKAR `status=closed`) — **not** a live parallel run |

### Knowledge Skills

| Skill ID | Ver | Applied To | How |
|----------|-----|-----------|-----|
| `knowledge/decision-graph` | 1.0 | `decisions/` + `ai/` | Track architectural decisions; flag stale assumptions |
| `knowledge/assumption-monitor` | 1.0 | Context governance | 20% staleness rule; sprint review gate |
| `knowledge/compliance-tracker` | 1.0 | ISO 13485 / IQ/OQ/PQ | Track compliance obligations per iteration |
| `knowledge/m3-documentation` | 1.0 | ERP Adapter + MI gap analysis | Movex MI transaction documentation |
| `knowledge/commit-miner` | 1.0 | Knowledge Vault | Post-commit hooks feed vault with OSKAR commit events |

### Data Skills

| Skill ID | Ver | Applied To | How |
|----------|-----|-----------|-----|
| `data/sql-optimization` | 1.0 | PostgreSQL queries | ECN list queries, audit chain queries, BOM queries — index design |

### Cloud / Deployment Skills

| Skill ID | Ver | Applied To | How |
|----------|-----|-----------|-----|
| `cloud/environment-parity-validation` | 1.0 | Dev/Staging/Prod | Validate Docker Compose env parity before each deployment |
| `cloud/dev-prod-parity` | 1.0 | IIS reverse proxy | Ensure dev Kestrel and prod IIS/Docker behave identically |

---

## 2. Skills Not Applicable (with reasons)

| Skill ID | Reason |
|----------|--------|
| `integration/ifs-connect-integration` | IFS out of scope for v1 — Karen confirmed 2026-04-07. IFSAdapter = stub only throughout. |
| `manufacturing/mes-integration` | Iteration 4+ |
| `manufacturing/inventory-operations` | OSKAR is engineering workflow, not inventory management |
| `migration/ifs-readiness` | IFS out of scope v1 |
| `cloud/aspnet-core-iis-configuration` | OSKAR backend is Python/FastAPI, not ASP.NET Core |
| `cloud/iis-deployment-automation` | Docker on Linux VM — IIS is reverse proxy only, not app host |
| `security/penetration-testing` | Not in scope for v1 — DISP compliance is a future initiative |
| `data/reporting-integration` | Phase 4+ (Power BI consumer — event source is PostgreSQL LISTEN/NOTIFY or polling, not Redis Streams) |

---

## 3. Skills Gaps — Propose After Sprint Usage

Propose these as new MAS skills **after** they are built and validated in sprints.
Premature specification before working code produces over-engineered specs.

| Gap | Proposed Skill ID | Propose When |
|-----|------------------|-------------|
| Multi-supplier async fan-out, per-supplier circuit breakers | `integration/supplier-api-aggregator` | After Sprint 3 |
| ~~Redis Streams event publishing~~ | ~~`integration/redis-streams-events`~~ | **Cancelled — ADR-007**. Replaced by HTTP polling + Celery SMTP tasks. Future live-push: `LISTEN/NOTIFY` + SSE (no new skill needed until Phase 4). |
| SHA-256 hash chain audit records | `compliance/hash-chain-audit` | After Sprint 1 |

Note: `integration/oauth-token-manager` already exists in the registry (v1.0) — no gap.

---

## 4. Agents Mapped to OSKAR

**Registry:** `C:\Projects\.github\agents\manifest.json`

### Active Agent Roles

| Agent | Tier | OSKAR Role | Phase |
|-------|------|-----------|-------|
| `@expert-movex-dotnet` | Domain Expert | MI gap analysis — which PDS001MI/PDS002MI transactions `movex-rest-api` exposes; ERP Adapter design | Phase 1 Track A |
| `@expert-manufacturing-engineering` | Domain Expert | Cross-check `ai/05` Stargile analysis; ECN Behavioural Spec review; UAT lead (with Branko/Nick) | Phase 1 + Sprint 4 |
| `@expert-db2-iseries` | Domain Expert | DB2/AS400 queries for MI gap analysis; Movex table analysis during Phase 1 Track A | Phase 1 |
| `@expert-cybersecurity` | Domain Expert | Threat modeling (Phase 2); JWT/LDAP security review; LLM agent security for MAS layer | Phase 2 + Sprint 1 |
| `@architect-system-design` | Technical Specialist | ADR authoring; data model extensibility review; Phase 2 architecture gate | Phase 2 |
| `@developer-dotnet` | Technical Specialist | `movex-rest-api` gap endpoint scheduling; coordinate PDS001MI/PDS002MI extension spec | Phase 2 |
| `@developer-integration` | Technical Specialist | ERP Adapter implementation; Supplier Adapter circuit breaker wiring | Sprint 1–3 |
| `@validator-quality` | Process Agent | IQ/OQ/PQ protocol draft review; Sprint 4 execution gate; ISO 13485 compliance checks | Phase 1 draft + Sprint 4 |
| `@documenter-technical` | Process Agent | ECN Behavioural Spec (Phase 1 primary output); API docs; runbooks | Phase 1 |
| `@expert-knowledge-manager` | Domain Expert | Knowledge Vault sync; commit hook events; decision graph maintenance | Ongoing |
| `@orchestrator-project` | Orchestrator | Critical path dependencies; agent coordination; scope change escalation | Ongoing |

### Agent Collaboration Pattern by Phase

```
Phase 1 Discovery (Weeks 1–4):
  @expert-movex-dotnet + @expert-db2-iseries  → MI gap analysis (Track A)
  @expert-manufacturing-engineering            → ECN Behavioural Spec (cross-check ai/05)
  @documenter-technical                        → Produce Phase 1 spec document
  @validator-quality                           → Draft IQ/OQ/PQ protocol skeleton

Phase 2 Architecture (Weeks 5–6):
  @architect-system-design                     → ADR + data model extensibility review
  @expert-cybersecurity                        → STRIDE threat model
  @developer-dotnet                            → movex-rest-api gap endpoint scheduling

Sprint 1 (Weeks 7–9):
  @developer-integration                       → FastAPI platform foundation, auth, data model
  @expert-cybersecurity                        → JWT/LDAP security review; LLM guardrails

Sprint 2–3 (Weeks 10–15):
  @developer-integration                       → ECN state machine, Movex push, supplier adapters
  @expert-movex-dotnet                         → ERP push validation, error handling patterns

Sprint 4 / Cutover (Weeks 16–20):
  @validator-quality                           → IQ/OQ/PQ execution sign-off
  @expert-manufacturing-engineering            → UAT with Branko and Nick (validate POC)
  @expert-knowledge-manager                    → Final vault sync; MEMORY.md refresh
```

### Agents Not Used in v1

| Agent | Reason |
|-------|--------|
| `@expert-ifs-integration` | IFS out of scope for v1 |
| `@expert-mes` | Iteration 4+ |
| `@expert-reporting-analytics` | Phase 4 (Power BI / Redis Streams) |
| `@validator-iis-deploy` | OSKAR is Docker/Linux — IIS is reverse proxy only |

---

## 5. Architecture Patterns Confirmed

| Pattern | Where Applied | Skill Reference |
|---------|--------------|-----------------|
| Clean Architecture | Domain / Application / Infrastructure layers | `clean-architecture` v1.2 |
| Strangler Fig | 2-week drain → hard cutover; Stargile read-only post go-live | `strangler-fig-pattern` |
| Anti-Corruption Layer | Stargile schema (ZECNHEAD etc.) isolated behind OSKAR service layer | `strangler-fig-pattern` |
| Adapter | ERPAdapter ABC — MovexRestAdapter (real) + IFSAdapter (stub) | `m3-transaction-builder` |
| Circuit Breaker | Per-supplier in SupplierAdapter; also on ERP Adapter | `resilience-patterns` |
| Event Sourcing | ECN state → SHA-256 audit chain (PostgreSQL `ecn_transition_history`) + Celery email tasks (ADR-007: Redis eliminated) | `audit-logging-framework` |
| Repository | Data access layer for ECN, BOM, MPN entities | `bom-management` |
| RBAC | Role enforcement per endpoint — Document Controller, Engineering Manager, Initiator | `rbac-endpoint-control` |
| STRIDE Threat Model | JWT forgery, Movex push injection, MPN data tampering, LDAP injection | `threat-modeling` |

---

## 6. Security Design Decisions

These were missing from the earlier audit entirely.

| Concern | Decision | Skill |
|---------|----------|-------|
| Authentication | JWT + LDAP bind (`ldap3`); 60min access token + 8h HttpOnly refresh cookie; `IdentityProvider` protocol | `auth-patterns` |
| Authorisation | RBAC per endpoint; roles derived from AD groups via LDAP | `rbac-endpoint-control` |
| Secrets | Never in code or logs; `.env` file (gitignored); env injection in Docker | `secrets-management` |
| API security | OWASP API Top 10 — input validation, rate limiting, no verbose errors | `api-security` |
| Audit trail | Immutable SHA-256 chain — INSERT+SELECT only for app user; no UPDATE/DELETE | `audit-logging-framework` |
| LLM/MAS security | Prompt injection protection; agent isolation; human approval gate on Movex push | `llm-ai-security` |
| Threat model | STRIDE analysis required before Sprint 1 — `@expert-cybersecurity` owns | `threat-modeling` |

---

## 7. Stargile Analysis Status (`migration/legacy-analyzer`)

| Area | Status | Location |
|------|--------|----------|
| 9 ECN table DDL (ZECNHEAD + children) | ✅ Complete | `ai/memory/05-stargile-ecn-reference.md` |
| 13 workflow statuses (`IECNStatus.java`) | ✅ Complete | `ai/memory/05` + `.providers/claude/skills/Tier1/oskar-ecn-rules.md` |
| 16 approval roles (`IECNRoles.java`) | ✅ Complete | `ai/memory/05` + `.providers/claude/skills/Tier1/oskar-ecn-rules.md` |
| Workflow routing graph (XPDL) | ✅ Skeleton | `ai/memory/05` |
| Movex API calls (PDS001MI, PDS002MI) | ✅ Confirmed | `ai/memory/05` |
| Java rule class method bodies | ⏳ Partial | Conditional approver logic not fully extracted |
| ZQ01–ZQ18 questionnaire field meanings | ⏳ Deferred | Confirm with Branko post-POC |
| Full PDS001MI/PDS002MI parameter specs | ⏳ Pending | Needed for Sprint 3 ERP push — Phase 1 Track A |
| AUComponents / JobMonitor projects | ⏳ Not read | May contain relevant integration code |

---

## 8. Phase Gate Checklist

### Phase 0 ✅
- [x] `ai/` provider-agnostic structure seeded (01–05 + memory/)
- [x] `.providers/claude/` — CLAUDE.md + 6 Tier 1 skills
- [x] Docker Compose (prod, staging, dev) — Redis eliminated (ADR-007), PostgreSQL broker
- [x] `src/` scaffold — auth, routers, adapters/erp, adapters/suppliers
- [x] `.gitignore`, `.env.example`, `Dockerfile`, `requirements.txt`
- [x] ADR-001 (SM-Portal navigation link, no auth coupling)
- [x] Stargile source analysis (`ai/05`)
- [x] Skills audit (this file)
- [x] `src/main.py` — Dockerfile entrypoint ✅
- [ ] Git init + first commit (blocked — project name TBD)
- [ ] Knowledge Vault post-commit hook

### Phase 1 ⏳ (Weeks 1–4)
- [ ] ECN Behavioural Spec — primary deliverable
- [ ] MI gap analysis — `movex-rest-api` PDS endpoint inventory
- [ ] IQ/OQ/PQ protocol draft
- [ ] IQ/OQ/PQ sign-off owner confirmed with Karen (open)
- [ ] STRIDE threat model (`@expert-cybersecurity`)
- [ ] Dream Factory alignment memo to Christian Kesten
