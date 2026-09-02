-- ============================================================================
-- Find a safe throwaway BOM line in CONO=300 for the FDAT=0 delete test
--
-- scripts/verify_delete_fdat_zero.py --destructive removes a real MPDMAT line
-- and does not put it back. These queries find a line where that is low-risk,
-- and give you the values to restore it afterwards.
--
-- What makes a line safe to delete:
--   1. CONO=300 (dev/UAT), never 100.
--   2. FDAT = 0 — the whole point; a line with a real date tests nothing.
--   3. The parent is obsolete or a test item — no live production depends on it.
--   4. No open manufacturing orders against the parent.
--   5. The parent is NOT on an active Oskar ECN (check that separately in the
--      Oskar DB — query at the bottom).
--
-- ── TWO THINGS THAT WASTED HOURS. READ BEFORE WRITING ANY QUERY HERE. ──────
--
-- 1. SCHEMA IS PER-COMPANY.
--        CONO 100 (production) -> MVXCDTA
--        CONO 300 (dev/UAT)    -> MVXC300
--    Source: movex-rest-api Db2Settings.cs (SchemaCmp100 / SchemaCmp300) and
--    Db2QueryService.ResolveSchema(). Stargile's custom tables follow the same
--    pattern: COMCDTA100 / COMCDTA300.
--
-- 2. PMCONO MUST BE COMPARED AS A STRING: PMCONO = '300', NOT PMCONO = 300.
--    A numeric literal silently matches NOTHING. The API binds it as a string
--    parameter (Db2QueryService.cs — `cono` is a C# string), which is why the
--    same logical query works there and returned empty by hand.
--
--    Confirmed 2026-09-01: SELECT PMCONO, COUNT(*) FROM MVXC300.MPDMAT
--    GROUP BY PMCONO  ->  300, 530632 rows.
--
--    Every "CONO=300 returns nothing" result during the ECN-2026-D-0021
--    investigation was this, including one that led to a wrong conclusion
--    that UAT was reading production. The data was always there.
--
-- Column prefixes: MPDMAT -> PM, MPDHED -> PH, MITMAS -> MM
-- All READ-ONLY.
-- ============================================================================


-- ---------------------------------------------------------------------------
-- Q0. Sanity check — confirms the schema and the string comparison.
--
-- Expect a non-zero count (530,632 as of 2026-09-01). If this returns 0, stop
-- and re-read the two notes above before going further.
-- ---------------------------------------------------------------------------
SELECT COUNT(*) AS cono300_lines
FROM MVXC300.MPDMAT WHERE PMCONO = '300';


-- ---------------------------------------------------------------------------
-- Q1. Obsolete parents with FDAT=0 lines — the best candidates.
--
-- M3 marks obsolete items with status 90 in MITMAS (MMSTAT). An obsolete
-- parent's BOM is not used for anything live, so removing a line from it is
-- about as safe as a destructive test gets.
--
-- Ordered by line count descending: a bigger BOM means removing one line
-- matters even less, and gives you spares if the first attempt is messy.
-- ---------------------------------------------------------------------------
SELECT
    TRIM(m.PMPRNO)                                   AS parent,
    TRIM(i.MMITDS)                                   AS description,
    i.MMSTAT                                         AS item_status,
    COUNT(*)                                         AS total_lines,
    SUM(CASE WHEN m.PMFDAT = 0 THEN 1 ELSE 0 END)    AS zero_fdat_lines
FROM MVXC300.MPDMAT m
JOIN MVXC300.MITMAS i
  ON  i.MMCONO = m.PMCONO
  AND TRIM(i.MMITNO) = TRIM(m.PMPRNO)
WHERE m.PMCONO = '300'
  AND TRIM(m.PMFACI) = 'D'
  AND i.MMSTAT = '90'                    -- 90 = obsolete
GROUP BY m.PMPRNO, i.MMITDS, i.MMSTAT
HAVING SUM(CASE WHEN m.PMFDAT = 0 THEN 1 ELSE 0 END) > 0
ORDER BY zero_fdat_lines DESC
FETCH FIRST 20 ROWS ONLY;


-- ---------------------------------------------------------------------------
-- Q2. Parents whose DESCRIPTION marks them obsolete or test.
--
-- Catches items flagged in text rather than status — EP00002's own
-- description is "*Obsolete* ADL REV F 10.1", so this pattern is in use here.
-- Run alongside Q1; an item matching both is the strongest candidate.
-- ---------------------------------------------------------------------------
SELECT
    TRIM(m.PMPRNO)                                   AS parent,
    TRIM(i.MMITDS)                                   AS description,
    i.MMSTAT                                         AS item_status,
    COUNT(*)                                         AS total_lines,
    SUM(CASE WHEN m.PMFDAT = 0 THEN 1 ELSE 0 END)    AS zero_fdat_lines
FROM MVXC300.MPDMAT m
JOIN MVXC300.MITMAS i
  ON  i.MMCONO = m.PMCONO
  AND TRIM(i.MMITNO) = TRIM(m.PMPRNO)
WHERE m.PMCONO = '300'
  AND TRIM(m.PMFACI) = 'D'
  AND (   UPPER(i.MMITDS) LIKE '%OBSOLETE%'
       OR UPPER(i.MMITDS) LIKE '%TEST%'
       OR UPPER(i.MMITDS) LIKE '%DUMMY%'
       OR UPPER(i.MMITDS) LIKE '%SCRAP%')
GROUP BY m.PMPRNO, i.MMITDS, i.MMSTAT
HAVING SUM(CASE WHEN m.PMFDAT = 0 THEN 1 ELSE 0 END) > 0
ORDER BY zero_fdat_lines DESC
FETCH FIRST 20 ROWS ONLY;


-- ---------------------------------------------------------------------------
-- Q3. SAFETY CHECK — no open manufacturing orders against the candidate.
--
-- An open MO means someone may still be building this, and deleting a
-- component line could disturb a live order. Substitute your candidate.
-- Expect 0 rows.
--
-- MWOHED = work order header. Status < 90 is roughly "not closed"; confirm
-- the exact status semantics with the M3 admin if this returns anything.
-- ---------------------------------------------------------------------------
SELECT
    VHCONO  AS cono,
    VHFACI  AS faci,
    TRIM(VHPRNO) AS parent,
    VHMFNO  AS mo_number,
    VHWHST  AS status
FROM MVXC300.MWOHED
WHERE VHCONO = '300'
  AND TRIM(VHPRNO) = 'PUT_CANDIDATE_HERE'
  AND VHWHST < '90';


-- ---------------------------------------------------------------------------
-- Q4. THE RESTORE SCRIPT — capture these values BEFORE deleting.
--
-- Everything AddComponent needs to put the line back. Save the output
-- somewhere outside the terminal before running anything destructive.
-- ---------------------------------------------------------------------------
SELECT
    PMCONO        AS cono,
    TRIM(PMFACI)  AS faci,
    TRIM(PMPRNO)  AS prno,
    TRIM(PMSTRT)  AS strt,
    PMMSEQ        AS mseq,
    TRIM(PMMTNO)  AS mtno,
    PMOPNO        AS opno,
    PMCNQT        AS cnqt,
    TRIM(PMPEUN)  AS peun,
    PMFDAT        AS fdat,
    PMTDAT        AS tdat
FROM MVXC300.MPDMAT
WHERE PMCONO = '300'
  AND TRIM(PMPRNO) = 'PUT_CANDIDATE_HERE'
  AND TRIM(PMFACI) = 'D'
  AND PMFDAT = 0
ORDER BY PMMSEQ;


-- ---------------------------------------------------------------------------
-- Q5. Pick the least-connected line on the candidate.
--
-- Prefer deleting a component used in FEW other BOMs — if something goes
-- wrong, the blast radius is smaller. This counts where else each component
-- of your candidate appears across CONO=300.
-- ---------------------------------------------------------------------------
SELECT
    m.PMMSEQ                AS mseq,
    TRIM(m.PMMTNO)          AS component,
    m.PMFDAT                AS fdat,
    (SELECT COUNT(*)
       FROM MVXC300.MPDMAT x
      WHERE x.PMCONO = '300'
        AND TRIM(x.PMMTNO) = TRIM(m.PMMTNO)) AS used_in_n_bom_lines
FROM MVXC300.MPDMAT m
WHERE m.PMCONO = '300'
  AND TRIM(m.PMPRNO) = 'PUT_CANDIDATE_HERE'
  AND TRIM(m.PMFACI) = 'D'
  AND m.PMFDAT = 0
ORDER BY used_in_n_bom_lines ASC, m.PMMSEQ
FETCH FIRST 10 ROWS ONLY;


-- ============================================================================
-- FINALLY — check the candidate is not on an active Oskar ECN.
-- Run this against the OSKAR POSTGRES DB (10.131.1.10:5433/oskar_staging),
-- not DB2. Expect zero rows.
--
--   SELECT e.ecn_number, e.status, e.title
--   FROM ecn_instances e
--   LEFT JOIN ecn_items i        ON i.ecn_id = e.id
--   LEFT JOIN ecn_bom_changes b  ON b.ecn_id = e.id
--   WHERE (i.item_number = 'PUT_CANDIDATE_HERE'
--          OR b.parent_item_number = 'PUT_CANDIDATE_HERE')
--     AND e.status < 90;
-- ============================================================================
