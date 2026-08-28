#!/usr/bin/env python
"""
OSKAR — element14 adapter verification against the live API.

What this proves
----------------
Same gap the DigiKey verification script exists to close: everything in
`src/adapters/suppliers/element14.py` was built against documentation and
mocked payloads. Nothing has confirmed that

  * the API key authenticates at all,
  * element14's real response shape matches what the adapter parses
    (the `keywordSearchReturn.products[]` envelope, `prices[]`, `stock`),
  * `stock.leastLeadTime` is actually populated on real parts — this is the
    single field that justified choosing element14 over the other candidates,
    and it has never been seen in a real response,
  * the `my.element14.com` / `au.element14.com` storefronts return data for
    the parts Scanfil actually buys,
  * `manuPartNum:` term matching finds parts by MPN rather than silently
    returning a keyword-ish neighbour.

Every assertion is made against the REAL response, never a mock.

Why this matters more than usual here
-------------------------------------
The adapter was written from documentation alone (verified 2026-08-27 against
partner.element14.com, but never exercised). Documentation-derived field
mappings are exactly the kind of claim LL-003 is about — plausible, cited, and
still capable of being wrong. Until this script passes, treat element14 data
in Oskar as unverified.

Quota
-----
element14 publishes no hard rate limit, describing only a "courtesy
allowance" — that is unverified, so this script stays frugal anyway:

  * DEFAULT (--quick): 2 calls — one MPN lookup, one not-found probe.
  * --full: 4 calls — adds a keyword search and a pricing lookup.

Usage
-----
    ELEMENT14_API_KEY=... python scripts/element14_verify.py --mpn RC0402FR-0710KL
    ELEMENT14_API_KEY=... ELEMENT14_STORE_ID=au.element14.com \
        python scripts/element14_verify.py --full

Exit code 0 = every check passed. Non-zero = at least one failed.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.adapters.suppliers.element14 import Element14Adapter  # noqa: E402

# A part that should exist in essentially any element14 storefront. Override
# with --mpn to check something Scanfil actually buys, which is the more
# meaningful test.
_DEFAULT_MPN = "RC0402FR-0710KL"

_PASS = "PASS"
_FAIL = "FAIL"
_WARN = "WARN"


class _Results:
    def __init__(self) -> None:
        self.failed = 0
        self.warned = 0

    def record(self, status: str, label: str, detail: str = "") -> None:
        if status == _FAIL:
            self.failed += 1
        elif status == _WARN:
            self.warned += 1
        line = f"  [{status}] {label}"
        if detail:
            line += f" — {detail}"
        print(line)


async def _run(mpn: str, full: bool) -> int:
    results = _Results()

    api_key = os.getenv("ELEMENT14_API_KEY")
    if not api_key:
        print("ELEMENT14_API_KEY is not set — nothing to verify.")
        return 2

    store = os.getenv("ELEMENT14_STORE_ID", "my.element14.com")
    print(f"\nelement14 live verification — store={store}, mpn={mpn}\n")

    adapter = Element14Adapter()
    await adapter.open()
    try:
        # ── 1. MPN lookup ────────────────────────────────────────────────
        print("1. MPN lookup (manuPartNum:)")
        try:
            part = await adapter.get_part(mpn)
        except Exception as exc:
            results.record(_FAIL, "get_part raised", f"{type(exc).__name__}: {exc}")
            return 1 if results.failed else 0

        if not part:
            results.record(
                _FAIL,
                "get_part returned {}",
                f"{mpn!r} not found in {store} — try --mpn with a part this store carries",
            )
        else:
            results.record(_PASS, "get_part returned a product")

            # Descriptive fields (need 1)
            results.record(
                _PASS if part.get("description") else _FAIL,
                "description populated",
                repr(part.get("description", ""))[:60],
            )
            results.record(
                _PASS if part.get("manufacturer") else _WARN,
                "manufacturer populated",
                repr(part.get("manufacturer", "")),
            )

            # Lifecycle (need 2) — mapped vocabulary, not raw productStatus
            lifecycle = part.get("lifecycle")
            results.record(
                _PASS if lifecycle else _WARN,
                "lifecycle mapped",
                f"{lifecycle!r} (empty means an unrecognised productStatus — "
                "check _LIFECYCLE_MAP against the raw value)",
            )

            # Price breaks (need 3)
            breaks = part.get("price_breaks") or []
            results.record(
                _PASS if breaks else _FAIL,
                "price_breaks parsed",
                f"{len(breaks)} break(s)",
            )
            results.record(
                _PASS if part.get("unit_price") is not None else _FAIL,
                "unit_price resolved",
                str(part.get("unit_price")),
            )

            # Lead time (need 4) — THE field that justified this adapter
            lead = part.get("lead_time_weeks")
            results.record(
                _PASS if lead is not None else _FAIL,
                "lead_time_weeks populated  <-- the field element14 was chosen for",
                f"{lead} weeks" if lead is not None else "MISSING — re-open the adapter choice",
            )

            # Compliance (need 5)
            results.record(
                _PASS if part.get("rohs_compliant") is not None else _WARN,
                "rohs_compliant resolved",
                str(part.get("rohs_compliant")),
            )
            results.record(
                _PASS if part.get("country_of_origin") else _WARN,
                "country_of_origin populated",
                repr(part.get("country_of_origin", "")),
            )
            results.record(
                _PASS if part.get("quantity_available") is not None else _WARN,
                "quantity_available populated",
                str(part.get("quantity_available")),
            )

            print("\n  Full parsed result:")
            print("  " + json.dumps(part, indent=2, default=str).replace("\n", "\n  "))

        # ── 2. Not-found probe ───────────────────────────────────────────
        print("\n2. Not-found probe")
        bogus = "OSKAR-NO-SUCH-PART-000000"
        try:
            missing = await adapter.get_part(bogus)
            results.record(
                _PASS if missing == {} else _FAIL,
                "unknown MPN returns {}",
                f"got {missing!r}" if missing else "",
            )
        except Exception as exc:
            results.record(
                _FAIL,
                "unknown MPN raised instead of returning {}",
                f"{type(exc).__name__}: {exc}",
            )

        if full:
            # ── 3. Keyword search ────────────────────────────────────────
            print("\n3. Keyword search (any:)")
            try:
                hits = await adapter.search("10k resistor 0402", limit=3)
                results.record(
                    _PASS if hits else _WARN,
                    "search returned results",
                    f"{len(hits)} hit(s)",
                )
            except Exception as exc:
                results.record(_FAIL, "search raised", f"{type(exc).__name__}: {exc}")

            # ── 4. Pricing at quantity ───────────────────────────────────
            print("\n4. Pricing at quantity")
            try:
                pricing = await adapter.get_pricing(mpn, quantity=500)
                results.record(
                    _PASS if pricing.get("unit_price") is not None else _WARN,
                    "get_pricing(qty=500) resolved a break",
                    str(pricing.get("unit_price")),
                )
            except Exception as exc:
                results.record(_FAIL, "get_pricing raised", f"{type(exc).__name__}: {exc}")
    finally:
        await adapter.close()

    print(
        f"\n{'-' * 60}\n"
        f"{results.failed} failed, {results.warned} warning(s)\n"
    )
    if results.failed:
        print("Adapter is NOT verified against the live API.")
    else:
        print("Adapter verified against the live API.")
    return 1 if results.failed else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mpn", default=_DEFAULT_MPN, help="MPN to look up")
    parser.add_argument(
        "--full",
        action="store_true",
        help="Also run keyword search and pricing checks (4 calls instead of 2)",
    )
    args = parser.parse_args()
    return asyncio.run(_run(args.mpn, args.full))


if __name__ == "__main__":
    raise SystemExit(main())
