# Oskar — Workflow Scenario Matrix (robustness plan §5)

**Created:** 2026-08-17
**Owner:** Lead Engineer (hector.salazar@srxglobal.com)
**Source:** `docs/robustness-plan-uat-readiness.md` §5
**Status:** scoped from source (verified, not assumed — see "Evidence" per row)

## Why this exists

The suite is strong on each area *individually* (ECN state machine: 47 tests;
routing/MPN/BOM: adapter + service + router + integration tests each). What is
not proven is realistic **combinations** — the way Stargile/PLM users actually
worked. Coverage of each dimension separately does not imply coverage of their
interaction.

This document turns §5's first-pass list into a scoped matrix with explicit
pass/fail criteria, so the tests can be written against a definition of done
rather than invented one at a time.

---

## Corrections to §5's assumptions (verified against source 2026-08-17)

§5's bullets were written from memory of the design. Two are wrong in ways that
change what the tests must assert. Per LL-003, recording the evidence:

| §5 claim | Reality | Evidence |
|---|---|---|
| "routing + BOM + MPN all fire together at `dc_approve`" | **Only routing and BOM fire at `dc_approve`.** The MPN-master hook (`_upsert_ecn_mpns_to_item_master`) and alias outbox fire at **`movex_write_complete`** — a different, later transition. A test asserting all three at `dc_approve` would assert something false. | `workflow.py:151-152` (dc_approve) vs `workflow.py:155-157` (movex_write_complete) |
| "with correct `depends_on` ordering across all three" | **There is no cross-area `depends_on`.** `_queue_routing_operations_outbox` inserts rows with **no `depends_on` column at all**. Ordering exists only *within* a BOM CHANGE pair (delete→add). Routing and BOM writes for one ECN dispatch fully concurrently. | `workflow.py:900-914` — INSERT column list omits `depends_on`; compare `workflow.py:984-991` which includes it |

**Consequence:** §5's third bullet ("does M3-side write ordering matter") is not
a hypothetical to confirm later — it is a live, unanswered question about
behaviour that *already ships*. It is promoted to S-3 below and blocks nothing
else, but should be answered before UAT rather than after.

---

## Scenario matrix

Priority: **P1** = write before UAT · **P2** = write if time allows · **P3** = defer

| ID | Scenario | Priority | Why it matters | Pass criteria |
|---|---|---|---|---|
| **S-1** | ECN with routing changes + BOM changes in one submission reaches `dc_approve` | P1 | The single junction where two independent queueing paths run in one transaction (`workflow.py:151-152`). Tested individually today; never together. A failure here means an approved ECN silently writes only half its changes. | Both `_queue_routing_operations_outbox` and `_queue_bom_changes_outbox` produce their rows in one transition; total outbox count = routing ops + BOM rows (CHANGE counting as 2); every row has correct `ecn_id`/`idempotency_key`; no row is dropped by the `ON CONFLICT DO NOTHING`. |
| **S-2** | Same ECN, but MPNs added too — verify MPN timing | P1 | Directly corrects §5's wrong assumption. Must prove MPNs are *not* queued at `dc_approve` and *are* handled at `movex_write_complete`. | At `dc_approve`: zero `MMS025MI.AddAlias` rows. After `movex_write_complete`: alias rows exist and `item_mpns` is populated. |
| **S-3** | Routing-vs-BOM M3 write ordering — **ANSWERED 2026-08-17: ordering DOES matter** | **P0 — real defect** | M3 rejects a BOM component whose `OPNO` has no existing routing operation: `"Operation number 777 does not exist"`. Oskar queues routing and BOM writes with **no ordering guarantee** (`workflow.py:900-914` inserts routing rows without `depends_on`), so an ECN that adds a routing operation *and* a BOM line referencing it can dispatch them in either order. Losing that race means the BOM write fails, retries 10×, abandons, and alerts EM — a spurious failure caused purely by dispatch order. See "S-3 evidence" below. | A BOM outbox row whose `operation_number` matches a routing-op row created by the same ECN must have `depends_on` set to that routing row, so the component write is gated behind its operation. |
| **S-4** | ECN rejected at `MANAGEMENT_REVIEW`, resubmitted with *different* BOM changes | P1 | The concurrency gate (I2-6) diffs live BOM against the snapshot captured at submit (`workflow.py:538-539`). If resubmission does not refresh that snapshot, the gate compares against stale data — either blocking a valid approval or, worse, passing a genuinely conflicting one. | After resubmission, `_check_bom_concurrency` evaluates against the **resubmitted** content; a conflict on a newly-added key blocks with 409; a resolved conflict no longer blocks. |
| **S-5** | ECN placed `ON_HOLD` mid-workflow with BOM changes staged, then resumed | P1 | Hold/resume is tested only at machine + router level (`test_machine.py`, `test_ecn.py`) — never with staged `ecn_bom_changes` rows. A hold that drops or duplicates staged rows corrupts the ECN silently; `pre_hold_status` restore is the risky part. | Staged `ecn_bom_changes` rows are byte-identical before hold and after resume (same count, same ids); `pre_hold_status` restores the exact prior status; a subsequent `dc_approve` queues exactly the same outbox rows it would have without the hold. |
| **S-6** | DELETE-type BOM change followed by CHANGE-type on the *same* component in one ECN | P2 | A real Stargile pattern (DC clarifying an edit into explicit DELETE + re-ADD). Risk is a false `depends_on` chain linking two independent close/reopen pairs, creating a spurious ordering conflict or a dependency cycle. | Each pair's `depends_on` points only within its own pair; no row depends on a row from the other pair; both pairs complete independently; no cycle. |
| **S-7** | Two ECNs touching the same parent item concurrently (one BOM, one routing) | P2 | Not a DB-level race (single Postgres, normal isolation) but an M3-side one. Overlaps S-3; only meaningful once S-3 is answered. | Both ECNs' outbox rows dispatch without deadlock; final M3 state contains both sets of changes. Blocked on S-3. |
| **S-8** | Zero-write ECN (no routing, no BOM, no MPN) at `dc_approve` | P2 | `workflow.py:168-175` has a special path: with no outbox rows, `movex_write_complete` fires immediately, since nothing else would ever trigger it. An easy path to regress, and the failure is an ECN stuck at APPROVED forever. | ECN advances to IMPLEMENTED without any outbox row; the immediate-fire path is exercised. |

