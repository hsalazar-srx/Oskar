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
| MMS200MI | GetItmBasic, GetItmFac, LstItmFac, GetItmWhsBal, UpdItmBasic | Item master read + basic update | **Partially useful** — `GetItmBasic` feeds item search; `UpdItmBasic` could update STAT/ITDS/FUDS/RESP/UNMS on item change |
| MMS310MI | Get, Update | Stock adjustment | Not ECN-related |

**Finding:** None of the 4 exposed programs cover product structure (PDS) or item alias (MMS025MI) operations. All 7 ECN write transactions are missing.

---

### Gap Matrix — ECN Required vs Exposed

| MI Program | Transaction | ECN Purpose | Stargile source | Status in movex-rest-api | Sprint priority |
|-----------|-------------|------------|----------------|--------------------------|----------------|
| PDS001MI | AddProduct | Create new product/item header in Movex at APPROVED→IMPLEMENTED | `BOMService.java` — confirmed | **MISSING** | Sprint 2 blocker |
| PDS002MI | AddComponent | Add BOM line (component + qty + operation) | `BOMService.java` — confirmed | **MISSING** | Sprint 2 blocker |
| PDS002MI | DeleteComponent | Remove BOM line | `BOMService.java` — confirmed | **MISSING** | Sprint 2 blocker |
| PDS002MI | UpdateOperation | Modify routing operation | `BOMService.java` — confirmed | **MISSING** | Sprint 2 blocker |
| PDS002MI | AddOperation | Add new routing step | `BOMService.java` — confirmed | **MISSING** | Sprint 2 blocker |
| MMS025MI | AddAlias | Register MPN (POPN) as item alias in MITPOP | `ItemService.addItemAlias()` — graph analysis §8.2 | **MISSING** | Sprint 2 blocker |
| MPDDOC | (see note) | Drawing number creation — copy `#TEMPLATE` record | `ItemService.createDwno()` — graph analysis §8.1 | **MISSING — may not be an MI program** | Sprint 2 blocker |

**MPDDOC note:** `createDwno()` copies a `#TEMPLATE` record in the MPDDOC table. This is likely a direct DB2 operation (`PreparedStatementHelper` pattern confirmed in Stargile source), not an MI API call. The `@developer-dotnet` team must confirm: is there an MI program for MPDDOC manipulation, or does movex-rest-api need a custom DB2 endpoint? Flag as investigation item before Sprint 2 design.

**Partial coverage note:** `MMS200MI.UpdItmBasic` is already exposed and covers status, description, and responsible-engineer updates on existing items. This may satisfy the "change item" path for items that already exist in Movex (OSKAR ECN scope: only new items go through `PDS001MI.AddProduct`). Confirm with Branko post-POC.

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

#### MPDDOC — Drawing number creation (investigation required)

**Action for @developer-dotnet:** Determine whether MPDDOC manipulation is exposed via an MI API program or requires a custom DB2 query endpoint. Stargile uses `ItemService.createDwno()` which copies a `#TEMPLATE` record via `PreparedStatementHelper` — this suggests direct DB2, not MI. If confirmed, add a custom `/api/ecn/drawing` endpoint to movex-rest-api that wraps the DB2 INSERT. Deliver finding before Sprint 2 design session.

---

## 7. SSoT Rules for AI Suggestions

When an AI agent makes a suggestion that involves item data, BOM data, or supplier data:

1. Always fetch current state from Movex via adapter before reasoning about it.
2. Never present cached OSKAR data as current Movex state without a freshness timestamp.
3. Any suggested change to Movex data must be flagged as requiring human approval before submission.
4. The SHA-256 audit chain records: agent suggestion → human decision → Movex commit. All three links must be present.
