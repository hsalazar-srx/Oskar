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

### 3. Supplier Adapter with Circuit Breaker (S3-3)

Two real adapters in Phase 1 — both use pybreaker + tenacity retry:

- `DigiKeyAdapter` (`src/adapters/suppliers/digikey.py`) — OAuth2 client-credentials, REST
- `NexarAdapter` (`src/adapters/suppliers/nexar.py`) — OAuth2, GraphQL (api.nexar.com)

`SupplierChain` (`src/adapters/suppliers/chain.py`) runs them serially (DigiKey → Nexar → stubs)
with a PostgreSQL `supplier_part_cache` table (30-day TTL, migration 0010) in front.
Adapters are optional at startup: wired in lifespan only when `CLIENT_ID` env var is set.

```python
# Uses skill: architecture/resilience-patterns v1.9
class DigiKeyAdapter(SupplierAdapter):
    _circuit_breaker = pybreaker.CircuitBreaker(fail_max=5, reset_timeout=60)
```

### 4. New Adapter / Provider Pattern (ADR-010)

When adding any new external capability (AI provider, IoT broker, supplier, identity provider):

1. Define a `Protocol` (or `ABC`) in `src/adapters/<category>/base.py`
2. Create a `NoOp<Name>Provider` that returns safe defaults, never raises, never calls external services
3. Create a `factory.py` with a `get_<name>()` function reading an env var
4. Wire the `NoOp` as default — platform works without the real provider
5. Tests assert `isinstance(NoOpProvider(), Protocol)` is `True`
6. Real implementations added in later sprints without touching caller code

```python
# src/adapters/<category>/base.py
from typing import Protocol, runtime_checkable

@runtime_checkable
class MyProvider(Protocol):
    def do_thing(self, arg: str) -> MyResult: ...

# src/adapters/<category>/noop.py
class NoOpMyProvider:
    def do_thing(self, arg: str) -> MyResult:
        return MyResult(...)  # safe default, never raises

# src/adapters/<category>/factory.py
def get_my_provider() -> MyProvider:
    cls_name = os.getenv("MY_PROVIDER_CLASS", "NoOpMyProvider")
    if cls_name == "NoOpMyProvider":
        return NoOpMyProvider()
    raise ValueError(f"Unknown MY_PROVIDER_CLASS: {cls_name!r}")
```

See: `src/adapters/ai/` (AIProvider), `src/adapters/erp/` (ERPAdapter), `src/auth/providers.py` (IdentityProvider).

**Prompt injection note (ADR-010):** If the provider processes external text data (BOM descriptions,
MPN fields, customer-supplied strings), call `sanitize_for_prompt(text)` from `src/adapters/ai/base.py`
before building any AI prompt. This is mandatory — not optional.

### 5. JSONB vs Proper Column Rule (ADR-010)

Any JSONB field value that is:
- (a) filtered in a `WHERE` clause,
- (b) displayed in a list or detail view, or
- (c) consumed by the AI layer

→ **must be promoted to a typed column** in the next migration sprint.
File a task in the sprint backlog when the promotion criterion is met.

Sanctioned JSONB fields (remain as JSONB — see ADR-010 for rationale):
- `questionnaire_data` on `ecn_items` — ZQ01–ZQ18, pending Branko validation
- `extra_data` on `ecn_instances` — POC/UAT catch-all
- `agent_provenance` on `ecn_transition_history` — opaque AI audit metadata
- `payload` / `result` on `agent_actions` — vary by action type

### 6. Settings Hierarchy

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
<type>(oskar-<scope>): <short subject — what changed>

<body — bullet points explaining the why, what, and any non-obvious decisions>
- Use present tense imperative ("add", "remove", "fix")
- One bullet per logical change; group related lines
- Name files, endpoints, and classes explicitly
- Capture decisions that would otherwise be lost (why a field was removed,
  why a guard fires synchronously, which ADR drove a choice)

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
```

Types:  feat | fix | docs | refactor | chore | test | adr | security
Scopes: ecn | bom | supplier | auth | api | db | docker | ai | harness | security

**Body is mandatory for feat/fix/refactor.** Optional for docs/chore/test when the subject
is self-explanatory. The body is the primary input for the knowledge base graph — it must
capture decisions and rationale, not just file names.

Examples:
```
feat(oskar-ecn): add dc_approve drawing number guard to ECNWorkflowMachine

- _guard_dc_approve reads _pending_missing_drawings attr set by ECNService before trigger fires
- Synchronous guard reads pre-computed list (transitions library is sync-only)
- ECNService.transition() awaits _missing_drawings() and stores result on machine instance
- Same pre-computation pattern as _guard_all_required_approved (parallel approval block)
- Raises GuardFailed → ECNTransitionError → HTTP 422 (consistent with all other transition errors)

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

feat(oskar-ecn): rejection flows restart/proceed paths POST /ecn/{id}/resubmit

- ECNService.resubmit(): restart resets all ecn_approval_steps + increments revision_number;
  proceed resets only the rejecting role's step, preserving other approvals
- Mirrors Stargile RejectECN.awf two-path design (ai/memory/05-stargile-ecn-reference.md §8)
- ECNTransitionError → 409 on resubmit (conflict semantics — differs from transition's 422)
- resolution field validated to 'restart' | 'proceed' at Pydantic layer

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

test(oskar-ecn): TDD — 14 failing tests for drawing number workflow before implementation

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
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

## Local Dev — Known Gotchas

| Symptom | Cause | Fix |
|---|---|---|
| `comm rc=11001` / DB2 ODBC failure | GlobalProtect VPN not connected | Connect VPN — `150.3.2.x` is office LAN only |
| M3 MI socket connection refused (port 6300) | Same — VPN off | Connect GlobalProtect, restart API |
| Movex API 401 on all requests | `ASPNETCORE_ENVIRONMENT` set to `Production` — user-secrets not loaded | Set `$env:ASPNETCORE_ENVIRONMENT = "Development"` before `dotnet run` |
| Movex API build fails — file locked | Previous instance still running | `Stop-Process -Name Movex.API -Force` |
| Oskar `/api/v1/*` → 502 Bad Gateway | FastAPI backend not running | `uvicorn src.main:app --reload --port 8000 --env-file .env` |
| Oskar DB connection error | PostgreSQL not running | `docker compose up -d postgres` |

**VPN check (run before starting any dev session):**
```powershell
Test-NetConnection -ComputerName 150.3.2.100 -Port 6300 -InformationLevel Quiet
# Must return True — if False, connect GlobalProtect first
```

---

## Pre-Deployment Checklist

- [ ] All tests pass on staging (port 8001)
- [ ] Secrets injected via Docker env — none hardcoded
- [ ] Audit chain integrity validated
- [ ] DB backup verified — Manal confirms `pg_dump` working
- [ ] IQ/OQ/PQ protocol executed and signed — Karen
- [ ] Stargile drain period complete — zero open ECNs
- [ ] Harbor image tagged and pushed via `scripts/push-image.sh`