---

---

## S-3 evidence (live-verified 2026-08-17, CONO=300, item LFAM050001)

Answered empirically because it could not be answered from source: `PDS002MI`'s
`RCOM05` (AddComponent) only marshals fields and delegates to `PDS002BE`
(`analysis/PDS002MI.txt:493` — `CALL 'PDS002BE'`), returning whatever `DCRTCD`/
`DCMSID` that program sets. `PDS002BE`'s source is not available locally, so the
validation rule had to be observed rather than read.

A controlled A/B against real M3, one variable changed:

| # | Call | Result |
|---|---|---|
| 1 | `AddComponent` MSEQ=777, **OPNO=777** (no such operation) | ❌ `{"success": false, "error": "Operation number 777 does not exist"}` |
| 2 | `AddOperation` OPNO=777 | ✅ `MSID: "000"` |
| 3 | **The identical call from step 1**, retried | ✅ `MSID: "000"` |

The same payload fails before the operation exists and succeeds after. This is a
hard referential constraint enforced by M3, consistent with `MPDMAT`'s key
including `OPNO` and `PMOPNO` being documented as the "linked operation"
(`ai/memory/02-movex-erp-authority.md:38`).

All probe data removed; baseline re-verified via
`scripts/movex_smoke_test.py --read-only` (11 open lines, OPNO 777 absent).

### Why this is a live defect, not a hypothetical

`_queue_bom_changes_outbox` takes each BOM change's own `operation_number`
(`workflow.py:1035`) with no reference to whether that operation is being created
by the same ECN. `_queue_routing_operations_outbox` inserts its rows with no
`depends_on` (`workflow.py:900-914`). Both sets are dispatched together at
`dc_approve`, so with `--concurrency=2` the component write can reach M3 first.

Consequence when the race is lost: the BOM write fails with a *legitimate* M3
error, consumes all 10 retry attempts (~1 hour of backoff), abandons, and pages
the EM — for an ECN that was entirely valid. The DC/EM see a Movex failure with
no obvious cause, which is exactly the trust-destroying UAT experience §1 of the
robustness plan set out to prevent.

**Not yet observed in production** — it needs an ECN that adds a routing
operation and a BOM line referencing that new operation in one submission. That
combination is plausible for a new-process ECN but is not the common case, which
is likely why it has not surfaced.

### End-to-end confirmation (2026-08-18)

`scripts/e2e_s3_ordering_proof.py` drives the whole chain with nothing mocked:
real ECN → real workflow transitions → real outbox rows carrying the S-3
`depends_on` → real Celery worker (separate process, Postgres broker) → real
movex-rest-api → real M3 (CONO=300) → read-back from M3.

Result: **PASS**. Both writes reached `completed` on **attempt 1** — no retry,
no ordering error — and both the routing operation and the BOM component were
confirmed present in M3 by a fresh read. Before the fix this combination was a
coin flip that, when lost, burned all 10 retries and paged the EM.

### Second defect found by the E2E run: `AddOperation` was missing required `OPDS`

The end-to-end run surfaced a bug that no unit test could have caught, because
a unit test *enforced the bug*.

