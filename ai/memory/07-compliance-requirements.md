# OSKAR — ISO 13485 Compliance and IQ/OQ/PQ Framework

> **PROVIDER-AGNOSTIC — Non-Negotiable #12**
> No tool-specific syntax. Readable by any LLM tool or none.

**Version:** 1.2
**Date:** 2026-05-04
**Phase:** Phase 1 Track C deliverable
**Status:** Draft — pending UAT sign-off

**QMS Document Ownership**

| Role | Name | Scope |
|------|------|-------|
| Author (IQ) | Manal | Installation Qualification |
| Author (OQ/PQ) | Mihai | Operational & Performance Qualification |
| Approver | Lead Engineer (hsalazar) | All protocols |
| Quality Manager | Divya | Melbourne site docs |

**Standards covered:** ISO 13485:2016 (primary — both sites), ISO 9001:2015 (both sites), ISO 14001:2015 (both sites), IATF 16949:2016 (JB/Malaysia only), ISO 27005/DISP
**Scope:** OSKAR Iteration 1 — ECN module validation only

---

## 1. Why IQ/OQ/PQ Applies

OSKAR processes Engineering Change Notices that directly affect medical device BOMs and manufacturing processes. Scanfil APAC holds ISO 13485:2016 certification. Any software system that controls or records product changes for medical device clients must be validated per ISO 13485 §7.5.6 (software validation) and §4.1.6 (software used in quality management).

**Consequence of skipping:** Audit finding at next ISO 13485 surveillance. Risk to certification.

---

## 2. Validation Protocol Structure

### IQ — Installation Qualification

**Protocol author:** Manal | **Approver:** Lead Engineer (hsalazar) | **QM:** Divya

Verifies that OSKAR is installed correctly and that the environment matches the specification.

| Test ID | Test description | Pass criterion | Owner |
|---------|-----------------|---------------|-------|
| IQ-01 | Docker Compose stack starts all services (oskar-app, oskar-db, oskar-worker, oskar-frontend) — 4 containers; no `oskar-redis` (ADR-007) | All containers healthy within 60s | Manal |
| IQ-02 | PostgreSQL 16 — correct version confirmed | `SELECT version()` returns `PostgreSQL 16.x` | Manal |
| IQ-03 | Celery broker tables present in PostgreSQL — `kombu_message`, `kombu_queue`, `celery_taskmeta` (ADR-007: Redis eliminated) | `SELECT tablename FROM pg_tables WHERE tablename LIKE 'kombu%'` returns rows | Manal |
| IQ-04 | OSKAR API responds to health endpoint | `GET /api/v1/health` returns `200 OK` | Lead Engineer |
| IQ-05 | LDAPS connection to AD on port 636 confirmed | Auth endpoint returns JWT on valid credentials | Lead Engineer + Devian |
| IQ-06 | Harbor registry reachable from OSKAR VM | `docker pull apac-plm-ops.srxglobal.local/oskar-app:latest` succeeds | Manal |
| IQ-07 | IIS reverse proxy routes `/api/v1/` to oskar-app correctly | External HTTPS request reaches FastAPI | Manal |
| IQ-08 | Backup: pg_dump runs and produces non-zero archive | Cron job runs; output file > 0 bytes | Manal |
| IQ-09 | `.env` file absent from Docker image layers | `docker history oskar-app:latest` contains no secret values | Lead Engineer |
| IQ-10 | Non-root user confirmed inside container | `docker exec oskar-app whoami` returns non-root user | Lead Engineer |

### OQ — Operational Qualification

**Protocol author:** Mihai | **Approver:** Lead Engineer (hsalazar) | **QM:** Divya

Verifies that OSKAR functions correctly according to its specification under normal and boundary conditions.

#### Authentication and RBAC

| Test ID | Test description | Pass criterion |
|---------|-----------------|---------------|
| OQ-01 | Valid AD credentials return JWT access token (60min) + HttpOnly refresh cookie (8h) | Response contains `access_token`; `Set-Cookie` header with `HttpOnly; Secure; SameSite=Strict` |
| OQ-02 | Invalid credentials return 401 | No token issued; no stack trace in response body |
| OQ-03 | Expired access token rejected; refresh cookie issues new token | 401 on expired token; 200 on `/auth/refresh` with valid cookie |
| OQ-04 | User not in `OSKAR-Engineers` AD group cannot log in | 403 Forbidden |
| OQ-05 | User in `OSKAR-Engineers` cannot access approver endpoints | 403 on `POST /api/v1/ecn/{id}/approve` |
| OQ-06 | Self-approval blocked | Originator of ECN cannot approve any stage — 403 returned |
| OQ-07 | JTI blocklist — logout invalidates token immediately | Logged-out token returns 401 on subsequent request |

