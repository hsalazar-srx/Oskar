# OSKAR — Testing Strategy

> **PROVIDER-AGNOSTIC — Non-Negotiable #12**
> No tool-specific syntax. Readable by any LLM tool or none.

**Version:** 1.1
**Date:** 2026-05-04
**Phase:** Phase 1 Track E deliverable
**Stack:** Python 3.12, FastAPI, PostgreSQL 16, Celery, `transitions` library

---

## 1. Testing Principles

- **≥80% line coverage** on all business logic (state machine, RBAC, outbox, audit chain). Coverage gate enforced in CI.
- **Real PostgreSQL in integration tests** — no mocks for the database. Test database is a separate Docker service (`oskar-test-db`) running in the same Compose network.
- **Mock `movex-rest-api`** in unit and integration tests — the ERP adapter is the boundary. `httpx.MockTransport` or `respx` for HTTP-level mocking.
- **No test that requires a real Movex connection** — all Movex interactions go through the adapter; tests mock at the adapter boundary.
- **Audit chain tests are mandatory** — SHA-256 chain integrity must be verified in every test that writes a transition.

---

## 2. Test Pyramid

```
         ┌──────────────────────────────┐
         │   E2E / IQ/OQ/PQ (manual)   │  ~10 tests — validation protocol (ai/memory/07)
         ├──────────────────────────────┤
│   Integration tests          │  ~40% of suite — real PG, mock ERP adapter
         ├──────────────────────────────┤
         │   Unit tests                 │  ~60% of suite — state machine, guard conditions, RBAC logic
         └──────────────────────────────┘
```

---

## 3. Unit Tests

**Framework:** `pytest` + `pytest-asyncio`
**Coverage tool:** `pytest-cov`
**Assertion style:** Standard pytest assertions (no FluentAssertions equivalent in Python — use plain `assert` with descriptive messages)
**Mock library:** `unittest.mock` + `respx` for HTTP

### State Machine — `ECNWorkflowMachine`

Every transition in the state table (Section 2 of `ai/memory/06-ecn-requirements.md`) must have at least one test:

```
test_draft_submit_valid                    DRAFT → ENGINEERING_REVIEW (all guards pass) [ADR-009]
test_draft_submit_no_items                 submit guard: 0 items → ValueError
test_draft_submit_missing_effectivity      submit guard: item missing effectivity_type → ValueError
test_engineering_approve                   ENGINEERING_REVIEW → MANAGEMENT_REVIEW
test_management_parallel_all_approve       All required roles approve → DC_APPROVED (automatic) [ADR-009]
test_management_parallel_conditional_skip  PM skipped when routing_changes=FALSE
test_management_any_rejection_wins         One rejection → REJECTED regardless of others approved
test_dc_approved_dc_approve                DC_APPROVED → APPROVED (dc_approve, actor_role=DC) [ADR-009]
test_dc_approved_customer_gate             dc_approve blocked if requires_customer_approval and no customer_approved_at
test_approved_celery_complete              APPROVED → IMPLEMENTED (outbox all completed)
test_approved_celery_fail_stays_approved   APPROVED stays on MI failure
test_implemented_auto_close               IMPLEMENTED → CLOSED (Celery auto_close, no DC) [ADR-009]
test_rejected_resubmit_restart             REJECTED → ENGINEERING_REVIEW, all steps reset [ADR-009]
test_rejected_resubmit_proceed             REJECTED → prior stage, only rejecting step reset
test_self_approval_blocked                 Originator cannot approve own ECN → 403
test_on_hold_resume_restores_status        ON_HOLD → prior status from pre_hold_status field
test_archived_is_flag_not_transition       is_archived=TRUE on CLOSED; no status change
```

### RBAC

```
test_jwt_groups_do_not_grant_per_ecn_role  JWT group alone insufficient for approve endpoint
test_per_ecn_role_required_for_approval    ecn_role_assignments checked on every approve
test_rbac_insert_only_role_assignments     UPDATE on ecn_role_assignments raises permission denied
test_admin_cannot_approve                  AD role has no approval authority
```

### Audit Chain

```
test_transition_creates_history_record     ecn_transition_history row created on every transition
test_sha256_chain_unbroken                 sha256_prev matches previous record's sha256_self
test_audit_record_not_updatable            UPDATE on ecn_transition_history raises permission denied
test_audit_record_not_deletable            DELETE on ecn_transition_history raises permission denied
test_movex_payload_stored_before_write     payload in history record created before Celery task fires
```

### Outbox / Celery