`MovexRestAdapter.add_routing_operation` never sent `OPDS` (operation
description). Its docstring asserted "this transaction has no description field
(PLGR/PITI only)", `_queue_routing_operations_outbox` therefore dropped
`operation_description`, and
`test_payload_does_not_include_invalid_opds_field` actively asserted OPDS must
NOT be present. Three layers agreeing with each other — and all three wrong.

Live-verified 2026-08-18, CONO=300:

| Payload | Result |
|---|---|
| `{CONO, FACI, PRNO, STRT, OPNO, PLGR, PITI}` (what Oskar sent) | ❌ `"Operation description must be entered"` |
| identical **+ `OPDS`** | ✅ `MSID "000"` |

`transactions/PDS002MI.json` marks `OPDS` `required: false`, which is the
likely origin of the wrong belief — the config's `required` flags do **not**
reflect what M3 enforces (the same trap already documented for `FDAT` on
`Delete`). Treat that file as a field *catalogue*, never as a validation spec.

**Impact:** every `AddOperation` Oskar dispatched would have failed, retried
10×, abandoned, and paged the EM. Any ECN with a routing change was affected —
a far broader blast radius than S-3's new-operation-only case. It survived
because routing writes had never been exercised end-to-end against real M3.

Fixed in `add_routing_operation` (sends `OPDS`, falling back to
`"Operation {n}"` when the row has no description, since M3 rejects a blank)
and in `_queue_routing_operations_outbox` (now selects and forwards
`operation_description`). The inverted test was replaced with two that assert
the live-verified behaviour.

**This is an LL-003 case in its purest form:** an unverified claim about a
legacy/external system, written into a docstring, propagated into production
code, and then *locked in* by a test asserting the same unverified belief.

### Caution: `LstOperation` returns unstable results — do not use it to assert state

Discovered while verifying cleanup for the run above. Three identical
`LstOperation` calls, seconds apart, on the same item returned:

| Call | raw records | distinct OPNOs | spurious `OPNO=0`? |
|---|---|---|---|
| 1 | 29 | 29 | no |
| 2 | 29 | 29 | no |
| 3 | 40 | 30 | **yes** |

This is the M3 list-protocol behaviour already documented for this codebase
(`docs/movex-rest-api-bom-contract.md`: `FDAT` is a **cursor seek position, not
a filter**, and `LstOperation`/`LstComponent` share it). A separate trap sits on
`GetOperation`: querying with `FDAT=0` returned a **stale//repositioned record**
claiming OPNO 888 existed with a description that was never written
(`"Kitting & Component Prep"` vs the created `"E2E proof op"`). Re-querying with
the exact `FDAT=20260901` correctly reported it absent.

**Practical rules for anything that reads routing data (including §7 checks):**
- Never assert presence/absence of an operation from an `LstOperation` count.
- Always pass the **exact** `FDAT` to `GetOperation`; `FDAT=0` is a cursor seek
  and can return an unrelated record.
- The BOM read path (`GET /bom/{item}`, B-1) was stable across every run here
  and is the reliable basis for assertions — which is what
  `scripts/movex_smoke_test.py` uses.

### Scope note

This concerns a **new** operation created by the same ECN. The overwhelmingly
common case — a BOM line referencing an operation that already exists in M3
(e.g. all 11 baseline lines on LFAM050001 point at the pre-existing OPNO 190) —
is unaffected, since the referent is already there.

---

## Definition of done (per §6 — `validator-quality`'s remit)

A scenario is complete when:

1. It is a **DB-backed integration test** (not a mocked-cursor unit test) — these
   are combination scenarios, so the interaction *is* the thing under test.
2. It asserts on **committed state**, not on call arguments. Asserting a
   function was called is the exact failure shape LL-003 identified.
3. Its failure message states the **user-visible consequence**, not just the
   mismatch (e.g. "the ECN would sit at APPROVED forever with nobody told").
4. It is **mutation-checked**: break the behaviour deliberately, confirm the test
   fails. A test never seen to fail proves nothing.

## Sequencing

1. **S-3's question first** — it is the only item that can invalidate others'
   design (S-7 depends on it, and S-1's concurrency assumption rests on it).
   It needs a domain answer, not code.
2. **S-1, S-2, S-4, S-5** — independent, parallelisable, all P1.
3. **S-6, S-8** — P2.
4. **S-7** — blocked on S-3.

## Known constraints

- **I2-18**: DB-backed integration test files must run one at a time on
  Windows/Python 3.14 (asyncio teardown bug). These scenarios are DB-backed, so
  they inherit that. Not a blocker; affects how they are run.
- `tests/integration/conftest.py`'s `db_session` is rollback-only. For scenarios
  needing a second connection to observe state (any involving a real worker), use
  the committing fixtures in `tests/tasks/conftest.py` instead.
