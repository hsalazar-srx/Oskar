# PRE-3 — Identity Provider Interface

**Status:** Accepted — Final for OSKAR v1
**Date:** 2026-04-08
**Owner:** Lead Engineer
**Type:** Architectural — type-2 reversible (add new provider implementation)

---

## Decision

`IdentityProvider` Protocol class in `src/auth/providers.py`.
- `LDAPIdentityProvider` — production implementation (on-prem AD bind)
- `EntraIDProvider` — stub only (future Scanfil Group Entra ID push)

JWT expiry: 480 minutes (8 hours, matches working day).

## Rationale

Docker containers cannot use Windows Negotiate (Kerberos/NTLM inside Linux Docker is
a known support problem). LDAP bind to on-prem AD is the correct path. Engineers use
the same AD credentials via a different bind mechanism — transparent to the user.

## Consequences

- Auth returns JWT; all subsequent requests are JWT-validated (no per-request LDAP bind)
- `EntraIDProvider` stub must raise `NotImplementedError` — never silently pass
- When Scanfil Group pushes Entra ID, swap `LDAPIdentityProvider` → `EntraIDProvider` with no API contract change
