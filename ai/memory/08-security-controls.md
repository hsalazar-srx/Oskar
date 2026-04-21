# OSKAR — Security Controls and STRIDE Threat Model

> **PROVIDER-AGNOSTIC — Non-Negotiable #12**
> No tool-specific syntax. Readable by any LLM tool or none.

**Version:** 1.0
**Date:** 2026-04-13
**Phase:** Phase 1 Track D deliverable
**Sources:** Expert review by `@expert-cybersecurity` (2026-04-10); `decisions/ADR-006` (auth); `decisions/ADR-003` (RBAC); `decisions/ADR-004` (audit chain)

---

## 1. STRIDE Threat Model — Top 5 Threats

| # | Threat | STRIDE category | Attack vector | Mitigation |
|---|--------|----------------|--------------|-----------|
| 1 | JWT forgery — attacker crafts a token claiming approver role | Spoofing | Weak/leaked JWT secret; `alg:none` attack | Strong random secret (≥256 bit); `alg=HS256` only; validate on every request; JTI blocklist on logout |
| 2 | Movex write injection — malicious payload in ECN item fields passed to MI call | Tampering | Unvalidated string fields passed directly to `movex-rest-api` | Pydantic field validation on all ECNItem fields; MI call parameters constructed server-side — never user-supplied strings interpolated directly |
| 3 | Audit chain tampering — DELETE or UPDATE on `ecn_transition_history` | Tampering | Compromised DB credentials or SQL injection | PostgreSQL RLS + INSERT-only grant on `ecn_transition_history` for application user; SHA-256 chain detects any modification |
| 4 | Privilege escalation — user claims approver role by manipulating `system_role_users` | Elevation of privilege | Direct DB access or compromised admin account | RLS on `ecn_role_assignments`; all role changes logged; separate DB user for migrations vs application |
| 5 | Secrets exfiltration — API keys or DB password leaked in logs | Information disclosure | Verbose error logging; accidental `print()` or debug output | Structured Serilog-equivalent logging (structlog); no secrets in log fields; `OSKAR_DB_PASSWORD` never in application log output |

---

## 2. Security Controls — All P0 (Pre-Sprint 1 mandatory)

These must be in place before Sprint 1 code is written. Failure = DISP Tier 1 finding.

### P0-1: LDAPS (port 636) — not plain LDAP (port 389)

**Why:** LDAP on 389 sends credentials in cleartext. DISP Tier 1 requirement.

**Implementation:**
- `LDAP_SERVER=ldaps://srxdc01.srxglobal.local:636` in `.env`
- `ldap3.Server(..., use_ssl=True)` in `LDAPIdentityProvider`
- Certificate validation against ADCS root CA (Manal provisions ADCS cert)
- Confirm with Devian before Sprint 1 starts — record in `ai/evidence/decision-log.md`

### P0-2: JWT TTL — 60min access token + 8h HttpOnly refresh cookie

**Why:** 8h access token gives attacker too long a window if token is stolen. 60min access + refresh is industry standard.

**Implementation (ADR-006):**
- `ACCESS_TOKEN_EXPIRE_MINUTES=60` in settings
- Refresh token: 8h, issued as `HttpOnly; Secure; SameSite=Strict` cookie
- `POST /api/v1/auth/refresh` accepts refresh cookie, returns new access token
- JTI (JWT ID) blocklist in `jti_blocklist` PostgreSQL table — logout adds JTI; every request checks table (ADR-007: Redis eliminated)

### P0-3: PostgreSQL broker access hardening (replaces Redis AUTH — ADR-007)

**Why:** Redis is eliminated. The equivalent control is PostgreSQL connection security.

**Implementation:**
- `DATABASE_URL` uses a dedicated `oskar_app` role with minimum required privileges — not a superuser
- PostgreSQL `pg_hba.conf` restricts to Docker bridge network — not `0.0.0.0`
- `POSTGRES_PASSWORD` injected via Docker secret, not `.env`
- `CELERY_SECURITY_KEY` still required for Celery task signing (ADR-005)

### P0-4: PostgreSQL RLS on `ecn_role_assignments`; INSERT-only on audit chain

**Why:** Application-layer RBAC is necessary but not sufficient. DB-level enforcement prevents compromised code paths.

