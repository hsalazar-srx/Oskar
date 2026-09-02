#!/usr/bin/env python
"""
OSKAR — does PDS002MI.Delete accept a 6-field key when FDAT is 0?

The question
------------
M3 legitimately STORES FDAT=0 on old MPDMAT lines (EP00002: 65 of 66, verified
through B-1 against CONO=300 and CONO=100) but appears not to ACCEPT a zero as
a key value — every Delete Oskar sent for those lines came back 422.

Option 1 (now implemented in delete_bom_component) omits FDAT when it is zero,
leaving M3 to resolve the line on the remaining six key fields
(CONO+FACI+PRNO+STRT+MSEQ+OPNO). Whether M3 actually accepts that is the one
thing that could not be determined without calling it.

Option 2, if this fails: resolve the true key via PDS002MI.GetComponent first,
then delete with whatever it reports.

WHAT THIS SCRIPT DOES — read this before running
------------------------------------------------
Step 1 and 2 are READ-ONLY and safe. Step 3 DELETES A REAL BOM LINE and is
skipped unless you pass --destructive.

  1. B-1 read of the target BOM — finds a line whose FDAT is 0 and confirms
     the line exists right now.
  2. GetComponent on that line — proves the fallback path is available and
     shows what key M3 itself reports for a FDAT=0 line. This alone may
     answer the question: if GetComponent returns a different FDAT than B-1
     does, the read and the write disagree and option 2 is the answer.
  3. --destructive only: Delete without FDAT, then a B-1 read-back to confirm
     the line actually went. Then STOPS — it does not recreate the line.

On step 3 and cleanup
---------------------
There is no non-destructive way to prove a delete works. If you run it, the
line is gone and you must re-add it (AddComponent with the values step 1
printed, which the script prints as a ready-to-paste command). Use a
throwaway line on a CONO=300 test item, NOT EP00002 — that ECN is mid-
investigation and its BOM should stay as it is.

Usage
-----
    # Safe: steps 1-2 only
    python scripts/verify_delete_fdat_zero.py --item EP00002

    # Actually tests the delete (destroys a line)
    python scripts/verify_delete_fdat_zero.py --item MYTESTITEM --mseq 210 --destructive

Requires MOVEX_API_URL / MOVEX_CONO / MOVEX_API_KEY in the environment, the
same as the app. Exit 0 = option 1 works, 1 = it does not, 2 = inconclusive.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.adapters.erp.movex import MovexHTTPError, MovexRestAdapter  # noqa: E402


def _fmt(obj) -> str:
    return json.dumps(obj, indent=2, default=str)


async def _run(item: str, facility: str, strt: str, mseq: int | None, destructive: bool) -> int:
    adapter = MovexRestAdapter()
    await adapter.open()
    print(f"\nCONO={adapter.cono}  item={item}  faci={facility}  strt={strt}\n")
    if adapter.cono != "300":
        print(f"  !! CONO is {adapter.cono}, not 300. Refusing to continue.")
        await adapter.close()
        return 2

    try:
        # ── 1. Find a FDAT=0 line ────────────────────────────────────────
        print("1. B-1 read — locate a line with FDAT = 0")
        payload = await adapter.get_bom(item, facility, structure_type=strt)
        records = payload.get("data", {}).get("records", [])
        print(f"   {len(records)} lines returned")

        zero_lines = [r for r in records if not r.get("FDAT")]
        print(f"   {len(zero_lines)} of them have FDAT = 0")
        if not zero_lines:
            print("   No FDAT=0 line here — nothing for this script to test.")
            return 2

        if mseq is not None:
            target = next((r for r in zero_lines if int(r["MSEQ"]) == mseq), None)
            if target is None:
                print(f"   MSEQ {mseq} is not a FDAT=0 line on this BOM.")
                return 2
        else:
            target = zero_lines[0]

        print(f"   target: MSEQ={target['MSEQ']} MTNO={target['MTNO']} "
              f"OPNO={target['OPNO']} CNQT={target['CNQT']} FDAT={target['FDAT']}")

        # ── 2. GetComponent — what key does M3 itself report? ────────────
        print("\n2. GetComponent — the fallback path, and M3's own view of the key")
        try:
            # Uses the adapter method, not a hand-rolled call — it knows this
            # transaction is GET-only (live-verified 2026-09-01: a POST returns
            # HTTP 400 "Transaction is configured for GET").
            body = await adapter.get_bom_component(
                item,
                int(target["MSEQ"]),
                facility=facility,
                structure_type=strt,
            )
            print("   GetComponent (no FDAT) succeeded:")
            print("   " + _fmt(body).replace("\n", "\n   ")[:800])
            reported = body.get("FDAT") if isinstance(body, dict) else None
            reported_tdat = body.get("TDAT") if isinstance(body, dict) else None

            # GetComponent's field parsing is BROKEN on movex-rest-api
            # (live-verified 2026-09-01). It truncates and mis-splits values:
            #   B-1 FDAT=20120514 TDAT=99999999
            #   GC  FDAT=200      TDAT=1205        <- the same digits, wrong offsets
            # and MTNO comes back None. A plausible date is 8 digits; anything
            # shorter here is a parsing artefact, not M3's answer.
            looks_truncated = (
                (reported is not None and 0 < int(reported or 0) < 10000000)
                or (reported_tdat is not None and 0 < int(reported_tdat or 0) < 10000000)
                or body.get("MTNO") in (None, "")
            )
            if looks_truncated:
                print(f"\n   >> GetComponent returned FDAT={reported!r} TDAT={reported_tdat!r} "
                      f"MTNO={body.get('MTNO')!r}")
                print("   >> These are TRUNCATED — its field offsets are wrong on")
                print("   >> movex-rest-api. OPTION 2 IS NOT VIABLE: this call")
                print("   >> cannot be trusted to report a key. Needs a fix on the")
                print("   >> movex-rest-api side before it could be used.")
            elif reported not in (None, "", 0, "0"):
                print(f"\n   >> M3 reports FDAT={reported!r} for a line B-1 showed as 0.")
                print("   >> Read and write disagree — OPTION 2 is the answer:")
                print("   >> resolve the key via GetComponent, then delete with that value.")
        except MovexHTTPError as exc:
            print(f"   GetComponent without FDAT failed: {exc}")
            print("   (If this 422s too, the 6-field key is not accepted for reads")
            print("    either, which is strong evidence against option 1.)")

        if not destructive:
            print("\n3. Delete test SKIPPED — pass --destructive to run it.")
            print("   Steps 1-2 alone cannot confirm option 1; only a real")
            print("   Delete can. Use a throwaway line, not EP00002.")
            return 2

        # ── 3. The actual test ───────────────────────────────────────────
        print("\n3. Delete WITHOUT FDAT (this destroys the line)")
        restore = (
            f"   AddComponent CONO={adapter.cono} FACI={facility} PRNO={item} "
            f"STRT={strt} MSEQ={target['MSEQ']} MTNO={target['MTNO']} "
            f"OPNO={target['OPNO']} CNQT={target['CNQT']} PEUN={target.get('PEUN')}"
        )
        print("   restore values if this succeeds:")
        print(restore)

        try:
            result = await adapter.delete_bom_component(
                parent_item=item,
                component_item=str(target["MTNO"]).strip(),
                operation_number=int(target["OPNO"]),
                from_date=0,                     # the case under test
                facility=facility,
                structure_type=strt,
                sequence_number=int(target["MSEQ"]),
                idempotency_key=f"verify-fdat-zero:{item}:{target['MSEQ']}",
            )
            print("   Delete returned: " + _fmt(result)[:400])
        except MovexHTTPError as exc:
            print(f"\n   FAILED: {exc}")
            print("\n   >> OPTION 1 DOES NOT WORK. M3 will not resolve the line")
            print("   >> on a 6-field key. Implement option 2: GetComponent")
            print("   >> first, then Delete with the key M3 reports.")
            return 1

        # ── read-back ────────────────────────────────────────────────────
        print("\n4. B-1 read-back — did the line actually go?")
        after = await adapter.get_bom(item, facility, structure_type=strt)
        after_records = after.get("data", {}).get("records", [])
        still_there = any(int(r["MSEQ"]) == int(target["MSEQ"]) for r in after_records)
        print(f"   {len(after_records)} lines now (was {len(records)})")

        if still_there:
            print("\n   >> Delete reported success but the line is STILL THERE.")
            print("   >> Same class of bug as UpdateComponent/TDAT (I2-19):")
            print("   >> reports success, does not persist. Use option 2.")
            return 1

        print("\n   >> OPTION 1 WORKS. Line removed with a 6-field key.")
        print("   >> Restore it now with the values printed above.")
        return 0

    finally:
        await adapter.close()


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--item", required=True, help="Parent item number")
    p.add_argument("--facility", default="D")
    p.add_argument("--strt", default="001", help="Structure type")
    p.add_argument("--mseq", type=int, default=None, help="Specific MSEQ to target")
    p.add_argument(
        "--destructive",
        action="store_true",
        help="Actually run the Delete. DESTROYS a real BOM line.",
    )
    a = p.parse_args()
    return asyncio.run(_run(a.item, a.facility, a.strt, a.mseq, a.destructive))


if __name__ == "__main__":
    raise SystemExit(main())