#### ECN Workflow

| Test ID | Test description | Pass criterion |
|---------|-----------------|---------------|
| OQ-10 | Create ECN in DRAFT status | `POST /api/v1/ecn/` returns `201 Created`; status = `DRAFT` |
| OQ-11 | Submit ECN — guard: ≥1 item required | `POST /submit` with 0 items returns `422 Unprocessable` |
| OQ-12 | Submit ECN — guard: `effectivity_type` required on all items | `POST /submit` with item missing `effectivity_type` returns `422` |
| OQ-13 | Valid submit transitions DRAFT → ENGINEERING_REVIEW | Status in DB = `ENGINEERING_REVIEW`; SE/CE receives notification email (ADR-009 — no DC gate at submission) |
| OQ-14 | ~~DC accept (SUBMITTED→DC_REVIEW)~~ — **Removed by ADR-009** | Integers 10 and 20 tombstoned; trigger `accept` no longer exists |
| OQ-15 | DC reject transitions to REJECTED with mandatory reason | Status = `REJECTED`; rejection record created; originator notified |
| OQ-16 | ~~DC pass (DC_REVIEW→ENGINEERING_REVIEW)~~ — **Removed by ADR-009** | Replaced by OQ-16a |
| OQ-16a | DC approves at DC_APPROVED → APPROVED (`dc_approve`) | Status = `APPROVED`; `customer_approved_at` gate enforced if flag set; movex_outbox created |
| OQ-17 | SE approve triggers parallel block — all required roles notified simultaneously | Status = `MANAGEMENT_REVIEW`; all required role members receive email in same Celery batch |
| OQ-18 | Conditional role (PM) not notified when condition is FALSE | PM has `skipped=TRUE` in `ecn_approval_steps`; no email sent to PM |
| OQ-19 | All required parallel approvals → APPROVED | Status = `APPROVED`; outbox entries created |
| OQ-20 | Single rejection at MANAGEMENT_REVIEW → REJECTED | Even if others already approved; status = `REJECTED` immediately |
| OQ-21 | Proceed-path resubmit preserves other approvals | Only rejecting role's step reset; others retain `approved` |
| OQ-22 | Restart-path resubmit resets all steps | All `ecn_approval_steps` set to `pending`; ECN revision incremented |

#### Movex Write and Outbox

| Test ID | Test description | Pass criterion |
|---------|-----------------|---------------|
| OQ-30 | Celery outbox processes `AddProduct` MI call on APPROVED ECN with new item | `PDS001MI.AddProduct` called; outbox entry = `completed`; ECN → IMPLEMENTED |
| OQ-31 | Movex MI failure retries with exponential backoff | Retry at 30s, 5min, 30min; DC alerted at attempt 3 |
| OQ-32 | Outbox entry has idempotency key — duplicate call not made on retry | Second attempt with same `idempotency_key` is a no-op |
| OQ-33 | ECN stays at APPROVED on MI failure (does not regress) | Status = `APPROVED`; `ecn_movex_errors` record created |
| OQ-34 | MMS025MI.AddAlias called for each MPN on new items | One call per MPN; `alias_written=TRUE` after all succeed |
| OQ-35 | BOM concurrency detection blocks write when Movex BOM has changed | Outbox entry = `failed`; diff surface to DC panel |

#### Audit Chain

| Test ID | Test description | Pass criterion |
|---------|-----------------|---------------|
| OQ-40 | Every ECN status transition creates an `ecn_transition_history` record | Row exists with actor, timestamp, previous/new status, SHA-256 hash |
| OQ-41 | SHA-256 chain is unbroken — each record's `sha256_prev` matches previous record's `sha256_self` | Validation query returns no broken links |
| OQ-42 | Audit records cannot be updated or deleted by application user | `UPDATE` / `DELETE` on `ecn_transition_history` returns permission denied |
| OQ-43 | Movex payload stored in audit record before write attempt | `ecn_transition_history.movex_payload` populated at APPROVED transition |

### PQ — Performance Qualification

**Protocol author:** Mihai | **Approver:** Lead Engineer (hsalazar) | **QM:** Divya

Verifies that OSKAR performs correctly under production-representative load.

