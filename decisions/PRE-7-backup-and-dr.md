# PRE-7 — Backup and Disaster Recovery

**Status:** Accepted — Final for OSKAR v1
**Date:** 2026-04-08
**Owner:** Manal (Infrastructure Manager)
**Type:** Operational

---

## Decision

- `pg_dump` daily at 02:00 via Windows Task Scheduler → `D:\Backups\oskar\`
- Weekly NAS copy via Windows Server Backup
- RTO: 4 hours | RPO: 24 hours

## Gate Condition

Backup procedure documented + test restore executed before Phase 1 IQ sign-off.
Manal is named owner — this is not a Lead Engineer responsibility.

## Consequences

- IQ/OQ/PQ sign-off is blocked until Manal confirms backup + restore tested
- Redis DB 2 (`appendonly yes`) survives container restart — not a backup substitute
- PostgreSQL volume data is ephemeral inside Docker unless mounted to host path — `docker-compose.yml` must mount to `D:\oskar-data\postgres\`
