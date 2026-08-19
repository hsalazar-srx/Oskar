#!/usr/bin/env python
"""
OSKAR — DigiKey adapter verification against the live API (robustness plan §2).

What this proves
----------------
Same class of gap as the MOVEX smoke test: `src/adapters/suppliers/digikey.py`
is a real OAuth2 client whose response parsing has only ever been checked
against mocked payloads. Nothing automated has ever confirmed that

  * the OAuth2 client-credentials flow still authenticates,
  * DigiKey's real response shape still matches what the adapter parses
    (API drift — the v4 productdetails shape is deeply nested and has already
    caught this code out once: there is no top-level DigiKeyPartNumber),
  * MPN percent-encoding works against the real router (MPNs containing '/'
    404 before reaching the API if unencoded),
  * the rate-limit headers the quota guard depends on are actually present.

Every assertion is made against the REAL response, never against a mock.

Quota discipline
----------------
Budget: 1000 requests/month, allocated entirely to testing (confirmed by the
Lead Engineer, 2026-08-19). This script is deliberately frugal within that:

  * DEFAULT (--quick): 3 API calls — one token + two part lookups.
  * --full: 6 API calls — adds a not-found probe, a keyword search, and a
    categories/health call.

At the default cadence (say one run before each UAT milestone, plus ad-hoc)
this is a rounding error against 1000/month. The script PRINTS the observed
quota headers so consumption is visible rather than assumed, and refuses to
run if DigiKey reports the remaining quota is already below the configured
buffer.

Note the token endpoint call is not itself a products-API request, but it is
counted here as a call for honesty about network round trips.

Sandbox
-------
`sandbox-api.digikey.com` is confirmed non-functional (2026-08-13), so this
runs against production. That is why it is a deliberate, on-demand check and
NOT wired into CI or a nightly schedule.

Usage
-----
    python scripts/digikey_verify.py            # 3 calls
    python scripts/digikey_verify.py --full     # 6 calls

Exit codes: 0 = pass, 1 = failure, 2 = refused (missing creds / quota low).
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
import traceback
from typing import Any

# Known-stable MPNs. Chosen to be commodity parts that are extremely unlikely
# to be discontinued or removed from the catalogue — a verification script
# must fail because the ADAPTER broke, never because a part went obsolete.
# Verified present in DigiKey's live catalogue 2026-08-19 (HTTP 200 on
# productdetails). Note the exact MPN matters: bare "LM358DR" 404s — DigiKey
# stocks onsemi's "LM358DR2G". `productdetails` matches the manufacturer part
# number exactly, so a near-miss is indistinguishable from "not found".
STABLE_MPN = "LM358DR2G"        # onsemi dual op-amp, commodity part
SLASH_MPN = "LM741CN/NOPB"      # contains '/', exercises percent-encoding
MISSING_MPN = "OSKAR-NO-SUCH-PART-XYZ-000"

_calls = 0


def _ok(m: str) -> None: print(f"  [ OK ] {m}", flush=True)
def _step(m: str) -> None: print(f"  [ .. ] {m}", flush=True)
def _fail(m: str) -> None: print(f"  [FAIL] {m}", flush=True)
def _warn(m: str) -> None: print(f"  [WARN] {m}", flush=True)


class Refused(RuntimeError):
    """Prerequisites not met."""


class VerifyFailed(AssertionError):
    """The adapter does not behave correctly against the live API."""


def _count(n: int = 1) -> None:
    global _calls
    _calls += n


async def run(full: bool) -> None:
    for var in ("DIGIKEY_CLIENT_ID", "DIGIKEY_CLIENT_SECRET"):
        if not os.environ.get(var):
            raise Refused(
                f"{var} is not set — cannot authenticate. Populate it from .env "
                f"or user-secrets before running."
            )

    from src.adapters.suppliers.digikey import DigiKeyAdapter, DigiKeyQuotaExhausted

    adapter = DigiKeyAdapter()
    base = adapter._base_url
    _ok(f"credentials present; target {base}")
    if "sandbox" in base:
        _warn("targeting the SANDBOX base URL — it is known non-functional "
              "(2026-08-13); results here are not meaningful")

    await adapter.open()
    try:
        # ── 1. OAuth2 ───────────────────────────────────────────────────────
        _step("authenticating (OAuth2 client_credentials)")
        try:
            token = await adapter._ensure_token()
            _count()
        except Exception as exc:
            raise VerifyFailed(
                f"OAuth2 authentication failed: {exc}. Either the credentials "
                f"are wrong/expired, or DigiKey changed the token endpoint. "
                f"Every supplier lookup in Oskar depends on this."
            ) from exc
        if not token or len(token) < 20:
            raise VerifyFailed(f"token looks implausible: {token!r}")
        _ok(f"authenticated (token {len(token)} chars)")

        # ── 2. Known-stable part — the response-shape check ─────────────────
        _step(f"fetching known-stable MPN {STABLE_MPN}")
        try:
            part = await adapter.get_part(STABLE_MPN)
            _count()
        except DigiKeyQuotaExhausted as exc:
            raise Refused(str(exc)) from exc

        if not part:
            raise VerifyFailed(
                f"{STABLE_MPN} returned empty (404). Either the adapter's URL/"
                f"encoding is wrong, or this part left the catalogue — check by "
                f"hand on digikey.com before assuming the adapter is broken."
            )

        # These are the fields Oskar actually consumes. A silent None here is
        # exactly the API-drift failure this script exists to catch: the code
        # would keep "working" while populating empty ECN item data.
        for field in ("description", "manufacturer", "category", "lifecycle"):
            if not part.get(field):
                raise VerifyFailed(
                    f"field {field!r} came back empty for {STABLE_MPN} — DigiKey's "
                    f"response shape has drifted from what the adapter parses. "
                    f"Got: { {k: v for k, v in part.items()} }"
                )
        _ok(f"parsed: {part['manufacturer']} | {part['category']} | "
            f"{part['lifecycle']} | {str(part['description'])[:45]}")

        if not part.get("digikey_part_number"):
            _warn("digikey_part_number is empty — ProductVariations may have "
                  "changed shape (v4 has no top-level DigiKeyPartNumber)")
        else:
            _ok(f"digikey_part_number resolved from ProductVariations: "
                f"{part['digikey_part_number']}")

        if part.get("mounting_type") is None:
            _warn("mounting_type is None — check _extract_mounting_type against "
                  "the live Parameters block if this part should have one")
        else:
            _ok(f"mounting_type normalised: {part['mounting_type']}")

        # ── 3. Percent-encoding — MPNs with '/' ────────────────────────────
        _step(f"fetching MPN containing '/': {SLASH_MPN}")
        slash_part = await adapter.get_part(SLASH_MPN)
        _count()
        if not slash_part:
            raise VerifyFailed(
                f"{SLASH_MPN} returned empty. An unencoded '/' makes DigiKey's "
                f"router treat the MPN as extra path segments and 404 before the "
                f"request reaches the API — indistinguishable from 'not found', "
                f"which is precisely why this case is tested explicitly."
            )
        _ok(f"percent-encoding works: {slash_part['manufacturer']} | "
            f"{str(slash_part['description'])[:40]}")

        # ── 4. Rate-limit headers — the quota guard's foundation ───────────
        if adapter._rate_limit_remaining is None:
            _warn(
                "DigiKey returned no x-ratelimit-* headers, so _check_quota() is "
                "inert — the adapter would keep calling until DigiKey hard-fails. "
                "Worth confirming against DigiKey's current API docs."
            )
        else:
            _ok(f"quota headers present: {adapter._rate_limit_remaining} of "
                f"{adapter._rate_limit} remaining (buffer "
                f"{adapter._rate_limit_buffer})")

        if full:
            # ── 5. Not-found handling ──────────────────────────────────────
            _step("probing a deliberately nonexistent MPN")
            missing = await adapter.get_part(MISSING_MPN)
            _count()
            if missing != {}:
                raise VerifyFailed(
                    f"a nonexistent MPN returned {missing!r} instead of {{}} — "
                    f"SupplierChain relies on {{}} to fall through to the next "
                    f"supplier, so a non-empty result here breaks the fallback."
                )
            _ok("nonexistent MPN correctly returns {} (enables Nexar fallback)")

            # ── 6. Keyword search ──────────────────────────────────────────
            _step("keyword search")
            results = await adapter.search("LM358", limit=3)
            _count()
            if not isinstance(results, list) or not results:
                raise VerifyFailed(
                    f"keyword search returned {type(results).__name__} "
                    f"({len(results) if hasattr(results, '__len__') else '?'} items) "
                    f"— expected a non-empty list under the 'Products' key"
                )
            _ok(f"search returned {len(results)} products")

            # ── 7. Health check ────────────────────────────────────────────
            _step("health_check()")
            healthy = await adapter.health_check()
            _count()
            if not healthy:
                raise VerifyFailed("health_check() returned False against a live API")
            _ok("health_check() passed")

    finally:
        await adapter.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--full", action="store_true",
                        help="run the extended checks (6 calls instead of 3)")
    args = parser.parse_args()

    budget = "6 calls" if args.full else "3 calls"
    print(f"\nDigiKey adapter verification — {budget} against the LIVE API")
    print(f"  budget: 1000 requests/month, allocated to testing\n")

    try:
        asyncio.run(run(args.full))
    except Refused as exc:
        _fail(str(exc))
        print(f"\n  API calls used: {_calls}")
        print("\nRESULT: REFUSED\n")
        return 2
    except VerifyFailed as exc:
        _fail(str(exc))
        print(f"\n  API calls used: {_calls}")
        print("\nRESULT: FAIL — the DigiKey adapter does not match the live API\n")
        return 1
    except Exception:
        _fail("unexpected error:")
        traceback.print_exc()
        print(f"\n  API calls used: {_calls}")
        print("\nRESULT: FAIL (unexpected error)\n")
        return 1

    print(f"\n  API calls used: {_calls}")
    print("\nRESULT: PASS — DigiKey adapter verified against the live API\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
