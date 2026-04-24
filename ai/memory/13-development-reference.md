# OSKAR — Development Reference

> **Read on demand.** This file is referenced by `.providers/claude/CLAUDE.md`.
> It contains patterns, examples, and configuration details that would bloat the
> active context window if kept in CLAUDE.md.

---

## Agent Roster

| Agent | Domain |
|-------|--------|
| `@expert-movex-dotnet` | Movex M3 integration, MI transactions, PDS001MI/PDS002MI, ERP adapter |
| `@expert-manufacturing-engineering` | ECN/BOM/PLM domain, Stargile behaviours, approval workflows, UAT lead |
| `@expert-db2-iseries` | DB2/AS400 queries, Movex table analysis, MI endpoint inventory |
| `@expert-cybersecurity` | Threat modeling (STRIDE), JWT/LDAP security, LLM/MAS agent security, OWASP |
| `@expert-knowledge-manager` | Knowledge Vault sync, decision graph, assumption monitoring |
| `@architect-system-design` | ADRs, clean architecture, data model extensibility, Phase 2 review |
| `@developer-integration` | ERP Adapter, circuit breakers, async patterns, FastAPI |
| `@developer-dotnet` | `movex-rest-api` gap endpoint scheduling, PDS extension spec |
| `@validator-quality` | IQ/OQ/PQ protocol, ISO 13485 compliance gate, Sprint 4 sign-off |
| `@documenter-technical` | ECN Behavioural Spec, API docs, runbooks |
| `@orchestrator-project` | Critical path dependencies, scope change escalation |

**Registries (authoritative):**
- `C:\Projects\.github\agents\manifest.json`
- `C:\Projects\.github\skills\manifest.json`

---

## Agent Collaboration by Phase

| Phase | Agents |
|-------|--------|
| Phase 1 — MI gap analysis (Track A) | `@expert-movex-dotnet` + `@expert-db2-iseries` |
| Phase 1 — ECN Behavioural Spec (Track B) | `@expert-manufacturing-engineering` + `@documenter-technical` |
| Phase 1 — IQ/OQ/PQ draft | `@validator-quality` |
| Phase 2 — Architecture + ADR | `@architect-system-design` |
| Phase 2 — Threat model | `@expert-cybersecurity` |
| Sprint 1–3 — Implementation | `@developer-integration` |
| Sprint 4 — UAT + compliance gate | `@validator-quality` + `@expert-manufacturing-engineering` |

---

## Tier 1 Skill Invocations

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

## Relevant Skills for OSKAR

| Skill | Version | Used In |
|-------|---------|---------|
| `manufacturing/ecn-workflow` | 1.0 | ECN state machine |
| `integration/m3-transaction-builder` | 1.5 | ERP adapter |
| `architecture/resilience-patterns` | 1.9 | Circuit breakers, retry, pybreaker |
| `architecture/audit-logging-framework` | 1.0 | ISO 13485 SHA-256 chain |
| `architecture/configuration-management` | 1.0 | Settings, secrets hierarchy |

---

## Implementation Patterns

### 1. Audit Logging (ISO 13485 SHA-256 chain)

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

### 4. Settings Hierarchy

```python
# Uses skill: architecture/configuration-management v1.0
# Hierarchy: environment variables > .env file > defaults — never hardcode
class Settings(BaseSettings):
    database_url: str        # postgresql+psycopg2://... — broker, app DB, Celery result backend
    jwt_secret: str
    jwt_access_token_expire_minutes: int = 60   # ADR-006
    jwt_refresh_token_expire_hours: int = 8     # ADR-006
    movex_api_url: str
    movex_cono: int          # PRE-12: 300=dev/staging, 100=production
    smtp_host: str = "10.10.0.155"
    smtp_port: int = 25
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False)
```

---

## Error Handling Reference

| Error Type | Retry? | Action |
|------------|--------|--------|
| Movex date-from conflict | ❌ No | Structured error to DC retry UI; log to `ecn_movex_errors` |
| Movex timeout (Status 50) | ✅ Celery retry | Log to `ecn_movex_errors`; notify Document Controller |
| Supplier API down | ✅ Circuit breaker | Continue with other suppliers; log miss |
| LDAP bind failure | ❌ No | Return 401; never expose LDAP detail in response |
| Validation error | ❌ No | Return 422 with field-level detail |
| Unhandled exception | ❌ No | Return 500; log with correlation ID; never expose stack trace |

---

## Configuration Reference

| Setting | Value | Source |
|---------|-------|--------|
| API prefix | `/api/v1/` | Non-Negotiable #13 |
| JWT access token TTL | 60 min | ADR-006 |
| JWT refresh cookie TTL | 8 hours (HttpOnly) | ADR-006 |
| Celery broker | PostgreSQL (`celery[sqlalchemy]`) | ADR-007 |
| Event push (frontend) | HTTP polling `GET /api/v1/ecn/{id}` every 15–30s | ADR-007 |
| MOVEX_CONO | 300 (dev/staging) · 100 (prod only) | PRE-12 |
| Staging ports | App 8001, DB 5433 | PRE-8 |
| Python | 3.12 | `requirements.txt` |
| PostgreSQL | 16-alpine | `docker-compose.yml` |
| SMTP | 10.10.0.155 port 25 | Infrastructure |
| Container registry | Harbor on OSKAR VM | PRE-10 |

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
test(oskar-ecn): TDD — write failing tests for status transition guards
adr(oskar-auth): ADR-001 SM-Portal navigation link no auth coupling
security(oskar-auth): apply STRIDE findings to JWT issuance and LDAP bind
```

---

## AI Memory Index

| File | Purpose |
|------|---------|
| `ai/memory/00-skills-audit.md` | Skills/agents mapped; phase gate status |
| `ai/memory/01-manufacturing-context.md` | Scanfil APAC context, stakeholders, QSDC |
| `ai/memory/02-movex-erp-authority.md` | Movex SSoT rules, M3 tables, ERP adapter |
| `ai/memory/03-oskar-architecture.md` | Full system architecture |
| `ai/memory/05-stargile-ecn-reference.md` | Stargile ground truth: data model, statuses, roles |
| `ai/memory/06-ecn-requirements.md` | ECN Behavioural Spec |
| `ai/memory/07-compliance-requirements.md` | ISO 13485, IQ/OQ/PQ framework |
| `ai/memory/08-security-controls.md` | STRIDE output, auth/authz/secrets controls |
| `ai/memory/09-known-risks-and-pitfalls.md` | Stargile lessons + OSKAR architectural risks |
| `ai/memory/10-testing-strategy.md` | IQ/OQ/PQ, pytest strategy, benchmarks |
| `ai/memory/11-observability.md` | structlog JSON, correlation ID, /health endpoints |
| `ai/memory/12-data-model.md` | PostgreSQL schema — 13 tables, RLS, audit chain |
| `ai/memory/13-development-reference.md` | This file — patterns, agents, config reference |
| `ai/tasks/sprint-backlog.md` | Source of truth for all work status |
| `ai/evidence/decision-log.md` | Chronological decision index |

---

## Pre-Deployment Checklist

- [ ] All tests pass on staging (port 8001)
- [ ] Secrets injected via Docker env — none hardcoded
- [ ] Audit chain integrity validated
- [ ] DB backup verified — Manal confirms `pg_dump` working
- [ ] IQ/OQ/PQ protocol executed and signed — Karen
- [ ] Stargile drain period complete — zero open ECNs
- [ ] Harbor image tagged and pushed via `scripts/push-image.sh`
