# ADR-004 — Immutable Audit Chain: SHA-256 + PostgreSQL Append-Only

**Status:** Accepted
**Date:** 2026-04-10
**Owner:** Lead Engineer
**Reviewed by:** @expert-cybersecurity (expert review 2026-04-10)
**Type:** Architectural — type-1 (foundational; ISO 13485 + DISP compliance)

---

## Context

ISO 13485 §4.2.5 requires controlled records with documented retention. DISP requires tamper-
evident audit records. Stargile's `AuditTrailService` was plain text — no hash linkage, no
tamper evidence, reconstructable but not verifiable.

OSKAR must produce an audit chain that satisfies: ISO 13485, ISO 9001, IATF 16949, and DISP.

---

## Decision

**SHA-256 hash chain stored in `ecn_transition_history` (PostgreSQL), with append-only
enforcement and periodic out-of-band checkpoint.**

### Hash construction (canonical, deterministic)

```python
import hashlib, json
from datetime import timezone

def compute_audit_hash(event: AuditEvent, previous_hash: str) -> str:
    canonical = json.dumps({
        "event_id": str(event.event_id),
        "timestamp": event.timestamp.astimezone(timezone.utc).isoformat(),
        "actor": event.actor,          # LDAP username, verified at auth time
        "action": event.action,
        "resource_id": str(event.resource_id),
        "payload_hash": hashlib.sha256(
            json.dumps(event.payload, sort_keys=True).encode()
        ).hexdigest(),
        "previous_hash": previous_hash,
    }, sort_keys=True)               # sort_keys=True — field order is deterministic
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
```

`sort_keys=True` on all JSON serialization is mandatory. Test with a known vector before Sprint 1.
Timestamps are always UTC ISO 8601. Server-side only — never from client.

### Append-only enforcement (PostgreSQL)

```sql
-- API user has INSERT + SELECT only — no UPDATE or DELETE
REVOKE UPDATE, DELETE ON TABLE ecn_transition_history FROM oskar_api_user;
GRANT INSERT, SELECT ON TABLE ecn_transition_history TO oskar_api_user;
```

The `pg_audit` extension is enabled on the audit table. Any DDL (ALTER TABLE, TRUNCATE) on
`ecn_transition_history` generates a PostgreSQL-level log event that is separate from
application logs and outside the application's control.

### Audit writes are synchronous

Audit chain writes occur in the same database transaction as the state change. If the audit
write fails, the state change rolls back. No async audit writes for compliance-critical events.
This is slower than async but eliminates audit gaps.

### Periodic checkpoint (out-of-band witness)

Every 24 hours, a scheduled Celery task exports the current chain tail hash to Azure Blob
Storage (immutable container, WORM policy). This creates an independent witness that a DB
admin cannot retroactively tamper with by recomputing the chain. The checkpoint hash is also
logged to the Windows Event Log on SRXWEBAPP1 (accessible to Devian/DISP).

### Chain coverage

All of the following generate audit chain entries:
- ECN status transitions (every advance, reject, cancel, hold)
- Movex write initiation + completion/failure (includes full MI call payload)
- Drawing number creation
- MPN alias registration
- Role assignment changes on live ECNs
- Notification dispatch (who was notified, when, which channel)
- Agent suggestions accepted or rejected by engineers

### Agent provenance distinction

Agent actions use `actor = "agent:{agent_id}"` and `transition_type = "agent_suggestion"`.
They never appear as `actor = human_username` and never appear with `transition_type` of
`advance`, `approve`, `reject`, or `movex_write`. This is enforced by a PostgreSQL CHECK
constraint: `CHECK (transition_type NOT IN ('advance','approve','reject','movex_write') OR
actor NOT LIKE 'agent:%')`.

### Stargile migration data

Stargile audit records are imported to `legacy_ecn_history` (separate table, separate schema).
They are explicitly marked `source='stargile-migration'`. They are not included in the
OSKAR SHA-256 chain — the chain starts fresh at the OSKAR go-live date. Importing Stargile
plain-text records into the OSKAR hash chain would contaminate the chain's integrity guarantee.

---

## Rationale

PostgreSQL with append-only enforcement satisfies ISO 13485 + DISP requirements for a 50-user
on-premise system. A separate append-only store (e.g., WORM blob) would add operational
complexity without commensurate benefit at this scale. The checkpoint export provides the
out-of-band witness that prevents DB admin tampering — the gap that pure in-DB solutions have.

---

## Consequences

- `pg_audit` extension installed and configured before Sprint 1
- PostgreSQL `oskar_api_user` role: INSERT+SELECT on `ecn_transition_history`, no UPDATE/DELETE
- NTP enforced on Linux VM; NTP sync failures logged as security events
- Celery task: daily checkpoint export to Azure Blob (or SMTP to Devian if Blob not available)
- `ecn_transition_history` must be included in `pg_dump` daily backup (Manal — PRE-7)
- No PII in audit records — actor is LDAP username only (not full name, not email)
- Audit chain integrity check included in IQ/OQ/PQ test suite (Track E)
