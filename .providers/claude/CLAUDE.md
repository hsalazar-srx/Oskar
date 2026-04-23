# OSKAR: Claude Code Instructions

**Project:** OSKAR Engineering Intelligence Platform — Python 3.12 / FastAPI + React 18 / TypeScript
**Phase:** Phase 0 → Phase 1 Discovery
**Critical:** Read `../../ai/memory/00-skills-audit.md` BEFORE any implementation

---

## Multi-Agent System (MAS)

### Domain Experts
- **@expert-movex-dotnet** — Movex M3 integration, MI transactions, PDS001MI/PDS002MI, ERP adapter design
- **@expert-manufacturing-engineering** — ECN/BOM/PLM domain, Stargile behaviours, approval workflows, UAT lead
- **@expert-db2-iseries** — DB2/AS400 queries, Movex table analysis, MI endpoint inventory
- **@expert-cybersecurity** — Threat modeling (STRIDE), JWT/LDAP security, LLM/MAS agent security, OWASP
- **@expert-knowledge-manager** — Knowledge Vault sync, decision graph, assumption monitoring

### Technical Specialists
- **@architect-system-design** — ADRs, clean architecture, data model extensibility, Phase 2 review
- **@developer-integration** — ERP Adapter, Supplier Adapter circuit breakers, async patterns, FastAPI
- **@developer-dotnet** — `movex-rest-api` gap endpoint scheduling, PDS extension spec

### Process Agents
- **@validator-quality** — IQ/OQ/PQ protocol, ISO 13485 compliance gate, Sprint 4 sign-off
- **@documenter-technical** — ECN Behavioural Spec, API docs, runbooks
- **@orchestrator-project** — Critical path dependencies, scope change escalation

### Collaboration Pattern

| Phase | Agents |
|-------|--------|
| Phase 1 — MI gap analysis (Track A) | `@expert-movex-dotnet` + `@expert-db2-iseries` |
| Phase 1 — ECN Behavioural Spec (Track B) | `@expert-manufacturing-engineering` + `@documenter-technical` |
| Phase 1 — IQ/OQ/PQ draft | `@validator-quality` |
| Phase 2 — Architecture + ADR | `@architect-system-design` |
| Phase 2 — Threat model | `@expert-cybersecurity` |
| Sprint 1–3 — Implementation | `@developer-integration` |
| Sprint 4 — UAT + compliance gate | `@validator-quality` + `@expert-manufacturing-engineering` |

**Governance:** `C:\Projects\.github\governance\mas-rules.yaml`
**Agent Registry:** `C:\Projects\.github\agents\manifest.json`

---

## Quick Start (Every Session)

### 1. Read These First
```
../../ai/memory/01-manufacturing-context.md    Scanfil APAC context, stakeholders, QSDC
../../ai/memory/02-movex-erp-authority.md     Movex SSoT rules, M3 tables, ERP adapter
../../ai/memory/03-oskar-architecture.md      Technology stack, deployment, non-negotiables
../../ai/memory/05-stargile-ecn-reference.md  Stargile ECN ground truth — read before ECN work
../../ai/memory/00-skills-audit.md            Skills/agents mapped; phase gate status
../../decisions/                       All decisions: PRE-1–10 + ADRs (index: ai/evidence/decision-log.md)
```

### 2. Check Current Work
```
../../ai/tasks/sprint-backlog.md       Current sprint assignments
../../ai/evidence/decision-log.md     Recent decisions
oskar-state.md (project root)          Session state
```

### 3. Skills-First (BEFORE writing code)
```
1. Check C:\Projects\.github\skills\manifest.json
2. Check C:\Projects\.github\agents\manifest.json
3. Confirm in ai/memory/00-skills-audit.md — is this already mapped?
4. Reference in code: # Uses skill: category/name v1.0
```

---

## Review Checklist — Data Mutation (Mandatory for every PATCH/PUT/DELETE endpoint)

Added 2026-04-23 after LL-001. Apply before coding any endpoint that modifies shared state.

1. **Concurrent edit protection** — Is optimistic or pessimistic locking in place? What happens
   if two users submit the same mutation concurrently? (See ADR-008 for the OSKAR pattern.)
2. **Double-submit prevention** — Can the operation be submitted twice in quick succession?
   Is there a DB unique constraint or idempotency key that prevents a duplicate record?
3. **Stale-read / blind-write** — Does the flow read data, present it to a user, and write it
   back without checking whether the data changed in the interim?
