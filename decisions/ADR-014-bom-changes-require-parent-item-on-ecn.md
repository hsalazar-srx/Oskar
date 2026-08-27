# ADR-014 — BOM Changes Require a Parent Item on the ECN (Divergence from Stargile)

**Status:** Accepted — Option A — **implemented and live-verified 2026-08-25** (see Implementation
record)
**Date:** 2026-08-24
**Owner:** Lead Engineer
**Raised by:** End user, during user-manual review
**Type:** Data model + workflow — ECN BOM changes
**Affects:** ADR-012 (BOM module scope), `ecn_bom_changes`, Slice E

---

## Context

Oskar requires the parent assembly to exist as an **item row on the ECN** before any BOM change
line can be created against it. This is structural, not a validation toggle:

- The route is `POST /api/v1/ecn/{ecn_id}/items/{item_id}/bom-changes`
  (`src/routers/ecn_bom.py:189`) — a BOM change is addressed *through* an item.
- Bulk upload resolves every row's `Item No` against items already on the ECN and raises
  `item not found` otherwise (`src/services/ecn/bom_changes.py:352-375`).
- `ecn_bom_changes.ecn_item_id` is `NOT NULL REFERENCES ecn_items(id) ON DELETE RESTRICT`
  (`alembic/versions/0001_initial_schema.py:403`), and the table has **no `ecn_id` column** — a
  BOM change's only path back to its ECN is through the item row.

A user raised this during user-manual review: for an ECN that changes *only* a BOM — no item
master change at all — they must add the parent as an item purely to satisfy Oskar. They asserted
Stargile did not work this way.

**They are correct.** This was verified against Stargile's source, not inferred.

---

## Evidence — how Stargile actually models this

Per the workspace standard on legacy-parity claims, everything below cites source. Verified
2026-08-24 against `c:/Projects/SuperTool/Stargile_Source_Code/`.

### 1. `ZECNBOMS` has no link to the items table

`Docs/ZECNBOMS.sql` — primary key is `(BMCONO, BMZECNID, BMZECNLN)`. `BMZECNLN` is the BOM row's
**own** line number within the ECN, not a pointer to an item row. There is no foreign key and no
item identifier of any kind. Indexes are on `BMPRNO` and `BMMTNO` — plain part numbers.

`ZECNITMN` uses the same column name `ZECNLN` for its own independent line numbering
(`Docs/ZECNITMN.sql`), so `ZECNBOMS.BMZECNLN = 5` and `ZECNITMN.NIZECNLN = 5` are unrelated rows.

A BOM change line is **self-contained**: it carries its own parent (`BMPRNO`), component
(`BMMTNO`), structure type and sequence.

### 2. Stargile wrote this exact check — and commented it out

`src/java/com/startronics/ecn/request/services/RequestECNBoMDetailValidationHelper.java`,
lines 334-339 (CREATE branch) and 495-500 (UPDATE branch):

```java
/*//Product MUST exist in ZECNITMN
    exist = RequestECNHelper.existItemInZECNITMN(processData, zecnid, prno);
    if (!exist) {
        appError = ... "Product No " + prno + ", does not exist in ECN Items table.");
        listTemp.add(appError);
    }*/
```

This is the method `UploadECNBoMs.java:118` calls. The check was deliberately disabled. Note it
was only ever inside the `if (znwbmf)` (new-BOM) branch — **it never applied to changes to
existing BOMs**, which is precisely the case the user raised.

### 3. The one surviving call site does not block

`RequestECNBoMDetailValidatePreDMProcInRule.java:57` still calls `validateProductNo`, which
retains an active `existItemInZECNITMN`. It is defused twice over:

- It sits inside `if (znwbmf)` — new BOMs only.
- The rule **returns `true` regardless** (line 74). It displays the message, then the blocking
  version is commented out at lines 68-72.

A non-blocking warning, on new BOMs only.

### 4. The BOM apply engine never reads the items table

`ProcessBOMLineRule.java` takes 17 scalar parameters and touches `BOMService`,
`ECNMovexErrorLogService` and `ZECNBOMS`. No reference to `ZECNITMN`. Its caller
`ProcessBOMHelper.java:51-76` selects from `ZECNBOMS INNER JOIN ZECNHEAD` only — the items table
is not in the query.

