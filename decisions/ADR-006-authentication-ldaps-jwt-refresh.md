# ADR-006 — Authentication: LDAPS + JWT 60min + HttpOnly Refresh Cookie

**Status:** Accepted
**Date:** 2026-04-10
**Owner:** Lead Engineer
**Reviewed by:** @expert-cybersecurity (expert review 2026-04-10)
**Type:** Architectural — supersedes PRE-3 on token TTL and transport security

---

## Context

PRE-3 established: LDAP bind → JWT (8h expiry), `IdentityProvider` Protocol,
`LDAPIdentityProvider` production + `EntraIDProvider` stub.

The security review identified two problems with the PRE-3 design:
1. **LDAP port 389** transmits bind credentials in cleartext — DISP Tier 1 finding
2. **8-hour access token** is too long for a system that authorizes ERP writes; a stolen
   token grants 8 hours of write capability with no server-side revocation

This ADR supersedes PRE-3 on these two points. The `IdentityProvider` Protocol, LDAP bind
mechanism, and `EntraIDProvider` stub are unchanged.

---

## Decision

### Transport: LDAPS (port 636), not plain LDAP (389)

LDAPS with the internal ADCS certificate. STARTTLS on port 389 is not acceptable — it is
vulnerable to downgrade attacks. The ADCS root CA certificate is injected into the OSKAR
container as a Docker secret, not baked into the image.

```python
from ldap3 import Server, Connection, Tls
import ssl

tls = Tls(
    validate=ssl.CERT_REQUIRED,
    version=ssl.PROTOCOL_TLS_CLIENT,
    ca_certs_file="/run/secrets/internal_ca.crt"
)
server = Server("ldap.scanfil.local", port=636, use_ssl=True, tls=tls)
```

LDAP bind account (`svc-oskar-ldap`): read-only, scoped to OSKAR-related OUs, excluded from
AD lockout policy (lockout-susceptible bind account = DoS vector), 90-day password rotation.

**LDAP unavailability:** Fail closed. No new logins issued. Existing valid JWTs continue to
work until expiry. A `/health/auth` endpoint reports LDAP reachability (for ops alerting, not
for bypass). Circuit breaker (`pybreaker`) on the LDAP connection pool.

**Break-glass account:** One local PostgreSQL account (`svc-oskar-admin`), bcrypt-hashed,
disabled by default. Enabled only by Devian (DISP security owner) via documented procedure.
This account can trigger operational recovery only — it cannot approve ECNs (enforced by
`ecn_approval_steps.approver_type = 'HUMAN'` constraint + OSKAR-Approvers group check).

### Token design: 60-minute access + 8-hour refresh

| Token | TTL | Storage | Purpose |
|---|---|---|---|
| Access token | 60 minutes | React in-memory only (context/Redux) | API authorization |
| Refresh token | 8 hours | `HttpOnly`, `Secure`, `SameSite=Strict` cookie | Silent renewal |

The 8-hour session is preserved from a UX perspective. The attack window for a stolen access
token is 60 minutes. Refresh tokens are stored hashed in the `refresh_tokens` PostgreSQL table
with `expires_at` matching the 8h session window (ADR-007: Redis DB1 eliminated).

**Refresh token rotation:** Each refresh issues a new refresh token and sets `revoked_at` on the
previous one (`refresh_tokens` table). On family detection (reuse of a revoked refresh token),
the entire session family is invalidated — theft detection.

**Access token storage:** In-memory only. Never `localStorage`, never `sessionStorage`.
Lost on page refresh → silently renewed via refresh token cookie. The React app handles
this with an auth context that attempts silent refresh on 401 responses.

**CSRF protection:** `SameSite=Strict` on the refresh cookie. For state-mutating API calls,
verify the `Origin` header matches the expected OSKAR frontend origin.

### JTI blocklist (session invalidation)

Every JWT has a `jti` (JWT ID) claim (UUIDv4). A row in the `jti_blocklist` PostgreSQL table
with `expires_at` equal to the token TTL enables server-side invalidation before expiry. Check
performed on every request (UUID PK lookup at 50 users is sub-millisecond — ADR-007).

Use cases: user termination (Devian action), role change requiring immediate effect, security
incident. The blocklist auto-cleans at startup and hourly via FastAPI lifespan task — no `pg_cron` needed.

### JWT claims

```json
{
  "sub": "jsmith",
  "name": "John Smith",
  "email": "jsmith@scanfil.apac",
  "groups": ["OSKAR-Engineers", "OSKAR-Approvers"],
  "iat": 1744200000,
  "exp": 1744203600,
  "jti": "uuid-v4",
  "iss": "oskar.scanfil.apac",
  "aud": "oskar-api"
}
```

No per-ECN roles in the JWT. No PII beyond name/email. No internal system paths or IPs.

### AD group re-check on sensitive writes

Sensitive write operations (approve, reject, trigger Movex write) re-check AD group membership
via a cached LDAP lookup (refreshed every 30 minutes). This catches the case where a user's
AD account is disabled mid-session. Stale window of 30 minutes is documented in the IQ as
a known limitation acceptable for this environment.

---

## Consequences

- PRE-3 remains valid for `IdentityProvider` Protocol and `EntraIDProvider` stub design
- This ADR supersedes PRE-3 on: token TTL (60min not 8h), LDAPS not LDAP, refresh token design
- `svc-oskar-ldap` account creation required before Sprint 1 (Manal + Devian action)
- ADCS certificate for LDAPS required before Sprint 1 (Devian action)
- Refresh token endpoint: `POST /api/v1/auth/refresh` (HttpOnly cookie input, new access token output)
- Auto-logout on browser inactivity: 15 minutes (configurable via env var)
- Frontend: no token in localStorage — store in React auth context only
- `get_email(username: str) -> str` added to `IdentityProvider` Protocol (for notification dispatch)
- Docker secrets: `ldap_bind_password`, `internal_ca.crt`, `jwt_secret`, `refresh_token_secret`
