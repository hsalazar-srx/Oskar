# OSKAR — Risk Register and Known Pitfalls

> **PROVIDER-AGNOSTIC — Non-Negotiable #12**
> No tool-specific syntax. Readable by any LLM tool or none.

**Version:** 1.2
**Date:** 2026-05-01
**Phase:** Phase 1 Track D deliverable
**Sources:** `context/OSKAR_Integrated_Plan_v5.1.md` §12; `ai/memory/05-stargile-ecn-reference.md` §5 (pain points); expert reviews 2026-04-10

---

## 1. Active Risk Register

| # | Risk | Likelihood | Impact | Status | Mitigation |
|---|------|-----------|--------|--------|-----------|
| R-01 | **Stargile MI gap reveals larger scope than expected** | Medium | High | Active | Phase 1 Track A complete — 7 gaps confirmed, all Sprint 2. No surprises beyond known MPDDOC investigation item. |
| R-02 | **Python/FastAPI skill gap** | Medium | High | Active | Skills audit complete. Audit Lead Engineer capability before Sprint 1 code starts. Pair with `@developer-integration` agent. |
| R-03 | **Budget withdrawal between iterations** | Low | Critical | Active | Credibility-first delivery. Iteration 1 is proof event. Frame every decision in QSDC/Dream Factory terms for Christian Kesten. |
| R-04 | **Lead Engineer single point of failure** | Medium | High | Active | `ai/` context layer is the mitigation — any LLM tool can resume a session. `oskar-state.md` + sprint backlog = full resumability. |
| R-05 | **JB IFS migration timing clashes with OSKAR cutover** | Low | Medium | Active | IFSAdapter = stub; interface validated Sprint 3. Karen confirmed IFS out of scope for v1. No action until IFS date announced. |
| R-06 | **Shadow spreadsheets at cutover** | Medium | Medium | Active | Stargile read-only enforcement from go-live day. Pre-cutover training for all engineers. Hard cutover date communicated early. |
| R-07 | **In-flight ECN at cutover** | Medium | Medium | Reduced | 2-week drain period. ECN-level boundary. Any Stargile ECN not closed by go-live is cancelled + re-raised in OSKAR. |
| R-08 | **Context rot — ai/ files become stale** | Medium | Medium | Mitigated | Sprint review gate: `ai/memory/` files reviewed at start of each sprint. 20% staleness rule triggers update before code. |
| R-09 | **LDAPS not confirmed before Sprint 1** | High (if not done) | High | Active | Confirm with Devian before Sprint 1 starts. Record in `ai/evidence/decision-log.md`. DISP Tier 1 finding if missed. |
| R-10 | **Harbor registry not provisioned by Sprint 1** | Medium | Medium | Active | Manal target: 2026-04-17. Sprint 1 can proceed with local Docker images; Harbor needed before first production deploy. |
| R-11 | **IQ/OQ/PQ sign-off owner not named** | — | — | **Resolved 2026-04-14** | Divya confirmed as QM. Chain: Manal (IQ author), Mihai (OQ/PQ author), hsalazar (Approver), Divya (QM), Karen (SVP). |
| R-12 | **Stargile MPDDOC drawing creation is not an MI program** | — | — | **Resolved 2026-05-06** | Confirmed via Stargile source (`ItemService.createDwno()`) + live DB2 query: no MI program exists. Operation is a raw `INSERT … SELECT` from `#TEMPLATE` row in `MVXCDTA.MPDDOC`. `#TEMPLATE` row confirmed present (CONO=100). `CSYTAB CFI1` template also confirmed present. `@developer-dotnet` to implement `POST /api/ecn/drawing` as a parameterised DB2 query — full SQL known, no reverse engineering needed. |

