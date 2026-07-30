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
| B-1 | End of Slice 0 | Not started |
| B-2 | End of Slice A (+ perf gate, see below) | Not started |
| B-3 | End of Slice A | Not started |
| M-1 | Start of Slice C | Not started |
| W-1 | Start of Slice E0 | Not started (name-corrected — see Prior art) |
| W-0 | — | ✅ Done — `develop@e913522`, 2026-07-15, confirmed merged into current `develop` |

Escalate immediately to the Lead Engineer if a checkpoint is missed — the Lead Engineer directly controls the
movex-rest-api team, so these are actionable, not aspirational.

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
- **MI transactions already catalogued for PDS002MI** (some implemented, some not):
  `AddComponent`/`DeleteComponent`/`CpyComponent`/`GetComponent`/`LstComponent`/`UpdateComponent` (BOM side,
  writes to `MPDMAT`) and `AddOperation`/`UpdateOperation`/`CpyOperation`/`GetOperation`/`LstOperation`
  (routing side, writes to `MPDOPE`). `AddComponent`/`DeleteComponent`/`AddOperation`/`UpdateOperation` are
  confirmed implemented in `transactions/PDS002MI.json` (commit `74b66f5`, 2026-04-22, explicitly flagged in
  that commit's message as required for the Oskar ECN workflow). `LstComponent`/`GetComponent`/
  `UpdateComponent` are **not yet implemented** — worth checking whether B-1/B-2's custom DB2 read + W-1's
  write can reuse `LstComponent`/`UpdateComponent` as native MI transactions (like `LstOperation` already
  does for routing) instead of new bespoke DB2 SQL, before committing to the custom-endpoint approach below.
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
