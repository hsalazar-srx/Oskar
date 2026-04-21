# PRE-12 — Movex Company Number (CONO) Environment Mapping

**Status:** Accepted
**Date:** 2026-04-15
**Owner:** Lead Engineer
**Type:** Operational — affects all ERP adapter calls and environment configuration

---

## Context

Movex/M3 is a multi-company ERP. All DB2 tables that are company-scoped (MITMAS, OHEDCO,
FGINHE, etc.) require CONO in every WHERE clause to avoid returning data from all companies.

OSKAR calls Movex via movex-rest-api. The CONO used determines which Movex company the
read or write operation targets. Using the wrong CONO in a write operation will corrupt
production data or write to the wrong company.

---

## Decision

| Environment | CONO | Movex company | Used by |
|-------------|------|--------------|---------|
| Development | 300 | Development / UAT company | Local dev, Docker dev stack, Sprint demos |
| Staging | 300 | Development / UAT company | Docker staging stack (PRE-8), OQ test cases |
| Production | 100 | Production company | Production Docker stack only |

**CONO is an environment variable — never hardcoded in Python code or SQL.**

```
MOVEX_CONO=300   # .env.development, .env.staging, docker-compose.dev.yml, docker-compose.staging.yml
MOVEX_CONO=100   # .env.production only — production stack only
```

The `ERPAdapter` implementations read `MOVEX_CONO` at startup. All MI call parameters
and DB2 queries that require CONO use this value. The CONO is never passed by callers —
it is injected at the adapter layer.

---

## Consequences

- `MOVEX_CONO` added to `.env.example` alongside existing Movex config vars
- `MovexRestAdapter` passes `MOVEX_CONO` in all MI request payloads
- IQ test cases (IQ-06: ERP connectivity) run against CONO=300
- OQ test cases run against CONO=300 on staging
- Production go-live checklist: confirm `MOVEX_CONO=100` in production `.env` before first deploy
- No OSKAR test or demo ever writes to CONO=100 — staging enforces CONO=300 by config

---

## Go-Live Checklist Item

Before first production deploy, verify:
```
grep MOVEX_CONO /etc/oskar/secrets.env   # Must return MOVEX_CONO=100
```
Document this verification in the IQ sign-off (IQ-06).
