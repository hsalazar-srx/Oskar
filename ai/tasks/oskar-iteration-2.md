# Oskar Iteration 2 — BOM Management (TDD Implementation Plan)

**Decision provenance:** this plan's current scope, sequencing, external-dependency checkpoints, and comparison-engine design corrections were established via source re-verification (2026-07-16) and a structured stress-test (2026-07-20). Full rationale: [ADR-012](../../decisions/ADR-012-bom-module-iteration-2-scope-and-comparison-engine.md). Index: [ai/evidence/decision-log.md](../evidence/decision-log.md). This file states current decisions inline at point of use — it does not carry the narrative history of how they were reached.

## Execution model — parallel worktrees (ADR-012 Decision 10)

Slice 0 (fixtures, stub, contract doc) is a shared prerequisite, completed once on `master`. After it merges, two worktrees proceed independently:

| Worktree | Branch | Scope | Depends on |
|---|---|---|---|
| `.claude/worktrees/oskar-bom-slice-ab` | `claude/oskar-bom-slice-ab` | Slice A (browse), Slice B (explosion/where-used) | Slice 0 only |
| `.claude/worktrees/oskar-bom-slice-c` | `claude/oskar-bom-slice-c` | Slice C (MPN master + ZECNMPMS migration) | Slice 0 only |

Both branch from the commit where Slice 0 lands on `master`. Neither touches the other's files (`src/services/bom/{browse,explode}.py` vs `src/services/bom/{mpn_master,zecnmpms_transform}.py`) — no shared mutable state, coordinated only through `master` and the shared `tests/fixtures/bom/` golden fixtures from Slice 0. Slice D depends on both and is not started until both branches merge back to `master`. E0 and E stay serial after D — not further parallelized (diminishing returns past 2-3 concurrent tracks on a plan this size).

## Context

Oskar (FastAPI + React, ECN workflow live in UAT) must absorb the BOM Management workload that today lives in two legacy systems: **Stargile** (Java/ComActivity on Movex DB2 — ECN-driven BOM changes, MPN cross-reference in custom `Z*` tables, multi-level explosion via custom M3 program PDZ100MI — **user-confirmed: PDZ100MI is broken in M3**, so it is not an option) and **PLM** (PHP/MySQL + M3 datawarehouse). The PLM working copy at `C:\Projects\PLM` is the `master` branch; the **deployed app (v1.3.0, built from the `v3` branch, github.com/aaronquansrx/plm) has more features than the source we hold**, verified live at `http://srxapp07.corp.startronics.com.au/PLM/`: BOM Comparison (`/bomcomparison`), BOM Scrub (`/bomscrub`), Single Component Attribute Search (`/singlecomponent`), Mass Update COO (`/updatecoo`), E-Quote (`/quoting`), Open Market BOM/Part Search. Users' ECN workload is majority BOM changes, so Iteration 2 (BOM Module, ~8 wks per `context/Oskar_Integrated_Plan_v5.1.md`) is being pulled forward. **All new features build on top of the existing Oskar ECN module** (same FastAPI service, same `v1_router`, same workflow/outbox, same React app) — nothing is a separate system. **Scope note (2026-07-20 grilling session):** Iteration 2 is now Slice 0 → A → B → C → D → E0 → E only (~10.4-10.8wks, see below); Slice F (I2-12) and Slice G (I2-11) are deferred to Iteration 3 to keep this closer to the committed 8-week figure.

**Live PLM BOM Comparison — parity spec (verified against source, `src/BOMComparison/` at `C:\Projects\PLM\plm-3`, not just the running app):** two sides "BOM Old" / "BOM New", each loadable via file **Upload** (xlsx/csv, user picks header row, columns auto-detected via label/alias/regex matching, supports repeated MFRn/MPNn column pairs and an optional "multiple lines per key" collapse mode) or **Find from MoveX** (finder: search by customer/product number → pick → paginated line fetch, multi-row-per-IPN collapse into MPN/MFR arrays); canonical line shape is IPN, Alias/CPN, MPN\[\], MFR\[\], Designator, Description, Quantity (**MPN/MFR are arrays**, not scalars — a line can carry multiple manufacturer/part-number pairs; **Footprint** is a mappable upload column but is dropped before comparison, effectively dead). Comparison Key is **dynamic** — any field present in both loaded BOMs, not a fixed list — defaulting arbitrarily to the first common field. Results render as **Differences / Additions / Subtractions** counts plus a side-by-side table (BOM Old | Changes | BOM New, PLM has no reachable "all lines" view — that code path is dead); **Export** to `.xlsx` only, always using the full fixed field set regardless of on-screen column visibility. Slice D must reach at least this parity, **with corrections** (per 2026-07-16 verification + user decision): PLM's "Options" modal (column visibility) and its separate column-header-click diff-field-toggle are **unified into one per-field control** in Oskar; three known PLM engine defects are **deliberately fixed, not replicated** — (a) inconsistent array-key derivation that silently breaks MPN/MFR-keyed matching on multi-value lines, (b) `parseFloat`-based quantity diffing that always flags non-numeric quantities as changed even against themselves, (c) inconsistent case-sensitivity (case-insensitive for MPN/MFR/Designator, case-sensitive elsewhere) — Oskar uses one consistent rule for all fields.

