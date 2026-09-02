# Querying M3 DB2 by hand — two things that silently return nothing

Both cost hours during the ECN-2026-D-0021 investigation (2026-08-31 →
2026-09-01). Neither raises an error. Both just return an empty result set,
which reads exactly like "the data is not there".

> **Canonical source:** Knowledge-Management vault —
> `learnings/cross-project/db2-cono-must-be-compared-as-string-and-schema-is-per-company.md`
> and `m3-knowledge/tables/movex-db2-schema-company-mapping.md`.
> Also encoded in the `expert-db2-iseries` MAS agent (v1.1) so generated
> queries carry the rules. This page is the Oskar-local quick reference.

---

## 1. The schema is per-company

| CONO | Purpose | M3 schema | Stargile custom tables |
|------|---------|-----------|------------------------|
| 100  | Production | `MVXCDTA` | `COMCDTA100` |
| 300  | Dev / UAT  | `MVXC300` | `COMCDTA300` |

Querying `MVXCDTA` for CONO=300 data returns nothing — that library holds
company 100 only.

**Verified against source:** `movex-rest-api/Infrastructure/Configuration/Db2Settings.cs`
(`SchemaCmp100` / `SchemaCmp300`), resolved at runtime by
`Services/Db2QueryService.ResolveSchema(cono)`.

---

## 2. `CONO` must be compared as a **string**

```sql
-- WRONG — silently matches nothing
SELECT COUNT(*) FROM MVXC300.MPDMAT WHERE PMCONO = 300;

-- RIGHT
SELECT COUNT(*) FROM MVXC300.MPDMAT WHERE PMCONO = '300';
```

Confirmed 2026-09-01:

```sql
SELECT PMCONO, COUNT(*) FROM MVXC300.MPDMAT GROUP BY PMCONO;
-- 300, 530632
```

movex-rest-api gets this right by accident of typing — `cono` is a C# `string`
throughout `Db2QueryService`, so ODBC binds it as a character parameter. A
hand-written numeric literal does not match. Applies to every `*CONO` column.

---

## Why this matters beyond convenience

During the ECN-2026-D-0021 investigation, an empty `CONO=300` result was read
as evidence that item EP00002 did not exist in the UAT company. Since Oskar had
demonstrably read a 66-line BOM for it, the apparent contradiction led to the
conclusion that **UAT must be reading production** — which prompted an urgent
check of the staging VM's `MOVEX_CONO`, correctly set to `300` all along.

Both traps were active at once: wrong schema *and* numeric CONO.

**The lesson worth keeping:** an empty result from a hand-written DB2 query is
weak evidence. Before concluding anything from one, prove the query can find
*anything*:

1. Drop every predicate, `SELECT COUNT(*)` — does the table hold rows at all?
2. `GROUP BY` the column you are filtering on — what values does it actually
   hold, and in what type?
3. Add predicates back one at a time.

A query returning zero because of a type mismatch is indistinguishable from one
returning zero because the data is absent.

---

## Working template

```sql
SELECT PMMSEQ, TRIM(PMMTNO) AS component, PMOPNO, PMCNQT, PMFDAT, PMTDAT
FROM MVXC300.MPDMAT              -- MVXCDTA for CONO 100
WHERE PMCONO = '300'             -- STRING, not numeric
  AND TRIM(PMPRNO) = 'EP00002'   -- TRIM: fixed-width CHAR
  AND TRIM(PMFACI) = 'D'
  AND TRIM(PMSTRT) = '001'
ORDER BY PMMSEQ;
```

`TRIM()` on text predicates was already in the workspace standards (M3 text
columns are fixed-width CHAR, padded with trailing blanks — `'D  '`,
`'EP00002        '`). The two above were not.

---

## Related

- `docs/runbooks/find-throwaway-bom.sql` — uses the corrected schema and comparison
- `scripts/verify_delete_fdat_zero.py` — live probe for the FDAT=0 delete question
- `docs/movex-rest-api-bom-contract.md` — B-1/B-2/B-3 endpoint contracts
