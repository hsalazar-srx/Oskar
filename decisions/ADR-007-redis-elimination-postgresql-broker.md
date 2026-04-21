# ADR-007 — Redis Elimination: PostgreSQL as Celery Broker and Session Store

**Status:** Accepted
**Date:** 2026-04-17
**Owner:** Lead Engineer
**Supersedes:** PRE-2 (Redis logical separation — three-DB design)
**Type:** Architectural — infrastructure simplification

---

## Context

PRE-2 established a three-DB Redis architecture:
- DB0 — Celery broker (task queue)
- DB1 — Application cache (JTI blocklist, refresh token hashes)
- DB2 — Event stream (Redis Streams, `appendonly yes`)

This was designed before the scale and usage patterns of OSKAR were fully understood. With those constraints now clear, the three Redis jobs were reassessed:

**Scale facts:**
- ~50 users, one manufacturing plant (Melbourne)
- Human-paced workflow — ECN approval steps take hours to days, not seconds
- Movex write volume: 5–20 MI calls per day at peak
- Supplier Intelligence: 6+ supplier API fan-outs, but no real-time response requirement
- Infrastructure: 2 vCPU / 4 GB VM — minimising container count reduces resource pressure

---

## Assessment of Each Redis Job

### DB0 — Celery broker

Celery is retained for Supplier Intelligence fan-out (6+ APIs in parallel, per-adapter circuit breakers, result aggregation, retry). This is a genuine async task queue use case.

However, the broker does not need to be Redis. The `celery[sqlalchemy]` PostgreSQL transport (`kombu_message` table as queue, `celery_taskmeta` for results) handles the actual task volume — tens to low hundreds of tasks per day — without measurable overhead. PostgreSQL is already present; adding Redis solely as a broker is net complexity with no benefit at this scale.

### DB1 — JTI blocklist + refresh token hashes

At 50 users, the JTI blocklist holds at most 50–100 rows (one per active session plus recently logged-out tokens within their TTL window). A PostgreSQL table with a UUID primary key lookup is sub-millisecond — indistinguishable from Redis at this scale.

Refresh token hashes: same argument. A `refresh_tokens` table replaces the Redis key-value store with no practical performance difference.

### DB2 — Event stream

OSKAR is a human-paced workflow system. ECN status changes happen when a human takes an action — seconds to hours apart. The frontend does not need sub-second push. A 15–30 second `GET /api/v1/ecn/{id}` polling interval is invisible to users when approval steps take hours.

Redis Streams (`oskar:ecn:events`, consumer groups, 7-day retention) was designed for a real-time push model that is not required at this scale or workflow cadence.

PostgreSQL `LISTEN/NOTIFY` is documented as a future option if a genuine live-push requirement ever emerges, with no infrastructure change required.

---

## Decision

**Redis is removed from the OSKAR stack.**

| Former Redis job | Replacement |
|-----------------|-------------|
| DB0 — Celery broker | `celery[sqlalchemy]` PostgreSQL transport |
| DB1 — JTI blocklist | `jti_blocklist` table — UUID PK, `expires_at TIMESTAMPTZ` |
| DB1 — Refresh tokens | `refresh_tokens` table — `token_hash` PK, `username`, `expires_at`, `revoked_at` |
| DB2 — Event stream | HTTP polling on `GET /api/v1/ecn/{id}` (15–30s interval) |

**Celery is retained.** The task queue is necessary for Supplier Intelligence fan-out and the Transactional Outbox Movex write pattern. Only the broker backend changes.

**`LISTEN/NOTIFY` is documented but deferred.** If a future requirement demands live push (e.g., a real-time operations dashboard), PostgreSQL `LISTEN/NOTIFY` + FastAPI SSE is the upgrade path. It requires no new infrastructure — a DB trigger fires `pg_notify()` and an SSE endpoint listens. No Redis needed even then.

---

## Implementation

### New Alembic migration — `0004_auth_tables.py`

