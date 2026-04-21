# ADR-005 — ERP Write Gate: State Machine + Write Authorization Token

**Status:** Accepted
**Date:** 2026-04-10
**Owner:** Lead Engineer
**Reviewed by:** @expert-cybersecurity + @architect-system-design (expert review 2026-04-10)
**Type:** Architectural — type-1 (Non-Negotiable #5: no Movex write without human confirmation)

---

## Context

Non-Negotiable #5: no Movex write without explicit human confirmation. This is an ISO 13485
non-repudiation requirement and a DISP control. In Stargile, the human confirmation gate was
a UI-level control only — a form submission that triggered a synchronous Movex write. Any
authenticated API client could bypass the UI and call the transition endpoint directly.

The Celery async architecture introduces a second bypass risk: if a Movex write Celery task
can be injected directly into the `kombu_message` queue table, it could execute without going
through the approval API at all. (ADR-007: Redis DB0 broker replaced by PostgreSQL.)

---

## Decision

**Three technical controls that together make ERP write bypass architecturally impossible:**

### Control 1: State machine gate (PostgreSQL)

The Movex write Celery task only reads `movex_outbox` entries. `movex_outbox` entries are only
created by the FastAPI approval endpoint. The approval endpoint checks:

1. `ecn_instances.status == APPROVED` (state machine guard)
2. All required `ecn_approval_steps` rows have `state='approved'` (all required approvals collected)
3. Authenticated user's JWT `jti` is not in the `jti_blocklist` PostgreSQL table (ADR-007: Redis eliminated)

If any check fails → 400/403 returned, no outbox entry created, no Celery task dispatched.

### Control 2: Single-use write authorization token

When the approval endpoint succeeds (all checks pass):

1. A `write_authorization_token` is generated: `HMAC-SHA256(secret_key, ecn_id + jti + timestamp)`
2. The token is stored in the `movex_outbox.write_authorization_token` column — consumed on first use (ADR-007: Redis DB1 eliminated; token stored directly in the outbox row)
3. The Celery task reads the outbox entry, validates the HMAC, and marks the token consumed
4. If the token is absent or already consumed → task aborts; error logged

This prevents Celery task injection: even if an attacker injects a `movex_outbox` row directly
into PostgreSQL or directly into the `kombu_message` broker table, the task will fail validation
because it cannot generate a valid `write_authorization_token` (the HMAC key is in Docker secrets).

### Control 3: movex-rest-api caller verification

`movex-rest-api` (.NET 8, Windows Server) requires an API key from OSKAR. The key is stored
in Docker secrets on the OSKAR VM and in Azure Key Vault / user-secrets on the Windows Server.
Windows Firewall on the Windows Server restricts inbound connections to the OSKAR backend IP
only — `movex-rest-api` cannot be called from any other host.

### Approval record (non-repudiation)

The `ecn_approval_steps` table records each approval as a distinct row:
```
ecn_id | step_status | role_code | actioned_by | actioned_at | jwt_jti | ip_address
```

The `jwt_jti` ties the approval to the specific authenticated session. This is non-repudiable:
the approver cannot later claim they did not approve, because the specific token used is recorded.

### Audit evidence per Movex write

Each Movex write generates these audit chain entries (in `ecn_transition_history`):
1. `MOVEX_WRITE_INITIATED` — actor, ecn_id, jwt_jti, MI call list
2. `MOVEX_WRITE_COMPLETED` — full MI response payloads
3. (On failure) `MOVEX_WRITE_FAILED` — error details, retry count

Plus the `movex-rest-api` access log on Windows Server (separate, outside OSKAR control).

---

## Rationale

A UI-only approval gate is not a technical control — it is a convention. An authenticated API
client with a valid JWT can bypass it. The state machine (PostgreSQL) + outbox pattern
(write gate) + HMAC token (injection prevention) + caller verification (network control)
create defense in depth: no single control failure allows an unauthorized Movex write.

The `write_authorization_token` design was chosen over a separate approval table FK because
it is time-limited (5-minute TTL), single-use, and does not persist state that must be cleaned
up — it expires automatically on successful use or TTL expiry.

---

## Consequences

- `write_authorization_token` HMAC secret stored in Docker secrets (never in `.env`)
- Celery task: validate token before any MI call; abort and alert if invalid
- `ecn_approval_steps.jwt_jti` column added to the schema
- `movex-rest-api` API key added to Sprint 1 configuration (both ends)
- Windows Firewall rule: restrict movex-rest-api inbound to OSKAR backend IP (Manal action)
- ISO 13485 SDD must document the three-control model — this ADR is the reference
- The `approver_type` CHECK constraint on `ecn_approvals`: `CHECK (approver_type = 'HUMAN')`
  prevents agent records from appearing as approvals at the DB level