**User-confirmed decisions:**
1. Iteration 2 in full detail; Iteration 3 (Supplier Intelligence) outline only.
2. BOM reads: **extend the external .NET movex-rest-api** (`C:\Projects\MOVEX\API-Integration\movex-rest-api`) — no local BOM mirror; Postgres snapshot cache OK for comparison/concurrency.
3. MPN master: **migrate Stargile `ZECNMPMS` → new Oskar Postgres table**; Oskar becomes system of record at Stargile decommission.
4. **Movex-only** now, via the existing `ERPAdapter` ABC with ERP-neutral signatures; IFS later.
5. **TDD**: every slice starts with failing tests (pytest backend; Playwright e2e — frontend has no unit runner).

**Verified code anchors:**
- Workflow (ADR-009): `DRAFT(0) → submit → ENGINEERING_REVIEW(30) → MANAGEMENT_REVIEW(40) → DC_APPROVED(25) → dc_approve → APPROVED(50) → movex_write_complete → IMPLEMENTED(60) → CLOSED(70)`. DC_REVIEW no longer exists — snapshot anchors move to `submit`/`resubmit`; concurrency check at `dc_approve`.
- Outbox queue points: `src/services/ecn/workflow.py:132` (dc_approve → routing ops), `:135` (movex_write_complete → alias), auto-fire of movex_write_complete when nothing queued (`:153`).
- `ecn_bom_changes` exists (migration 0001) but has no old-value/ref-des/sequence columns — needs extension for Stargile's supersession model.
- `ERPAdapter.get_bom(item_number, bom_type)` at `src/adapters/erp/base.py:61`; `MovexRestAdapter.get_bom` calls `GET /bom/{item}` — **that endpoint does not exist yet** on movex-rest-api. `add_bom_component` hardcodes `"faci": "D"` (`src/adapters/erp/movex.py:372`).
- Highest migration = 0024 → new ones start at 0025.
- Test patterns: `tests/routers/test_parts_alias.py` (patch `MovexRestAdapter` with AsyncMock + `__new__` app.state stub); `tests/integration/conftest.py` (real Postgres 5433, Alembic upgrade); Playwright e2e vs live backend.

