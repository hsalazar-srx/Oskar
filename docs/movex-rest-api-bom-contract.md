# movex-rest-api BOM Contract

**Status:** Draft — handshake doc for the movex-rest-api (.NET) owner, per Iteration 2 Slice 0 (ADR-012).
**Purpose:** Defines the five new endpoints Oskar's BOM module (Slices A–C) needs from movex-rest-api.
**Reference implementation:** `scripts/movex_stub.py` implements all five routes below against the golden
fixtures in `tests/fixtures/bom/`, so Oskar-side development and e2e tests can proceed without waiting on
this repo. Diff any real implementation's response shape against that stub's output before wiring it up.
**Verified against movex-rest-api `develop` @ `5501b00`, 2026-07-23** — see "Prior art" section below for a
correction to the ADR's W-1 transaction name and a research doc that wasn't previously cross-referenced.

Conventions (matching the rest of movex-rest-api): `/api/...` paths, `X-API-Key` header auth, `{data: {...}}`
envelope. The generic MI passthrough (`POST/GET /api/{program}/{transaction}`, `Controllers/
TransactionController.cs:631,746`) does **not** auto-inject `cono` — callers supply it as an ordinary field.
The custom read endpoints below (B-1/B-2/B-3/C-1/M-1, analogous to the existing `mitpop/search`/
`mitmas/next-sequence` endpoints in `Db2QueryService`) should accept `cono` as an explicit query param the
same way those do; `cono` is never hardcoded and never passed by Oskar callers — see `MOVEX_CONO` env mapping
in `src/adapters/erp/base.py`.

---

## Checkpoints (ADR-012 Decision 2)

| Item | Due | Status |
|---|---|---|
| B-1 | End of Slice 0 | ✅ Done — live-verified against real CONO=300 data throughout Slices A-E |
| B-2 | End of Slice A (+ perf gate, see below) | ✅ Done |
| B-3 | End of Slice A | ✅ Done |
| M-1 | Start of Slice C | ✅ Done |
| W-1 | Start of Slice E0 | ⚠️ Deployed 2026-08-11, **TDAT confirmed does not persist** — see "W-1 live-test findings" below. Not a blocker for Oskar any more: Oskar switched to a Delete+AddComponent close/reopen pattern (I2-19 resolution, see below) instead of waiting on a movex-rest-api-side fix. `UpdateComponent` itself is still broken and worth fixing on movex-rest-api's side if convenient, but nothing in Oskar depends on it any more. |
| W-0 | — | ✅ Done — `develop@e913522`, 2026-07-15, confirmed merged into current `develop` |

Escalate immediately to the Lead Engineer if a checkpoint is missed — the Lead Engineer directly controls the
movex-rest-api team, so these are actionable, not aspirational.

---

## W-1 live-test findings (2026-08-11) — TDAT does not persist

`PDS002MI.UpdateComponent` is deployed and mostly working, live-tested directly against real CONO=300 data
(item `LFAM050001`). **The field this transaction exists for Oskar to use it — `TDAT`, closing a BOM line by
setting its end-effective date — does not actually update, despite the call reporting success.**

**Reproduction:**
1. `AddComponent` a throwaway line (`MSEQ=990`, `FDAT=20260901`, confirmed present via `GET /api/bom/{itno}`).
2. `UpdateComponent` with `{CONO, FACI, PRNO, STRT, MSEQ, OPNO, FDAT, TDAT: 20260930}` →
   `{"success": true, "data": {"MSID": "000", "MSDT": ""}}`. `?raw=true` shows the raw M3 buffer starts `OK`.
3. Re-read via `GET /api/bom/{itno}?includeExpired=true` and directly via `GetComponent` (`raw=true`) — `TDAT`
   is still `99999999`, unchanged.
4. Reproduced 3× with different payload shapes, all with the identical wrong result:
   - Minimal payload (only `CONO/FACI/PRNO/STRT/MSEQ/FDAT/TDAT`, no `OPNO`/`MTPL`/`CNQT`).
   - `TDAT` sent as a JSON string (`"20260930"`) instead of a bare integer.
   - `TDAT` sent under the position-number key (`"11"`) instead of the field name (`"TDAT"`), to rule out a
     name-vs-position lookup bug in `ResolveFieldValue`.
5. **Isolation control:** an identical `UpdateComponent` call updating `CNQT` instead (`1.0 → 5.0`, no `TDAT`
   in the payload) succeeded and was confirmed via read-back on the same line — so the transaction's general
   update mechanism, key resolution, and response handling are all correct. This is `TDAT`-specific.

