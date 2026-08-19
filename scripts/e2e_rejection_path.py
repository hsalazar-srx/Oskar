#!/usr/bin/env python
"""
OSKAR — end-to-end rejection path: a rejected ECN must write NOTHING to M3.

Why this is a separate check from the happy path
------------------------------------------------
`scripts/e2e_s3_ordering_proof.py` proves the happy path: an approved ECN's
writes reach M3, correctly ordered. This proves the complementary — and
arguably more important — property: an ECN that is rejected, or that is still
mid-workflow, must produce **no Movex writes at all**.

The failure this guards against is the worst kind for UAT trust: a change the
business explicitly *rejected* silently appearing in the ERP anyway. Unlike a
failed write (loud, retried, alerted), a spurious write is silent and lands in
real production data. Nothing in the suite asserted this end-to-end.

Three states are checked, each with real workflow transitions:

  1. DRAFT / mid-workflow  — writes queue ONLY at dc_approve, so an ECN that
     has been submitted but not DC-approved must have an empty outbox.
  2. REJECTED              — rejecting at MANAGEMENT_REVIEW must leave the
     outbox empty and M3 untouched.
  3. Resubmit -> approve   — the same ECN, after rework, MUST then write.
     Without this third step the first two would pass trivially if writes were
     broken entirely (asserting "nothing happened" is only meaningful if you
     also prove the thing CAN happen).

M3 state is compared before and after, so the assertion is against the ERP
itself rather than against Oskar's own bookkeeping.

Safety
------
* CONO=300 only — hard guard (CONO=100 is production).
* The approve step at the end DOES write to M3; it is cleaned up in a finally
  block and the baseline is re-verified.

Usage
-----
    python scripts/e2e_rejection_path.py

Exit codes: 0 = pass, 1 = failure, 2 = refused (unsafe config / prerequisites).
"""
from __future__ import annotations

import asyncio
import os
import sys
import time
import traceback
import uuid
from typing import Any

import psycopg2
import psycopg2.extras

TARGET_ITEM = "LFAM050001"
FACILITY = "D"
STRUCTURE_TYPE = "001"

# Throwaway ids, outside the real ranges on this item.
NEW_MSEQ = 887
COMPONENT = "LFAM700006"
FROM_DATE = 20260901
OPNO_EXISTING = 190          # a REAL, pre-existing operation on this item, so
                             # this test exercises the ordinary BOM-only case
                             # rather than S-3's new-operation dependency.
REQUIRED_CONO = "300"

WORKER_TIMEOUT = 90
POLL = 1.0


def _ok(m: str) -> None: print(f"  [ OK ] {m}", flush=True)
def _step(m: str) -> None: print(f"  [ .. ] {m}", flush=True)
def _fail(m: str) -> None: print(f"  [FAIL] {m}", flush=True)


class Refused(RuntimeError):
    """Prerequisites not met."""


class ProofFailed(AssertionError):
    """The end-to-end behaviour is wrong."""


def _dsn() -> str:
    raw = os.environ.get(
        "DATABASE_URL", "postgresql://oskar:oskar_dev@oskar-test-db:5432/oskar_test"
    )
    return (
        raw.replace("postgresql+asyncpg://", "postgresql://")
        .replace("postgresql+psycopg2://", "postgresql://")
        .split("?")[0]
    )


def _conn() -> Any:
    c = psycopg2.connect(_dsn())
    c.autocommit = True
    c.cursor_factory = psycopg2.extras.RealDictCursor
    return c


def _sa_text(s: str):
    import sqlalchemy as sa
    return sa.text(s)


async def _m3_bom_mseqs() -> list[int]:
    from src.adapters.erp.movex import MovexRestAdapter
    a = MovexRestAdapter()
    await a.open()
    try:
        bom = await a.get_bom(TARGET_ITEM, FACILITY, structure_type=STRUCTURE_TYPE)
        recs = (bom.get("data") or {}).get("records") or []
        out = []
        for r in recs:
            mseq = r.get("MSEQ", r.get("mseq"))
            tdat = int(r.get("TDAT", r.get("tdat", 99999999)))
            if tdat == 99999999:
                out.append(int(mseq))
        return sorted(out)
    finally:
        await a.close()


async def _m3_cleanup() -> None:
    """Delete the throwaway BOM line, retrying and tolerating 'does not exist'."""
    from src.adapters.erp.movex import MovexRestAdapter
    for attempt in range(3):
        a = MovexRestAdapter()
        await a.open()
        try:
            resp = await a._post(
                "/PDS002MI/Delete",
                json={"CONO": a.cono, "FACI": FACILITY, "PRNO": TARGET_ITEM,
                      "STRT": STRUCTURE_TYPE, "MSEQ": NEW_MSEQ, "FDAT": FROM_DATE},
                headers={"Idempotency-Key": f"rej-cleanup-{uuid.uuid4().hex[:6]}"},
            )
            body = resp.json()
            if body.get("success") or "does not exist" in str(body.get("error", "")):
                return
            print(f"  (cleanup attempt {attempt + 1}: {body.get('error')})", flush=True)
        except Exception as exc:
            print(f"  (cleanup attempt {attempt + 1}: {exc})", flush=True)
        finally:
            await a.close()
        await asyncio.sleep(1.0)