```sql
CREATE TABLE jti_blocklist (
    jti        UUID        PRIMARY KEY,
    expires_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX idx_jti_expires ON jti_blocklist(expires_at);

CREATE TABLE refresh_tokens (
    token_hash VARCHAR(64)  PRIMARY KEY,  -- SHA-256 hex of the raw refresh token
    username   VARCHAR(50)  NOT NULL,
    expires_at TIMESTAMPTZ  NOT NULL,
    revoked_at TIMESTAMPTZ,               -- NULL = active; set on logout or family revocation
    created_at TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX idx_rt_username ON refresh_tokens(username) WHERE revoked_at IS NULL;
CREATE INDEX idx_rt_expires  ON refresh_tokens(expires_at);
```

Cleanup: a FastAPI lifespan startup task deletes `jti_blocklist WHERE expires_at < now()` and `refresh_tokens WHERE expires_at < now()`. Runs at startup and every hour. No `pg_cron` dependency needed at this scale.

### Celery broker configuration

```python
# celery_app.py
CELERY_BROKER_URL    = os.environ["DATABASE_URL"]  # postgresql+psycopg2://...
CELERY_RESULT_BACKEND = os.environ["DATABASE_URL"]
CELERY_BROKER_TRANSPORT_OPTIONS = {
    "visibility_timeout": 3600,
}
```

Kombu creates `kombu_message` and `kombu_queue` tables on first use. Celery creates `celery_taskmeta` for results. These are managed by Celery/Kombu — not Alembic.

### requirements.txt changes

**Remove:** `redis==5.2.1`

**Add:** `celery[sqlalchemy]==5.4.0` (replaces `celery==5.4.0`), `psycopg2-binary==2.9.9` (Kombu PostgreSQL transport requires sync psycopg2, not asyncpg)

### Docker Compose changes

Remove the `oskar-redis` service. The production stack becomes:

```
oskar-db       — PostgreSQL 16
oskar-app      — FastAPI
oskar-worker   — Celery (PostgreSQL-brokered)
oskar-frontend — React/TS
```

### Event stream migration

The Redis Streams schema defined in F-6 (`ai/memory/03-oskar-architecture.md §15`) is superseded. The `schema_version` envelope concept is retained as a design pattern — applied to future `LISTEN/NOTIFY` payloads if that path is taken.

The `oskar-frontend` and `oskar-notifier` consumer groups are replaced by:
- Frontend: polling `GET /api/v1/ecn/{id}`
- Notifier: Celery task triggered from the FastAPI service layer after each status transition (direct `aiosmtplib` call, no stream intermediary)

---

## Consequences

**Positive:**
- One fewer container in Docker Compose
- No Redis AUTH configuration, no persistence mode decisions, no eviction policy
- No Redis circuit breaker in the application
- Simpler `.env.example` — `REDIS_*` variables removed
- Consistent single-database mental model: PostgreSQL is the system of record for everything

**Negative / accepted trade-offs:**
- Celery PostgreSQL broker is slower than Redis at high throughput — accepted; OSKAR volume is tens of tasks/day
- No built-in message TTL on the `kombu_message` queue — Celery handles cleanup via `celery beat` task or manual pruning
- If a real-time dashboard is ever required, `LISTEN/NOTIFY` must be implemented — this is a documented future path, not a surprise

**Non-impact:**
- The Transactional Outbox pattern (`movex_outbox` table + `SKIP LOCKED`) is unchanged — it was always PostgreSQL-native
- The SHA-256 audit chain is unchanged
- `aiosmtplib` notifications are unchanged — SMTP 10.10.0.155:25

---

## Future Path — `LISTEN/NOTIFY`

If a genuine real-time push requirement emerges:

```sql
-- Trigger on ecn_instances status change
CREATE OR REPLACE FUNCTION notify_ecn_status_change()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.status <> OLD.status THEN
        PERFORM pg_notify(
            'oskar_ecn_events',
            json_build_object(
                'ecn_id',   NEW.id,
                'ecn_number', NEW.ecn_number,
                'facility', NEW.facility,
                'status',   NEW.status
            )::text
        );
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
```

A FastAPI SSE endpoint listens on the channel via `asyncpg.connection.add_listener()`. Payload max 8KB — adequate for ECN status notifications. No Redis required even for this.
