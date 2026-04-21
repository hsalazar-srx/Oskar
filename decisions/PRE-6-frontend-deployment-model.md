# PRE-6 — Frontend Deployment Model

**Status:** Accepted — Final for OSKAR v1
**Date:** 2026-04-08
**Owner:** Lead Engineer
**Type:** Architectural — type-2 reversible
**See also:** [ADR-001](ADR-001-sm-portal-oskar-navigation-link-no-auth-coupling.md)

---

## Decision

OSKAR frontend is a standalone React/TypeScript app on its own IIS vhost (`oskar.srxglobal.local`).
SM-Portal is the primary entry point — it contains a navigation tile linking to OSKAR (opens in new tab).
No auth coupling between the two systems.
Share Tailwind design tokens with SM-Portal for visual coherence.

## Rationale

SM-Portal uses Windows Negotiate auth (.NET 8). OSKAR uses JWT + LDAP (Python/FastAPI in
Docker/Linux). Kerberos inside Docker is unsupported. Auth bridging adds complexity
disproportionate to the UX benefit. Navigation link gives engineers a single entry point
(SM-Portal) without coupling the auth stacks.

## Consequences

- Engineers authenticate twice: Windows auth to SM-Portal, then LDAP/JWT to OSKAR (transparent — same AD credentials)
- JWT 8-hour expiry matches working day — no mid-day re-login for most users
- SM-Portal change: add OSKAR tile to navigation (one frontend component change)