| R-13 | **No secrets rotation policy** | Medium | Medium | Active | PRE-11 eliminates plaintext secrets in git. Rotation policy deferred to Phase 2. **OpenBao (Linux Foundation Vault fork) evaluated 2026-04-15 — confirmed feasible on-prem (single Docker container, zero app code change, integrated Raft storage). Decision: implement in Phase 2 post-go-live as ADR-007, superseding PRE-11. Unseal key custody to be owned by Devian. Accepted risk for v1 — document in IQ sign-off.** |
| R-14 | **Single on-prem Linux VM — no redundancy** | Medium | High | Active | Network/VM outage = total OSKAR outage. Shopfloor engineers lose ECN visibility. See §8 (manual fallback). Define standby VM procedure in Phase 2. |
| R-15 | **WebSocket / real-time push** | — | — | **Resolved — Sprint 2 (2026-05-01)** | SSE endpoint `GET /api/v1/ecn/{id}/stream` implemented via PostgreSQL LISTEN/NOTIFY (migration 0007 trigger `trg_ecn_instances_notify`). No Redis, no WebSocket. Frontend polling (15–30s) retained as automatic fallback on SSE disconnect. Raw `asyncpg.connect()` used directly (SQLAlchemy AsyncSession incompatible with LISTEN). Semaphore cap: 20 concurrent SSE connections. |
| R-16 | **SMS / Teams notification channel not specified** | Low | Low | Deferred | Email-only currently (PRE-9). SMS and Teams are stubs. No action until email is live; escalate at Sprint 3 planning. |
| R-17 | **DBCHK_OpenECN SQL Server job not decommissioned at go-live** | Medium | Medium | Active | Karen's open ECN email job on DBSRV must be disabled on OSKAR go-live day. Add to go-live checklist. Parallel operation during cutover is acceptable; dual-running after go-live creates confusion. Confirm SQL Server Agent access with Infrastructure. |
| R-18 | **DBSRV replicated tables become stale before OSKAR go-live** | Low | Low | Active | `SRX_Apps.dbo.ZECNHEAD` is replicated from Stargile/ComActivity. If replication breaks before OSKAR is live, Karen loses her daily digest. OSKAR has no dependency on this path — risk is operational continuity of the existing job only. |
| R-19 | **BOM-level IP inference via DigiKey / Octopart API query patterns** | Medium | Medium | **Active — Scanfil management approval gate required before Stage 3 BOM tools proceed** | Individual MPN lookups to external supplier APIs (DigiKey, Octopart) are low-risk — MPNs are public. However, when OSKAR systematically queries for all MPNs on a product during ECN processing, the **aggregate query pattern** reveals the BOM structure: which components are used together, at what quantities, for what product families. External API providers log queries for analytics and may retain them. A sophisticated third party observing API traffic (e.g. a supplier with access to DigiKey analytics) could infer Scanfil's assembly BOMs — a competitively sensitive asset. **Mitigation:** (1) No BOM-level external API queries until Karen/management explicitly approves the data-sharing boundary and reviews provider terms of service. (2) Only MPNs should be sent — never internal Movex item numbers (MITMAS.MMITNO) or BOM structure data. (3) Queries should be cached locally (Redis or PostgreSQL) to minimise query frequency and reduce the observable pattern. (4) Add as a Phase 3 design review gate before DigiKey/Octopart integration is activated. |

### Resolved Risks (archived)

| Risk | Resolution |
|------|-----------|
| Stargile source not obtained | Source fully analysed — `ai/memory/05-stargile-ecn-reference.md` (2026-04-10) |
| Data migration scope | Eliminated — data stays in Movex; no live migration |
| 24-week single-timeline failure | Eliminated — modular iterative delivery |
| IQ/OQ/PQ as late event | Eliminated — per-iteration; framework written Phase 1 |
| IFS scope ambiguity | Resolved — Karen confirmed IFS out of scope 2026-04-07 |

---

## 2. Stargile Pain Points — Design Decisions for OSKAR

These are confirmed operational problems with Stargile (source: `ai/memory/05-stargile-ecn-reference.md` §5 and Branko/Nick transcripts). Each has a confirmed OSKAR design decision.

