#!/usr/bin/env python
"""
OSKAR — MOVEX write-path smoke test (robustness plan §1).

What this proves
----------------
That Oskar's Movex BOM write path *actually works against real M3*, end to
end: read → add → read-back-confirm → delete → read-back-confirm-removed →
final state matches the starting state exactly.

Why it exists
-------------
Two production bugs (I2-19, I2-21) shipped and hid for weeks because every
test that exercised these paths mocked the exact boundary where the bug
lived. The suite proved "the code does what I told it to do"; it never
proved "the write actually landed in M3". Both bugs had the same shape:
*something reported success while silently not doing what it claimed.*

The only defence against that shape of bug is a **read-back check against
the real system** — asserting on the write call's own response is precisely
what failed before, since a broken write returned `"success": true`. So
every assertion here is made against a fresh GET, never against the
response of the write that is being verified.

This sequence is the one that was previously run by hand, from a terminal,
whenever someone remembered to. This makes it code.

Safety
------
* Runs against **CONO=300 only** (development/UAT company) and refuses to
  run against any other company — CONO=100 is production. This is a hard
  guard, not a default.
* Writes one throwaway line at a deliberately out-of-range MSEQ that no
  real line uses, then deletes it.
* Cleanup runs in a `finally` block, so an assertion failure mid-test still
  attempts to remove the throwaway line.
* Verifies the baseline is intact *before* writing, and refuses to proceed
  if the BOM does not look as expected — it will not write into an item
  whose state it does not recognise.

Usage
-----
    python scripts/movex_smoke_test.py              # full round trip
    python scripts/movex_smoke_test.py --read-only  # no writes at all

Exit codes: 0 = pass, 1 = failure (details on stdout), 2 = refused to run
(unsafe config). Intended for the §7 pre-UAT checklist and, once trusted, a
scheduled run.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
import traceback
from typing import Any

# --- Configuration -----------------------------------------------------------

TARGET_ITEM = "LFAM050001"
FACILITY = "D"
STRUCTURE_TYPE = "001"

# Expected clean baseline for TARGET_ITEM (verified live 2026-08-17 against
# CONO=300). If the real BOM stops matching this, the smoke test refuses to
# write rather than mutating an item whose state it does not recognise.
EXPECTED_BASELINE_MSEQ = [10, 20, 100, 105, 120, 140, 150, 160, 170, 180, 200]

# Throwaway line. MSEQ 999 is deliberately far outside the real sequence
# range (max real = 200) so it cannot collide with a genuine line, and is
# obvious as test data if cleanup ever fails and a human finds it.
THROWAWAY_MSEQ = 999
THROWAWAY_COMPONENT = "LFAM700006"  # a real component already on this BOM
THROWAWAY_QTY = 1.0
THROWAWAY_UOM = "EA"
THROWAWAY_OPNO = 190
THROWAWAY_FDAT = 20260901

REQUIRED_CONO = "300"


class SmokeTestFailure(AssertionError):
    """A check failed — the write path is not behaving correctly."""


class UnsafeConfiguration(RuntimeError):
    """Refusing to run: configuration would touch the wrong system."""


# --- Output helpers ----------------------------------------------------------

def _step(msg: str) -> None:
    print(f"  [ .. ] {msg}", flush=True)


def _ok(msg: str) -> None:
    print(f"  [ OK ] {msg}", flush=True)


def _fail(msg: str) -> None:
    print(f"  [FAIL] {msg}", flush=True)


# --- Core checks -------------------------------------------------------------

def _records(bom: dict[str, Any]) -> list[dict[str, Any]]:
    return (bom.get("data") or {}).get("records") or []


def _field(record: dict[str, Any], name: str, default: Any = None) -> Any:
    """Read a field regardless of key casing.

    B-1's raw JSON returns lowercase keys (mseq/tdat), but MovexRestAdapter
    normalises records through _uppercase_keys() before returning them. This
    script must survive either — and must not silently read a default when
    the casing convention changes, which would make a missing line look like
    a present one.
    """
    for key in (name.upper(), name.lower(), name):
        if key in record:
            return record[key]
    return default


def _open_mseqs(bom: dict[str, Any]) -> list[int]:
    """MSEQ values of lines that are currently open (not date-closed).

    A BOM line is closed by setting TDAT to a real date; 99999999 is M3's
    "no end date" sentinel. Only open lines count as present.
    """
    out: list[int] = []
    for r in _records(bom):
        mseq = _field(r, "mseq")
        if mseq is None:
            raise SmokeTestFailure(
                f"BOM record has no MSEQ field in any casing — the response "
                f"shape has changed and this check can no longer be trusted. "
                f"Record keys: {sorted(r)}"
            )
        if int(_field(r, "tdat", 99999999)) == 99999999:
            out.append(int(mseq))
    return sorted(out)


def _guard_configuration(adapter: Any) -> None:
    """Refuse to run anywhere except the development/UAT company."""
    cono = str(adapter.cono)
    if cono != REQUIRED_CONO:
        raise UnsafeConfiguration(
            f"MOVEX_CONO is {cono!r}, refusing to run. This script performs "
            f"real BOM writes and must only ever target CONO={REQUIRED_CONO} "
            f"(development/UAT). CONO=100 is PRODUCTION."
        )
    _ok(f"CONO={cono} (development/UAT) — safe to proceed")


async def _read_bom(adapter: Any) -> dict[str, Any]:
    return await adapter.get_bom(
        TARGET_ITEM, FACILITY, structure_type=STRUCTURE_TYPE,
    )


async def run_smoke_test(read_only: bool = False) -> None:
    from src.adapters.erp.movex import MovexRestAdapter

    adapter = MovexRestAdapter()
    _guard_configuration(adapter)

    await adapter.open()
    added = False
    try:
        # ── 1. Baseline read ────────────────────────────────────────────────
        _step(f"reading baseline BOM for {TARGET_ITEM}")
        baseline = await _read_bom(adapter)
        baseline_mseqs = _open_mseqs(baseline)
        _ok(f"read {len(baseline_mseqs)} open lines: {baseline_mseqs}")

        if baseline_mseqs != EXPECTED_BASELINE_MSEQ:
            raise SmokeTestFailure(
                f"baseline does not match the known-clean state.\n"
                f"    expected: {EXPECTED_BASELINE_MSEQ}\n"
                f"    actual:   {baseline_mseqs}\n"
                f"  Refusing to write. Either the item genuinely changed (update "
                f"EXPECTED_BASELINE_MSEQ in this script) or a previous run failed "
                f"to clean up (look for MSEQ {THROWAWAY_MSEQ})."
            )
        _ok("baseline matches known-clean state")

        if THROWAWAY_MSEQ in baseline_mseqs:
            raise SmokeTestFailure(
                f"MSEQ {THROWAWAY_MSEQ} already exists — a previous run leaked "
                f"a throwaway line. Remove it before re-running."
            )

        if read_only:
            print("\n  --read-only: skipping write round trip")
            return

        # ── 2. Write a throwaway line ───────────────────────────────────────
        _step(f"adding throwaway line MSEQ={THROWAWAY_MSEQ}")
        add_resp = await adapter.add_bom_component(
            parent_item=TARGET_ITEM,
            component_item=THROWAWAY_COMPONENT,
            quantity=THROWAWAY_QTY,
            unit_of_measure=THROWAWAY_UOM,
            operation_number=THROWAWAY_OPNO,
            from_date=THROWAWAY_FDAT,
            facility=FACILITY,
            structure_type=STRUCTURE_TYPE,
            sequence_number=THROWAWAY_MSEQ,
            idempotency_key=f"smoke-add-{THROWAWAY_MSEQ}",
        )
        added = True
        # NOTE: deliberately NOT asserting on add_resp["success"] as proof of
        # anything. That is exactly what I2-19 did, and it reported true while
        # persisting nothing. The response is printed for diagnosis only; the
        # real verdict comes from the read-back below.
        _ok(f"add call returned: {add_resp}")

        # ── 3. Read back and confirm it actually landed ─────────────────────
        _step("reading back to confirm the line actually persisted")
        after_add = _open_mseqs(await _read_bom(adapter))
        if THROWAWAY_MSEQ not in after_add:
            raise SmokeTestFailure(
                f"THE WRITE SILENTLY DID NOT PERSIST.\n"
                f"    add reported: {add_resp}\n"
                f"    but MSEQ {THROWAWAY_MSEQ} is absent on read-back.\n"
                f"    open lines now: {after_add}\n"
                f"  This is the I2-19/I2-21 failure mode: success reported, "
                f"nothing written."
            )
        _ok(f"line {THROWAWAY_MSEQ} confirmed present ({len(after_add)} open lines)")

        # ── 4. Delete it ────────────────────────────────────────────────────
        _step(f"deleting throwaway line MSEQ={THROWAWAY_MSEQ}")
        del_resp = await adapter.delete_bom_component(
            parent_item=TARGET_ITEM,
            component_item=THROWAWAY_COMPONENT,
            operation_number=THROWAWAY_OPNO,
            from_date=THROWAWAY_FDAT,
            facility=FACILITY,
            structure_type=STRUCTURE_TYPE,
            sequence_number=THROWAWAY_MSEQ,
            idempotency_key=f"smoke-del-{THROWAWAY_MSEQ}",
        )
        _ok(f"delete call returned: {del_resp}")

        # ── 5. Read back and confirm removal ────────────────────────────────
        _step("reading back to confirm the line actually went away")
        after_delete = _open_mseqs(await _read_bom(adapter))
        if THROWAWAY_MSEQ in after_delete:
            raise SmokeTestFailure(
                f"THE DELETE SILENTLY DID NOT PERSIST.\n"
                f"    delete reported: {del_resp}\n"
                f"    but MSEQ {THROWAWAY_MSEQ} is still present.\n"
                f"    open lines now: {after_delete}"
            )
        added = False  # cleanup already achieved
        _ok(f"line {THROWAWAY_MSEQ} confirmed removed")

        # ── 6. Final state must equal starting state exactly ────────────────
        _step("confirming final state matches the starting state exactly")
        if after_delete != baseline_mseqs:
            raise SmokeTestFailure(
                f"BOM did not return to its starting state.\n"
                f"    before: {baseline_mseqs}\n"
                f"    after:  {after_delete}"
            )
        _ok("final state identical to baseline — no residue left behind")

    finally:
        # Best-effort cleanup if we failed after adding but before deleting.
        if added:
            print("\n  !! test failed with the throwaway line still present — "
                  "attempting cleanup", flush=True)
            try:
                await adapter.delete_bom_component(
                    parent_item=TARGET_ITEM,
                    component_item=THROWAWAY_COMPONENT,
                    operation_number=THROWAWAY_OPNO,
                    from_date=THROWAWAY_FDAT,
                    facility=FACILITY,
                    structure_type=STRUCTURE_TYPE,
                    sequence_number=THROWAWAY_MSEQ,
                    idempotency_key=f"smoke-cleanup-{THROWAWAY_MSEQ}",
                )
                residual = _open_mseqs(await _read_bom(adapter))
                if THROWAWAY_MSEQ in residual:
                    print(f"  !! CLEANUP FAILED — MSEQ {THROWAWAY_MSEQ} is STILL "
                          f"on {TARGET_ITEM}. Remove it manually.", flush=True)
                else:
                    print("  cleanup succeeded", flush=True)
            except Exception as exc:  # pragma: no cover - diagnostic path
                print(f"  !! CLEANUP RAISED: {exc}\n"
                      f"  !! MSEQ {THROWAWAY_MSEQ} may still be on {TARGET_ITEM} "
                      f"— check manually.", flush=True)
        await adapter.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--read-only", action="store_true",
        help="only read and verify the baseline; perform no writes",
    )
    args = parser.parse_args()

    mode = "READ-ONLY" if args.read_only else "FULL WRITE ROUND TRIP"
    print(f"\nMOVEX smoke test — {mode}")
    print(f"  target: {TARGET_ITEM} (facility {FACILITY}, structure {STRUCTURE_TYPE})")
    print(f"  api:    {os.environ.get('MOVEX_API_URL', '<unset>')}\n")

    try:
        asyncio.run(run_smoke_test(read_only=args.read_only))
    except UnsafeConfiguration as exc:
        _fail(str(exc))
        print("\nRESULT: REFUSED (unsafe configuration)\n")
        return 2
    except SmokeTestFailure as exc:
        _fail(str(exc))
        print("\nRESULT: FAIL — the Movex write path is NOT behaving correctly\n")
        return 1
    except Exception:
        _fail("unexpected error:")
        traceback.print_exc()
        print("\nRESULT: FAIL (unexpected error)\n")
        return 1

    print("\nRESULT: PASS — Movex write path verified against real M3\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