4. **TOCTOU** — Is any guard condition checked outside the transaction that performs the write?
   If yes, repeat the check inside the transaction.
5. **Terminal state protection** — Can a terminal-state record (CLOSED, CANCELLED) be mutated
   by a concurrent request that arrived before the status committed? Is the status check
   inside the write transaction?

---

## Critical Rules (Never Violate)

### OSKAR Non-Negotiables
- ❌ **Never write to Movex without human approval and audit trail** — flag `[HUMAN APPROVAL REQUIRED]`
- ❌ **Never call M3 MI APIs directly** — all via `movex-rest-api` HTTP boundary
- ❌ **Never design against IFS semantics** — `IFSAdapter` = stub only in v1
- ❌ **Never skip ISO 13485 audit trail** — SHA-256 chain on every ECN state transition
- ❌ **Redis is eliminated (ADR-007)** — no `oskar-redis` container; broker = PostgreSQL (`celery[sqlalchemy]`); session store = `jti_blocklist`/`refresh_tokens` tables; event push = HTTP polling
- ❌ **Never put tool-specific syntax in `ai/`** — Claude-specific content belongs here only
- ✅ **`/api/v1/` prefix on every FastAPI route** — no exceptions, from Sprint 1 Day 1
- ✅ **Validate payload before every ERP push** — prevent date-from conflict errors at Status 50

### Workspace Standards
- ✅ No hardcoded secrets — `.env` file (gitignored); env injection in Docker
- ✅ No PII in logs or error messages
- ✅ Test coverage ≥ 80% (pytest + pytest-asyncio)
- ✅ Type hints on all Python functions
- ✅ Pydantic models for all API inputs

---

## Critical Constraints Quick Reference

| Area | Rule | Source |
|------|------|--------|
| ERP | Movex is SSoT — OSKAR owns workflow only | Non-Negotiable #1 |
| ERP | No direct MI API calls — all via movex-rest-api | Non-Negotiable #2 |
| Compliance | ISO 13485 audit trail on all ECN state changes | Non-Negotiable #3 |
| Compliance | ERP push requires explicit human confirmation | Non-Negotiable #5 |
| Security | Never hardcode credentials | Workspace Rules |
| Security | Never log PII | Workspace Rules |
| API | `/api/v1/` prefix — every endpoint, Sprint 1 Day 1 | Non-Negotiable #13 |
| Auth | JWT + LDAP bind; 60min access token + 8h refresh cookie; `IdentityProvider` protocol | PRE-3, ADR-006 |
| Redis | Eliminated — PostgreSQL broker + tables replace all Redis jobs | ADR-007 |
| IFS | `IFSAdapter` stub only — Karen confirmed 2026-04-07 | Karen |
| Testing | ≥ 80% coverage (pytest) | Workspace Rules |

---

## Development Workflow

### Decision Tree
```
Is it documented in ai/ or ai/memory/?
  YES → Follow the documented decision
  NO  → Small / reversible?  → Document in ai/evidence/decision-log.md, proceed
        ADR-level?            → Write ADR in decisions/, Lead Engineer approves
        Unclear?              → Escalate — do not guess
```

### Step by Step
1. **Understand** — Read sprint backlog + relevant `ai/` and `ai/memory/` files
2. **Check skills** — Registry first; confirm in `ai/memory/00-skills-audit.md`
3. **Security** — For auth/API/data changes apply relevant security skill explicitly
4. **Implement** — Reference skills in comments; follow conventions
5. **Test** — Write tests alongside code; ≥ 80% coverage
6. **Commit** — Pre-commit checklist; Conventional Commits format

---

## Key Implementation Patterns

### 1. Audit Logging (ISO 13485)
```python
# Uses skill: architecture/audit-logging-framework v1.0
await audit_logger.log(AuditEntry(
    action="ECN_STATUS_CHANGED",
    category="ChangeControl",
    resource_type="ECN",
    resource_id=ecn_id,
    status="SUCCESS",
    user_id=current_user.username,
    previous_hash=last_hash,
    current_hash=sha256(last_hash + payload),
    # No PII in log fields
))
```

### 2. ERP Push — Status 50
```python
# Uses skill: integration/m3-transaction-builder v1.5
# [HUMAN APPROVAL REQUIRED] — this call writes to Movex
result = await erp_adapter.push_bom(ecn_id, bom_lines, approved_by=user.username)
if not result.success:
    await ecn_error_log.record(ecn_id, result.errors)  # ecn_movex_errors table
```