### 5. An ECN can have BOM lines and no item lines

`ProcessItemRule.java:45-57` gates BOM processing on items *succeeding*, not *existing*.
`ProcessItemHelper.update()` initialises `error2 = true` and returns it after a
`while(result.next())` loop — with zero item rows the loop never runs and it returns `true`.
BOM processing then proceeds normally.

### 6. What Stargile *does* enforce

The parent must exist **in Movex** — `MITMAS` and `MPDHED`
(`RequestECNBoMDetailValidationHelper.java:342-352`). A check against the **ERP**, not against the
ECN.

This is very likely the real requirement that was garbled into "must have an item on the ECN".

---

## The divergence, stated plainly

| | Stargile | Oskar |
|---|---|---|
| BOM line's parent | `BMPRNO` on the row itself | FK to an `ecn_items` row |
| Parent must be on the ECN | **No** | **Yes** |
| Parent must exist in Movex | **Yes** (`MITMAS` + `MPDHED`) | Not checked at authoring time |
| BOM-only ECN (no items) | Supported | **Not possible** |

Oskar enforces a constraint Stargile deliberately removed, and does **not** enforce the one
Stargile actually kept.

### Why this matters operationally

A BOM-only change is a normal, frequent case: an engineer revises the structure of a long-standing
assembly with no change to any item master record. Today that engineer must add a dummy item row
to satisfy the data model. That row then:

- appears on the Items tab as though the item master is changing, when it is not
- carries an `effectivity_type` that means nothing for a BOM-only change
- misleads every reviewer downstream about the scope of the change

The workaround is not merely inconvenient — it **puts misleading data in front of approvers**,
which is the opposite of what the ECN process exists to do.

---

## Options

**A. Make `item_id` nullable on `ecn_bom_changes`; carry `parent_item_number` on the row.**
Matches Stargile's model directly. Add ERP-existence validation for the parent (Stargile's real
rule) to replace the ECN-membership rule. Largest change: migration, service layer, both routes,
the upload path, and the outbox queueing in `_queue_bom_changes_outbox`.

**B. Auto-create a hidden/implicit item row when a BOM change names a parent not on the ECN.**
Preserves the current schema and outbox path. The item row exists for referential purposes but is
flagged so the UI does not present it as an item-master change. Smaller change, but introduces a
second class of item row that every consumer must understand.

**C. Keep the constraint; document it as an intentional improvement.**
Defensible only if the ECN is deliberately meant to declare every item it touches. Requires
accepting the misleading-data problem above, or solving it in the UI. **Not recommended without
first asking users whether BOM-only ECNs are common** — if they are, this is a daily friction.

---

## Implementation analysis (2026-08-24)

A design pass traced the full blast radius. Recorded here so the decision is made on facts:

**Option A is recommended.** `parent_item_number` maps directly onto Stargile's `BMPRNO`, and the
failure modes are NULL-shaped and loud.

**The migration must add `ecn_id` as well as `parent_item_number`.** Without it a NULL-item row is
an orphan with no path back to its ECN — the ownership check in `_get_bom_change`, the aggregate
list, and the outbox `WHERE` clause all lose their anchor. Backfill both from the existing FK and
make both `NOT NULL`, leaving `ecn_item_id` as a nullable convenience link.

**The outbox is the cheap part, not the hard part.** `_queue_bom_changes_outbox`
(`workflow.py:1018-1031`) takes the parent from `i.item_number` — one `COALESCE` and a `LEFT JOIN`
fixes it. Facility already comes from `ecn_instances`, not the item. `movex_outbox.ecn_item_id` is
*already* nullable, so `src/tasks/movex_outbox.py` needs no change at all.

**One trap worth naming.** The snapshot stamp-back at `workflow.py:622-628` is
`UPDATE ecn_bom_changes SET snapshot_id = ... WHERE ecn_item_id = :item_id`. If the parent-set
query is fixed but this is not, NULL-item rows get no snapshot, and `_check_bom_concurrency`
(`:692-697`) then logs a warning and *proceeds* — silently disabling the I2-6 concurrency gate for
exactly the new case. Making `parent_item_number` NOT NULL on every row removes the trap entirely.

