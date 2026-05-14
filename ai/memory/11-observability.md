# OSKAR — Observability Strategy

> **PROVIDER-AGNOSTIC — Non-Negotiable #12**
> No tool-specific syntax. Readable by any LLM tool or none.

**Version:** 1.0
**Date:** 2026-04-13
**Phase:** Phase 0 deliverable — must be in place before Sprint 1 code is written
**Stack:** Python 3.12, FastAPI, Celery, PostgreSQL 16, Redis 7, Docker, Linux VM

---

## 1. Why Observability is Phase 0, Not Phase 3

Observability added after the fact means:
- Debugging Sprint 1 failures without logs → blind debugging, multiplied effort
- Celery worker failures silent until an ECN is discovered stuck at APPROVED
- LDAP bind failures invisible to on-call
- No correlation ID = cannot trace a request from frontend → FastAPI → Celery → Movex

The cost of retrofitting structured logging across 12 modules is higher than building it once on Day 1. This document defines the observability contract before the first line of application code is written.

---

## 2. Structured Logging

**Library:** `structlog` (Python) — JSON output, same philosophy as Serilog in SM-Portal.

**Required fields on every log record:**

| Field | Type | Source |
|-------|------|--------|
| `timestamp` | ISO 8601 | structlog processor |
| `level` | string | INFO / WARNING / ERROR / CRITICAL |
| `correlation_id` | UUID | Generated at request boundary; propagated to Celery tasks |
| `actor` | string | Authenticated username (from JWT); `"system"` for Celery |
| `service` | string | `"oskar-app"` or `"oskar-worker"` |
| `module` | string | Python module name (`__name__`) |
| `event` | string | Human-readable description of what happened |

**Additional fields by context:**

| Context | Extra fields |
|---------|-------------|
| ECN transitions | `ecn_id`, `from_status`, `to_status` |
| Movex MI calls | `ecn_id`, `mi_program`, `mi_transaction`, `attempt_count` |
| Auth events | `username`, `ad_group`, `outcome` |
| Celery tasks | `task_id`, `task_name`, `ecn_id`, `outbox_id` |

**What must NEVER appear in logs:**
- `OSKAR_DB_PASSWORD` — even partially
- `JWT_SECRET_KEY`
- `REDIS_PASSWORD`
- `LDAP_BIND_PW`
- JWT token values (only claims are permitted: `sub`, `groups`)
- Full LDAP DN of service account

**Enforcement:** `gitleaks` pre-commit hook catches accidental `print()` of secrets. Structured logging library channels all output — no raw `print()` in application code.

---

## 3. Log Levels — Rules

| Level | Use when |
|-------|---------|
| `DEBUG` | Detailed diagnostic info — only enabled in development. Never enabled in production. |
| `INFO` | Normal operations: request received, ECN submitted, Celery task started, transition completed |
| `WARNING` | Recoverable issue: Movex retry attempt, LDAP `mail` attribute missing, cache miss |
| `ERROR` | Operation failed but service continues: MI call failed all retries, outbox entry abandoned |
| `CRITICAL` | Service cannot continue: database unreachable on startup, Redis unreachable, cert error on LDAPS |

**Rule:** `ERROR` and `CRITICAL` always include the exception type and message. No silent except clauses.

---

## 4. Correlation ID Propagation

A correlation ID must be generated at every external entry point and propagated through the entire call chain:

```
FastAPI request in  →  generate UUID4 correlation_id
                    →  store in contextvars.ContextVar (request-scoped)
                    →  include in all log records for that request
                    →  pass as Celery task kwarg: task.apply_async(kwargs={"correlation_id": ...})

Celery task starts  →  read correlation_id from kwargs
                    →  store in contextvars.ContextVar (task-scoped)
                    →  include in all log records for that task execution

HTTP response       →  include as response header: X-Correlation-ID
```

**Inbound correlation ID:** If `X-Correlation-ID` header is present on the incoming request (e.g. from IIS reverse proxy), use it instead of generating a new one. This allows end-to-end trace across IIS logs → FastAPI logs → Celery logs.

---

## 5. Log Output and Retention

**Development:** stdout (Docker logs), human-readable via `structlog.dev.ConsoleRenderer`

**Production:** stdout (Docker logs) → captured by Docker logging driver → file on OSKAR VM

```yaml
# docker-compose.prod.yml — logging config for all services
logging:
  driver: json-file
  options:
    max-size: "50m"
    max-file: "10"
```

