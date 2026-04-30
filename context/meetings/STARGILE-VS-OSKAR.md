# Stargile → OSKAR: What Changes for You
**For use in:** 2026-04-29 meeting — Segment 3 + Demo narrative
**Audience:** Branko (Lead Engineer) + Nick (Production Manager)

> This document is a direct response to the Stargile issues and VSM pain points documented by the Melbourne engineering team in 2019 and from Stargile source code analysis.

---

## Status Legend

| Symbol | Meaning |
|--------|---------|
| ✅ **Fixed** | Fully addressed — this pain is gone |
| 🔶 **Improved** | Partially addressed — core fixed, some detail deferred |
| 🔵 **Sprint 2** | In active development, available at POC |
| 🟡 **Planned** | In OSKAR scope, post-POC |
| ⬜ **Out of scope** | Requires a different system decision |

---

## Part A — The 16 Stargile Issues

| # | Stargile Issue | Status | OSKAR Resolution |
|---|---|---|---|
| 1 | Only works in Internet Explorer 9 | ✅ **Fixed** | React SPA — Chrome, Edge, Firefox, Safari |
| 2 | No pre-set process configurations / distribution lists | ✅ **Fixed** | Data-driven conditional routing by ECN type; roles auto-assigned at creation |
| 3 | No validation between distribution list names and role checkboxes — random routing | ✅ **Fixed** | State machine computes `next_action_users[]` from database — no free-text names |
| 4 | Cannot upload files directly into ECN — must type DMR path | 🔵 **Sprint 2** | New `ecn_attachments` table; upload/download directly on the ECN record |
| 5 | No duplicate sequence number validation in BOM upload — silent data corruption | ✅ **Fixed** | Server-side validation at submission — rejects with error before any write |
| 6 | BOM/MPN/ITEM/ROUTES buttons not highlighted when data is present | 🟡 **Planned** | UI section completion indicators — React frontend Sprint 3 |
| 7 | BOM Revision and ECN Text in PDS001 not updated automatically | 🔶 **Improved** | Movex write at APPROVED includes PDS001MI header — confirm exact field mapping with Branko |
| 8 | Cannot delete customer Alias via ECN | 🔵 **Sprint 2** | MMS025MI manages all MPN alias operations including delete |
| 9 | No Purchase Price or Currency visible in View Items | 🔵 **Sprint 2** | New "View Items" screen: PN + Description + Manufacturer + MPN + Stock on Hand |
| 10 | Two concurrent ECNs on same PN — no warning, silent overwrite | ✅ **Fixed** | Conflict detection at submission + BOM snapshot at DC_REVIEW vs write time (ADR-008) |
| 11 | Uploading items on status 95 (Complete) ECN | ✅ **Fixed** | Terminal states enforced by state machine — no writes possible on CLOSED / CANCELLED |
| 12 | View Items shows current Movex state only — no change history | 🔶 **Improved** | SHA-256 audit chain records every transition; point-in-time state snapshot at APPROVED |
| 13 | ECR Implementation Schedule not customisable (AOI, MES, Valor, wave pallets) | 🟡 **Planned** | Post-APPROVED checklist — Sprint 3 (fits in `extra_data` JSONB without schema change) |
| 14 | Separate ECNs required for items / routes / BOM / MPN | ✅ **Fixed** | One ECN covers all four: `ecn_items` + `ecn_mpns` + `ecn_bom_changes` unified |
| 15 | Currency field mandatory for MPN uploads even though not used | ✅ **Fixed** | Not in schema — field doesn't exist |
| 16 | Manufacturer Code + Manufacturer Name both required | ✅ **Fixed** | Only `mpn` + `manufacturer` (name only) required; code lookup via Movex API |
| 17 | No customisable view: PN + Description + Manufacturer + MPN + Stock on Hand | 🔵 **Sprint 2** | Dedicated "View Items" endpoint joining OSKAR data + live CITMAS read |
| 18 | MPN missing: Shelf Life, Packaging, EOL, Do Not Buy, MSL | 🔵 **Sprint 2** | 5 new nullable columns on `ecn_mpns`: `msl_level`, `shelf_life_months`, `packaging_type`, `is_eol`, `is_dnb` |

---

## Part B — VSM Step-by-Step (12 Steps)

