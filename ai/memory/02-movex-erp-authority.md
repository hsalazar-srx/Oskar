# OSKAR — Movex ERP Authority and Adapter Interface

> **PROVIDER-AGNOSTIC — Non-Negotiable #12**
> No tool-specific syntax in this file. Readable by any LLM tool or none.

---

## 1. Movex/M3 as Single Source of Truth

**Rule:** Movex is the SSoT for all item master data, BOM structures, and supplier relationships.
OSKAR reads from Movex via the ERP adapter. OSKAR writes back to Movex only through explicit
human-approved actions with full audit trail.

Never trust OSKAR-internal data over Movex data. If there is a conflict, Movex wins.

---

## 2. Movex Connection Facts

| Fact | Value |
|------|-------|
| Company number (CONO) | 100 |
| DB2/AS400 schema | MVXCOBJ |
| IBM i version | 7.4 (LATERAL, LISTAGG, modern DB2 for i SQL available) |
| Primary adapter | MovexRestAdapter → movex-rest-api (.NET 8, `http://movex-rest-api/api`) |
| IFS adapter | IFSAdapter — **stub only in v1**, not production-wired |

---

## 3. Key M3 Tables

| Table | Purpose | Notes |
|-------|---------|-------|
| MITMAS | Item master | MMITNO = item number, MMITDS = description, MMITCL = product group |
| MMBOMS / MMBOML | BOM header / lines | BOM structure |
| MPDHED | Product structure head | PHPRNO = product, PHSTRT = structure type, PHNUOP = op count; written by PDS001MI.AddProduct |
| MPDOPE | Routing operations | POOPNO = op no, POPLGR = work centre, POPITI = run time (col F from Labour Routing template), POSETI = setup time; physical file MPDMOP00 format PDOPE |
| MPDMAT | BOM components | PMMTNO = component, PMOPNO = linked operation, PMMSEQ = sequence; physical file MPDMOP00 format PDMAT |
| OCUSMA | Customer master | OKCUNO = customer number |
| OHEDCO | Sales order header | OACUNO = customer, OAORDT = order date (YYYYMMDD numeric) |
| FGINHE / FGLINE | Invoice header / lines | FGINHE.UHVONO = invoice number |
| FSLEDG | AR ledger | ESVONO joins to FGINHE.UHVONO |

**Date fields:** Numeric YYYYMMDD — never SQL DATE type.
**Text fields:** Fixed-width — always TRIM().
**CONO:** Always in WHERE clause — multi-company table.

---

## 4. ERP Adapter Interface

The ERP adapter pattern decouples OSKAR business logic from any specific ERP system.
All ERP access goes through the adapter interface — never direct DB2 calls from business logic.

**Live definition:** `src/adapters/erp/base.py` — that file is the authority. Do not duplicate the interface here.

Current abstract methods: `get_item`, `get_bom`, `search_items`, `get_ecn`, `health_check`.

**Write methods (to be added before Sprint 1 — Phase 2 gate F-2):** All ERPAdapter write methods
must be on the ABC before any business logic is written. See `decisions/ADR-005-erp-write-gate.md`.

**MovexRestAdapter:** `src/adapters/erp/movex.py` — production implementation calling movex-rest-api.
**IFSAdapter:** `src/adapters/erp/ifs.py` — stub, raises `NotImplementedError`. Not wired in v1.

---

## 5. movex-rest-api Facts

- Path: `c:/Projects/MOVEX/API-Integration/movex-rest-api`
- Routes: `/api` (unversioned — do NOT replicate this in OSKAR)
- OSKAR calls it as an internal service via Docker network
- Gap endpoints (if needed for OSKAR) must be scheduled with the movex-rest-api roadmap

## 6. MI Gap Analysis (Track A — Phase 1 deliverable, completed 2026-04-13)

### Currently Exposed Transactions

