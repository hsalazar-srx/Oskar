# PRE-8 — Staging Environment

**Status:** Accepted — Final for OSKAR v1
**Date:** 2026-04-08
**Owner:** Manal (Infrastructure Manager)
**Type:** Operational

---

## Decision

Second Docker Compose stack on same SRXWEBAPP1, separate ports and volumes.

| Service | Staging Port | Production Port |
|---------|-------------|-----------------|
| App (FastAPI) | 8001 | 8000 |
| PostgreSQL | 5433 | 5432 |
| Redis | 6380 | 6379 |

Config file: `docker-compose.staging.yml`
IIS vhost: `oskar-staging.srxwebapp1.local`

## Gate Condition

Staging environment live before Phase 2 begins. OQ test cases and performance demos run
on staging — never on production data.

## Consequences

- All Sprint demos use staging stack — never production
- Staging has its own `.env.staging` with separate DB credentials
- Performance benchmark (100 parts, 6 suppliers, <90 sec) runs on staging in Sprint 3