### 3. Supplier Adapter with Circuit Breaker
```python
# Uses skill: architecture/resilience-patterns v1.9
class DigiKeyAdapter(SupplierAdapter):
    def __init__(self):
        self.circuit_breaker = CircuitBreaker(failure_threshold=5, recovery_timeout=60)
```

### 4. Settings (Configuration Hierarchy)
```python
# Uses skill: architecture/configuration-management v1.0
# Hierarchy: environment variables > .env file > defaults — never hardcode
# ADR-007: Redis eliminated — PostgreSQL is broker, session store, and event bus
class Settings(BaseSettings):
    database_url: str        # postgresql+psycopg2://... — used for app, Celery broker, and result backend
    jwt_secret: str
    jwt_access_token_expire_minutes: int = 60   # ADR-006: 60min access token
    jwt_refresh_token_expire_hours: int = 8     # ADR-006: 8h HttpOnly refresh cookie
    movex_api_url: str
    movex_cono: int          # PRE-12: 300=dev/staging, 100=production — never hardcode
    smtp_host: str = "10.10.0.155"
    smtp_port: int = 25
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False)
```

---

## Error Handling

| Error Type | Retry? | Action |
|------------|--------|--------|
| Movex date-from conflict | ❌ No | Structured error to DC retry UI; log to `ecn_movex_errors` |
| Movex timeout (Status 50) | ✅ Celery retry | Log to `ecn_movex_errors`; notify Document Controller |
| Supplier API down | ✅ Circuit breaker | Continue with other suppliers; log miss |
| LDAP bind failure | ❌ No | Return 401; never expose LDAP detail in response |
| Validation error | ❌ No | Return 422 with field-level detail |
| Unhandled exception | ❌ No | Return 500; log with correlation ID; never expose stack trace |

---

## Configuration Quick Reference

| Setting | Value | Source |
|---------|-------|--------|
| API prefix | `/api/v1/` | Non-Negotiable #13 |
| JWT access token TTL | 60 min | ADR-006 |
| JWT refresh cookie TTL | 8 hours (HttpOnly) | ADR-006 |
| Celery broker | PostgreSQL (`celery[sqlalchemy]`) — Redis eliminated | ADR-007 |
| Event push (frontend) | HTTP polling `GET /api/v1/ecn/{id}` every 15–30s | ADR-007 |
| MOVEX_CONO | 300 (dev/staging) · 100 (prod only) | PRE-12 |
| Staging ports | App 8001, DB 5433 | PRE-8 |
| Python | 3.12 | `requirements.txt` |
| PostgreSQL | 16-alpine | `docker-compose.yml` |
| Container registry | Harbor on OSKAR VM | PRE-10 |

---

## Tier 1 Skills (Claude Invocations)

| Invocation | Purpose |
|-----------|---------|
| `/oskar-context-governance` | Sprint review — check `ai/` files for staleness |
| `/oskar-movex-authority` | M3 table lookup, field mapping, SSoT rule check |
| `/oskar-ecn-rules` | ECN business rules, workflow, approval gates |
| `/oskar-commit-template` | Generate Conventional Commits message |
| `/oskar-session-protocol` | Start/end session — orient, check open items, update state |
| `/oskar-iso-compliance` | IQ/OQ/PQ checklist, audit chain review, ISO 13485 gate |

Skill files: `.providers/claude/skills/Tier1/`

---

## Conventional Commits Format

```
<type>(oskar-<scope>): <description>

Types:  feat | fix | docs | refactor | chore | test | adr | security
Scopes: ecn | bom | supplier | auth | api | db | docker | ai | harness | security
```

Examples:
```
feat(oskar-ecn): add ECN approval workflow POST /api/v1/ecn/{id}/approve
chore(oskar-harness): merge .github/OSKAR into ai/ structure
adr(oskar-auth): ADR-001 SM-Portal navigation link no auth coupling
security(oskar-auth): apply STRIDE findings to JWT issuance and LDAP bind
test(oskar-ecn): pytest coverage for Status 50 error recovery path
```

---

## AI Memory Structure