| Program | Transaction(s) | Purpose | OSKAR relevance |
|---------|---------------|---------|-----------------|
| MMS003 | Get | Item cost information (UCOS) | Read-only; useful for cost review display |
| MMS175MI | Update | Change item location (warehouse movement) | Not ECN-related |
| MMS200MI | GetItmBasic, GetItmFac, LstItmFac, GetItmWhsBal, UpdItmBasic, **AddItmViaItmTyp, AddItmBasic, AddItmFac, AddItmWhs** | Item master full CRUD | Read transactions cover item search/validation; `UpdItmBasic` covers existing-item changes; **Add* transactions now added — cover new item creation path** |
| MMS310MI | Get, Update | Stock adjustment | Not ECN-related |

**Finding:** PDS (product structure) and MMS025MI (item alias) write transactions were missing. `MMS200MI` Add* transactions were also missing — these are required to create new items in Movex as part of the ECN workflow (Stargile used a manual workaround). All gaps now captured in the matrix below.

---

### Gap Matrix — ECN Required vs Exposed

| MI Program | Transaction | ECN Purpose | Stargile source | Status in movex-rest-api | Sprint priority |
|-----------|-------------|------------|----------------|--------------------------|----------------|
| MMS200MI | AddItmViaItmTyp | Create item master record (MITMAS) using item type template — **preferred path** for new items; pre-populates defaults from item type. Maps to `ecn_items.item_template` (NIATPL). | 2018-04-17 Branko session — Excel upload template with `is_new_item=true`; confirmed as Stargile normalised workaround (engineers manually created item in Movex first) | **MISSING — added to MMS200MI.json** | Sprint 2 blocker |
| MMS200MI | AddItmBasic | Create item master record (MITMAS) without template — fallback when no item type applies | Same source | **MISSING — added to MMS200MI.json** | Sprint 2 blocker |
| MMS200MI | AddItmFac | Create facility-level record (MITFAC) — required after AddItm*; item unusable at facility until this exists | Implicit in Movex item creation sequence | **MISSING — added to MMS200MI.json** | Sprint 2 blocker |
| MMS200MI | AddItmWhs | Create warehouse-level record (MITWHL) — required after AddItmFac for warehouse transactions | Implicit in Movex item creation sequence | **MISSING — added to MMS200MI.json** | Sprint 2 blocker |
| PDS001MI | AddProduct | Create product structure header (MPDHED) in Movex | `BOMService.java` — confirmed | **MISSING** | Sprint 2 blocker |
| PDS002MI | AddComponent | Add BOM line (component + qty + operation) | `BOMService.java` — confirmed | **MISSING** | Sprint 2 blocker |
| PDS002MI | DeleteComponent | Remove BOM line | `BOMService.java` — confirmed | **MISSING** | Sprint 2 blocker |
| PDS002MI | UpdateOperation | Modify routing operation | `BOMService.java` — confirmed | **MISSING** | Sprint 2 blocker |
| PDS002MI | AddOperation | Add new routing step | `BOMService.java` — confirmed | **MISSING** | Sprint 2 blocker |
| PDS002MI | LstOperation | Read current routing ops for a product | Source-analysed + live-tested 2026-05-08 | Call without FDAT and without OPNO — e.g., `LstOperation 100 D <PRNO> 001`. FDAT is a seek position not a filter; passing a date skips earlier records. Verified correct at Scanfil APAC. | Read path |
| MMS025MI | AddAlias | Register MPN (POPN) as item alias in MITPOP | `ItemService.addItemAlias()` — graph analysis §8.2 | **MISSING** | Sprint 2 blocker |
| MPDDOC | `POST /api/ecn/drawing` (custom DB2 endpoint) | Drawing number creation — copy `#TEMPLATE` record | `ItemService.createDwno()` — Stargile source confirmed 2026-05-06 | **MISSING — `@developer-dotnet` to implement** | Sprint 2 blocker |

