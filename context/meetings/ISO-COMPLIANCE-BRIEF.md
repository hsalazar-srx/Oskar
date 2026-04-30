# OSKAR — ISO 13485 Compliance Brief
**For:** Karen (IT GM) — to frame the compliance posture of the platform
**Date:** 2026-04-29

> Use this in Segment 2 if Karen raises compliance or audit questions. Not intended as a full slide — it's a reference document.

---

## Why ISO 13485 Compliance Is Engineered In, Not Bolted On

OSKAR was designed from the ground up for ISO 13485 compliance. These are not features added after the fact — they are load-bearing architectural decisions that cannot be removed.

---

## What Stargile Fails (Active Compliance Risks Today)

| Risk | ISO 13485 Clause | Stargile Behaviour | Severity |
|------|-----------------|-------------------|---------|
| BOM duplicate sequence silent corruption | §7.5.8 (Process control) | Two BOM lines with the same sequence number are silently merged — wrong components could be ordered and used in production | 🔴 Critical |
| No change history | §4.2.5 (Document control) | "View Items" shows current Movex state only — cannot reconstruct what was approved at any point in time | 🔴 Critical |
| Concurrent ECN conflict | §4.1.2 (General requirements) | Two ECNs on the same PN can be approved simultaneously; only one writes to Movex — the other's changes are lost without any notification | 🔴 Critical |
| Alternative MPN without customer approval trail | §7.4.2 (Purchasing control) + §7.3.9 (Design change control) | Consolidation-category MPNs (substitutions for customer-specified parts) have no documented approval pathway | 🟠 High |
| Transmittal not tracked electronically | §7.3.6 (Design output) | Gerbers and drawings sent to suppliers with no electronic record of what was sent, to whom, when | 🟠 High |
| No training acknowledgement on ECN close | §6.2 (Human resources / competence) | No mechanism to confirm affected personnel were notified of changes and acknowledged training | 🟠 High |

---

## What OSKAR Provides (As Designed)

| ISO 13485 Requirement | OSKAR Implementation |
|----------------------|---------------------|
| §4.2.5 — Document change control and change history | SHA-256 immutable audit chain (`ecn_transition_history`) — every state transition is hash-chained; DELETE is prohibited at database level via Row-Level Security |
| §4.2.4 — Record retention | 7-year retention enforced; no DELETE policy on audit tables; RLS applied in `0003_rls_policies` migration |
| §6.2 — Training records | `ecn_training_acknowledgements` table: on ECN CLOSED, all affected personnel receive acknowledgement work items; DC and QM can view outstanding acknowledgements |
| §7.3.9 — Design change control (customer approval) | `customer_approval_reference` + `customer_approved_at` fields; APPROVED→IMPLEMENTED gate blocked until customer approval is recorded when `requires_customer_approval=TRUE` |
| §7.5.8 — Process control (BOM integrity) | Server-side duplicate sequence validation at submission — rejects before any write to Movex |
| Controlled process (no autonomous changes) | Human-in-the-loop is non-negotiable: no ECN may write to Movex without explicit human approval at MANAGEMENT_REVIEW. AI assists; humans decide. |
| Audit trail integrity | SHA-256 chain: `sha256_self` = hash of all transition fields; `sha256_prev` = hash of previous record. Chain integrity verifiable by SQL query. |
| Self-approval prevention | Originator cannot approve any stage of their own ECN regardless of AD group membership — enforced at API layer on every approval endpoint |

---

## What Is Still Open (Honest Assessment)

| Gap | Clause | Plan |
|-----|--------|------|
| Concurrent ECN conflict check at SUBMIT | §4.1.2 | Sprint 2 — query open ECNs on same PN at SUBMITTED→DC_REVIEW; surface warning to originator |
| Point-in-time MPN/BOM snapshot at APPROVED | §7.3.7 | Confirm `movex_payload JSONB` on `ecn_transition_history` is populated at APPROVED status in outbox worker |
| Transmittal electronic tracking | §7.3.6 | Out of OSKAR v1 scope — requires DMR/document system decision |
| Alternative MPN customer approval gate | §7.4.2 | `ecn_step_conditions` rule needed: `requires_customer_approval=TRUE` triggered by MPN category — Sprint 3 |

---

## IQ / OQ / PQ Test Evidence (What We'll Produce)

These are the test cases that become ISO 13485 validation evidence:

### IQ Evidence (Installation Qualification)
| Test | Pass Criterion |
|------|---------------|
| SHA-256 audit chain table deployed | `ecn_transition_history` exists with RLS; `oskar_app` cannot DELETE any row |
| `ecn_training_acknowledgements` table present | Table exists with FK to `ecn_instances` |
| LDAPS TLS configured | `CERT_REQUIRED` enforced; CA from Docker secret; `_make_server()` test passes |
| Secrets in Docker secrets, not environment variables | No credentials in `docker inspect` output |

### OQ Evidence (Operational Qualification)
| Test | Pass Criterion |
|------|---------------|
| BOM duplicate sequence rejected | POST with duplicate `operation_number` returns 422 with descriptive error |
| Self-approval blocked with audit entry | Originator `/approve` returns 403; `ecn_transition_history` records attempted violation |
| No-DELETE on audit tables | `oskar_app` DELETE on `ecn_transition_history` raises permission denied |
| Customer approval gate blocks | `requires_customer_approval=TRUE` + null `customer_approved_at` → APPROVED→IMPLEMENTED returns 409 |
| Concurrent ECN conflict warning | Two ECNs on same PN; second submit returns conflict warning |
| Training ack created on CLOSED | ECN transitions to CLOSED; `ecn_training_acknowledgements` rows created for all required roles |

### PQ Evidence (Performance Qualification)
| Test | Pass Criterion |
|------|---------------|
| End-to-end ECN: DRAFT to CLOSED with Movex write | All MI calls succeed; audit chain intact; training acks issued |
| ECN cycle time vs Stargile baseline | Measurable reduction vs. current average |
| BOM upload error rate vs Stargile baseline | Reduction in rework due to Movex write failures |

---

## Plain Language Summary for Karen

> "OSKAR is built so that an ISO auditor could trace any engineering decision — from the moment an engineer proposed a BOM change, through every approval, to the exact Movex write that committed it — without needing to ask anyone. The audit chain cannot be edited or deleted. Stargile has none of this. Today, if an auditor asks 'who approved this change and when?' — the answer is an email thread. After OSKAR, the answer is a database query that takes three seconds."