| Step | Description | Status | OSKAR Resolution |
|------|-------------|--------|-----------------|
| 1 | Get BOM + QCW — received by email from PM | ⬜ **Out of scope** | NPI database / RFQ system decision needed above OSKAR |
| 2 | BOM comparison: customer BOM vs QCW BOM (manual Excel) | 🟡 **Iteration 2** | BOM comparison tool — Iteration 2 (BOM module) |
| 3 | Movex PN duplicate check: manual Customer Part Mapping in Excel | 🔵 **Sprint 2** | Pre-submission CITMAS lookup: search by MPN + Manufacturer or Customer Alias before creating new PN |
| 4 | Create SRX PN: manual commodity code + sequential numbering + 30-char limit | 🔶 **Improved** | 30-char limit enforced at DB (`VARCHAR(30)`). Auto-numbering and commodity code lookup = stretch goal for POC |
| 5 | ECN Routing Upload — requires batch qty from PM | 🟡 **Planned** | Routing module — Iteration 2. `operation_number` field present in BOM changes |
| 6 | BOM Upload — manual SMT/TH/Mech/Packing classification | 🔶 **Improved** | `operation_number` field present; auto-classification rules table = stretch goal |
| 7 | MPN Uploads — manual manufacturer search, currency field | ✅ **Fixed** | Currency field removed; manufacturer name only required |
| 8 | Verify Movex BOM vs customer BOM — manual Excel comparison | 🟡 **Iteration 2** | BOM comparison tool — Iteration 2 |
| 9 | Purge (MPN end-date) — done on paper | ⬜ **Out of scope v1** | Should be an OSKAR feature calling Movex end-date API — scope decision needed |
| 10 | Transmittal — no tracking database | ⬜ **Out of scope v1** | Requires document management system integration |
| 11 | Upload BOM to MTS — manual download and re-upload | ⬜ **Out of scope** | MTS integration boundary decision |
| 12 | Create routings/process flow in MTS | ⬜ **Out of scope** | MTS integration boundary decision |

---

## Part C — The 5 Demo Moments

These are the five moments in the POC demo where OSKAR is visibly and unmistakably better than Stargile. Script these.

### Demo Moment 1 — "No more manual Movex item creation"

> **Today:** Branko logs into M3, manually finds the last sequence number for that customer + commodity, creates the item master, then references it in Stargile. Confirmed in the 2018 session (timestamp 43:57): *"this is another step where we use a shortcut sometimes by manually creating it in Movex."*
>
> **In OSKAR:** Engineer fills in the ECN item line with `is_new_item=TRUE`. ECN is approved. The system fires `MMS200MI → PDS001MI → PDS002MI → MMS025MI` automatically. Item appears in Movex. Nobody logged into M3.

### Demo Moment 2 — "No more silent Movex failures"

> **Today:** Stargile Status 50 fires a synchronous Movex call with no feedback. If it times out — and it does — the ECN sits stuck. Discovery: the next day when someone notices the BOM hasn't changed.
>
> **In OSKAR:** DC recovery panel shows every MI call attempt, the exact Movex MSID error code, the full response body, and a Retry button. DC resolves it without calling IT.

### Demo Moment 3 — "'Who is sitting on this ECN?' — actually answered"

> **Today:** DBCHK_OpenECN (Karen's SQL Server job) shows the originator name in the "Next Action Person" column — because it never joined to the actual approver assignments. The cursor has a bug: the "Created" column shows the ECN ID instead of the date.
>
> **In OSKAR:** Dashboard shows Nick's name under his pending MANAGEMENT_REVIEW items, Branko's name under ENGINEERING_REVIEW, DC's queue of unreviewed submissions. Anything over 48 hours is highlighted red. The nightly email report is also gone — replaced by a live web view any approver can check.

### Demo Moment 4 — "Rejection is a record, not an email"

> **Today:** Stargile rejection sends a free-text email to the originator. No required reason code. No record of whether the whole workflow restarts or just the rejecting step. No audit trail entry.
>
> **In OSKAR:** Rejection records: reason text (mandatory), the rejecting engineer's identity, their decision (restart whole workflow or only the rejecting stage), and a SHA-256 audit chain entry. That is the ISO 13485 audit record for this change decision.

### Demo Moment 5 — "MSL and EOL live next to the MPN — not in a spreadsheet"

> **Today:** Purchasing maintains a separate Excel file for MSL levels and EOL status. When it's wrong or out of date, obsolete components get committed to a BOM.
>
> **In OSKAR:** MSL level, shelf life months, packaging type, EOL flag, and Do Not Buy flag are captured alongside the MPN, inside the ECN change record, traceable to that specific ECN and approval date. The spreadsheet can be retired.

---

## Part D — What OSKAR Cannot Help With (Be Honest)

These are out of scope for v1. Do not hedge or promise — be direct.

| Topic | Honest answer |
|-------|--------------|
| BOM comparison tool (Steps 2 + 8) | "Iteration 2 — BOM module. Not in the June/July POC." |
| MTS integration | "Out of scope — MTS is a separate boundary. OSKAR makes the BOM that feeds MTS more accurate." |
| Transmittal tracking | "Out of scope. If this is a priority, we need a document management system decision." |
| RFQ / QCW integration | "Out of scope. Upstream of OSKAR. Requires an NPI database decision." |
| Purge (MPN end-date) | "Should be in OSKAR — it's a Movex API call. Not in the June POC but on the roadmap." |
| Multiple Movex routings for same BOM | "Movex limitation. OSKAR can't change Movex's data model." |
