# ADR-008 — Optimistic Locking for Concurrent ECN Edits

**Status:** Accepted
**Date:** 2026-04-23
**Owner:** Lead Engineer
**Reviewed by:** Lead Engineer (gap identified during Sprint 2 design — self-review)
**Type:** Architectural — data integrity; applies to all mutable ECN endpoints

---

## Context

During Sprint 2 design (2026-04-23), a concurrency gap was identified that was not addressed by
the original architect review (2026-04-10). The gap: two users can open the same ECN in DRAFT
(or any non-terminal status), make independent edits, and submit — the last write wins silently.
No error is raised. The earlier user's changes are lost with no notification.

The original expert review (ADR-002, ADR-004, ADR-005) focused on:
- Approval-level concurrency (handled by DB unique index on `ecn_approval_steps`)
- Movex write safety (handled by outbox + idempotency key + write_authorization_token)
- Audit chain integrity (handled by SHA-256 chain on `ecn_transition_history`)

The DRAFT editing scenario — the most common user interaction — was not covered. This is a
classic lost-update problem. See `ai/evidence/lesson-learned-LL-001.md` for root cause analysis.

`ecn_instances.updated_at` already exists (Sprint 1 schema) as a timestamp managed by the
`set_updated_at()` PostgreSQL trigger. This ADR uses it as the optimistic lock token.

---

## Decision

**Optimistic locking via `If-Unmodified-Since` header on all mutable ECN endpoints.**

No new column is required. `updated_at` (TIMESTAMPTZ, existing) is used as the lock token.

### Protocol

**GET response:** Every `GET /api/v1/ecn/{id}` response includes:
```
Last-Modified: <updated_at as RFC 7231 HTTP date>
```
The response body also echoes `updated_at` as an ISO 8601 field (`"updated_at": "2026-04-23T04:10:00Z"`)
for clients that prefer JSON over headers.

**Mutating requests:** Every `PATCH /api/v1/ecn/{id}` and `PATCH /api/v1/ecn/{id}/status`
request MUST include:
```
If-Unmodified-Since: <the updated_at value received in the prior GET>
```

**Server validation (service layer, before any DB write):**
```python
current = await db.get(ECNInstance, ecn_id)
if current.updated_at != request.if_unmodified_since:
    raise HTTPException(409, detail={
        "code": "ECN_MODIFIED",
        "message": "This ECN was modified by another user. Reload and reapply your changes.",
        "current_updated_at": current.updated_at.isoformat()
    })
```

The check happens **inside the same DB transaction** as the write, preventing a TOCTOU race.
PostgreSQL serialises concurrent writes to the same row — only one succeeds.

**409 response body includes `current_updated_at`** so the client can present a "reload"
option and show the user exactly when the conflicting change occurred.

### Scope

Applied to all endpoints that mutate `ecn_instances`:

| Endpoint | Requires `If-Unmodified-Since` |
|---|---|
| `PATCH /api/v1/ecn/{id}` (field edits) | Yes |
| `PATCH /api/v1/ecn/{id}/status` (transitions) | Yes |
| `POST /api/v1/ecn/{id}/approve-role` | Yes |
| `POST /api/v1/ecn/{id}/reject` | Yes |
| `POST /api/v1/ecn/{id}/hold` | Yes |
| `POST /api/v1/ecn/{id}/resume` | Yes |
| `DELETE /api/v1/ecn/{id}` (cancel) | Yes |

`POST /api/v1/ecn/` (create) — exempt; no prior state to conflict with.

### Why optimistic, not pessimistic

Pessimistic locking (`SELECT FOR UPDATE` row lock) would require holding a DB lock for the
duration of a user's editing session — potentially minutes. With 50 users and normal browser
behaviour (open a tab, get distracted, come back), this would cause cascading lock waits and
connection exhaustion on a 2-vCPU/4 GB VM. Optimistic locking is appropriate when conflicts
are rare (true here — most ECNs are owned by one engineer at a time) and the cost of a retry
is low (reload and reapply is acceptable).

### ecn_items sub-resources

`ecn_items` (BOM line items) are also mutable. The same pattern applies to:
- `POST /api/v1/ecn/{id}/items` — exempt (create)
- `PATCH /api/v1/ecn/{id}/items/{item_id}` — requires `If-Unmodified-Since` against `ecn_items.updated_at`
- `DELETE /api/v1/ecn/{id}/items/{item_id}` — requires `If-Unmodified-Since`

`ecn_items.updated_at` already exists in the Sprint 1 schema.

---

## Rationale

`updated_at` was already present and managed by a DB trigger. Reusing it as the lock token
requires zero schema change — only a migration to add the validation check in the service layer.

HTTP `If-Unmodified-Since` is a standard conditional request mechanism (RFC 7232). It is
framework-agnostic and understood by any HTTP client including the React frontend.

A dedicated integer `version` column was considered. It is slightly more precise (no clock skew
risk) but adds a new column and a `DEFAULT 1` backfill migration. Clock skew is not a concern
here — OSKAR is single-server with a single PostgreSQL instance; all `updated_at` values come
from the same clock. `updated_at` is sufficient.

---

## Consequences

- **Migration 0005** adds no new columns. It documents the locking pattern as a DB comment on
  `ecn_instances` and `ecn_items` for future maintainers.
- `ECNService.update_ecn()` and `ECNService.transition_ecn()` gain an `if_unmodified_since`
  parameter. Callers that do not supply it receive `428 Precondition Required`.
- Frontend PATCH calls must include `If-Unmodified-Since`. The React client stores `updated_at`
  from GET response and sends it on every mutation.
- New test cases required (see Testing section).
- Lesson learned `LL-001` documents why this was missed in the original review.

---

## Testing

| Test ID | Description | Pass criterion |
|---|---|---|
| OQ-40 | PATCH with correct `If-Unmodified-Since` succeeds | 200 OK; `updated_at` advanced |
| OQ-41 | PATCH with stale `If-Unmodified-Since` rejected | 409; body contains `current_updated_at` |
| OQ-42 | PATCH without `If-Unmodified-Since` header rejected | 428 Precondition Required |
| OQ-43 | Two concurrent PATCHes — first wins, second gets 409 | Exactly one 200, one 409 |
| OQ-44 | Status transition with stale header rejected | 409 before state machine fires |
| OQ-45 | `ecn_items` PATCH with stale header rejected | 409 on item-level conflict |

---

## Implementation Notes

The `if_unmodified_since` check must happen **before** `ECNWorkflowMachine` is called. If the
machine fires and the DB write then fails the timestamp check, the machine's in-memory state
would be advanced but not persisted — leaving the caller with a stale machine object. Check
timestamp → then trigger machine → then commit, all in one transaction.