**New item write sequence (when `ecn_items.is_new_item = TRUE`):**
All steps execute at Status 50 (APPROVED) via the Transactional Outbox in order:
1. `MMS200MI.AddItmViaItmTyp` — create MITMAS record
2. `MMS200MI.AddItmFac` — create MITFAC record for ECN facility
3. `MMS200MI.AddItmWhs` — create MITWHL record for default warehouse
4. `MPDDOC.CreateDrawing` — copy `#TEMPLATE` row in MPDDOC for the drawing number (custom DB2 endpoint; idempotent via WHERE NOT EXISTS)
5. `PDS001MI.AddProduct` — create product structure header
6. `PDS002MI.AddComponent` — BOM lines
7. `MMS025MI.AddAlias` — register MPN

**Why Stargile did not do this:** Engineers manually created the item in Movex first, then referenced it in Stargile. Confirmed in the 2018-04-17 Branko session (timestamp 43:57): *"this is another step where we use a shortcut sometimes by manually creating it in Movex."* This was a normalised workaround, not a named pain point — which is why it was not flagged in the original gap analysis. OSKAR must eliminate this manual step.

**MPDDOC note (resolved 2026-05-06):** `createDwno()` is a raw DB2 `INSERT … SELECT` — there is no MI program. Confirmed via Stargile source (`ItemService.java` lines 116–152) and live DB2 query against CONO=100. The `#TEMPLATE` row exists in `MVXCDTA.MPDDOC`. The `CSYTAB CFI1` template (10-space key) also exists. `@developer-dotnet` must implement `POST /api/ecn/drawing` as a parameterised DB2 query copying all 42 MPDDOC columns from `DODOID='#TEMPLATE'`, substituting `DODOID=<new_dwno>` and `DOCHID=<current_user>`. The `WHERE NOT EXISTS` clause makes it idempotent — safe for outbox retry. Also note: Stargile creates matching `CSYTAB` entries for `CFI1`, `CFI3`, `CFI4` (user-defined field lookups) via the same pattern — include these in the endpoint spec.

**Existing-item change path:** `MMS200MI.UpdItmBasic` (already exposed) covers STAT/ITDS/FUDS/RESP/UNMS updates on items that already exist in Movex. This satisfies the change path for ECN lines where `is_new_item = FALSE`.

---

### Read Operations Available (no gap)

| MI Program | Transaction | Purpose |
|-----------|-------------|---------|
| MMS200MI | GetItmBasic | Validate item exists before ECN references it |
| MMS200MI | GetItmFac | Retrieve facility-specific item data (status, cost) |
| MMS003 | Get | Retrieve unit cost for cost review display |

These cover the **read path** in `src/adapters/erp/movex.py` methods `get_item()` and `search_items()`.

---

### Endpoint Spec for @developer-dotnet (Sprint 2 pre-conditions)

Deliver all of the following to movex-rest-api **before Sprint 2 starts**. Each must follow the existing `transactions/*.json` schema.

#### PDS001MI — AddProduct

```json
{
  "program": "PDS001MI",
  "library": "MVXCOBJ",
  "description": "Product Structure Management — Add Product Header",
  "transactions": [
    {
      "name": "AddProduct",
      "httpMethod": "POST",
      "returnsList": false,
      "fields": [
        { "name": "CONO", "type": "numeric", "length": 3, "required": true, "description": "Company Number (100)" },
        { "name": "FACI", "type": "text", "length": 3, "required": true, "description": "Facility" },
        { "name": "PRNO", "type": "text", "length": 15, "required": true, "description": "Product Number" },
        { "name": "STRT", "type": "text", "length": 3, "required": true, "description": "Product Structure Type" },
        { "name": "ITDS", "type": "text", "length": 30, "required": false, "description": "Product Description" },
        { "name": "ECVE", "type": "text", "length": 4, "required": false, "description": "Revision Number" }
      ],
      "responseFields": [
        { "name": "MSID", "type": "text", "length": 7, "description": "Message ID (blank = success)" },
        { "name": "MSDT", "type": "text", "length": 100, "description": "Error detail" }
      ]
    }
  ]
}
```