| Test ID | Test description | Pass criterion |
|---------|-----------------|---------------|
| PQ-01 | 10 concurrent users submit ECNs simultaneously | All succeed within 5s; no deadlocks; DB consistent |
| PQ-02 | ECN list endpoint with 500 ECNs in DB | `GET /api/v1/ecn/` responds in < 500ms |
| PQ-03 | Celery processes 50 outbox entries in sequence | All complete within 10min; no entries lost |
| PQ-04 | SHA-256 chain validation across 1,000 records | Completes in < 30s |
| PQ-05 | 30-day production operation without data loss | Defined by hypercare period; monitored by Lead Engineer |

---

## 3. Sign-off Chain

| Gate | Document | Author | Approver | Quality Manager |
|------|---------|--------|----------|----------------|
| IQ complete | IQ Report | Manal | Lead Engineer (hsalazar) | Divya |
| OQ complete | OQ Report | Mihai | Lead Engineer (hsalazar) | Divya |
| PQ complete | PQ Report | Mihai | Lead Engineer (hsalazar) | Divya |
| Full validation package | SVP (Software Validation Package) | Lead Engineer | Karen | Christian Kesten (awareness) |

**QMS approval chain confirmed (2026-04-14):** Divya is the Quality Manager for Melbourne-site documents. Formal/approved QMS docs are held in SharePoint. IQ/OQ/PQ execution may proceed once staging environment is available (Sprint 4).

---

## 4. Compliance Clauses — ECN Module Mapping

| ISO 13485 clause | Requirement | OSKAR implementation |
|-----------------|------------|---------------------|
| §4.1.6 | Software used in QMS must be validated | IQ/OQ/PQ per iteration (this document) |
| §4.2.5 | Change control — define effectivity | `effectivity_type` + `effectivity_from` mandatory fields on ECNItem |
| §7.3.9 | Design change control — customer/regulatory approval | `requires_customer_approval` flag; blocks APPROVED→IMPLEMENTED |
| §7.5.6 | Production process validation | OQ-30 through OQ-35 cover Movex write validation |
| §6.2 | Training records for changes | Training acknowledgement trigger on CLOSED (Sprint 2+) |
| §8.2.6 | Complaint and corrective action traceability | SHA-256 audit chain as immutable evidence |
| §8.3 | Control of non-conforming product | ECN rejection flow with mandatory reason + restart/proceed paths |

---

## 5. Compliance Mapping — Other Standards

| Standard | Site | Clause | OSKAR contribution |
|---------|------|--------|-------------------|
| ISO 9001:2015 / BS EN ISO 9001:2015 | Both | §8.5.6 | ECN workflow as documented change control; audit trail as corrective action evidence |
| IATF 16949:2016 | JB (MY) only | §10.2.3 | ECN traceability for automotive product changes; BOM version control (Iteration 2) |
| ISO 27005 / DISP | Both | General | Immutable audit log; RBAC; LDAPS/HTTPS; no secrets in logs; JWT session management |

> **Site note:** OSKAR is deployed at the JB (Malaysia) site. JB holds BS EN ISO designations; Australian site holds plain ISO designations. See `c:/Projects/Knowledge-Management/vault/compliance/scanfil-apac-certifications.md` for full details.

---

## 6. Deferred Compliance Items (Sprint 2+)

| Item | Clause | Sprint |
|------|--------|-------|
| Training record acknowledgements | ISO 13485 §6.2 | Sprint 2 |
| Customer approval gate enforcement | ISO 13485 §7.3.9 | Sprint 2 |
| Emergency ECN QM mandatory path | ISO 13485 — no bypass | Sprint 2 |
| `ecn_circuit_refs` table (PCB traceability) | ISO 13485 §7.5.6 | Phase 2 |
| IFS adapter validation | ISO 13485 §4.1.6 | Iteration 3 (IFS out of scope v1) |

---

## 7. Document Control

This document is draft until UAT validation is complete. After UAT sign-off:

1. Lead Engineer (hsalazar) updates status to `Approved`
2. Divya (Quality Manager) signs the IQ/OQ/PQ reports as QM approver
3. Karen signs as final validation authority
4. Document is archived with the SVP in the OSKAR SharePoint project folder
5. Version incremented (v1.x for minor changes; v2.0 for scope changes)

**Formal/approved QMS documents** are held in the Scanfil APAC SharePoint. This file is the working draft and OSKAR AI context copy — it mirrors the approved document structure but is not the QMS record of truth.