**Option B (implicit item rows) is rejected.** It is smaller in lines changed and larger in ways to
be wrong: every consumer of `ecn_items` would need to understand the flag, and a missed one turns
an implicit row into a real item-master write to Movex. That is a data-corruption failure mode,
where A's are all NULL-handling. It also does not fix the misleading-data problem — it moves it
behind a flag.

**The Movex-existence check belongs in the router**, not the service — the ERP adapter is injected
per-route, and `routers/parts.py:407-440` is the existing precedent. De-duplicate by distinct
parent first: a 200-row upload names 1-10 distinct parents, so it is a handful of calls, not 200.

**Estimate:** ~3½-4½ days for the user's actual problem (migration, service/workflow read paths,
allowing the NULL, minimal frontend). The submit-guard change adds ½-1 day, mostly test churn.

**Sequencing note:** the submit guard must land *after* BOM-only ECNs are possible, or there will
be a window where they can be created but not submitted.

---

## Decision

**Accepted — Option A.** 2026-08-24, Lead Engineer.

BOM changes become self-contained: `ecn_bom_changes` gains `ecn_id` and `parent_item_number`, both
`NOT NULL` and backfilled from the existing FK, and `ecn_item_id` becomes nullable — a convenience
link recording "this parent also happens to be an item on this ECN", carrying no semantic load.

**The deciding input is settled.** The open question was how common BOM-only ECNs are. User
feedback confirms they are **really common** — which was also what prompted this ADR. That removes
the only argument for Option C, and makes the current constraint a daily friction rather than an
edge case.

Two supporting reasons:

- `parent_item_number` maps directly onto Stargile's `BMPRNO`, and `ecn_id` onto `BMZECNID`. This
  is a return to the legacy model, not a novel design.
- Failure modes are NULL-shaped and loud. Option B's are data-corruption-shaped and quiet.

Stargile's real rule — the parent must exist in **Movex** (`MITMAS`) — is adopted at authoring
time, replacing the ECN-membership rule Oskar invented.

### Consequences

- A BOM-only ECN becomes possible and normal: BOM change rows with no item rows at all.
- Reviewers stop seeing dummy item rows that imply an item-master change that is not happening.
- `ecn_item_id`'s FK moves to `ON DELETE SET NULL`, turning today's raw `IntegrityError` 500 on
  deleting an item with BOM changes into correct behaviour.
- Slices 1-2 are pure refactor — every row still has an item, and all ~79 existing tests must pass
  unchanged. That is the proof the rewrite is faithful before any behaviour changes in slice 3.
- The submit guard (below) must land **after** BOM-only ECNs are possible, or there will be a
  window where they can be created but not submitted.

### Still to confirm during implementation

1. **Does the ERP-existence check belong at authoring time?** Yes per this decision, but the
   `MITMAS`-only vs `MITMAS`+`MPDHED` question is a judgement call, not verified parity — Stargile
   checked both, inside its new-BOM branch. `MITMAS` only is proposed for v1.
   → **Implemented as `MITMAS` only** (via `erp.get_item`). The `MPDHED` half remains an open
   question, deliberately not adopted; revisit if a parent with no product-structure header turns
   out to be reachable in practice.
2. **`fk_outbox_item`'s `ON DELETE` clause** — confirm before writing the migration.
   → **No change needed.** `movex_outbox.ecn_item_id` was already nullable, so the outbox required
   no migration at all; `src/tasks/movex_outbox.py` is untouched, as predicted.
3. **How many existing test fixtures submit a contentless ECN** — determines the submit guard's
   real cost.
   → **Two.** `tests/workflow/test_machine.py::test_submit_allowed_with_no_items` (which asserted
   the too-loose behaviour outright and was replaced) and
   `test_snapshot_at_submit.py::test_no_bom_changes_captures_nothing` (whose own docstring
   describes a routing-only ECN but which never added any content — now adds one item, matching
   its stated scenario). Materially cheaper than the ½-1 day estimated.

---

## Implementation record (2026-08-25)

Landed in four sequenced steps, matching this ADR's own guidance.

