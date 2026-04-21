# PRE-2 — Redis Logical Separation

**Status:** Accepted — Final for OSKAR v1
**Date:** 2026-04-08
**Owner:** Lead Engineer
**Type:** Architectural — type-2 reversible (env var change per service)

---

## Decision

One Redis 7 instance, three logical DBs. `appendonly yes` on DB 2 only.

| DB | Purpose | Persistence |
|----|---------|-------------|
| DB 0 | Celery broker | None (ephemeral) |
| DB 1 | Application cache | None (`allkeys-lru`, TTL-driven) |
| DB 2 | Event stream | `appendonly yes` — events survive restart |

## Rationale

Separating into three Redis containers adds operational complexity with no benefit at
current scale. Logical DBs give clean isolation at zero cost. Splitting to separate
containers later requires only one env var change per service.

## Consequences

- Never conflate DB numbers in code — connection strings must explicitly specify the DB index
- `docker-compose.yml` mounts a `redis.conf` that enables `appendonly yes`
- If Redis instance fails, all three logical DBs go down simultaneously — acceptable for v1