#### PDS002MI — AddComponent / DeleteComponent / UpdateOperation / AddOperation

```json
{
  "program": "PDS002MI",
  "library": "MVXCOBJ",
  "description": "Product Structure Management — BOM Component and Routing Operations",
  "transactions": [
    {
      "name": "AddComponent",
      "httpMethod": "POST",
      "returnsList": false,
      "fields": [
        { "name": "CONO", "type": "numeric", "length": 3, "required": true, "description": "Company Number (100)" },
        { "name": "FACI", "type": "text", "length": 3, "required": true, "description": "Facility" },
        { "name": "PRNO", "type": "text", "length": 15, "required": true, "description": "Parent Product Number" },
        { "name": "STRT", "type": "text", "length": 3, "required": true, "description": "Product Structure Type" },
        { "name": "MSEQ", "type": "numeric", "length": 4, "required": true, "description": "Sequence Number" },
        { "name": "OPNO", "type": "numeric", "length": 4, "required": false, "description": "Operation Number" },
        { "name": "MTNO", "type": "text", "length": 15, "required": true, "description": "Component Item Number" },
        { "name": "CNQT", "type": "decimal", "length": 15, "required": true, "description": "Component Quantity" },
        { "name": "FDAT", "type": "numeric", "length": 8, "required": false, "description": "From Date (YYYYMMDD)" }
      ],
      "responseFields": [
        { "name": "MSID", "type": "text", "length": 7, "description": "Message ID" },
        { "name": "MSDT", "type": "text", "length": 100, "description": "Error detail" }
      ]
    },
    {
      "name": "DeleteComponent",
      "httpMethod": "POST",
      "returnsList": false,
      "fields": [
        { "name": "CONO", "type": "numeric", "length": 3, "required": true, "description": "Company Number (100)" },
        { "name": "FACI", "type": "text", "length": 3, "required": true, "description": "Facility" },
        { "name": "PRNO", "type": "text", "length": 15, "required": true, "description": "Parent Product Number" },
        { "name": "STRT", "type": "text", "length": 3, "required": true, "description": "Product Structure Type" },
        { "name": "MSEQ", "type": "numeric", "length": 4, "required": true, "description": "Sequence Number" }
      ],
      "responseFields": [
        { "name": "MSID", "type": "text", "length": 7, "description": "Message ID" },
        { "name": "MSDT", "type": "text", "length": 100, "description": "Error detail" }
      ]
    },
    {
      "name": "UpdateOperation",
      "httpMethod": "POST",
      "returnsList": false,
      "fields": [
        { "name": "CONO", "type": "numeric", "length": 3, "required": true, "description": "Company Number (100)" },
        { "name": "FACI", "type": "text", "length": 3, "required": true, "description": "Facility" },
        { "name": "PRNO", "type": "text", "length": 15, "required": true, "description": "Product Number" },
        { "name": "STRT", "type": "text", "length": 3, "required": true, "description": "Product Structure Type" },
        { "name": "OPNO", "type": "numeric", "length": 4, "required": true, "description": "Operation Number" },
        { "name": "PLGR", "type": "text", "length": 8, "required": false, "description": "Work Centre" },
        { "name": "PITI", "type": "decimal", "length": 9, "required": false, "description": "Run Time (minutes)" }
      ],
      "responseFields": [
        { "name": "MSID", "type": "text", "length": 7, "description": "Message ID" },
        { "name": "MSDT", "type": "text", "length": 100, "description": "Error detail" }
      ]
    },
    {
      "name": "AddOperation",
      "httpMethod": "POST",
      "returnsList": false,
      "fields": [
        { "name": "CONO", "type": "numeric", "length": 3, "required": true, "description": "Company Number (100)" },
        { "name": "FACI", "type": "text", "length": 3, "required": true, "description": "Facility" },
        { "name": "PRNO", "type": "text", "length": 15, "required": true, "description": "Product Number" },
        { "name": "STRT", "type": "text", "length": 3, "required": true, "description": "Product Structure Type" },
        { "name": "OPNO", "type": "numeric", "length": 4, "required": true, "description": "Operation Number" },
        { "name": "PLGR", "type": "text", "length": 8, "required": false, "description": "Work Centre" },
        { "name": "PITI", "type": "decimal", "length": 9, "required": false, "description": "Run Time (minutes)" }
      ],
      "responseFields": [
        { "name": "MSID", "type": "text", "length": 7, "description": "Message ID" },
        { "name": "MSDT", "type": "text", "length": 100, "description": "Error detail" }
      ]
    }
  ]
}
```

