# OSKAR — Claude Code Instructions

**Project:** OSKAR Engineering Change Management — Python 3.12 / FastAPI + React 18 / PostgreSQL 16
**Workspace rules:** `C:\Projects\.github\WORKSPACE_RULES.md` (read this for organisation-wide standards)

---

## Every Session — Read First

```
ai/tasks/sprint-backlog.md          Source of truth for all work status
ai/evidence/decision-log.md         Recent decisions
ai/memory/03-oskar-architecture.md  Stack, non-negotiables, deployment
ai/memory/05-stargile-ecn-reference.md  ECN ground truth — read before any ECN work
oskar-state.md (project root)       Session state (gitignored)
```

Reference material (read on demand): `ai/memory/13-development-reference.md`

---

## Development Principles — Non-Negotiable

### TDD (Test-Driven Development)
TDD is the design tool, not just a testing practice. Every piece of code is designed by writing the test first.

**The cycle — no exceptions:**
1. Write the failing test — run it — confirm it fails (red)
2. Write the minimum implementation to make it pass (green)
3. Refactor if needed

No implementation file is created before a failing test exists for it. This applies to every function, module, endpoint, migration, and workflow step.

### PostgreSQL-Native First
When designing any constraint, security control, or data rule: reach for PostgreSQL before application code.
Prefer: RLS policies · role permissions · CHECK constraints · UNIQUE indexes · triggers.
Fall back to application code only when the database cannot express the rule.

---

## Critical Rules — Never Violate

### OSKAR Non-Negotiables
- ❌ Never write to Movex without human approval and audit trail — flag `[HUMAN APPROVAL REQUIRED]`
- ❌ Never call M3 MI APIs directly — all calls via `movex-rest-api` HTTP boundary
- ❌ Never design against IFS semantics — `IFSAdapter` = stub only in v1
- ❌ Never skip ISO 13485 audit trail — SHA-256 chain on every ECN state transition
- ❌ Redis is eliminated (ADR-007) — broker = PostgreSQL (`celery[sqlalchemy]`); no Redis container
- ❌ Never put tool-specific syntax in `ai/` — Claude-specific content belongs here only
- ✅ `/api/v1/` prefix on every FastAPI route — no exceptions
- ✅ Validate payload before every ERP push — prevent date-from conflict errors at Status 50

### Workspace Standards
- ✅ No hardcoded secrets — env injection only
- ✅ No PII in logs or error messages
- ✅ Type hints on all Python functions
- ✅ Pydantic models for all API inputs
- ✅ Test coverage ≥ 80% (pytest)

---

## Data Mutation Review — Mandatory Before Every PATCH / PUT / DELETE

Before designing or coding any endpoint that modifies shared state, answer all five:

1. **Concurrent edit** — optimistic or pessimistic locking in place? (OSKAR pattern: ADR-008 `If-Unmodified-Since`)
2. **Double-submit** — DB unique constraint or idempotency key preventing duplicate records?
3. **Stale-read / blind-write** — is data read, presented to user, written back without checking for interim changes?
4. **TOCTOU** — is any guard checked outside the write transaction? If yes, repeat it inside.
5. **Terminal state** — can a CLOSED/CANCELLED record be mutated by a concurrent request that arrived before status committed?

---

## Development Workflow

1. **Understand** — Read sprint backlog + relevant `ai/memory/` files
2. **Check skills** — `C:\Projects\.github\skills\manifest.json` + `ai/memory/00-skills-audit.md`
3. **Test first** — Write the failing test. Run it. Confirm failure. Then implement.
4. **Implement** — Reference skills in comments; follow conventions; make the test pass
5. **Commit** — Pre-commit checklist below; Conventional Commits format

**Decision tree:**
```
Documented in ai/ or ai/memory/?
  YES → Follow it
  NO  → Small/reversible? → Log in ai/evidence/decision-log.md, proceed
        ADR-level?        → Write ADR in decisions/, Lead Engineer approves
        Unclear?          → Escalate — do not guess
```

---

## Pre-Commit Checklist

```bash
pytest --cov=src --cov-fail-under=80   # Must pass
```
- [ ] Tests written before implementation (TDD)
- [ ] Skills registry checked; no duplicate work
- [ ] Type hints on all functions; Pydantic models on all API inputs
- [ ] No hardcoded secrets or credentials; no PII in logs
- [ ] Audit logging on all ECN state changes
- [ ] RBAC enforcement on endpoint; `[HUMAN APPROVAL REQUIRED]` flagged if ERP write
- [ ] `ai/evidence/decision-log.md` updated if a decision was made

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

---

## Critical Constraints Quick Reference

| Area | Rule | Source |
|------|------|--------|
| ERP | Movex is SSoT — OSKAR owns workflow only | Non-Negotiable #1 |
| ERP | No direct MI calls — all via movex-rest-api | Non-Negotiable #2 |
| Compliance | ISO 13485 audit trail on all ECN state changes | Non-Negotiable #3 |
| Compliance | ERP push requires explicit human confirmation | Non-Negotiable #5 |
| Auth | JWT + LDAP; 60min access token + 8h refresh cookie | PRE-3, ADR-006 |
| Redis | Eliminated — PostgreSQL broker + tables replace all Redis | ADR-007 |
| IFS | `IFSAdapter` stub only — Karen confirmed 2026-04-07 | Karen |
| CONO | 300=dev/staging · 100=production only — never hardcode | PRE-12 |
| Design | TDD — test before implementation, always | WORKSPACE_RULES |
| Design | PostgreSQL-native first for constraints and controls | WORKSPACE_RULES |
