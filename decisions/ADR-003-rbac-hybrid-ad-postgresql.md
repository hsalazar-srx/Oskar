# ADR-003 — RBAC: AD Groups (Coarse) + PostgreSQL Per-ECN Assignments (Fine)

**Status:** Accepted
**Date:** 2026-04-10
**Owner:** Lead Engineer
**Reviewed by:** @architect-system-design + @expert-cybersecurity (expert review 2026-04-10)
**Type:** Architectural — type-1 (foundational; affects all auth/authz code)

---

## Context

Stargile's `FileRoleManagement` stored roles in a `System/System.rolemap` XML file with an
in-memory cache. It mixed system-level role definitions with instance-level per-ECN assignments.
This caused: cache invalidation bugs, no audit trail of who was assigned which role, no record
of role changes, and inability to answer "who was the DC for ECN-2026-0042 on date X."

OSKAR must satisfy ISO 13485 non-repudiation requirements and DISP audit evidence requirements.

---

## Decision

**Four-layer RBAC model:**

| Layer | Store | Question | Who manages |
|---|---|---|---|
| Authentication | Active Directory (LDAPS 636) | Valid Scanfil APAC user? | IT (Manal) |
| Platform access | AD groups (`ecn-*`) | Can this user log into OSKAR? | IT (Manal) |
| System role | `system_role_users` (PostgreSQL) | Is this user a DC / QM system-wide? | OSKAR Admin |
| Per-ECN role | `ecn_role_assignments` (PostgreSQL) | Who is DC for ECN-2026-0042? | Auto-assigned; Admin override |

### What goes in the JWT

The JWT issued at login carries:
- `sub`: LDAP username (sAMAccountName)
- `groups`: AD group membership (e.g., `["ecn-initiator", "ecn-approver"]`)
- `name`, `email` (from LDAP `displayName` and `mail` attributes)
- `iat`, `exp`, `jti`, `iss`, `aud`

**The JWT does not carry per-ECN role assignments.** These are mutable (a PM can be reassigned
mid-ECN) and must always be queried live from `ecn_role_assignments`.

### FastAPI dependency pattern

Every approval-gate endpoint uses a two-layer check:

1. **Coarse (stateless):** JWT `groups` claim — "Is this user in `ecn-approver` at all?"
2. **Fine (live DB):** `ecn_role_assignments` query — "Is this user the QM for this specific ECN?"

Both must pass. Either failure returns 403. The fine check is never cached in the JWT.

### AD Group Structure

Groups are located under `OU=Application Roles,OU=Groups,DC=srxglobal,DC=com`
(Security Group — Universal). Domain: `srxglobal.com`, DC: `srxdc01.srxglobal.com`.

| AD Group CN | Distinguished Name | OSKAR gate | Managed by |
|---|---|---|---|
| `ecn-initiator` | `CN=ecn-initiator,OU=Application Roles,OU=Groups,DC=srxglobal,DC=com` | Can create ECNs and view items/BOM | IT (Manal) |
| `ecn-approver` | `CN=ecn-approver,OU=Application Roles,OU=Groups,DC=srxglobal,DC=com` | Can action approval steps (SE, CE, EM, QM, PM, SC, FN, CA, AD) | IT (Manal) |
| `ecn-doc-controller` | `CN=ecn-doc-controller,OU=Application Roles,OU=Groups,DC=srxglobal,DC=com` | Document Controller gate (subset of ecn-approver) | IT (Manal) |

Service account `svc-oskar-ldap` resides in `OU=Managed Service Accounts,DC=srxglobal,DC=com`.
Read-only, excluded from AD lockout policy. 90-day password rotation.

### OSKAR Role Set (11 active + 3 observer — from @expert-manufacturing-engineering)

**Active workflow participants:**
DC, CHIEF_ENGINEER, SENIOR_ENGINEER, JUNIOR_ENGINEER, ENGINEERING_MANAGER,
PRODUCTION_MANAGER, QUALITY_MANAGER, SUPPLY_CHAIN, FINANCE, IT_ADMIN, AUDITOR

**Observer / notification only:**
OBSERVER, EXTERNAL_REVIEWER, SUPPLIER

**Retired (from Stargile):**
- MG (Management) — too vague; accountability ambiguity; route via ENGINEERING_MANAGER
- HR — no ECN workflow function; training requirements are outbound notifications, not a role

### Auto-assignment at ECN creation

Query `system_role_users` for each required role. If exactly 1 active user → auto-assign with
`is_auto_assigned=TRUE` (preserves AsynchControl behaviour, with full audit trail).
If 0 users → ECN creation fails with a clear error. If >1 users → DC assigns manually.

### Data-driven approval routing

The `ecn_step_conditions` table maps ECN change scope flags to required roles:

```
role_code | required_when_flag
----------|-----------------
PM        | change_routings
SC        | new_parts
SC        | new_mpns
FN        | wapc_threshold_exceeded  (application-computed)
```

This replaces Stargile's hardcoded `isRoleChecked()` conditionals. Routing logic is auditable,
configurable without code changes, and readable by Karen/Branko directly.

---

## Rationale

Stargile's XML RBAC mixed two concerns that must be separated:
- **System roles** (global): "Who is the Quality Manager for OSKAR?" → `system_role_users`
- **Instance roles** (per-ECN): "Who is the QM for ECN-2026-0042?" → `ecn_role_assignments`

Putting per-ECN assignments in the JWT would create stale claims after reassignment.
Putting them back in a global XML file replicates Stargile's failure mode.

PostgreSQL per-ECN assignments are: auditable, immutable (INSERT-only, never UPDATE),
queryable, and readable by any future compliance tool without special access.

---

## Consequences

- `system_role_users` is admin-only; writes are audited via `pg_audit`
- `ecn_role_assignments` is INSERT-only for the API user; PostgreSQL RLS enforced
- Self-approval is prohibited at the application layer regardless of role membership
- AD group membership changes are re-checked every 30 minutes on sensitive write operations
  (not a full re-bind — cached group lookup). Stale window documented in IQ as known limitation.
- `get_email(username)` method added to `IdentityProvider` Protocol for notification dispatch
- Separation of duties enforced: ECN originator cannot be assigned QM or final approver
  for their own ECN (enforced at INSERT time via API check + PostgreSQL trigger)
