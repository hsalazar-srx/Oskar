#!/usr/bin/env python
"""
OSKAR — end-to-end proof of the S-3 routing-before-BOM ordering fix.

What this closes
----------------
S-3 established (live, CONO=300) that M3 rejects a BOM component whose OPNO
has no routing operation, and the fix wires `depends_on` so the component
write is gated behind the routing write. Tests prove the dependency is
*recorded* correctly, and tests/tasks/test_outbox_depends_on.py proves the
gate machinery works — but nothing had yet driven a real ECN through a real
Celery worker to real M3 with that ordering in play.

This script does exactly that, with nothing mocked anywhere:

    real ECN (real workflow transitions)
      -> real movex_outbox rows with the S-3 depends_on
      -> real Celery worker (separate process, Postgres broker)
      -> real movex-rest-api
      -> real M3 (CONO=300)
      -> read back from M3 to confirm BOTH writes landed

The assertion that matters: the BOM component write must SUCCEED. Before the
fix, dispatch order was a coin flip and losing it produced
"Operation number NNN does not exist", 10 burned retries, and an EM page.

Safety
------
* CONO=300 only — hard guard, refuses to run otherwise (CONO=100 is prod).
* Uses a throwaway OPNO/MSEQ far outside the real ranges on the target item.
* Cleans up M3 (component, then operation) and the DB in a finally block.
* Verifies the target item's baseline before touching anything.

Usage
-----
    # requires the worker profile running:
    docker compose --env-file .env -f docker/docker-compose.dev.yml \
        --profile worker up -d

    python scripts/e2e_s3_ordering_proof.py

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

# Target the same real item the MOVEX smoke test uses (facility D, CONO 300).
TARGET_ITEM = "LFAM050001"
FACILITY = "D"
STRUCTURE_TYPE = "001"

# Throwaway identifiers, deliberately outside the real ranges on this item
# (real MSEQ max 200; real OPNO set does not include 888).
NEW_OPNO = 888
NEW_MSEQ = 888
COMPONENT = "LFAM700006"   # a real component already used on this BOM
FROM_DATE = 20260901
# add_routing_operation sends no FDAT, so M3 stores the operation with FDAT=0.
# Both GetOperation and Delete match on the full key including FDAT, so every
# check/cleanup for the OPERATION must use 0 — not FROM_DATE, which is the
# BOM component's effective date. Getting this wrong made a successful run
# report a false "silent write failure" and left residue in M3 (2026-08-18).
OP_FDAT = 0
REQUIRED_CONO = "300"

WORKER_TIMEOUT = 90
POLL = 1.0


def _ok(m: str) -> None: print(f"  [ OK ] {m}", flush=True)
def _step(m: str) -> None: print(f"  [ .. ] {m}", flush=True)
def _fail(m: str) -> None: print(f"  [FAIL] {m}", flush=True)


class Refused(RuntimeError):
    """Prerequisites not met — refuse to run rather than produce a false result."""


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


# ---------------------------------------------------------------------------
# M3 helpers (direct, via the adapter — same code path production uses)
# ---------------------------------------------------------------------------

async def _operation_exists(opno: int, fdat: int) -> bool:
    """Whether a specific routing operation exists, via GetOperation.

    Deliberately NOT LstOperation. Verified 2026-08-18: three identical
    LstOperation calls seconds apart returned 29, 29, then 40 records — the
    last including a spurious OPNO=0. `FDAT` on the list transactions is a
    cursor SEEK POSITION, not a filter (see docs/movex-rest-api-bom-contract.md),
    so list output is not a sound basis for asserting presence or absence.

    The FDAT passed must be the one the row was CREATED with, since Get/Delete
    match on the full key. add_routing_operation sends no FDAT, so operations
    are stored with FDAT=0 — hence OP_FDAT, not FROM_DATE (which is the BOM
    component's effective date). An earlier version checked with FROM_DATE and
    reported a successful run as a "silent write failure" while leaving the
    operation behind in M3.
    """
    from src.adapters.erp.movex import MovexRestAdapter
    a = MovexRestAdapter()
    await a.open()
    try:
        resp = await a._get(
            "/PDS002MI/GetOperation",
            params={"CONO": a.cono, "FACI": FACILITY, "PRNO": TARGET_ITEM,
                    "STRT": STRUCTURE_TYPE, "OPNO": opno, "FDAT": fdat},
        )
        return bool(resp.json().get("success"))
    except Exception:
        return False
    finally:
        await a.close()


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
    """Remove the throwaway component, then the throwaway operation.

    Order matters and is not optional: the component references the operation
    (that is the whole point of S-3), so the operation cannot be removed while
    the component still points at it.

    Each delete is retried and then VERIFIED, because a silent cleanup failure
    is genuinely costly here — observed 2026-08-18: a cleanup that reported a
    422 but was assumed to have worked left OPNO 888 in M3, which made the next
    run's AddOperation fail with a confusing 422 ("already exists") and look
    like a product bug. Leaving residue in a shared test company also breaks
    the next person's baseline.
    """
    from src.adapters.erp.movex import MovexRestAdapter

    async def _try_delete(label: str, payload: dict[str, Any]) -> None:
        for attempt in range(3):
            a = MovexRestAdapter()
            await a.open()
            try:
                resp = await a._post(
                    "/PDS002MI/Delete",
                    json={"CONO": a.cono, **payload},
                    headers={"Idempotency-Key": f"e2e-cleanup-{label}-{uuid.uuid4().hex[:6]}"},
                )
                body = resp.json()
                # "does not exist" is success for cleanup purposes — the row is gone.
                if body.get("success") or "does not exist" in str(body.get("error", "")):
                    return
                print(f"  ({label} cleanup attempt {attempt + 1}: {body.get('error')})", flush=True)
            except Exception as exc:
                print(f"  ({label} cleanup attempt {attempt + 1}: {exc})", flush=True)
            finally:
                await a.close()
            await asyncio.sleep(1.0)

    # Component first (it references the operation), then the operation.
    await _try_delete("comp", {
        "FACI": FACILITY, "PRNO": TARGET_ITEM, "STRT": STRUCTURE_TYPE,
        "MSEQ": NEW_MSEQ, "FDAT": FROM_DATE,
    })
    await _try_delete("op", {
        "FACI": FACILITY, "PRNO": TARGET_ITEM, "STRT": STRUCTURE_TYPE,
        "OPNO": NEW_OPNO, "FDAT": OP_FDAT,
    })


# ---------------------------------------------------------------------------
# ECN construction via the real service layer
# ---------------------------------------------------------------------------

async def _build_and_approve_ecn() -> tuple[str, list[str]]:
    """Create a real ECN carrying a NEW routing op + a BOM line referencing it,
    drive it through the real workflow to dc_approve, and return
    (ecn_id, dispatched_outbox_ids)."""
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from src.adapters.erp.movex import MovexRestAdapter
    from src.services.ecn.models import (
        BOMChangeRequest, ECNCreateRequest, ECNStatusTransitionRequest,
        RoutingOperationRequest,
    )
    from src.services.ecn.service import ECNService

    async_url = _dsn().replace("postgresql://", "postgresql+asyncpg://") + "?ssl=disable"
    engine = create_async_engine(async_url, pool_size=3)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    erp = MovexRestAdapter()
    await erp.open()
    try:
        async with factory() as session:
            svc = ECNService(session)

            # The workflow needs DC/SE/QM role users for THIS facility (the
            # test DB is seeded for facility 'L' only; the real M3 item is 'D').
            await session.execute(_sa_text(
                "DELETE FROM system_role_users WHERE facility = :f"), {"f": FACILITY})
            for role, user in (("DC", "dc_user"), ("SE", "eng_user"), ("QM", "qm_user")):
                await session.execute(_sa_text(
                    "INSERT INTO system_role_users "
                    "(id, facility, role_id, username, is_active, added_by) "
                    "VALUES (gen_random_uuid(), :f, :r, :u, TRUE, 'e2e-proof')"),
                    {"f": FACILITY, "r": role, "u": user})
            await session.commit()

            ecn = await svc.create(
                ECNCreateRequest(
                    facility=FACILITY, title="E2E S-3 ordering proof",
                    is_new_item=False, routing_changes=True, operation_changes=True,
                    new_parts=False, change_parts=True, bom_changes=True,
                    lead_time_changes=False, change_to_documents=False,
                    requires_customer_approval=False, regulatory_impact=False,
                ),
                "hsalazar",
            )
            item = await svc.create_item(ecn.id, line_number=10, item_number=TARGET_ITEM)

            # The S-3 combination: a NEW operation, and a BOM line on it.
            await svc.create_routing_operation(
                ecn.id, item.id,
                RoutingOperationRequest(
                    operation_number=NEW_OPNO, operation_description="E2E proof op",
                    work_centre="KIT", run_time=1.0, change_type="ADD",
                ),
            )
            await svc.create_bom_change(
                ecn.id, item.id,
                BOMChangeRequest(
                    change_type="ADD", component_number=COMPONENT, quantity=1.0,
                    unit_of_measure="EA", operation_number=NEW_OPNO,
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

            await _go("submit")
            await _go("approve_engineering", actor="eng_user", role="SE")
            await _go("approve_role", actor="eng_user", role="EM", role_id="EM")
            await _go("approve_role", actor="qm_user", role="QM", role_id="QM")
            await _go("complete_management_review", actor="qm_user", role="QM")
            await session.commit()

            _, dispatched = await _go("dc_approve", actor="dc_user", role="DC")
            await session.commit()

            return ecn.id, list(dispatched or [])
    finally:
        await erp.close()
        await engine.dispose()


def _sa_text(s: str):
    import sqlalchemy as sa
    return sa.text(s)


# ---------------------------------------------------------------------------
# Main proof
# ---------------------------------------------------------------------------

def _outbox_rows(conn: Any, ecn_id: str) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, mi_transaction, state, depends_on, attempt_count, last_error "
            "FROM movex_outbox WHERE ecn_id = %s ORDER BY mi_transaction", (ecn_id,))
        return [dict(r) for r in cur.fetchall()]


def _worker_alive(conn: Any) -> bool:
    # RealDictCursor yields dicts, not tuples — index by column name.
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass('public.kombu_message') AS t")
        return cur.fetchone()["t"] is not None


def run() -> None:
    from src.adapters.erp.movex import MovexRestAdapter
    if str(MovexRestAdapter().cono) != REQUIRED_CONO:
        raise Refused(
            f"MOVEX_CONO is {MovexRestAdapter().cono!r} — this script performs real "
            f"M3 writes and must only target CONO={REQUIRED_CONO}. CONO=100 is PRODUCTION."
        )
    _ok(f"CONO={REQUIRED_CONO} (development/UAT)")

    conn = _conn()
    if not _worker_alive(conn):
        raise Refused(
            "no kombu_message table — the Celery broker has never been used, so no "
            "worker is running. Start it: docker compose --env-file .env "
            "-f docker/docker-compose.dev.yml --profile worker up -d"
        )
    _ok("broker present")

    # Baseline: the throwaway ids must not already exist.
    op_before = asyncio.run(_operation_exists(NEW_OPNO, OP_FDAT))
    mseqs_before = asyncio.run(_m3_bom_mseqs())
    _ok(f"M3 baseline: {len(mseqs_before)} BOM lines; OPNO {NEW_OPNO} exists={op_before}")
    if op_before or NEW_MSEQ in mseqs_before:
        raise Refused(
            f"OPNO {NEW_OPNO} or MSEQ {NEW_MSEQ} already exists on {TARGET_ITEM} — "
            "a previous run leaked test data. Clean it up before re-running."
        )
    _ok(f"OPNO {NEW_OPNO} / MSEQ {NEW_MSEQ} are free")

    ecn_id = None
    try:
        _step("creating a real ECN: new routing op + BOM line referencing it")
        ecn_id, dispatched = asyncio.run(_build_and_approve_ecn())
        _ok(f"ECN {ecn_id} approved; {len(dispatched)} outbox rows dispatched")

        rows = _outbox_rows(conn, ecn_id)
        by_tx = {r["mi_transaction"]: r for r in rows}
        if "PDS002MI.AddOperation" not in by_tx or "PDS002MI.AddComponent" not in by_tx:
            raise ProofFailed(f"expected both writes queued; got {sorted(by_tx)}")

        routing_row, bom_row = by_tx["PDS002MI.AddOperation"], by_tx["PDS002MI.AddComponent"]
        if bom_row["depends_on"] is None:
            raise ProofFailed(
                "the BOM row has no depends_on — the S-3 fix is not in effect, so "
                "the component write can race ahead of its operation"
            )
        if str(bom_row["depends_on"]) != str(routing_row["id"]):
            raise ProofFailed("BOM row's depends_on does not point at the routing row")
        _ok("S-3 dependency present: AddComponent depends_on AddOperation")

        # Dispatch post-commit, exactly as the router does
        # (src/routers/ecn_core.py:339-343 — the service returns the ids, the
        # ROUTER apply_async's them in a BackgroundTask after the session
        # commits). This script bypasses the router, so it must do the same;
        # without it the rows sit 'pending' and no worker ever sees them.
        from src.tasks.movex_outbox import process_outbox_entry
        for oid in dispatched:
            process_outbox_entry.apply_async(args=[str(oid)])
        _ok(f"dispatched {len(dispatched)} rows to the real worker")

        # ── Let the REAL worker drive both writes to REAL M3 ────────────────
        _step(f"waiting for the real worker to process both writes (max {WORKER_TIMEOUT}s)")
        deadline = time.time() + WORKER_TIMEOUT
        final: list[dict[str, Any]] = []
        while time.time() < deadline:
            final = _outbox_rows(conn, ecn_id)
            if all(r["state"] in ("completed", "abandoned") for r in final):
                break
            time.sleep(POLL)

        for r in final:
            print(f"         {r['mi_transaction']:26} state={r['state']:10} "
                  f"attempts={r['attempt_count']} err={(r['last_error'] or '-')[:55]}",
                  flush=True)

        incomplete = [r for r in final if r["state"] != "completed"]
        if incomplete:
            raise ProofFailed(
                "not every write completed: "
                + "; ".join(f"{r['mi_transaction']}={r['state']} ({r['last_error']})"
                            for r in incomplete)
                + "\n  If AddComponent failed with 'Operation number ... does not exist', "
                  "the dependency gate did not hold and the S-3 race is still live."
            )
        _ok("both outbox rows reached 'completed'")

        # ── Confirm against M3 itself, not the outbox state ─────────────────
        _step("reading back from M3 to confirm both writes actually landed")
        op_after = asyncio.run(_operation_exists(NEW_OPNO, OP_FDAT))
        mseqs_after = asyncio.run(_m3_bom_mseqs())

        if not op_after:
            raise ProofFailed(
                f"outbox says completed, but OPNO {NEW_OPNO} is absent from M3 — "
                "a silent write failure (the I2-19/I2-21 shape)"
            )
        _ok(f"routing operation {NEW_OPNO} confirmed present in M3")

        if NEW_MSEQ not in mseqs_after:
            raise ProofFailed(
                f"outbox says completed, but MSEQ {NEW_MSEQ} is absent from M3 — "
                "a silent write failure (the I2-19/I2-21 shape)"
            )
        _ok(f"BOM component MSEQ {NEW_MSEQ} confirmed present in M3")

        _ok("END-TO-END PROVEN: ordered writes landed in real M3 via the real worker")

    finally:
        _step("cleaning up M3 and the test ECN")
        asyncio.run(_m3_cleanup())
        op_final = asyncio.run(_operation_exists(NEW_OPNO, OP_FDAT))
        mseqs_final = asyncio.run(_m3_bom_mseqs())
        clean = (not op_final) and NEW_MSEQ not in mseqs_final
        print(f"  M3 restored: BOM lines={len(mseqs_final)} "
              f"OPNO {NEW_OPNO} exists={op_final} clean={clean}", flush=True)
        if not clean:
            print(f"  !! MANUAL CLEANUP NEEDED on {TARGET_ITEM}: "
                  f"OPNO {NEW_OPNO} and/or MSEQ {NEW_MSEQ} remain", flush=True)
        if ecn_id:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM ecn_movex_errors WHERE ecn_id = %s", (ecn_id,))
                cur.execute("DELETE FROM movex_outbox WHERE ecn_id = %s", (ecn_id,))
        conn.close()


def main() -> int:
    print("\nE2E proof — S-3 routing-before-BOM ordering, real worker + real M3")
    print(f"  target: {TARGET_ITEM} (facility {FACILITY})")
    print(f"  api:    {os.environ.get('MOVEX_API_URL', '<unset>')}\n")
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