**1. Migration `0032_bom_changes_parent_item_number.py`.** Adds `ecn_id` (NOT NULL, `ON DELETE
CASCADE`) and `parent_item_number` (NOT NULL), both backfilled from the existing `ecn_item_id`
FK before the NOT NULL is applied; `ecn_item_id` becomes nullable and its FK moves from
`ON DELETE RESTRICT` to `ON DELETE SET NULL`. The auto-generated constraint name
(`ecn_bom_changes_ecn_item_id_fkey`) was **verified against the live database** via
`pg_constraint`, not assumed from the naming convention. Upgrade → downgrade → re-upgrade
round-trips cleanly; backfill verified with zero mismatches.

**2. Read-path refactor (pure, no behaviour change).** Every query that reached an ECN by joining
`ecn_bom_changes → ecn_items` now reads `b.ecn_id` / `b.parent_item_number` directly:
`bom_changes.py` (`_SELECT_COLUMNS`, `_get_bom_change`, `list_all_bom_changes`, both INSERTs) and
`workflow.py` (`_capture_bom_snapshots_at_submit`, `_check_bom_concurrency`,
`_queue_bom_changes_outbox`). **The named trap was handled**: the snapshot stamp-back is now keyed
on `(ecn_id, parent_item_number)` — there is a dedicated regression test asserting a NULL-item row
receives a `snapshot_id`, because the failure mode is a silently disabled concurrency gate rather
than an error.

