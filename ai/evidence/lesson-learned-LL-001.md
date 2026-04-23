# Lesson Learned — LL-001
# Concurrent Edit Protection (Lost-Update) Not Covered in Initial Architecture Review

**Date identified:** 2026-04-23
**Sprint:** Sprint 2 design (pre-coding)
**Identified by:** Lead Engineer (hector.salazar@srxglobal.com) during Sprint 2 scope review
**Severity:** Medium — data integrity risk under normal concurrent use
**Resolution:** ADR-008 (Optimistic Locking via `If-Unmodified-Since`)
**Status:** Resolved — ADR-008 accepted 2026-04-23

---

## What Happened

During Sprint 2 design, the Lead Engineer raised a concurrency question: *"How is this
architecture preventing concurrency issues like accessing or approving the same ECN or BOM at
the same time?"*

Analysis confirmed that four of the five relevant scenarios were well-handled (approval
uniqueness, parallel approvals, Celery idempotency, BOM snapshot detection). One scenario was
not covered: **two users concurrently editing the same ECN in DRAFT (or any editable status)**.

The lost-update problem was not identified in the Phase 0 expert review (2026-04-10) by
`@architect-system-design`, `@expert-cybersecurity`, or `@expert-manufacturing-engineering`.
It was also not flagged in any of the seven ADRs (ADR-001 through ADR-007) or twelve PRE
decisions written during Phase 0 and Phase 2.

---

## Root Cause Analysis

### Primary cause — Scope bias in the expert review

The expert review focused on the problems Stargile was known to have:
- Movex write failures (stuck ECNs at status 50) → led to Transactional Outbox (ADR-005)
- Audit chain tampering → led to SHA-256 chain (ADR-004)
- Auth bypass → led to write_authorization_token (ADR-005, Control 2)
- JWT forgery → led to JTI blocklist (ADR-006)

The review framed concurrency as a **Movex write safety** problem, not a **user data integrity**
problem. The DRAFT editing scenario — the highest-frequency user action — was outside that frame.

### Secondary cause — Missing category in the review checklist

The expert review used a STRIDE threat model (security-focused) and a workflow-safety checklist
(Movex write path). Neither checklist included a **data mutation concurrency** category covering:

- Lost-update on shared mutable records
- Double-submit (same form submitted twice)
- Stale read followed by blind write

These are standard distributed systems concerns, but they were not explicitly in scope for the
security or workflow reviews. No agent had a mandate to check them.

### Contributing factor — `updated_at` present but purpose not declared

`ecn_instances.updated_at` was included in the Sprint 1 schema for general auditing purposes.
Its potential use as a concurrency control token was not documented. A reviewer who noticed it
would have no basis to ask "is this being used for optimistic locking?" — because its purpose
was not declared.

---

## Impact Assessment

**Actual impact before fix:** Zero — Sprint 1 was a platform foundation sprint. No production
users. The gap was identified before Sprint 2 coding began.

**Potential impact if undetected until go-live:** A DC and an engineer simultaneously editing
the same DRAFT ECN would produce silent data loss — the earlier save would be overwritten. In
an ISO 13485 environment this could mean:
- A required field (e.g., `customer_approval_reference`) entered by one user silently dropped
- An engineering change description overwritten with an older version
- No audit evidence that the earlier edit was ever made

With ~50 users and ECNs that sit in DRAFT for hours or days, concurrent edits are a realistic
scenario, not an edge case.

---

## What Was Done Well

The review correctly prioritised:
- The most dangerous failure mode (unauthorised Movex write)
- The highest compliance risk (non-repudiation of approvals)
- The known Stargile operational failures (stuck ECNs, silent rollback failures)

The four other concurrency scenarios were all correctly handled. The `updated_at` trigger was
already in place — resolution required service-layer code only, no schema migration.

---

## Resolution

**ADR-008** adds optimistic locking via HTTP `If-Unmodified-Since` on all mutable ECN endpoints.
The implementation reuses the existing `updated_at` column — no schema change required.

Alembic migration `0005_optimistic_lock_comment.py` adds a DB comment to document the column's
dual purpose (audit timestamp + concurrency token) for future maintainers.

---

## Process Changes Adopted

The following items are now standing requirements for all future architectural reviews on Oskar
and companion projects. They have been added to the Oskar agent constitution
(`.providers/claude/CLAUDE.md`) under "Review Checklist — Data Mutation":

1. **Concurrent edit protection** — Is optimistic or pessimistic locking in place for every
   mutable shared resource? For each PATCH/PUT/DELETE endpoint: what happens if two users
   submit the same mutation concurrently?

2. **Double-submit prevention** — Can a form or API call be submitted twice in quick succession?
   What is the database constraint or idempotency key that prevents a duplicate record?

3. **Stale-read / blind-write** — Does any flow read data, present it to a user, and write it
   back without checking whether the data changed in the interim?

4. **TOCTOU (Time-of-Check to Time-of-Use)** — Is any guard condition checked outside the
   transaction that performs the write? If yes, the check must be repeated inside the
   transaction.

5. **Terminal state protection** — Can a terminal-state record (CLOSED, CANCELLED) be mutated
   by a concurrent request that arrived before the status committed? Is the status check
   inside the write transaction?

These five checks are in addition to (not replacing) the STRIDE security review and the Movex
write-safety checklist.

---

## References

- [ADR-008](../decisions/ADR-008-optimistic-locking-concurrent-ecn-edits.md) — Resolution
- [ADR-002](../decisions/ADR-002-workflow-engine-celery-postgresql-transitions.md) — Original workflow design (no concurrent edit coverage)
- [ADR-005](../decisions/ADR-005-erp-write-gate.md) — ERP write gate (Movex write concurrency covered)
- `ai/memory/12-data-model.md` §7.1 — `ecn_instances` schema with `updated_at`