def _outbox_count(conn: Any, ecn_id: str) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) AS n FROM movex_outbox WHERE ecn_id = %s", (ecn_id,))
        return int(cur.fetchone()["n"])


def _outbox_rows(conn: Any, ecn_id: str) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, mi_transaction, state, attempt_count, last_error "
            "FROM movex_outbox WHERE ecn_id = %s", (ecn_id,))
        return [dict(r) for r in cur.fetchall()]


async def _drive_workflow() -> tuple[str, list[str], dict[str, int]]:
    """Create an ECN, walk it to rejection, then resubmit and approve.

    Returns (ecn_id, dispatched_ids_from_approval, outbox_counts_by_stage).
    """
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from src.adapters.erp.movex import MovexRestAdapter
    from src.services.ecn.models import (
        BOMChangeRequest, ECNCreateRequest, ECNStatusTransitionRequest,
    )
    from src.services.ecn.service import ECNService

    async_url = _dsn().replace("postgresql://", "postgresql+asyncpg://") + "?ssl=disable"
    engine = create_async_engine(async_url, pool_size=3)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    erp = MovexRestAdapter()
    await erp.open()
    counts: dict[str, int] = {}
    probe = _conn()
    try:
        async with factory() as session:
            svc = ECNService(session)

            # Role users for this facility (test DB seeds 'L' only).
            await session.execute(_sa_text(
                "DELETE FROM system_role_users WHERE facility = :f"), {"f": FACILITY})
            for role, user in (("DC", "dc_user"), ("SE", "eng_user"), ("QM", "qm_user")):
                await session.execute(_sa_text(
                    "INSERT INTO system_role_users "
                    "(id, facility, role_id, username, is_active, added_by) "
                    "VALUES (gen_random_uuid(), :f, :r, :u, TRUE, 'e2e-reject')"),
                    {"f": FACILITY, "r": role, "u": user})
            await session.commit()

            ecn = await svc.create(
                ECNCreateRequest(
                    facility=FACILITY, title="E2E rejection path",
                    is_new_item=False, routing_changes=False, operation_changes=False,
                    new_parts=False, change_parts=True, bom_changes=True,
                    lead_time_changes=False, change_to_documents=False,
                    requires_customer_approval=False, regulatory_impact=False,
                ),
                "hsalazar",
            )
            item = await svc.create_item(ecn.id, line_number=10, item_number=TARGET_ITEM)
            await svc.create_bom_change(
                ecn.id, item.id,
                BOMChangeRequest(
                    change_type="ADD", component_number=COMPONENT, quantity=1.0,
                    unit_of_measure="EA", operation_number=OPNO_EXISTING,
                    from_date=FROM_DATE, sequence_number=NEW_MSEQ,
                ),
            )
            await session.commit()

            async def _go(trigger, actor="hsalazar", role="OR", **kw):
                return await svc.transition(
                    ecn.id,
                    ECNStatusTransitionRequest(trigger=trigger, actor_role=role, **kw),
                    actor_username=actor, erp=erp,
                )

            # ── Stage 1: mid-workflow (submitted, not DC-approved) ─────────
            await _go("submit")
            await _go("approve_engineering", actor="eng_user", role="SE")
            await session.commit()
            counts["mid_workflow"] = _outbox_count(probe, ecn.id)

            # ── Stage 2: rejected ──────────────────────────────────────────
            await _go("reject", actor="qm_user", role="QM",
                      rejection_reason="E2E rejection-path check")
            await session.commit()
            counts["rejected"] = _outbox_count(probe, ecn.id)

            # ── Stage 3: resubmit and approve (control) ────────────────────
            await _go("resubmit")
            await _go("approve_engineering", actor="eng_user", role="SE")
            await _go("approve_role", actor="eng_user", role="EM", role_id="EM")
            await _go("approve_role", actor="qm_user", role="QM", role_id="QM")
            await _go("complete_management_review", actor="qm_user", role="QM")
            await session.commit()
            _, dispatched = await _go("dc_approve", actor="dc_user", role="DC")
            await session.commit()
            counts["approved"] = _outbox_count(probe, ecn.id)

            return ecn.id, list(dispatched or []), counts
    finally:
        probe.close()
        await erp.close()
        await engine.dispose()