| Stargile pain point | Root cause | OSKAR decision |
|--------------------|-----------|---------------|
| Status 50 timeout — no feedback to user | Synchronous Movex push; no progress indicator | Celery async via Transactional Outbox; real-time status via Redis DB2 stream + DC recovery panel |
| Stuck ECNs — weekly manual report required | `LogicalUnitOfWork` rollback leaves ECN in ambiguous state | Transactional Outbox pattern (ADR-002): ECN state always correct — APPROVED = pending, IMPLEMENTED = confirmed |
| Date-from conflicts found only at push time | No pre-validation before Status 50 | Pre-validate component from-dates against Movex BOM before APPROVED write (BOM concurrency check — §10 of `ai/memory/06-ecn-requirements.md`) |
| XML file RBAC — no audit trail, stale cache | `System.rolemap` XML with in-memory cache | PostgreSQL `system_role_users` + `ecn_role_assignments` — full audit trail, no cache staleness (ADR-003) |
| MPN default unclear to purchasing | `CMZDEFFL` not surfaced in UI | `default_mpn` flag exposed in OSKAR UI; stored in `ecn_mpns.is_default` |
| Retry after Movex failure — admin-only | Limited access to push button | DC role can trigger retry via `POST /api/v1/ecn/{id}/movex-retry`; full error detail visible in DC panel |
| IE9 browser dependency | Hardcoded browser target in Stargile | Not applicable — OSKAR is React/FastAPI |
| Username case sensitivity bug | Stargile bug — lowercase required | LDAP bind normalises username to lowercase before bind |
| Multi-facility item warehouse status not managed | Stargile only updates main item master | Documented v1 limitation — defer to Phase 2 |

---

## 3. Architectural Risk Patterns to Avoid

### 3.1 Workflow state in Celery or Redis

**Risk:** If ECN status is stored in a Celery task payload or Redis key instead of PostgreSQL, a worker crash or Redis restart creates an unknown ECN state.

**Rule:** All ECN state lives in PostgreSQL `ecn_instances`. Celery and Redis are side-effect executors only. A Redis restart or worker crash must never require manual DB correction.

### 3.2 Hardcoded role conditions in Python

**Risk:** Every time an approval condition changes (e.g. PM now required for new product groups), a code change + deployment is required.

**Rule:** All conditional approval routing is data-driven via `ecn_step_conditions` table. Python code reads conditions from DB — never contains `if change_scope == 'routing': require_pm()` style logic.

### 3.3 Direct DB2 calls from OSKAR business logic

**Risk:** Bypasses the ERP adapter pattern; makes IFS migration harder; creates undocumented Movex dependencies.

**Rule:** All ERP access via `ERPAdapter` ABC. No `ibm_db` or direct SQL to Movex from OSKAR business logic. Ever.

### 3.4 Movex-assigned keys as primary keys

**Risk:** When IFS replaces Movex, all foreign key relationships break.

**Rule:** UUID PKs on all OSKAR tables. Movex item numbers / ECN IDs stored as VARCHAR fields — never as primary keys.

### 3.5 Parallel approval via sequential Celery tasks

**Risk:** If parallel approvals are implemented as a chain of Celery tasks, they are sequential in practice.

**Rule:** Each parallel approval is an independent FastAPI endpoint call. Celery is used only for side effects (email, Movex write, Redis publish) — never to gate the approval itself.

---

## 4. Integration Pitfalls — movex-rest-api

| Pitfall | Observed in Stargile | OSKAR guard |
|---------|---------------------|------------|
| MI error buried in 200 OK response | `ZECNMELG` exists because MI calls return 200 with `MSID` error code | Always check `MSID` field in response — non-blank = error regardless of HTTP status |
| Fixed-width fields padded with spaces | DB2 CHAR fields return trailing spaces | `TRIM()` all text fields before comparison or display |
| Numeric date fields (YYYYMMDD) | OHEDCO.OAORDT is numeric — not a SQL DATE | Convert to/from Python `datetime.date` explicitly; never pass Python date object directly |
| CONO missing from WHERE clause | Multi-company tables return all companies | `CONO=100` in every query; enforced at adapter layer — not optional |
| Idempotency on retry | Stargile's stuck-ECN problem from duplicate MI calls | `idempotency_key` on every `movex_outbox` entry; check before re-submitting |

---

## 5. Context Governance Rules

These rules prevent the `ai/` context layer from becoming stale and causing misguided AI suggestions.

| Rule | When it applies |
|------|----------------|
| Any `ai/memory/` file not reviewed in 3+ sprints is flagged for staleness check | Start of each sprint |
| If a decision in `ai/evidence/decision-log.md` has been superseded, update it immediately | When any ADR or PRE decision is changed |
| Never build from a memory file alone — verify against live code | Before writing any implementation |
| If agent suggestion contradicts a memory file, the memory file wins unless the engineer explicitly overrides | Always |

---

## 6. Open Security Items

