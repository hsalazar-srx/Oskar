# Skill: /oskar-movex-authority
**Tier:** 1 — ERP reference
**MAS skills:** `integration/m3-transaction-builder`, `integration/m3-response-parser`, `knowledge/m3-documentation`

## Purpose
Quick-reference for Movex/M3 facts relevant to OSKAR. Applies MAS M3 skills scoped to
OSKAR adapter and audit chain design. Always refers back to `ai/memory/02-movex-erp-authority.md`.

## When to Invoke
- Designing or reviewing the `MovexRestAdapter` implementation
- Writing DB2 queries for OSKAR data migration or gap analysis
- Checking M3 table/field names before using them in code
- Verifying SSoT rules before suggesting any Movex write operation

## Quick Reference

**Connection:** CONO=100, schema=MVXCOBJ, IBM i 7.4
**Adapter path:** `src/adapters/erp/movex.py` → calls `movex-rest-api` at `/api`

**Tables most relevant to OSKAR ECN module:**
- `MPDOCHEAD` — ECN header (DOID, DOTY, STAT)
- `MPDOCLINE` — ECN line items
- `MMBILL` / `MMBILLDET` — BOM header / lines
- `MITMAS` — Item master (MMITNO, MMITDS, MMITCL)

**Field rules (always apply):**
- Date fields: numeric YYYYMMDD — never SQL DATE
- Text fields: fixed-width — always TRIM()
- Every query: CONO=100 in WHERE clause

**SSoT rules:**
- Read from Movex first; never trust OSKAR cache as current state without freshness check
- Any suggested Movex write → flag `[HUMAN APPROVAL REQUIRED]`
- All Movex writes → SHA-256 audit chain entry required

## IFSAdapter Reminder
IFSAdapter is a stub in OSKAR v1. Do not design against IFS field names or semantics.
Karen confirmed 2026-04-07: IFS is out of scope for v1.