**Implementation:**
- Enable RLS on `ecn_role_assignments`: application user can only read rows where `ecn_id` is in their active ECN set
- `ecn_transition_history`: application user has `INSERT` + `SELECT` only — no `UPDATE` or `DELETE`
- Separate DB roles: `oskar_app` (runtime), `oskar_migration` (schema changes), `oskar_readonly` (reporting)

---

## 3. Security Controls — P1 (Sprint 1 scope)

### P1-1: PostgreSQL RLS on `ecn_instances`

Application user can only read ECNs where they have an assignment or are in a permitted AD group. Prevents information leakage between ECN types.

### P1-2: Docker container hardening baseline

- Non-root user in Dockerfile (already done in Phase 0)
- Read-only root filesystem where possible
- No `--privileged` flag
- `CAP_DROP ALL` in Compose; add back only what's needed
- `no-new-privileges: true` in Compose security context

### P1-3: Secret scanning in CI

- `gitleaks` pre-commit hook — blocks commits containing secrets
- `pip-audit` in CI — flags known CVEs in Python dependencies
- `npm audit` in CI — flags known CVEs in frontend dependencies

### P1-4: Celery task signing

- `CELERY_TASK_SERIALIZER=json` (not pickle — pickle allows arbitrary code execution)
- `CELERY_ACCEPT_CONTENT=['json']`
- Task authentication via shared secret (`CELERY_SECURITY_KEY`) — prevents malicious task injection

---

## 4. Security Controls — P2 (Sprint 2+ scope)

| Control | Description | Sprint |
|---------|------------|-------|
| Single-use `write_authorization_token` | One-time token issued at APPROVED gate; Celery worker validates before MI call | Sprint 2 |
| `schema_version` on `LISTEN/NOTIFY` payload envelope | Prevents stale consumers from processing mismatched events if live-push is introduced (ADR-007: Redis DB2 eliminated; concept retained) | Phase 4 if required |
| HTTPS between FastAPI and movex-rest-api | mTLS or at minimum HTTPS with ADCS cert | Sprint 4 |
| IIS security headers | `X-Frame-Options`, `X-Content-Type-Options`, `HSTS` on reverse proxy | Sprint 4 |
| Incident response runbook | See `ai/memory/09-known-risks-and-pitfalls.md` §7 | Sprint 1 |
| Stargile migration data as untrusted | Historical archive import must go into isolated legacy table; hash chain starts fresh | Sprint 3 |

---

## 5. `IdentityProvider` Protocol — `get_email()` Required

The notification system (Track B §7) requires looking up user email addresses from AD.

**Required change to `src/auth/providers.py`** (Phase 2 gate F-3):

```python
class IdentityProvider(Protocol):
    def authenticate(self, username: str, password: str) -> bool: ...
    def get_groups(self, username: str) -> list[str]: ...
    def get_email(self, username: str) -> str | None: ...  # ADD THIS
```

`LDAPIdentityProvider.get_email()` queries the `mail` attribute from AD. Returns `None` if not set (log warning; do not raise).

---

## 6. Secrets Management Rules

| Secret | Storage (dev) | Storage (prod) | Never |
|--------|--------------|---------------|-------|
| `OSKAR_DB_PASSWORD` | `dotenv user-secrets` equivalent / `.env` (gitignored) | Docker secret | In code, logs, or image layers |
| `JWT_SECRET_KEY` | `.env` (gitignored) | Docker secret | In code or logs |
| `POSTGRES_PASSWORD` | `.env` (gitignored) | Docker secret | In code, logs, or image layers |
| `LDAP_BIND_PW` | `.env` (gitignored) | Docker secret | In code or logs |
| `CELERY_SECURITY_KEY` | `.env` (gitignored) | Docker secret | In code or logs |

`.env.example` committed with placeholder values only. `.env` in `.gitignore`. Verified by `gitleaks` pre-commit hook.

---

## 7. LLM / MAS Security

OSKAR uses AI agents (this MAS framework) to assist development and provide operational suggestions. Controls:

- **No agent has direct DB access** — all suggestions go through the OSKAR API with human confirmation
- **Prompt injection:** `ai/` context files are provider-agnostic markdown; no executable instructions that could be injected into LLM context
- **Agent provenance log:** Every agent suggestion accepted by the engineer is recorded in `ecn_transition_history.agent_provenance` — JSONB field, append-only
- **Human-in-the-loop is non-negotiable** (Non-Negotiable #5 and #8): No autonomous Movex write; every ERP push requires explicit human confirmation