**3. BOM-only ECNs + the Movex-existence check.** `create_bom_change` accepts `item_id=None`;
a new `POST /api/v1/ecn/{ecn_id}/bom-changes` route carries `parent_item_number`; bulk upload no
longer rejects an off-ECN parent. The ERP check lives in the router per this ADR
(`routers/parts.py:407-440`'s error-handling shape), and de-duplicates by distinct parent —
parents already on the ECN skip the round-trip entirely, since they were validated when added.

**4. Submit guard.** `_guard_submit` now checks a new `content_count` (items + routing operations
+ BOM changes + MPNs, via `_count_ecn_content`) rather than the `≥1 item` its docstring had always
claimed and never enforced. Landed after step 3, per the sequencing note.

**Test results:** 1130 non-integration tests pass. Integration files run isolated (see the
pre-existing I2-18 note — DB-backed files must run one at a time on Windows/Python 3.14):
BOM-only 6/6, migration 8/8, core BOM changes 18/18, snapshot-at-submit 7/7, concurrency gate 5/5,
workflow combinations 12/12, outbox/tasks 39/39.

**5. Frontend (2026-08-25).** `+ Add BOM change` on the ECN-wide BOM Changes tab opens
`AddBomChangeDrawer.tsx`, which names the parent directly — no item needed. It embeds a BOM
browser (the "browse by item number" half of backlog item **I2-15**): type a parent, see its live
Movex structure, click a line to author a CHANGE/DELETE against it with the old values prefilled
from the real line. That prefill matters because `old_from_date` must identify the live MPDMAT
line, and hand-typing it is the most error-prone part of the form. The search-as-you-type item
finder remains the open half of I2-15 — it needs a backend route first (the adapter has
`search_items`; nothing exposes it).

`BOMChangeOut.ecn_item_id` is now nullable, which made `BOMChangesTabContent.tsx` pass `null`
into an item-id parameter; that row's "Manage" action is now hidden for BOM-only rows, and rows
carry a **BOM only** badge so reviewers can see no item-master change is implied.

**6. Live verification against CONO=300 (2026-08-25).** A BOM-only ECN was created, walked
submit → engineering → EM/QM/SC → `dc_approve`, and its queued `PDS002MI.AddComponent` dispatched
to real M3. The line landed correctly (`PRNO` sourced from `parent_item_number`, `ecn_item_id`
NULL on the outbox row), the submit-time snapshot was captured and stamped on the NULL-item row,
and the test line was deleted afterwards — BOM restored to its original 11 lines.

### Defect found by this work — `MovexRestAdapter.get_item` (fixed)

The ERP-existence check is the first caller that needed a real answer from `get_item`, and it
immediately failed with a 502. Two genuine, pre-existing bugs, both verified live:

1. It issued a **GET** to `/MMS200MI/GetItmBasic`. The generic MI passthrough route rejects GET —
   HTTP 400, `"Transaction is not configured for GET. Use POST with a JSON body."` Every other MI
   call in the adapter already POSTs; this one could never have worked against the real service.
2. Not-found is reported as **HTTP 422** with `success:false`, not 404 — so the existing
   `if status == 404: return {}` branch never fired.

It went unnoticed because its only prior caller was `parts.py`'s autofill preview, whose `dry_run`
path swallows ERP errors (`movex_item = None`) and degrades silently. Fixed to POST, and 404/422/
200-with-`success:false` all collapse to `{}`. Covered by `tests/adapters/test_movex_get_item.py`.

**Still outstanding — both deferred to backlog 2026-08-26, neither blocking:**

- **Search-as-you-type item finder** — needs a backend route over `search_items`, which exists on
  every adapter but is exposed by none. Tracked as **I2-15** (open half; the browse-by-item-number
  half shipped with this ADR).
- **`MPDHED` half of the parity check** — see "Still to confirm" §1 above; `MITMAS` only for v1.
  Tracked as **I2-22**.

---

## Related finding — the submit guard does not match its own docstring

`src/workflow/machine.py:452` documents `_guard_submit` as *"mandatory header + ≥1 item
(ADR-009)"*. The implementation checks only that the actor is the originator and that the title is
non-empty. **There is no item check.** An ECN with no content on any tab submits successfully and
is routed to a reviewer.

These two findings pull in opposite directions and should be settled together:

- Today Oskar requires an item for a *BOM change* (too strict, per this ADR)
- Today Oskar requires nothing at all to *submit* (too loose, per the docstring's intent)

A coherent outcome is likely: **BOM changes stand alone**, and **submit requires the ECN to carry
at least one item, routing operation, BOM change or MPN** — i.e. content of some kind, not items
specifically.

→ **Implemented 2026-08-25**, exactly as outlined above — see step 4 of the Implementation record.
`_guard_submit` now checks `content_count` (items + routing operations + BOM changes + MPNs) in
place of the item-only check its docstring had always claimed and never enforced.

---

## Correction to existing documentation

`ai/memory/05-stargile-ecn-reference.md` lines 109 and 117 are factually wrong. They state
`BMZACTFL` is "1=Add, 3=Change" and that "Delete operations use a separate PDS002MI
DeleteComponent call — no action flag 2."

**Action flag 2 is DELETE**, handled in-band by the same rule
(`ProcessBOMLineRule.java:360`, `if(zactfl.equals("2"))`), confirmed independently at
`RequestECNBoMDetailValidationHelper.java:165` (`case 2: //DELETE`) and `:420`. Stargile's own
comment at `ProcessBOMLineRule.java:362-363` describes the add-then-delete mechanism verbatim.

That file is used as ground truth for design decisions, so the error should be fixed regardless of
which option above is chosen.

→ **Corrected 2026-08-25.** `ai/memory/05-stargile-ecn-reference.md` now reads
"1=Add, 2=Delete, 3=Change" and describes the in-band delete with its source line references,
carrying an inline note recording what the previous text claimed.

---

## Scope of the verification

The Java tier and the DDL were read exhaustively. The XPDL workflow definitions
(`Processes/*.awf`) and ComActivity `.cml` data-model files were **not** fully read, so a
declarative constraint there cannot be entirely ruled out — though given the Java tier
deliberately disabled its own copy of this check, that would be surprising.

---

## References

- `src/routers/ecn_bom.py:189` — the item-scoped route
- `src/services/ecn/bom_changes.py:352-375` — upload-time parent resolution
- `src/workflow/machine.py:451-457` — the submit guard
- Stargile: `RequestECNBoMDetailValidationHelper.java` (334-339, 495-500, 342-352, 90-95),
  `RequestECNBoMDetailValidatePreDMProcInRule.java` (57-74), `ProcessBOMLineRule.java` (360-405),
  `ProcessBOMHelper.java` (51-76), `ProcessItemRule.java` (45-57), `Docs/ZECNBOMS.sql`
- ADR-012 — BOM module scope, which assumed the current model
- `ai/memory/05-stargile-ecn-reference.md` — contains the `BMZACTFL` error noted above
