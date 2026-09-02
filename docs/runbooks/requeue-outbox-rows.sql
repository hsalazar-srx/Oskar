-- ============================================================================
-- Requeue abandoned / failed movex_outbox rows (ECN-2026-D-0021)
--
-- Run against the OSKAR STAGING POSTGRES:
--     psql -h 10.131.1.10 -p 5433 -U oskar -d oskar_staging
--   (or on the VM:  docker exec -it oskar-db-staging psql -U oskar -d oskar_staging)
--
-- PREREQUISITE — the worker must be running the FDAT fix. Requeuing before
-- that replays the identical broken payload and burns another 10 attempts:
--
--     sudo docker exec oskar-worker-staging python -c \
--       "from src.adapters.erp.movex import MovexHTTPError; print('fix is live')"
--
-- Confirmed live 2026-09-02.
--
-- WHY THIS WORKS: mi_params stores the AUTHORED change, not the wire payload.
-- The adapter rebuilds the actual MI request at dispatch time, so the fixed
-- code (omit a zero FDAT on Delete) applies to these existing rows with no
-- data edit needed. Do NOT hand-edit mi_params.
-- ============================================================================


-- ---------------------------------------------------------------------------
-- Q1. Look before you touch. Current state of everything not completed.
-- ---------------------------------------------------------------------------
SELECT o.id,
       o.mi_transaction,
       o.state,
       o.attempt_count,
       o.depends_on,
       o.mi_params ->> 'component_item'  AS component,
       o.mi_params ->> 'sequence_number' AS mseq,
       o.mi_params ->> 'from_date'       AS fdat,
       left(coalesce(o.last_error, ''), 90) AS last_error
FROM movex_outbox o
JOIN ecn_instances e ON e.id = o.ecn_id
WHERE o.state <> 'completed'
ORDER BY o.created_at;


-- ---------------------------------------------------------------------------
-- Q2. START HERE — requeue ONE row and watch it.
--
-- 46d57494-4c93-4b03-8d93-1d3eb363f71f is the best first candidate:
--   PDS002MI.Delete, component 2700361, MSEQ 20, FDAT=0
--   depends_on IS NULL  -> nothing gates it, nothing is gated on it
--   It is the plain DELETE change type, the simplest of the three shapes.
--
-- Learn from one failure, not five.
-- ---------------------------------------------------------------------------
UPDATE movex_outbox
SET state          = 'pending',
    attempt_count  = 0,
    next_retry_at  = NULL,      -- else the dispatcher waits out the old backoff
    last_error     = NULL
WHERE id = '46d57494-4c93-4b03-8d93-1d3eb363f71f'
  AND state IN ('abandoned', 'failed');   -- guard: never touch a completed row


-- ---------------------------------------------------------------------------
-- Q3. Watch it. Re-run every few seconds.
--
-- 'completed'  -> the fix works. Proceed to Q4.
-- 'failed'     -> READ last_error. It now carries M3's real message (the
--                 error-capture fix), so it will say WHY rather than just 422.
-- unchanged    -> the worker is not picking it up; check the beat/worker logs.
-- ---------------------------------------------------------------------------
SELECT id, mi_transaction, state, attempt_count,
       last_error, completed_at
FROM movex_outbox
WHERE id = '46d57494-4c93-4b03-8d93-1d3eb363f71f';


-- ---------------------------------------------------------------------------
-- Q4. Only after Q2 completes successfully — requeue the rest.
--
-- Dependency ordering is handled for you: two AddComponent rows carry
-- depends_on pointing at their Delete, and the dispatcher will not run a row
-- whose dependency has not completed. Resetting them all at once is safe.
--
-- Note 69a577ce (AddComponent, MSEQ 210) shows attempt_count=0 but state
-- 'abandoned' — it was abandoned BECAUSE its dependency ca25fd54 was, not on
-- its own merit. It never actually ran.
-- ---------------------------------------------------------------------------
UPDATE movex_outbox
SET state          = 'pending',
    attempt_count  = 0,
    next_retry_at  = NULL,
    last_error     = NULL
WHERE state IN ('abandoned', 'failed')
  AND ecn_id = (SELECT id FROM ecn_instances WHERE ecn_number = 'ECN-2026-D-0021');


-- ---------------------------------------------------------------------------
-- Q5. Watch the whole set.
-- ---------------------------------------------------------------------------
SELECT o.mi_transaction,
       o.state,
       o.attempt_count,
       o.mi_params ->> 'component_item' AS component,
       left(coalesce(o.last_error, ''), 120) AS last_error
FROM movex_outbox o
JOIN ecn_instances e ON e.id = o.ecn_id
WHERE e.ecn_number = 'ECN-2026-D-0021'
ORDER BY o.created_at;


-- ---------------------------------------------------------------------------
-- Q6. Verify against M3, not against Oskar's own state.
--
-- 'completed' means the MI call returned success. Confirm the BOM actually
-- changed by reading it back — the UpdateComponent/TDAT bug (I2-19) is the
-- precedent for a write that reports success and does not persist:
--
--   GET http://srxwebapp1.srxglobal.com:5001/api/bom/EP00002?cono=300&faci=D&strt=001
--
-- Expect after a full successful run:
--   MSEQ  20 (2700361) gone           <- DELETE
--   MSEQ 210 (1200665) qty 6 -> 2     <- CHANGE (delete + re-add)
--   MSEQ 460 (1200735) qty 3 -> 5     <- CHANGE
--   MSEQ  25 (LFMT120001) present     <- ADD
-- ---------------------------------------------------------------------------


-- ============================================================================
-- ONE OPEN QUESTION BEFORE Q4
--
-- The AddComponent rows carry from_date = NULL. The FDAT fix covers Delete;
-- whether AddComponent accepts a null FDAT has NOT been verified. If those
-- rows fail where the Deletes succeed, that is the reason, and last_error
-- will now say so.
--
-- ALSO WORTH A THOUGHT: this ECN is titled "TEST - MOTEC EP00002 ADL REV F
-- 10.1 to REV G11.2". Replaying it makes REAL changes to EP00002's BOM in
-- CONO=300. Fine if that is intended; worth a moment if it only ever existed
-- to exercise the workflow.
-- ============================================================================