**What was traced from this side (Oskar has no write access to fix this):**
- RPG source (`analysis/PDS002MI.txt`, `RCOM14` — the `Update Component` subroutine) shows `Q2TDAT` is moved
  to `DCTDAT` unconditionally alongside every other field (line ~2052: `MOVE Q2TDAT    DCTDAT`), same pattern
  as every other field that does work (e.g. `CNQT`). No special-casing, no conditional skip visible there.
- The C# payload builder (`Infrastructure/TransactionBuilding/TransactionStringBuilder.cs`, `PadField`) pads a
  supplied numeric value with leading zeros to the configured length — looks correct for `TDAT`'s configured
  `startIndex`/`length` (contiguous right after `MTPL`, no apparent overlap).
- That leaves the bug most likely inside **`PDS002BE`** (the underlying M3 API program `PDS002MI`'s `RCOM14`
  calls, per `CALL 'PDS002BE'` in the source) — not visible in the RPG source available in this repo. Possible
  causes worth checking there: `DCOPT2='UPD'` update-mask/selective-field semantics that `TDAT` isn't
  registered for, a business rule that silently rejects `TDAT` changes under some condition (e.g. requires a
  separate "close" option code rather than a plain field update), or a field-length/offset mismatch specific
  to `PDS002BE`'s own internal structure (independent of the MI wrapper's own config, which otherwise checks
  out).

**Status (superseded 2026-08-11, see resolution below):** Oskar's dispatch layer originally hard-blocked this
transaction with a `RuntimeError` so it could never reach movex-rest-api and silently fail to close a BOM line
while reporting the write as completed. That guard has since been removed — see "I2-19 resolution" below —
because Oskar no longer calls `UpdateComponent` at all, not because `TDAT` was fixed. All test data from the
above reproduction was cleaned up (`Delete`d) after each attempt — the live BOM was back to its original
11-line state before this doc was updated.

---

## I2-19 resolution (2026-08-11) — Delete+AddComponent instead of UpdateComponent/TDAT

Rather than wait on a `PDS002BE`-side fix for the `TDAT` bug above, the movex-rest-api team suggested Oskar
sidestep it entirely: **delete the old BOM line and add a new one with a different `FDAT`**, instead of
closing the old line's `TDAT` in place. This is a well-known M3 pattern for date-effectivity changes precisely
because `UpdateComponent`'s `TDAT` is locked/unreliable in some M3 versions — confirmed here as exactly that.