#### MMS025MI — AddAlias

```json
{
  "program": "MMS025MI",
  "library": "MVXCOBJ",
  "description": "Item Alias Management — Register MPN as item alias in MITPOP",
  "transactions": [
    {
      "name": "AddAlias",
      "httpMethod": "POST",
      "returnsList": false,
      "fields": [
        { "name": "CONO", "type": "numeric", "length": 3, "required": true, "description": "Company Number (100)" },
        { "name": "ALWT", "type": "numeric", "length": 2, "required": true, "description": "Alias Type (qualifier category)" },
        { "name": "ALWQ", "type": "text", "length": 4, "required": true, "description": "Alias Qualifier" },
        { "name": "ITNO", "type": "text", "length": 15, "required": true, "description": "Item Number" },
        { "name": "POPN", "type": "text", "length": 30, "required": true, "description": "Manufacturer Part Number" },
        { "name": "E0PA", "type": "text", "length": 3, "required": false, "description": "Partner alias type (supplier identifier)" }
      ],
      "responseFields": [
        { "name": "MSID", "type": "text", "length": 7, "description": "Message ID (blank = success)" },
        { "name": "MSDT", "type": "text", "length": 100, "description": "Error detail" }
      ]
    }
  ]
}
```

#### MPDDOC — Drawing number creation (custom DB2 endpoint — resolved 2026-05-06)

**Confirmed:** No MI program exists for MPDDOC. Implement `POST /api/ecn/drawing` as a custom DB2 endpoint.

**SQL to execute** (parameterised — do not use string concatenation):

```sql
INSERT INTO MVXCDTA.MPDDOC (
    DOCONO, DODOID, DODOTY, DOADS1, DOAISB, DODNUM, DOADOB,
    DODOSS, DODOFM, DOLNCD, DODATE, DOECMA, DOECVE, DOECAC, DODODE,
    DOASBJ, DOASB2, DODOME, DOFIOF, DOFUNC, DOSTNC, DODGRP, DOMDOC,
    DODAUT, DODINT, DORESP, DODEPT, DOAREG, DOAISD, DOAEDT, DOAED2,
    DOCOPY, DOITNO, DOARVS, DOACPL, DOFACI, DOTXID, DORGDT, DORGTM,
    DOLMDT, DOCHNO, DOCHID
)
SELECT
    DOCONO, @dwno, DODOTY, DOADS1, DOAISB, DODNUM, DOADOB,
    DODOSS, DODOFM, DOLNCD, DODATE, DOECMA, DOECVE, DOECAC, DODODE,
    DOASBJ, DOASB2, DODOME, DOFIOF, DOFUNC, DOSTNC, DODGRP, DOMDOC,
    DODAUT, DODINT, DORESP, DODEPT, DOAREG, DOAISD, DOAEDT, DOAED2,
    DOCOPY, DOITNO, DOARVS, DOACPL, DOFACI, DOTXID, DORGDT, DORGTM,
    DOLMDT, DOCHNO, @usid
FROM MVXCDTA.MPDDOC AS T1
WHERE T1.DOCONO = @cono
  AND T1.DODOID = '#TEMPLATE'
  AND NOT EXISTS (
      SELECT 1 FROM MVXCDTA.MPDDOC AS T2
      WHERE T2.DOCONO = T1.DOCONO AND T2.DODOID = @dwno
  )
```

