# PRE-4 — API Versioning

**Status:** Accepted — Final for OSKAR v1
**Date:** 2026-04-08
**Owner:** Lead Engineer
**Type:** Architectural — type-1 (hard to change once consumers exist)

---

## Decision

`/api/v1/` prefix on all FastAPI routes from Sprint 1 Day 1. No exceptions.
Health check at `/health` is unversioned (Docker + IIS healthcheck use).

## Rationale

`movex-rest-api` ships unversioned `/api` routes. This now constrains SM-Portal
integration options. OSKAR must not repeat this mistake. Phase 4 consumers (Power BI,
MES, EDI/RPA) depend on stable versioned endpoints.

## Consequences

- All routers must be included under `v1_router` with prefix `/api/v1`
- Breaking changes to an endpoint require a `/api/v2/` path — never modify v1 in place
- SM-Portal integration calls `/api/v1/` from the OSKAR vhost