| File | Purpose | Status |
|------|---------|--------|
| `ai/memory/00-skills-audit.md` | Skills/agents mapped; phase gate status | ✅ Done |
| `ai/memory/01-manufacturing-context.md` | Scanfil APAC context, stakeholders, QSDC | ✅ Done |
| `ai/memory/02-movex-erp-authority.md` | Movex SSoT rules, M3 tables, ERP adapter | ✅ Done |
| `ai/memory/03-oskar-architecture.md` | Full system architecture (IS the arch doc) | ✅ Done |
| `ai/memory/05-stargile-ecn-reference.md` | Stargile ground truth: data model, statuses, roles | ✅ Done |
| `decisions/PRE-1` – `PRE-12` | Phase 0 architectural pre-decisions | ✅ Done |
| `decisions/ADR-001` | SM-Portal navigation link, no auth coupling | ✅ Done |
| `ai/evidence/decision-log.md` | Chronological index → decisions/ | ✅ Done |
| `ai/tasks/sprint-backlog.md` | Current sprint assignments | ✅ Done |
| `ai/memory/06-ecn-requirements.md` | ECN Behavioural Spec (OSKAR forward-looking) | ✅ Done |
| `ai/memory/07-compliance-requirements.md` | ISO 13485, IQ/OQ/PQ framework | ✅ Done |
| `ai/memory/08-security-controls.md` | STRIDE output, auth/authz/secrets controls | ✅ Done |
| `ai/memory/09-known-risks-and-pitfalls.md` | Stargile lessons + OSKAR architectural risks | ✅ Done |
| `ai/memory/10-testing-strategy.md` | IQ/OQ/PQ, pytest strategy, benchmarks | ✅ Done |
| `ai/memory/11-observability.md` | structlog JSON, correlation ID, /health endpoints | ✅ Done |
| `ai/memory/12-data-model.md` | PostgreSQL schema — 13 tables, RLS, audit chain | ✅ Done |

---

## Where to Find Everything

| Topic | Location |
|-------|----------|
| This file (quick reference) | `.providers/claude/CLAUDE.md` |
| Provider-agnostic context | `ai/memory/01` through `ai/memory/05` |
| Skills audit | `ai/memory/00-skills-audit.md` |
| AI memory / knowledge base | `ai/memory/` |
| Current sprint | `ai/tasks/sprint-backlog.md` |
| All decisions (PRE-1–10, ADRs) | `decisions/` |
| Decision index (lightweight log) | `ai/evidence/decision-log.md` |
| Workspace standards | `C:\Projects\.github\WORKSPACE_RULES.md` |
| MAS governance | `C:\Projects\.github\governance\mas-rules.yaml` |
| Skills registry | `C:\Projects\.github\skills\manifest.json` |
| Agents registry | `C:\Projects\.github\agents\manifest.json` |

---

## Pre-Commit Checklist

```bash
pytest --cov=src --cov-fail-under=80   # Must pass
```
- [ ] Skills registry checked; no duplicate work
- [ ] Skills referenced in code comments where applicable
- [ ] Type hints on all functions
- [ ] Pydantic models for all API inputs
- [ ] No hardcoded secrets or credentials
- [ ] No PII in logs or error messages
- [ ] Audit logging on all ECN state changes
- [ ] RBAC enforcement on endpoint; `[HUMAN APPROVAL REQUIRED]` flagged if ERP write
- [ ] Tests pass; coverage ≥ 80%
- [ ] `ai/evidence/decision-log.md` updated if a decision was made
- [ ] `ai/memory/00-skills-audit.md` updated if a new skill was used

---

## Pre-Deployment Checklist

- [ ] All tests pass on staging (port 8001)
- [ ] Secrets injected via Docker env — none hardcoded
- [ ] Audit chain integrity validated
- [ ] DB backup verified — Manal confirms `pg_dump` working
- [ ] IQ/OQ/PQ protocol executed and signed — Karen
- [ ] Stargile drain period complete — zero open ECNs
- [ ] Harbor image tagged and pushed via `scripts/push-image.sh`

---

## Escalation

| Situation | Escalate To |
|-----------|-------------|
| Requirements unclear or conflicting | Hector (Lead Engineer) |
| External dependency broken (LDAP, movex-rest-api, Harbor) | Hector → Manal |
| Multiple ADRs conflict | `@architect-system-design` |
| Fundamental data model change | `@architect-system-design` → Hector |
| Security breach suspected | Stop immediately → Hector → Manal |
| Audit chain integrity broken | Stop immediately → Hector |
| Production failure | Stop immediately → Hector → Manal |