**Retention:** 10 × 50 MB = 500 MB maximum per service. Docker rotates automatically.

**Log location on VM:** `/var/lib/docker/containers/{container_id}/` (default Docker path). Lead Engineer can tail with:
```bash
docker logs oskar-app --tail 100 -f
docker logs oskar-worker --tail 100 -f
```

**No external log aggregator in v1.** Log aggregation (e.g. Loki + Grafana, or ELK) is deferred to Phase 2. The 500 MB cap covers >3 months of normal operation.

---

## 6. Health Endpoints

Already implemented: `GET /api/v1/health` returns `200 OK`.

**Extend to liveness + readiness (Sprint 1):**

| Endpoint | Checks | Used by |
|----------|--------|---------|
| `GET /api/v1/health/live` | Service process is running | Docker `HEALTHCHECK` |
| `GET /api/v1/health/ready` | PostgreSQL reachable + LDAP reachable | IIS reverse proxy (before routing traffic) |

**Ready endpoint response (JSON):**
```json
{
  "status": "ready",
  "checks": {
    "postgres": "ok",
    "ldap": "ok"
  }
}
```

If any check fails: HTTP `503 Service Unavailable` with `status: "degraded"` and the failing check identified.

**Celery health:** Celery does not expose HTTP. Monitor via:
```bash
docker exec oskar-worker celery -A oskar.worker inspect ping
```
This is run by the incident runbook (`ai/memory/09` §7), not automated in v1.

---

## 7. Key Metrics (Manual — No Prometheus in v1)

No metrics server in v1. The following are observable from logs using `docker logs` + grep:

| Metric | How to observe |
|--------|---------------|
| Movex outbox failures | `grep '"level":"ERROR".*mi_program'` |
| ECN stuck at APPROVED >1h | Query: `SELECT ecn_id FROM ecn_instances WHERE status='APPROVED' AND updated_at < NOW() - INTERVAL '1 hour'` |
| Auth failure rate | `grep '"event":"auth_failed"'` — spikes indicate brute force or LDAP issue |
| Celery task latency | `grep '"task_name":"process_outbox_entry"'` — compare started_at vs completed_at |

**Phase 2 action:** Add Prometheus metrics endpoint (`/api/v1/metrics`) and Grafana dashboard when VM resources allow. This follows the same upgrade path as SM-Portal's observability roadmap.

---

## 8. Tracing (Deferred to Phase 2)

Distributed tracing (OpenTelemetry → Jaeger or Tempo) is out of scope for v1. The correlation ID pattern in §4 provides sufficient trace capability for v1 incident response.

When implemented: use `opentelemetry-sdk` + `opentelemetry-instrumentation-fastapi`. No code changes required to existing log records — correlation ID becomes the trace root.

---

## 9. Observability Checklist — Phase 0 / Sprint 1

These are **non-negotiable before Sprint 1 code is merged:**

- [ ] `structlog` added to `requirements.txt`
- [ ] `logging_config.py` created: configure structlog with JSON renderer for production, ConsoleRenderer for development
- [ ] `correlation_id` middleware added to FastAPI (`src/middleware/correlation.py`) — generates UUID4, stores in ContextVar, adds to response header
- [ ] All log calls use `structlog.get_logger()` — no `logging.getLogger()`, no `print()`
- [ ] `GET /api/v1/health/live` and `/ready` implemented (extend existing health endpoint)
- [ ] `correlation_id` passed as kwarg to all `apply_async()` calls
- [ ] At least one integration test verifies `X-Correlation-ID` is present in response headers

---

## 10. Additional Gaps Noted (Out of Scope v1)

| Gap | Recommendation | Sprint |
|-----|---------------|--------|
| WebSocket / SSE real-time push to frontend | Redis DB2 stream is wired server-side; frontend needs SSE consumer. Define SSE endpoint spec in Sprint 2 before UI build starts. | Sprint 2 |
| SMS notifications for critical ECN events | PRE-9 defers this. Add as Teams webhook stub at PRE-9 revision. No action until email notifications are live. | Sprint 3 |
| Poka-Yoke / MES integration | ECN approval status needed at shopfloor terminals during network outage. Out of scope v1. See `ai/memory/09` §8. | Phase 3 |
| Prometheus metrics endpoint | `GET /api/v1/metrics` + Grafana dashboard. Deferred until baseline VM resource usage is known. | Phase 2 |