**Key design decisions:**
- **D1** Multi-level explosion implemented in movex-rest-api as a recursive DB2 CTE over MPDMAT. PDZ100MI is broken in M3 (user-confirmed) and is **not** an option. Oskar-side recursion over single-level reads is the fallback if the .NET owner can't take the CTE — same `ERPAdapter` signature either way.
- **D2** `bom_snapshots` table (supplier_part_cache pattern): point-in-time JSONB line arrays + SHA-256 content hash. Serves comparison inputs, ECN concurrency baseline, history. **Retention (2026-07-20):** `reason=ecn_submit` rows kept indefinitely (audit trail of what the DC approved against); `compare`/`manual`-reason rows pruned after 90 days.
- **D3** MPN master = `item_mpns` keyed `(item_number, supplier_number, mpn)` like ZECNMPMS; `ecn_mpns` stays per-ECN staging and upserts into the master at `movex_write_complete`.
- **D4** Reference designators (Stargile `ZECNCIRF` — data M3's native BOM cannot hold) migrate into Oskar-owned `bom_circuit_refs`, keyed by ERP line key `(facility, parent_item, structure_type, sequence_number, from_date)`.
- **D5** Comparison engine = pure-Python zero-I/O module, reused by rev-vs-rev compare, customer-BOM compare (I2-2), and ECN concurrency detection (I2-6). Match key = normalised `(component_number, operation_number)` with Stargile padding rules (OPNO/MSEQ pad-4, STRT pad-3, undefined to-date = 99999999) + manufacturer-synonym normalisation (**Stargile `ZECNMPMS`/`MPTX30` concept, not PLM** — PLM's live compare engine has no synonym table at all, verified against source 2026-07-16; Oskar builds normalization anyway since it's needed for the MPN master transform regardless). Comparison key selection is **dynamic** across whichever fields both sides share (parity with PLM's header-intersection approach), and per-field participation in the diff is controlled by **one unified toggle per field** (both "diffed" and "shown" together) rather than PLM's split Options-modal/column-click mechanism. Three defects present in PLM's engine are deliberately **not** replicated: consistent key derivation for array-valued fields (MPN/MFR), real numeric validation for quantity (not `NaN`-always-differs), and one consistent case-sensitivity rule across all fields.
- **D6** ~~BOM apply follows Stargile supersession: CHANGE = close old line (TDAT = new FDAT − 1) + add new date-effective line; DELETE = close, never physical delete. Needs new `update_bom_component()` (PDS002MI.UpdComponent)~~ — **CORRECTED 2026-08-12 (I2-19, LL-003): this claim was never verified against Stargile's source and was found to be backwards.** Stargile's real `ProcessBOMLineRule.java` never calls `UpdateComponent`/TDAT for BOM component lines at all (`BOMService.updateComponent()` has zero real call sites) — its actual CHANGE handling is a plain `addComponent()` at the ECN's effective date, and its DELETE handling is itself an add-then-delete trick. Also independently confirmed broken on the M3 side: `PDS002MI.UpdateComponent`'s `TDAT` field does not persist despite reporting success (live-tested 2026-08-11, see `docs/movex-rest-api-bom-contract.md`). **Corrected design:** BOM apply now uses `PDS002MI.Delete` + `PDS002MI.AddComponent` — delete the old line, add a new one at the change's own `from_date` — which matches Stargile's actual pattern. Outbox ordering via `movex_outbox.depends_on` is unchanged — **the `depends_on` mechanism itself was built and tested in Slice E0** (core dispatch-engine change, not BOM-specific), ahead of Slice E's BOM-specific use of it, and required no changes for this correction since it was already generic. Full incident writeup: `ai/evidence/lesson-learned-LL-003.md`.
- **D7** e2e uses a fixture-serving stub movex-rest-api (`scripts/movex_stub.py`) pointed at via `MOVEX_API_URL`; all diff logic stays server-side.

---

## Feature slices (each: failing tests first → implement → e2e)

### Slice 0 — Enablers (~2 days)
- `tests/fixtures/bom/` golden fixtures: single-level (12 lines), multi-level (3 levels, phantom, repeated component), expired/superseded lines, ref-des, generated 500-line, customer-BOM `.xlsx`/`.csv`, `zecnmpms_sample.csv`.
- `tests/helpers/fake_erp.py` (`FakeERPAdapter` returning fixtures).
- `docs/movex-rest-api-bom-contract.md` — the contract appendix below, committed as the handshake doc for the .NET owner.
- `scripts/movex_stub.py` — FastAPI stub serving fixtures on the contract routes (e2e + local dev).

### Slice A — Single-level BOM browse (~1.5 wks)
Tests (red order): `tests/adapters/test_movex_bom.py` (get_bom contract, 404→`BOMNotFound`) → `tests/services/bom/test_browse.py` (merge ERP lines + ref-des + CPN alias, effectivity filter `to_date >= today` with include-expired toggle, MSEQ ordering, padding) → `tests/routers/test_bom_browse.py` (`GET /api/v1/bom/{item_number}`, auth, facility default 'D').
- Extend `src/adapters/erp/base.py`: `get_bom(item_number, facility, *, structure_type="001", bom_type="M", effective_on=None)`; update `movex.py` + `ifs.py` (stub). Also fix the `get_bom` docstring's stale "DC_REVIEW" reference (`base.py:64`, pre-ADR-009 terminology — that state no longer exists; DC gate is `dc_approve` at DC_APPROVED=25) while touching this method.
- New `src/services/bom/{__init__,browse,models}.py` (dataclasses `BOMLine`, `BOMHead`); new `src/routers/bom.py` registered on `v1_router` in `src/routers/__init__.py`.
- Frontend: `frontend/src/api/bom.ts`, `frontend/src/pages/BOMBrowserPage.tsx`, route `/bom` in `App.tsx` (+ nav). Table pattern from `ECNListPage.tsx`. e2e `frontend/e2e/bom-browser.spec.ts`.
- Needs movex-rest-api **B-1** — **checkpoint: due end of Slice 0**; escalate immediately if missed (2026-07-20 grilling session).

### Slice B — Multi-level explosion + where-used (~1 wk)
Tests: adapter contract (`get_bom_indented`, `get_where_used`) → `tests/services/bom/test_explode.py` (tree assembly from flat LEVL rows, cycle guard → `BOMCycleError`, cumulative qty roll-up) → router tests (`GET /api/v1/bom/{itno}/indented?depth=`, `/where-used`).
- `ERPAdapter.get_bom_indented(item_number, facility, *, structure_type="001", max_depth=12)`, `get_where_used(component_number, facility, *, effective_on=None)`; `src/services/bom/explode.py` (pure tree builder).
- Frontend: expandable tree + "Where used" tab in BOMBrowserPage. Needs **B-2**, **B-3** — **checkpoint: due end of Slice A**. **B-2's checkpoint includes a performance gate, not just correctness**: run the recursive CTE against the largest known real multi-level BOM in UAT and confirm bounded response time (<2s target) before this slice's tree-assembly code is built on top of it.

### Slice C — MPN master + ZECNMPMS migration + MPN search (~2 wks, +ZPOPEXTN replacement)
Tests: `tests/integration/test_migration_item_mpns.py` → `tests/services/bom/test_mpn_master.py` (upsert; default rule = `is_default AND (end_effective_date IS NULL OR >= today)`; `normalize_manufacturer()` synonyms) → `tests/scripts/test_migrate_zecnmpms.py` (transform rules on fixture, dry-run writes nothing, idempotent) → `tests/routers/test_mpn_search.py` (`GET /api/v1/mpn/search?q=STM32*` wildcard `*`→`%` with `%_` escaping, field selector item/mfr/mpn, pagination) → integration test: `movex_write_complete` upserts `ecn_mpns` → `item_mpns` with `source_ecn`.
- Migration `0025_item_mpns.py` (see schema); `src/services/bom/mpn_master.py`; `src/routers/mpn.py`; `scripts/migrate_zecnmpms.py` (CLI `--input csv|--from-api`, `--dry-run`, `--report`) with pure transform module `src/services/bom/zecnmpms_transform.py`.
- Hook in `src/services/ecn/workflow.py` beside `_queue_alias_outbox` (line ~135): upsert on `movex_write_complete`.
- Browse enrichment switches to `item_mpns`; MPN detail supplier enrichment via existing `SupplierChain` + `supplier_part_cache` (`GET /api/v1/mpn/{id}/supplier-data`).
- Frontend: `MPNSearchPage.tsx` route `/mpn`, item Sheet drawer with default badge + lifecycle chips. e2e `mpn-search.spec.ts`. Needs **M-1** (or DB2 CSV export) — **checkpoint: due start of Slice C**.
- **`scripts/add_manufacturer_synonym.py`** (2026-07-20, R5 fix-forward): insert-only CLI, raw string + canonical name → `manufacturer_synonyms`, re-runs affected `item_mpns` rows. Lets synonym misses surfaced by the migration's review file get corrected same-day without a deploy or waiting for the Iteration 3 admin UI.
- **`ZPOPEXTN`-equivalent replacement (2026-07-20, R7 — Oskar-owned, not Purchasing's dependency)**: minimal scheduled job reading `item_mpns.is_default` and writing whatever the PO-print process needs, so Stargile's `PurchaseExtensionNightJob` has a working successor before its Stargile MPN screens go read-only at cutover (adds ~2-3 days to this slice, accepted).

### Slice D — BOM comparison engine + I2-2 customer BOM compare (~2 wks)
Target = at least the live PLM `/bomcomparison` parity spec (see Context), **with the three PLM engine defects fixed rather than replicated and the Options/column-click split unified into one per-field toggle (user-confirmed 2026-07-16)**.
Tests (TDD showcase — engine is pure): `tests/services/bom/test_compare.py` ~30 cases (identical/added/removed/qty/op-moved/uom/effectivity/ref-des changes; padding equivalence "10"=="0010"; duplicate component at different ops matched independently; deterministic ordering; 500-line < 100 ms; **configurable match key** — default `(component_number, operation_number)` for ERP-vs-ERP, dynamically selectable from any field common to both sides for uploads/customer-BOM compare (parity with PLM's header-intersection behavior, not a hardcoded IPN/CPN/MPN list); **one per-field toggle** controlling both diff-inclusion and result-table visibility together — no separate "Options modal vs. click-to-diff" split; **array-valued fields (MPN/MFR) use consistent key derivation on both sides** — regression case specifically for the multi-value-line matching defect found in PLM's engine; **quantity comparison validates numerically and treats two non-numeric values as equal-if-equal-string, never NaN-always-differs**; **one consistent case-sensitivity rule across all fields**, not PLM's per-field inconsistency) → `test_compare_customer.py` (CPN alias → item, MPN → `item_mpns` → item, unresolved bucket, mfr synonyms) → `tests/integration/test_bom_snapshots.py` (hash stability, key-order independence) → `tests/routers/test_bom_compare.py` (`POST /api/v1/bom/compare` left/right descriptors + `options {key, fields[]}`; `GET /api/v1/bom/comparisons/{id}`; `POST /api/v1/bom/compare/upload` multipart, 422 with row numbers, reuse `ecn_items.py` bulk constants; export endpoint `GET /api/v1/bom/comparisons/{id}/export`).
- `src/services/bom/compare.py` — `diff_boms(left, right, *, opts) -> BOMDiff` serialising to NEXUS-style JSONB `{added, removed, changed:[{key, field_changes}], unresolved, stats}`.
- `src/services/bom/{snapshots,customer_bom,comparisons}.py`; migrations `0026_bom_snapshots.py`, `0027_bom_comparisons.py`.
- Frontend: `BOMComparePage.tsx` route `/bom/compare` — Old/New source pickers (live ERP item via a Movex BOM-finder dialog [search by item/customer, reusing `search_items`/OCUSMA endpoints] | saved snapshot | file upload), key selector (dynamic, from common fields) + a single per-field toggle list (replaces PLM's Options-modal/column-click split), Differences/Additions/Subtractions summary, side-by-side highlight table Old | Changes | New (green add / red remove / amber change), export (`.xlsx`, fixed field set — matches PLM), save + history; "Compare against…" launcher on BOMBrowserPage. e2e `bom-compare.spec.ts`.

### Slice E0 — Outbox dependency ordering (~3-4 days) — NEW 2026-07-20
Pulled out of Slice E because `movex_outbox.depends_on` is a change to the *dispatch engine itself* (used by every ECN write path — aliases, routing ops, and now BOM), not BOM-specific logic. Built and tested against the *existing* alias/routing dispatch paths first, so a bug in core ordering is caught in isolation rather than mid-way through BOM-specific work.
Tests: `tests/tasks/test_outbox_depends_on.py` — worker requeues an entry until its `depends_on` row completes; an abandoned dependency abandons the dependent; a synthetic two-row case built on the existing `AddOperation`/`AddAlias` dispatch paths (no new BOM transaction needed to prove the mechanism) → migration test for `0029_outbox_depends_on.py`.
- Migration `0029_outbox_depends_on.py`: `movex_outbox.depends_on UUID FK NULL` + partial index.
- `src/tasks/movex_outbox.py`: dependency check in the dispatch loop — skip/requeue while `depends_on` row is not `completed`; cascade-abandon when it's `abandoned`.
- Needs **W-1** — **checkpoint: due start of this slice** (see movex-rest-api contract section; **W-0 confirmed DONE 2026-07-15**, but that fix targeted `LstOperation`/routing transactions specifically — W-1 (`PDS002MI.UpdComponent`) is still fully unstarted on any branch as of 2026-07-16 and needs its own field-offset verification once built).

### Slice E — ECN BOM changes end-to-end, I2-6 (~2.5 wks)
Tests: migration test (0028) → `tests/routers/test_ecn_bom_changes.py` (CRUD under `/ecn/{ecn_id}/items/{item_id}/bom-changes`; CHANGE/DELETE require `old_from_date`; edits blocked at ≥ DC_APPROVED except DC role) → `tests/services/bom/test_snapshot_at_submit.py` (one snapshot per distinct parent item on submit/resubmit; Movex outage → skip with warning, don't block submit) → `test_concurrency_gate.py` (at dc_approve: re-fetch live, diff vs snapshot via slice-D engine; conflicting key → 409 `ECNTransitionError` with diff payload; non-conflicting → proceed + warning in history; hash-equal fast path) → `tests/services/ecn/test_queue_bom_changes_outbox.py` (ADD→1 AddComponent row; DELETE→1 UpdComponent close row; CHANGE→close+add using Slice E0's `depends_on`; idempotency keys `PDS002MI.X:{ecn_id}:{bom_change_id}[:close|:add]`) → `tests/adapters/test_movex_bom_writes.py` (UpdComponent field names per contract).
- Migration `0028_bom_changes_supersession.py` (+ `bom_circuit_refs`).
- `src/services/ecn/bom_changes.py`; router `src/routers/ecn_bom.py`; extend `workflow.py` transition(): snapshot on submit/resubmit, concurrency check then `_queue_bom_changes_outbox` on dc_approve (beside line 132).
- `src/tasks/movex_outbox.py`: dispatch `PDS002MI.UpdComponent` using Slice E0's `depends_on` mechanism; on add-row completion upsert `bom_circuit_refs`.
- `movex.py`: add `update_bom_component`; **fix hardcoded `"faci": "D"`** in `add_bom_component` (parameterise from ECN facility, as routing ops do).
- Frontend: `BOMChangesPanel.tsx` on ECNDetailPage (clone `RoutingOpsPanel.tsx`): change-type badges, old→new columns, ref-des editor, "current BOM" pick-from drawer, DC conflict banner reusing the slice-D diff table, outbox status chips (existing recovery panel pattern). e2e `ecn-bom-changes.spec.ts` (stub mutates live BOM → conflict blocks; restore → approve succeeds).
- Stargile parity extras: **bulk BOM-change upload** (`POST /ecn/{ecn_id}/items/{item_id}/bom-changes/bulk`, xlsx/csv — Stargile's `UploadECNBoMs`), built against `BulkUploadSpec`/`parse_bulk_upload` in `src/routers/bulk_upload.py` (shipped S9-8), following the exact `ecn_routing.py`/`ecn_items.py` S9-8 pattern: module-level spec constant → `parse_bulk_upload` → in-file dup-check → Pydantic row validation → service call, route declared before `/{item_id}/...` paths; BOM change lines included in the existing ECN detail/print output.

### Slice F — I2-12 BOM enhancements + Stargile parity (~1.5 wks) — **DEFERRED TO ITERATION 3 (2026-07-20)**
Per feature, test first: (1) TXT/CSV export `GET /api/v1/bom/{itno}/export?format=` vs golden expected-output fixture → `src/services/bom/export.py`; (2) ECN-deletion cross-ref: where-used check per DELETE/CHANGE line → advisory `GET /api/v1/ecn/{ecn_id}/bom-crossref` (warn, don't block); (3) DigiKey attribute enrich `POST /api/v1/bom/{itno}/enrich` via `SupplierChain` (cache-first, capped live lookups) — also covers PLM's deployed "Single Component Attribute Search" via the slice-C `GET /mpn/{id}/supplier-data`; (4) MPN-not-found → "Create ECN" prefill with `add_mpn` scope flag + staged `ecn_mpns` row; (5) **Item change history** (Stargile `ECNChangesBrowse` parity): `GET /api/v1/items/{itno}/ecn-history` aggregating, for one item number, its `ecn_items` rows (item-master changes), `ecn_bom_changes` where it is parent, where it is component (where-used-in-changes), and `ecn_mpns` rows — surfaced as an "ECN history" tab on the BOM browser item view.

### Slice G — I2-11 QT bulk price/lead-time upload (~1 wk) — **DEFERRED TO ITERATION 3 (2026-07-20)**
Tests: `tests/routers/test_qt_bulk_upload.py` + `tests/services/ecn/test_bulk_pricing.py` — new `POST /api/v1/ecn/{ecn_id}/items/bulk-pricing` (QT template), **allowed on APPROVED/IMPLEMENTED only for protected fields** (purchase_price, lead_time_days, …; others 422), QT/DC role gate, dry-run preview then commit, per-row unknown-item errors, idempotent, audit note in transition history.
- Reuse `_COLUMN_MAP` machinery in `ecn_items.py`; second tab in `ItemUploadDrawer.tsx` (S9-6 dry-run UX). e2e `qt-bulk-upload.spec.ts`.

Out of scope: I2-13 transmittal/SharePoint (independent workstream).

---

## New Alembic migrations (0025–0029)

- **0025 `item_mpns`** + **`manufacturer_synonyms`**: `item_mpns(id, item_number, supplier_number DEFAULT '', mpn, manufacturer_name, manufacturer_canonical, is_default, end_effective_date DATE NULL, from_date, to_date, source_ecn, price, currency, moq, spq, distributor_number, distributor_name, legacy_extra JSONB, source_system DEFAULT 'oskar', migrated_at, timestamps)`; `UNIQUE(item_number, supplier_number, mpn)`; `text_pattern_ops` index on mpn for wildcard search; partial unique index `(item_number, supplier_number) WHERE is_default AND end_effective_date IS NULL` (dated defaults enforced in service). `manufacturer_synonyms(raw_string PK, canonical_name, source)` seeded from PLM `manufacturer_strings`/`srx_manufacturer_reference_string`.
- **0026 `bom_snapshots`**: `(id, item_number, facility, structure_type, level_mode, lines JSONB, line_count, content_hash sha256, reason ecn_submit|compare|manual, ecn_id FK NULL, captured_by, captured_at)`. `ecn_bom_changes.movex_snapshot_at_review` deprecated (retained).
- **0027 `bom_comparisons`**: `(id, left_descriptor JSONB, right_descriptor JSONB, comparison_result JSONB, cost_impact, risk_flags TEXT[], created_by, created_at)` — sides are descriptors `{type: erp|snapshot|upload, ...}`, no local BOM mirror.
- **0028** extend `ecn_bom_changes` (`sequence_number, old_quantity, old_operation_number, old_from_date, old_to_date, circuit_refs_old, circuit_refs_new, snapshot_id FK`) + new **`bom_circuit_refs`** `(facility, parent_item, structure_type, sequence_number, from_date)` UNIQUE, `to_date, circuit_refs, source_ecn, source_system`.
- **0029** `movex_outbox.depends_on UUID FK NULL` + partial index. **Built in Slice E0** (2026-07-20 — split out as core dispatch-engine infrastructure, ahead of Slice E's BOM-specific use of it).

## movex-rest-api contract (external repo work items — `docs/movex-rest-api-bom-contract.md`)

Conventions: `/api/...`, `X-API-Key`, `{data:{...}}` envelope, `cono` query param from adapter.
- **B-1** `GET /api/bom/{itno}?cono&faci&strt=001&effectiveOn&includeExpired` — MPDHED head + MPDMAT lines join MITMAS, effectivity filter, ORDER BY PMMSEQ. `data: {head{PRNO,STRT,FACI,ITDS,...}, records[{MSEQ,MTNO,ITDS,OPNO,CNQT,PEUN,FDAT,TDAT,ITTY,STAT}]}`; 404 if no head. *(Today's `GET /bom/{item}` in movex.py points at nothing.)*
- **B-2** `GET /api/bom/{itno}/indented?cono&faci&strt&levl=12&effectiveOn` — recursive CTE over MPDMAT (depth-capped, cycle-guarded); PDZ100MI is broken in M3, do not use. Flat Stargile shape `records[{LEVL,PRNO,MSEQ,MTNO,ITDS,OPNO,CNQT,PEUN,FDAT,TDAT,STRT,WHLO}]` depth-first; Oskar assembles the tree. Follows the Dapper+`System.Data.Odbc` direct-query pattern from `Db2QueryService` (`mitpop/search`/`mitmas/next-sequence`) — **note for the contract doc: `BuildOdbcParams` currently caps at 3 positional binds (`p0`-`p2`); this endpoint needs ~6 (cono, faci, prno, strt, effectiveOn, maxDepth) and requires extending that helper first.**
- **B-3** `GET /api/bom/where-used/{mtno}?cono&faci&effectiveOn` — reverse MPDMAT on PMMTNO.
- **C-1** `GET /api/bom/{prno}/circuit-refs?cono&faci&strt` — ZECNCIRF read, migration/backfill only, retired after cutover.
- **M-1** `GET /api/mpm/export?cono&offset&limit=1000` — paged ZECNMPMS dump, migration only. Fallback: one-time DB2 `EXPORT ... OF DEL` CSV.
- **W-0** ✅ **DONE** — PDS002MI field offsets fixed and live-confirmed 2026-07-15 (`develop@e913522`), re-verified 2026-07-16. Covered `LstOperation`/`AddOperation`/routing transactions; also surfaced the `PITI` ×100 run-time scale factor (M3 stores minutes×100) as a pattern to check for BOM date/qty fields once W-1 lands.
- **W-1** Add `PDS002MI.UpdComponent` transaction config (close lines: set TDAT) — **confirmed NOT STARTED on any branch** (re-verified 2026-07-16, including the stale unmerged `feat-add-transactions-for-oskar` branch). Needs its own field-offset verification pass, same rigor as W-0. **Checkpoint (2026-07-20): due start of Slice E0.**
- Confirmed 2026-07-16: no `/bom`/`MPDHED`/`MPDMAT`/`PDZ100MI`/`ZECNMPMS`/`ZECNCIRF` code exists anywhere in movex-rest-api — B-1/B-2/B-3/C-1/M-1 are genuinely from-scratch, not partially scaffolded. Generic MI route is confirmed `POST/GET /api/{program}/{transaction}` (no `/mi/` prefix), matching what Oskar's adapter now calls post-S9-7 fix.

## ZECNMPMS migration plan

1. **Extract**: M-1 API or DBA DB2 CSV export (ZECNMPMS + ZECNCIRF; ZECNMPNI extracted only as a manual triage list — pending Stargile ECNs are completed or re-authored in Oskar, not migrated live).
2. **Transform** (pure, unit-tested): TRIM; uppercase ITNO/MPN; `0`/`99999999` dates → NULL; `MPZDEFFL '1'→true`; YYYYMMDD→DATE; `MPTX30` → canonical via synonyms (miss → raw + review file); leftovers → `legacy_extra`; `source_system='zecnmpms'`.
3. **Load**: idempotent upsert on the natural key, batches of 1000, `--dry-run` mode.
4. **Validate**: row counts, duplicate-key collapse report, default-flag violations (resolve manually), 100-row random field diff, MITPOP alias cross-check via `lookup_by_alias`.
5. **Cutover**: T-7d staging dry-run + sign-off → freeze Stargile MPN screens → delta extract (`MPLMDT >=` last run) → load → Oskar SoR; PLMServer BOM pages read-only with banner (**2-week overlap window, 2026-07-20**, with an automated daily reconciliation job — see R6). **Flag R7**: Stargile's `PurchaseExtensionNightJob` (default MPN → `ZPOPEXTN` for PO print) dies at decommission — **Oskar-owned minimal replacement built in Slice C** (2026-07-20 — not Purchasing's dependency to chase), must ship before this cutover step freezes Stargile's MPN screens.

## TDD mechanics (cross-slice)

- Pure unit (no DB/HTTP): compare engine, explode math, transform rules, mfr normalisation.
- Router tests: `TestClient` + dependency overrides + `patch.object(MovexRestAdapter, ..., new_callable=AsyncMock)` seeded with golden fixtures (exact `tests/routers/test_parts_alias.py` pattern incl. `__new__` app.state stub).
- Integration: real Postgres 5433 via Alembic (migrations, persistence, workflow hooks, depends_on with patched MI call).
- e2e: Playwright vs live backend + `scripts/movex_stub.py`; DB seeded via e2e helpers.
- Golden fixtures are the single dataset consumed by adapter mocks, the stub server, and expected-diff assertions.
- Uniform red-green order per slice: migration test → migration → adapter test → adapter → pure-service tests → service → router tests → router → e2e spec → page → refactor with full `pytest` + `npm run e2e`.
- Slice-E live-write verification deferred behind W-0; marked live-OQ cases tracked in the OQ checklist (S9-7 precedent).

## Coverage validation — legacy feature → Oskar slice

Everything below lands **inside the existing Oskar ECN module** (same service, router registry, workflow, outbox, React app).

**Stargile (delivered today):**

| Stargile feature | Oskar coverage |
|---|---|
| Single-level BOM browse (MPDHED/MPDMAT, effectivity-filtered) | Slice A |
| Multi-level BOM explosion (PDZ100MI — broken) | Slice B (recursive CTE via movex-rest-api) |
| ECN BOM change lines with old/new pairs (ZECNBOMS), spreadsheet upload | Slice E (`ecn_bom_changes` extension + bulk upload) |
| Date-effective supersession write-back to Movex (PDS001/PDS002MI, status ladder, error log) | Slice E (outbox + `depends_on`, Delete+AddComponent close/reopen — **corrected 2026-08-12, I2-19/LL-003**: originally scoped here as "UpdComponent close-then-add", which was an uncited, unverified claim about Stargile's behavior later found to be backwards — Stargile's real `ProcessBOMLineRule.java` never calls `UpdateComponent`/TDAT for BOM lines; its actual pattern is add-then-delete, which Oskar's Delete+AddComponent now matches — existing recovery panel) |
| Circuit references / ref-des (ZECNCIRF) | Slice A browse enrichment + Slice E editor; `bom_circuit_refs` (D4) |
| MPN cross-reference master (ZECNMPMS) + ECN-pending MPNs (ZECNMPNI) | Slice C `item_mpns` (+ existing `ecn_mpns` staging) + migration |
| MPN browse/maintenance (MPMBrowse, MaintainItemMasterMPNNumbers) | Slice C MPN search page + item MPN drawer |
| Per-item change history & where-used browse (ECNChangesBrowse) | Slice B where-used + Slice F item ECN-history endpoint/tab |
| ECN report incl. BOM/MPN changes | Slice E (BOM lines added to existing ECN detail/print) |
| Default-MPN → purchasing PO print (PurchaseExtensionNightJob → ZPOPEXTN) | Slice C — minimal Oskar-owned replacement job (2026-07-20 revision to R7; previously scoped as an unassigned external dependency) |
| Item-vendor AVL browse (MITVEN) | Iteration 3 (supplier master) |

**PLM (deployed v1.3.0, verified live):**

| PLM feature (route) | Oskar coverage |
|---|---|
| Movex BOM browse (`dbsrv.php`, PLM_Get_BOM + MPN/CPN/ref-des joins) | Slices A/B |
| **BOM Comparison** (`/bomcomparison`: upload/Movex-finder sources, key selector, field options, diff counts, side-by-side, export) | Slice D (full parity spec in Context) |
| Open Market Part Search (`/partsearch`, distributor APIs) | Slice C search + `supplier-data` endpoint; full open-market fan-out = Iteration 3 |
| Single Component Attribute Search (`/singlecomponent`) | Slice C/F (supplier-data + enrich) |
| Components Attributes Search / BOM scrub (`/bomscrub`) | Iteration 3 (BOM scrubbing tool) — parity required before PLM decommission |
| Open Market BOM Search / costing (`/bomtool`) | Iteration 3 (scrub + quoted-BOM intelligence) — **flag: by far the largest single legacy module found in verification (2026-07-16), ~4,100+ LOC across components/hooks/scripts, multi-distributor offer engine with excess-qty/price logic and Octopart fallback; budget it as its own sub-effort within Iteration 3, not a peer-sized item next to the others in this table** |
| Manufacturer/supplier master + AU/MYR links (`srx_records`) | Iteration 3 (synonyms seeded in Slice C) |
| E-Quote (`/quoting`) | **Outside Oskar's defined scope** (not in Iteration 2/3 docs) — stays in PLM; flag at decommission planning |
| Mass Update COO (`/updatecoo`) | **Not in Oskar docs** — recommend Iteration 3 backlog item; confirm owner. **Scope note (verified 2026-07-16): PLM's version does not write to the database from the browser at all** — it validates via `api/movex` (`valid_coo`/`valid_mitfac`) then generates a downloadable SQL script (`UPDATE mvxcdta.mitfac ...`) for manual execution; a much smaller lift than a live in-app editor if Oskar ports it as-is, though a real write endpoint (using the same MI-write pattern as Slice E) would be a natural improvement to scope in |

## Risks

| # | Risk | Mitigation |
|---|---|---|
| R1 | movex-rest-api is another repo/owner (B-1/B-2/B-3/M-1/W-1 external) | Contract doc in slice 0; Oskar work proceeds fully against mocks/stub |
| R2 | ~~W-0 PDS002MI offset bug still open~~ **Resolved 2026-07-15** — but W-1 (`UpdComponent`, not yet built) needs its own independent offset verification when implemented, not assumed covered by W-0 | Slice E's live-write path still ships mock-verified with a live-OQ gate until W-1 is built and offset-verified |
| R3 | PDZ100MI broken in M3 (confirmed) | D1: recursive CTE in movex-rest-api; Oskar-side bounded recursion as fallback |
| R4 | Large-BOM perf (500+ lines, deep trees) | Hash fast-path, depth/fan-out caps, perf assertion in unit tests; **B-2's own CTE performance validated against a real large multi-level UAT item as part of its Slice-A checkpoint (2026-07-20), not left until Slice B discovers it's slow** |
| R5 | Manufacturer synonym coverage | Pass-through-raw on miss + review file; admin-editable in I3; **fix-forward `scripts/add_manufacturer_synonym.py` CLI added in Slice C (2026-07-20) for same-day correction without waiting for the I3 admin UI** |
| R6 | PLMServer read-only overlap drift | ~~Cutover banner; spot-check compares during overlap~~ **Revised 2026-07-20**: explicit 2-week overlap window + automated daily reconciliation job (reuses Slice D's compare engine to diff Oskar snapshot vs PLMServer live BOM for a sample of active items, alerts on unexpected diffs) |
| R7 | Stargile night job (ZPOPEXTN PO print) dies at decommission | ~~Purchasing confirms replacement before cutover~~ **Revised 2026-07-20**: Oskar-owned, not Purchasing's dependency — minimal replacement built in Slice C, must ship before the Stargile-MPN-screens-read-only cutover step |
| R8 | Stale snapshot vs edited change lines | Re-capture on resubmit; DC gate always re-fetches live |
| R9 | Hardcoded facility 'D' in add_bom_component — **confirmed still present 2026-07-16**; S9-7 fixed the analogous routing-op bug but explicitly did not touch BOM component writes (no `facility` param exists on the method at all) | Fixed in slice E (parameterised from ECN facility) |

## Iteration 3 — Supplier Intelligence (outline, ~8–10 wks + deferred Iteration 2 slices, planned later)

**Deferred from Iteration 2 (2026-07-20 scope cut, see Grilling session):**
- **Slice F — I2-12 BOM enhancements + Stargile parity** (~1.5 wks as scoped): TXT/CSV export, ECN-deletion cross-ref advisory, DigiKey attribute enrich (also covers PLM's Single Component Attribute Search parity), MPN-not-found → Create ECN flow, item change history (`ECNChangesBrowse` parity). Full spec retained in its own section above — unchanged, just resequenced.
- **Slice G — I2-11 QT bulk price/lead-time upload** (~1 wk as scoped): two-phase upload with QT-role-gated protected fields on APPROVED/IMPLEMENTED ECNs. Full spec retained above.
- **`/bomscrub` and `/bomtool` parity** (already scoped below) — `/bomtool` flagged as the single largest legacy module found in verification (~4,100+ LOC); budget its own sub-effort, not a peer-sized item.

**Core Iteration 3 scope:**
- Real distributor adapters for `stubs.py` placeholders (Mouser, Arrow, Element14, RS) behind `SupplierAdapter` ABC; `supplier_part_cache` PK → `(supplier_id, mpn)` with price-breaks/stock; parallel fan-out mode on `SupplierChain`.
- Supplier/manufacturer master: migrate PLM `srx_manufacturer`/`srx_supplier`/AU-MYR region link tables; synonyms FK'd to master; admin CRUD (supersedes the Slice C `add_manufacturer_synonym.py` CLI fix-forward path once live).
- Bulk enrichment: Celery beat sweep of `item_mpns` (rate-limit/quota aware); EOL/do-not-buy/lead-time-spike alerts joined to where-used → one-click "draft ECN" (reuses deferred Slice F flow).
- BOM scrubbing standalone tool (quoting): upload any BOM → resolve (alias + item_mpns + synonyms) → all-distributor fan-out → risk/cost report → xlsx; feeds I2-11 (deferred Slice G) pricing prefill.
- Dependencies: supplier API credentials/quotas, Scanfil data-privacy sign-off, populated `item_mpns`.

## Verification

- Per slice: `.\run-tests.ps1` (full pytest incl. integration vs Postgres 5433) + `npm run e2e` with `scripts/movex_stub.py` running; new specs listed per slice.
- Slice A/B live smoke vs UAT movex-rest-api once B-1/B-2 land (compare stub vs live for a known item, e.g. via `/screenshot` skill on `/bom`); **B-2 additionally requires the <2s performance-gate check against the largest known real multi-level UAT item (2026-07-20) before Slice B proceeds**.
- Slice C: migration dry-run report reviewed; `item_mpns` count vs ZECNMPMS extract; MITPOP alias spot-check; **ZPOPEXTN-replacement job verified against a real PO-print cycle before the Stargile MPN-screens-read-only cutover step (2026-07-20, R7)**.
- Slice E0: dependency-ordering mechanism verified against the *existing* alias/routing outbox paths with a synthetic case (2026-07-20) before Slice E builds BOM-specific dispatch on top of it.
- Slice E: full ECN walkthrough in UAT (author BOM changes → submit → mutate BOM in Movex dev → dc_approve blocked with diff → restore → approve → outbox rows complete in recovery panel); live M3 write OQ gated on **W-1** (W-0 is done — see movex-rest-api contract section).
- Post-cutover: automated daily reconciliation job running through the full 2-week PLMServer overlap window (2026-07-20, R6) — alerts on unexpected Oskar-vs-PLMServer diffs, not manual spot-checks.
- Sprint-backlog bookkeeping: mark I2-2/I2-6 items as they land in `ai/tasks/sprint-backlog.md`; I2-11/I2-12 re-flagged there as Iteration 3 (2026-07-20 scope cut).