This was cross-checked against Stargile's real source (`ProcessBOMLineRule.java`,
`com.startronics.ecn.process.rules`, in the Stargile source tree) before adopting it, since Oskar's design
principle is to match or improve on Stargile's proven behaviour, not invent new BOM semantics. The result:
**Stargile's live BOM-apply engine never called `UpdateComponent`/`TDAT` for BOM component lines at all** —
`BOMService.updateComponent()` is defined but has zero real call sites in the ECN-processing rule classes.
Stargile's actual CHANGE handling is a plain `addComponent` at the ECN's own effective date
(`ZECNHEAD.EHFDAT`, applied uniformly to every line touched by that ECN); its DELETE handling is itself an
add-then-delete trick ("perform an add with a new from date to update the original line with a new to date
and then delete the newly added line", per that file's own comment). So Delete+AddComponent isn't just a
workaround for this bug — it's *closer* to Stargile's real design than the original `UpdateComponent`-based
plan was.

**Oskar's new model** (`_queue_bom_changes_outbox` in `src/services/ecn/workflow.py`):
- **DELETE** → 1 `PDS002MI.Delete` row removing the existing line outright (no replacement).
- **CHANGE** → 2 rows: a `PDS002MI.Delete` row removing the old line, then a `PDS002MI.AddComponent` row
  (`FDAT` = the `ecn_bom_changes` row's own `from_date` — already captured from the user today, no new field
  needed, matches Stargile's `EHFDAT`-sourced effective date) whose `depends_on` is the delete row's id
  (Slice E0's dispatch-ordering mechanism), so the add never dispatches until the delete has completed.

**Live-verified 2026-08-11** against real CONO=300 data (item `LFAM050001`, `MSEQ 150`, originally
`FDAT=20240118`/`CNQT=1.0`):
1. `PDS002MI.Delete` with `{CONO, FACI, PRNO, STRT, MSEQ:150, FDAT:20240118}` → `{"success": true, "data":
   {"MSID": "000"}}`. Read-back confirmed `MSEQ 150` absent.
2. `PDS002MI.AddComponent` with `{..., MSEQ:150, OPNO:190, FDAT:20260901, MTPL:"LFAM700006", CNQT:2.0,
   PEUN:"EA"}` → `{"success": true, "data": {"MSID": "000"}}`. Read-back confirmed `MSEQ 150` now present with
   `FDAT=20260901` and `CNQT=2.0` — both values actually changed, proving the pattern achieves what
   `UpdateComponent`/`TDAT` could not. Total record count stayed at 11 throughout — no duplicate/orphan lines.
3. Test line deleted and re-added with its exact original values (`FDAT=20240118`, `CNQT=1.0`) to restore the
   real BOM; confirmed via a final read-back.

`update_bom_component` (the `UpdateComponent`-calling adapter method) is retired — no longer on
`_dispatch_mi_call`'s dispatch table, no longer queued by `_queue_bom_changes_outbox` — and kept only as
reference-only dead code in case a future `PDS002BE` fix makes `TDAT` worth revisiting.

**For the movex-rest-api owner:** fixing the underlying `TDAT` bug (see diagnosis above) is no longer a
blocker for Oskar, so there's no urgency on Oskar's account — but it may still be worth fixing independently,
since other M3 customers/integrations calling `UpdateComponent` directly would hit the same silent-failure
behavior.

---

## Prior art — read before implementing

`analysis/PDS002MI-routing-analysis.md` (movex-rest-api repo, gitignored — not previously linked from ADR-012
or the Iteration 2 plan) is a source-verified (RPG source + live MITEST testing, 2026-05-08) field-mapping
doc for exactly this area. Key facts from it that should shape B-1/B-2/W-1:

- **Physical/logical tables:** RPG physical file `MPDMOP00`; DB2 logical views `MPDMAT` (BOM components) and
  `MPDOPE` (routing operations), both in schema `MVXCDTA`.
- **MPDMAT key:** `CONO+FACI+PRNO+STRT+MSEQ+OPNO+FDAT` (7 fields). **MPDOPE key:**
  `CONO+FACI+PRNO+STRT+OPNO+FDAT` (already correctly handled post-W-0).
- **Critical gotcha — FDAT is a cursor seek position, not a filter.** Confirmed via RPG source (`PDS002MI.txt`
  RCOM13) for `LstOperation`: passing a non-zero `FDAT` repositions the list cursor to that point in the
  index and silently skips earlier records — it does not filter by effective date. The correct call omits
  `OPNO`/`FDAT` entirely (4-field `EPDMOP` key) and returns the full list from the start. The analysis doc's
  confirmed-transactions table explicitly flags `LstComponent` as sharing "the same TDAT=0 bug as
  LstOperation" — **whoever builds B-1/B-2 must apply the same fix (omit FDAT/OPNO on the list call, filter
  effectivity in the response) rather than rediscovering this the hard way.**
- **MI transactions catalogued for PDS002MI** — all now implemented as of 2026-08-11
  (`transactions/PDS002MI.json`): `AddComponent`/`Delete`/`CopyComponent`/`GetComponent`/`LstComponent`/
  `UpdateComponent` (BOM side, writes to `MPDMAT`) and `AddOperation`/`UpdateOperation`/`CopyOperation`/
  `GetOperation`/`LstOperation` (routing side, writes to `MPDOPE`). Note the real delete transaction is named
  `Delete` (not `DeleteComponent`) and handles both component and operation delete via `MSEQ` vs `OPNO`. See
  "W-1 live-test findings" above for `UpdateComponent`'s current known issue (`TDAT` doesn't persist).
- **Name correction:** ADR-012 and the Iteration 2 plan both call W-1 `PDS002MI.UpdComponent`. The verified
  MI transaction name is **`UpdateComponent`** (matching the existing `UpdateOperation` naming pattern) — the
  ADR's shorthand was imprecise. Use `UpdateComponent` when scoping W-1's implementation and its field-offset
  verification pass.
- Field-mapping table for `AddOperation`/`UpdateOperation` (MI field → `MPDOPE` column, e.g. `PITI`→`POPITI`
  run time in minutes, `FDAT`→`POFDAT`, `TDAT`→`POTDAT`, use `99999999` for open-ended) is directly reusable
  as a template for mapping `MPDMAT`'s equivalent BOM fields once W-1 is scoped in detail.

---

## B-1 — Single-level BOM

```
GET /api/bom/{itno}?cono&faci&strt=001&effectiveOn&includeExpired
```

MPDHED head + MPDMAT lines joined MITMAS, effectivity-filtered, `ORDER BY PMMSEQ`. **See the FDAT-cursor-seek
gotcha above** — build this as a full list + application-side effectivity filter, not a filtered list call.

```json
{
  "data": {
    "head": {"PRNO": "...", "STRT": "...", "FACI": "...", "ITDS": "..."},
    "records": [
      {"MSEQ": 10, "MTNO": "...", "ITDS": "...", "OPNO": 10, "CNQT": 4.0, "PEUN": "EA",
       "FDAT": 20240101, "TDAT": 99999999, "ITTY": "3", "STAT": "20"}
    ]
  }
}
```

404 if no head record exists for `itno`. Today's `GET /bom/{item}` stub in `movex.py` points at nothing —
this replaces it.

Reference fixture: `tests/fixtures/bom/single_level.json` (12 lines, includes one component repeated at two
different `OPNO` values — regression fixture for the compare engine's array/key-derivation defect, Slice D).

## B-2 — Multi-level (indented) explosion

```
GET /api/bom/{itno}/indented?cono&faci&strt&levl=12&effectiveOn
```

Recursive CTE over MPDMAT (depth-capped, cycle-guarded). **PDZ100MI is broken in M3 (user-confirmed) — do not
use it.** Flat, depth-first Stargile shape; Oskar assembles the tree client-side.

```json
{
  "data": {
    "records": [
      {"LEVL": 1, "PRNO": "...", "MSEQ": 10, "MTNO": "...", "ITDS": "...", "OPNO": 10, "CNQT": 1.0,
       "PEUN": "EA", "FDAT": 20240101, "TDAT": 99999999, "STRT": "001", "WHLO": "MAIN"}
    ]
  }
}
```

**Open question for the .NET owner:** the reference fixture (`multi_level.json`) also carries an `ITTY` field
on every record, used by Oskar to detect phantom assemblies (`ITTY="9"`) during tree assembly. The Stargile
flat shape as specified above does not list `ITTY`. Confirm whether the MPDMAT/MITMAS join for this endpoint
can include it, or whether phantom detection needs a separate MITMAS lookup per component instead.

**Performance gate (2026-07-20, ADR-012 Decision 4):** before Slice B builds tree-assembly logic on this
endpoint, it must return in bounded time (**<2s target**) against the largest known real multi-level BOM in
UAT — not just pass functional correctness. This is a go/no-go gate, not a nice-to-have.

`BuildOdbcParams` (`Services/Db2QueryService.cs:188-197`) currently hard-caps at 3 positional binds
(`p0`-`p2`, `ArgumentOutOfRangeException` beyond that — verified still true 2026-07-23); this endpoint needs
~6 (`cono, faci, prno, strt, effectiveOn, maxDepth`) and requires extending that helper first.

Reference fixture: `tests/fixtures/bom/multi_level.json` (3 levels, one phantom assembly, one component
repeated at two different tree positions for cumulative-quantity roll-up testing).

## B-3 — Where-used

```
GET /api/bom/where-used/{mtno}?cono&faci&effectiveOn
```

Reverse MPDMAT lookup on `PMMTNO`.

```json
{
  "data": {
    "records": [
      {"PRNO": "...", "STRT": "...", "FACI": "...", "MSEQ": 20, "MTNO": "...", "OPNO": 20,
       "CNQT": 3.0, "PEUN": "EA", "FDAT": 20240101, "TDAT": 99999999}
    ]
  }
}
```

Reference fixture: `tests/fixtures/bom/where_used.json`.

## C-1 — Circuit references (migration/backfill only)

```
GET /api/bom/{prno}/circuit-refs?cono&faci&strt
```

ZECNCIRF read. **Retired after cutover** — Oskar owns `bom_circuit_refs` (D4) going forward; this endpoint
only exists to backfill data during the Stargile decommission window.

```json
{
  "data": {
    "records": [
      {"FACI": "...", "PRNO": "...", "STRT": "001", "MSEQ": 10, "FDAT": 20240101, "CIRF": ["R1", "R7", "R12"]}
    ]
  }
}
```

Keyed by the ERP line key `(facility, parent_item, structure_type, sequence_number, from_date)` per D4.

Reference fixture: `tests/fixtures/bom/ref_des.json`.

## M-1 — ZECNMPMS export (migration only)

```
GET /api/mpm/export?cono&offset&limit=1000
```

Paged ZECNMPMS dump, raw/untransformed rows — TRIM, uppercasing, date-null normalisation, and manufacturer
synonym resolution are the migration script's job (`scripts/migrate_zecnmpms.py`, Slice C), not this
endpoint's. **Fallback if this isn't built in time:** one-time DB2 `EXPORT ... OF DEL` CSV, DBA-run.

**Real column names, verified 2026-07-27** against the actual Stargile source
(`c:/Projects/SuperTool/Stargile_Source_Code/workspace/Startronics/DataModels/ECN/Maintenance/{MPMDetail,MPMBrowse}.cml`)
— superseding the inferred/placeholder names used earlier in this doc and in Slice 0/C's original fixture:
`MPCONO, MPITNO, MPSUNO, MPZMANPN` (manufacturer part number — not `MPN`), `MPZDEFFL, MPZEEFDT` (effective date),
`MPZECNID` (originating ECN), `MPTX30` (manufacturer), `MPMPRC` (price — not `MPPRIC`), `MPZMPMOQ` (MOQ — not
`MPMOQ`), `MPFDAT, MPTDAT, MPCUCD` (currency — not `MPCURR`), `MPZMPSPQ` (SPQ — not `MPSPQ`), `MPZCAWID`
(cancellation window days), `MPZREWID` (reschedule window days), `MPZMNCNR` (NCNR flag), `MPFACI, MPLMDT, MPLMTM`.
**`MPDIST`/`MPDISTNM` (distributor number/name) do not exist on this table at all** — they were invented with
no source backing; `item_mpns.distributor_number`/`distributor_name` stay `NULL` for zecnmpms-origin rows.

```json
{
  "data": {
    "records": [ { "...": "raw ZECNMPMS columns above, one dict per row" } ],
    "offset": 0,
    "limit": 1000,
    "total": 4213
  }
}
```

Reference fixture: `tests/fixtures/bom/zecnmpms_sample.csv` (7 rows covering: leading/trailing whitespace,
mixed case `ITNO`/`MPZMANPN`, `MPFDAT`/`MPTDAT` = `0` and `99999999` edge cases, two manufacturer-synonym
misses, and one duplicate natural key `(ITNO, SUNO, MPZMANPN)` for the migration's duplicate-key collapse
report).

---

## W-0 / W-1 — Write transactions (PDS002MI)

- **W-0** ✅ **Done** — PDS002MI field offsets added, commit `e913522`, 2026-07-15, confirmed present on
  current `develop`. Covered `LstOperation`/`AddOperation`/routing transactions (this was net-new work in
  that commit, not a re-fix of previously-broken PDS002MI — PDS002MI's `startIndex` offsets didn't exist
  before it). Also surfaced the `PITI` ×100 run-time scale factor (M3 stores minutes×100) as a pattern to
  check for BOM date/qty fields once W-1 lands. "Live-confirmed" is the commit author's claim — not
  independently verifiable from repo state alone, but the code change itself is real and merged.
- **W-1** `PDS002MI.UpdateComponent` (name-corrected — see Prior art; close lines by setting `TDAT`) —
  **confirmed NOT STARTED on any branch or in history** (verified 2026-07-23: zero matches for
  `UpdComponent`/`UpdateComponent` across all refs, including full history pickaxe search; the stale
  unmerged `feat-add-transactions-for-oskar` branch, tip `60e07c1`, does not contain it either — its BOM/
  routing work was superseded by `e913522`, not merged). Needs its own field-offset verification pass, same
  rigor as W-0 — `analysis/PDS002MI-routing-analysis.md`'s `AddOperation`/`UpdateOperation` field-mapping
  table is a directly reusable template for this. **Checkpoint: due start of Slice E0.**

Generic MI route confirmed: `POST/GET /api/{program}/{transaction}` (`Controllers/TransactionController.cs:
631,746`, no `/mi/` prefix) — matches what Oskar's adapter calls post-S9-7 fix. Auth via `X-API-Key` header
(`Middleware/ApiKeyAuthenticationMiddleware.cs:23`).

---

## Local dev / e2e usage

```
uvicorn scripts.movex_stub:app --port 8100
```

```
MOVEX_API_URL=http://localhost:8100
```

`scripts/movex_stub.py` serves all five routes above from the golden fixtures — used by Playwright e2e specs
and available for local dev against a backend that has no live movex-rest-api BOM support yet. It is not a
substitute for the live UAT smoke test each endpoint gets once it actually lands on movex-rest-api (see the
plan's `## Verification` section) — only a way for Oskar-side work to proceed without being blocked on this
repo.