**Request body:**

```json
{
  "cono": 100,
  "dwno": "LF-AB-IC-0001",
  "itno": "LF-AB-IC-0001",
  "usid": "dc_user"
}
```

**Response:** HTTP 200 `{ "created": true }` if row inserted, `{ "created": false }` if already existed (idempotent — safe for outbox retry). HTTP 500 on DB2 error with detail.

**Pre-condition check** (run once at startup, not per request): `SELECT COUNT(*) FROM MVXCDTA.MPDDOC WHERE DOCONO = @cono AND DODOID = '#TEMPLATE'` must return 1. If 0, the template is missing — alert and refuse all drawing creation requests.

**Also required — CSYTAB CFI1 entry** (same pattern, `CTSTCO='CFI1'`, template key = 10 spaces). Implement as `POST /api/ecn/drawing/cfi1` or fold into the drawing endpoint as a second DB2 statement. Confirmed present in CONO=100.

---

## 7. MITPOP Reverse Alias Lookup — Custom DB2 Endpoint (Sprint 3, S3-1)

**Finding (2026-05-11):** No M3 MI program supports reverse alias lookup (POPN → ITNO).
- `MMS025MI.GetAlias` input: CONO + ALWT + ITNO + ALWQ + E0PA + VFDT — ITNO-first, not usable.
- `MMS025MI.LstAlias` input: CONO + ITNO — also ITNO-first.
- `MMS001MI` not enabled at Scanfil APAC.
- Stargile never implemented reverse lookup either — `RequestECNDBHelper.java:313` comment from 2008: *"So far, this value is not retrieved."*

**Solution:** Custom parameterised DB2 endpoint on movex-rest-api, same pattern as `POST /api/ecn/drawing`.

### Endpoint Spec for @developer-dotnet (Sprint 3 pre-condition)

**`GET /api/mitpop/search`**

```
Query params:
  cono  int     required  Company number (from MOVEX_CONO env var)
  popn  string  required  Customer/manufacturer part number — max 30 chars
  e0pa  string  optional  Customer/partner code — narrows results when provided
```

**SQL to execute** (parameterised — never string-concatenated):

```sql
SELECT TRIM(MPITNO) AS ITNO,
       TRIM(MPPOPN) AS POPN,
       TRIM(MPALWT) AS ALWT,
       TRIM(MPALWQ) AS ALWQ,
       TRIM(MPE0PA)  AS E0PA
FROM MVXCDTA.MITPOP
WHERE MPCONO = @cono
  AND MPPOPN = @popn
  AND (@e0pa IS NULL OR MPE0PA = @e0pa)
ORDER BY MPITNO
```

**Response:** `{ "data": { "records": [ { "ITNO": "...", "POPN": "...", "ALWT": "...", "ALWQ": "...", "E0PA": "..." } ] } }`

Empty `records: []` when POPN has no alias — never a 404. HTTP 500 on DB2 error with detail.

**OSKAR consumption:** `MovexRestAdapter.lookup_by_alias()` → `src/adapters/erp/movex.py`.
Response mapped to `full_match` / `partial_match` / `no_match` in `src/routers/parts.py`.
Endpoint: `GET /api/v1/parts/alias?popn=&cuno=`. 34 tests passing as of 2026-05-11.

**Pre-condition check** (startup): confirm `MVXCDTA.MITPOP` is accessible from the DB2 connection.

---

## 8. SSoT Rules for AI Suggestions

When an AI agent makes a suggestion that involves item data, BOM data, or supplier data:

1. Always fetch current state from Movex via adapter before reasoning about it.
2. Never present cached OSKAR data as current Movex state without a freshness timestamp.
3. Any suggested change to Movex data must be flagged as requiring human approval before submission.
4. The SHA-256 audit chain records: agent suggestion → human decision → Movex commit. All three links must be present.