def run() -> None:
    from src.adapters.erp.movex import MovexRestAdapter
    if str(MovexRestAdapter().cono) != REQUIRED_CONO:
        raise Refused(
            f"MOVEX_CONO is {MovexRestAdapter().cono!r} — refusing. This script "
            f"writes to M3 and must only target CONO={REQUIRED_CONO}."
        )
    _ok(f"CONO={REQUIRED_CONO} (development/UAT)")

    conn = _conn()
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass('public.kombu_message') AS t")
        if cur.fetchone()["t"] is None:
            raise Refused("no Celery broker table — start the worker profile first")
    _ok("broker present")

    baseline = asyncio.run(_m3_bom_mseqs())
    _ok(f"M3 baseline: {len(baseline)} open BOM lines")
    if NEW_MSEQ in baseline:
        raise Refused(
            f"MSEQ {NEW_MSEQ} already exists on {TARGET_ITEM} — leaked test data "
            f"from an earlier run. Clean it up before re-running."
        )

    ecn_id = None
    try:
        _step("driving a real ECN: submit -> reject -> resubmit -> approve")
        ecn_id, dispatched, counts = asyncio.run(_drive_workflow())
        _ok(f"ECN {ecn_id} walked through the full rejection cycle")

        # ── Assertion 1: nothing queued mid-workflow ───────────────────────
        if counts["mid_workflow"] != 0:
            raise ProofFailed(
                f"{counts['mid_workflow']} outbox row(s) existed before dc_approve — "
                f"an ECN still under review would write to the ERP before anyone "
                f"approved it."
            )
        _ok("mid-workflow (submitted, not approved): 0 outbox rows")

        # ── Assertion 2: nothing queued by rejection ───────────────────────
        if counts["rejected"] != 0:
            raise ProofFailed(
                f"{counts['rejected']} outbox row(s) existed after REJECTION — a "
                f"change the business explicitly rejected would reach the ERP."
            )
        _ok("rejected: 0 outbox rows")

        # ── Assertion 3: M3 genuinely untouched ────────────────────────────
        after_reject = asyncio.run(_m3_bom_mseqs())
        if after_reject != baseline:
            raise ProofFailed(
                f"M3's BOM changed across the rejection cycle.\n"
                f"    before: {baseline}\n    after:  {after_reject}"
            )
        _ok("M3 BOM unchanged by the submit/reject cycle")

        # ── Assertion 4: control — approval DOES write ─────────────────────
        if counts["approved"] < 1:
            raise ProofFailed(
                "approval produced no outbox rows — the 'nothing was written' "
                "assertions above are meaningless if writes never happen at all"
            )
        _ok(f"control: approval queued {counts['approved']} outbox row(s)")

        _step("dispatching to the real worker")
        from src.tasks.movex_outbox import process_outbox_entry
        for oid in dispatched:
            process_outbox_entry.apply_async(args=[str(oid)])

        deadline = time.time() + WORKER_TIMEOUT
        final: list[dict[str, Any]] = []
        while time.time() < deadline:
            final = _outbox_rows(conn, ecn_id)
            if final and all(r["state"] in ("completed", "abandoned") for r in final):
                break
            time.sleep(POLL)

        for r in final:
            print(f"         {r['mi_transaction']:26} state={r['state']:10} "
                  f"attempts={r['attempt_count']}", flush=True)

        incomplete = [r for r in final if r["state"] != "completed"]
        if incomplete:
            raise ProofFailed(
                "the approved write did not complete: "
                + "; ".join(f"{r['mi_transaction']}={r['state']} ({r['last_error']})"
                            for r in incomplete)
            )
        _ok("approved write completed through the real worker")

        after_approve = asyncio.run(_m3_bom_mseqs())
        if NEW_MSEQ not in after_approve:
            raise ProofFailed(
                f"outbox says completed but MSEQ {NEW_MSEQ} is absent from M3 — "
                f"a silent write failure (the I2-19/I2-21 shape)"
            )
        _ok(f"MSEQ {NEW_MSEQ} confirmed in M3 after approval")
        _ok("REJECTION PATH PROVEN: rejected ECNs write nothing; approved ones do")

    finally:
        _step("cleaning up M3 and the test ECN")
        asyncio.run(_m3_cleanup())
        final_state = asyncio.run(_m3_bom_mseqs())
        clean = NEW_MSEQ not in final_state
        print(f"  M3 restored: {len(final_state)} open lines | clean={clean}", flush=True)
        if not clean:
            print(f"  !! MANUAL CLEANUP NEEDED: MSEQ {NEW_MSEQ} remains on {TARGET_ITEM}",
                  flush=True)
        if ecn_id:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM ecn_movex_errors WHERE ecn_id = %s", (ecn_id,))
                cur.execute("DELETE FROM movex_outbox WHERE ecn_id = %s", (ecn_id,))
        conn.close()


def main() -> int:
    print("\nE2E rejection path — a rejected ECN must write NOTHING to M3")
    print(f"  target: {TARGET_ITEM} (facility {FACILITY})\n")
    try:
        run()
    except Refused as exc:
        _fail(str(exc)); print("\nRESULT: REFUSED\n"); return 2
    except ProofFailed as exc:
        _fail(str(exc)); print("\nRESULT: FAIL\n"); return 1
    except Exception:
        _fail("unexpected error:"); traceback.print_exc()
        print("\nRESULT: FAIL (unexpected error)\n"); return 1
    print("\nRESULT: PASS\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