```
test_outbox_entry_created_at_approved      movex_outbox row created when ECN → APPROVED
test_outbox_idempotency_key_unique         duplicate key raises integrity error
test_outbox_retry_exponential_backoff      30s → 5min → 30min backoff on failure
test_outbox_dc_alerted_at_attempt_3        email dispatched when attempt_count reaches 3
test_outbox_abandoned_at_attempt_10        state = ABANDONED; EM notified
test_celery_acks_late                      task not acked until completion (no message loss on crash)
```

---

## 4. Integration Tests

Run against `oskar-test-db` (PostgreSQL 16). ERP adapter mocked at HTTP boundary.

**Fixtures:** `pytest-postgresql` or plain Docker Compose test profile. Test DB is created fresh per test session; migrations applied via Alembic before tests run.

### Full ECN Lifecycle

```
test_full_ecn_lifecycle_simple_ecn
  Create ECN → submit → DC accept → SE approve → EM+QM approve → APPROVED →
  Celery mock confirms outbox → IMPLEMENTED → DC close → CLOSED
  Assert: status at each stage; audit chain unbroken; correct notifications queued

test_full_ecn_lifecycle_rejection_restart
  Create ECN → submit → DC accept → SE approve → QM rejects →
  REJECTED → originator resubmits (restart) → all steps reset → repeat approval →
  Assert: revision incremented; all prior approval steps reset

test_full_ecn_lifecycle_proceed_path
  QM rejects → originator resubmits (proceed) →
  Assert: only QM step reset; EM approval preserved
```

### API Endpoint Tests (FastAPI TestClient)

```
test_create_ecn_returns_201
test_list_ecn_filters_by_status
test_get_ecn_returns_full_detail
test_patch_ecn_draft_only
test_patch_ecn_submitted_returns_403
test_approve_wrong_role_returns_403
test_approve_self_returns_403
test_movex_errors_visible_to_dc
test_movex_retry_triggers_celery_task
```

### Database Integrity

```
test_ecn_items_cascade_delete_on_ecn_cancel
test_uuid_pk_on_all_tables
test_cono_stored_not_used_as_pk
test_rls_app_user_cannot_delete_audit_chain
```

---

## 5. Performance Benchmarks

Defined in `ai/memory/07-compliance-requirements.md` (PQ tests). Summary for code-level reference:

| Endpoint | Max response time | Condition |
|---------|-----------------|----------|
| `GET /api/v1/ecn/` | 500ms | 500 ECNs in DB |
| `POST /api/v1/ecn/{id}/approve` | 200ms | Single user |
| `POST /api/v1/auth/login` | 1s | LDAP bind included |
| Celery: 50 outbox entries | 10min total | Sequential MI mock |

Performance tests run in CI on merge to `main` only (not on every PR — too slow).

---

## 6. Coverage Requirements

| Module | Minimum coverage |
|--------|----------------|
| `src/workflow/state_machine.py` | 95% |
| `src/services/ecn_service.py` | 85% |
| `src/services/audit_service.py` | 90% |
| `src/adapters/erp/movex.py` | 80% |
| `src/routers/ecn.py` | 80% |
| Overall project | 80% |

Coverage gate enforced in CI via `pytest --cov=src --cov-fail-under=80`.

---

## 7. CI Pipeline (Sprint 1)

```
on: push, pull_request

jobs:
  test:
    services:
      oskar-test-db:   postgres:16

    steps:
      - gitleaks scan           (secret detection — blocks on any finding)
      - pip-audit               (CVE check — blocks on CRITICAL)
      - npm audit               (frontend CVE check — blocks on CRITICAL)
      - pytest (unit + integration, --cov, --cov-fail-under=80)
      - mypy src/               (type checking)
```

---

## 8. Test Data Strategy

- **No real Movex data in tests** — all item numbers, ECN IDs, and user data are synthetic
- **Factories not fixtures** for complex objects — use `factory_boy` or plain Python factory functions
- **Seed data for integration tests:** Minimal `system_role_users` rows (DC, EM, QM, SE) loaded by Alembic seed migration
- **Sensitive test patterns:** Tests that verify rejection of secrets in logs must use synthetic secret patterns (`sk-test-XXXX`), not real-looking credentials

---

## 9. IQ/OQ/PQ Test Execution

IQ/OQ/PQ tests (defined in `ai/memory/07-compliance-requirements.md`) are **manual** and run in Sprint 4 against the production-identical staging environment. They are not automated — they require human observation and sign-off.

**Procedure:**
1. Lead Engineer runs each test case sequentially on staging
2. For each test: record actual result, pass/fail, date, and executor name in the IQ/OQ/PQ Report document
3. Any failure: log as defect, fix, re-run affected test cases
4. Karen signs completed report before go-live approval