| Item | Owner | Blocks |
|------|-------|--------|
| LDAPS confirmation with Devian | Devian | Sprint 1 pre-condition |
| `/etc/oskar/secrets.env` provisioned on OSKAR VM (PRE-11) — run `scripts/setup-server-secrets.sh` | Lead Engineer + Manal | Sprint 1 first deploy |
| PostgreSQL separate DB roles (`oskar_app`, `oskar_migration`) — provision before Sprint 1 | Lead Engineer | Sprint 1 |
| `gitleaks` pre-commit hook — install before first commit | Lead Engineer | P0-1 git init |

---

## 8. VM Redundancy and Manual Fallback (R-14)

OSKAR runs on a single on-prem Linux VM. A VM crash, ESXi host failure, or network outage means:
- Engineers cannot submit or view ECNs
- Approvers cannot approve — ECNs stop moving
- DC cannot view Movex write errors

**Accepted for v1:** Single VM is accepted. The following manual fallback applies for outages >30 minutes:

| Step | Action |
|------|--------|
| 1 | Lead Engineer sends email to all engineers: "OSKAR down — use Stargile read-only for ECN status reference" |
| 2 | Any ECN approval decisions made verbally/email during outage must be re-entered in OSKAR within 2h of restoration |
| 3 | DC documents all verbal approvals in a Word register (template: `docs/templates/ecn-verbal-approval-register.docx`) |
| 4 | On restoration: Lead Engineer runs SHA-256 chain integrity check (§7 of this file) before allowing new approvals |

**Phase 2 action:** Evaluate standby VM (cold spare, Manal) or VMware HA for the OSKAR VM. Decision deferred until production baseline is established.

**Poka-Yoke note (deferred):** Shopfloor Poka-Yoke / MES integration is not in scope for OSKAR v1. If production line needs real-time ECN status during outage, this requires a local MES cache — scoped to Phase 3 Supplier Intelligence iteration at earliest. Record as a Phase 2 planning item.

---

## 7. Incident Response Runbook (1-page)

### Scope

OSKAR production on OSKAR VM (Linux, Docker). Covers: service down, data integrity issue, security incident.

### Severity Levels

| Level | Definition | Response time |
|-------|-----------|--------------|
| P1 | All users cannot access OSKAR; or ECN data integrity issue detected | 30min |
| P2 | Feature degraded (e.g. Movex writes failing; notifications not sending) | 2h |
| P3 | Non-critical feature broken; workaround available | Next business day |

### Initial Triage

```
1. Check Docker service health:
   docker ps -a                          (all containers running?)
   docker logs oskar-app --tail 50       (recent errors?)
   docker logs oskar-worker --tail 50

2. Check PostgreSQL:
   docker exec oskar-db psql -U oskar -c "SELECT now();"

3. Check Redis:
   docker exec oskar-redis redis-cli -a $REDIS_PASSWORD ping

4. Check Movex outbox (stuck entries):
   docker exec oskar-db psql -U oskar -c \
     "SELECT ecn_id, state, attempt_count FROM movex_outbox WHERE state IN ('failed','abandoned');"
```

### Rollback (within 30-day window)

```
1. Stop production stack:   docker compose -f docker-compose.prod.yml down
2. Restore DB from backup:  pg_restore -d oskar < /backups/oskar_YYYYMMDD.dump
3. Start previous image:    docker compose -f docker-compose.prod.yml up -d \
                              --scale oskar-app=1 (with previous image tag)
4. Notify Karen and affected engineers
```

### SHA-256 Audit Chain Integrity Check

```sql
-- Run to verify no tampering. Should return 0 rows.
SELECT id, sha256_self
FROM ecn_transition_history t1
WHERE sha256_prev != (
  SELECT sha256_self FROM ecn_transition_history t2
  WHERE t2.ecn_id = t1.ecn_id
    AND t2.created_at < t1.created_at
  ORDER BY t2.created_at DESC LIMIT 1
);
```

### Escalation

| Condition | Notify |
|-----------|-------|
| P1 | Lead Engineer → Karen (within 30min) → Christian Kesten (if >2h unresolved) |
| Security incident (breach suspected) | Lead Engineer → Devian → Karen immediately |
| Movex write data integrity confirmed | Lead Engineer → Bryan → Mihai (Group IT) |
