"""
OSKAR Element14Adapter — Farnell / element14 / Newark Product Search API
(Iteration 3, Supplier Intelligence)

Why this adapter, and why it displaces the Future6 placeholder rather than
one of the named stubs (full analysis: docs/supplier-api-landscape.md §4):

  - It is the only FREE, self-service API found that covers needs 3, 4 and 5
    together — price breaks, lead time, and compliance:
      * prices[].cost / .from / .to      → real quantity breaks
      * stock.leastLeadTime              → the ONLY free source found with
                                           lead time as a first-class field
      * rohsStatusCode, countryOfOrigin  → compliance attributes
  - It is the only one with native Malaysian AND Australian storefronts
    (my.element14.com, au.element14.com), matching Scanfil's two sites.

Auth is a plain API key passed as a query parameter (callInfo.apiKey) — no
OAuth, no token cache, no refresh window. That makes this adapter markedly
simpler than DigiKeyAdapter, which is most of why it was cheap to add.

API shape verified against primary documentation 2026-08-27:
  https://partner.element14.com/docs/Product_Search_API_REST__Description
  https://partner.element14.com/search_api/storeInfoid_Values

Rate limits (issued with the "Oskar" app key, 2026-08-28):
  * 2 calls per second
  * 1,000 calls per day

element14 returns NO quota headers, so unlike DigiKey — which reads its live
remaining quota off x-ratelimit-* on every response — this adapter must track
both limits locally. That makes these guards load-bearing, not advisory:
nothing else will stop a burst from breaching the per-second cap or a runaway
loop from burning the day's budget.

Two different mechanisms on purpose:
  * per-second -> THROTTLE (sleep). A transient, self-correcting condition;
    waiting a few hundred ms is correct and invisible to the caller.
  * per-day    -> REFUSE (raise Element14DailyBudgetExhausted). Sleeping until
    midnight is never right. It raises rather than returning {} because
    SupplierChain treats {} as "no such part" and would cache that.

The local counters are per-process. With multiple workers the real ceiling is
per-worker, so the effective budget is (workers x budget) — set
ELEMENT14_DAILY_CALL_BUDGET to the per-worker share, not the account total,
if this ever runs multi-worker.

Caching: results flow through SupplierChain's split-TTL cache, which holds
element14's commercial fields for ≤24h. element14's terms prohibit caching
("cache, record, pre-fetch, or otherwise store any portion of the Farnell
Content") and invite contact for a variance — see the landscape doc §3.
"""

from __future__ import annotations

import asyncio
import math
import os
import time
from collections import deque
from datetime import datetime, timezone
from typing import Any

import httpx
import pybreaker
import structlog
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from src.adapters.suppliers.base import SupplierAdapter

# Reuse DigiKey's mounting-type vocabulary rather than defining a second one —
# S9-3's TH/SMD/MECHANICAL/OTHER field must mean the same thing regardless of
# which supplier answered.
from src.adapters.suppliers.digikey import _normalise_mounting_type

log = structlog.get_logger(__name__)

_circuit_breaker = pybreaker.CircuitBreaker(
    fail_max=5,
    reset_timeout=60,
    name="element14-api",
)

_BASE_URL = "https://api.element14.com/catalog/products"

# Documented limits for the "Oskar" app key (2026-08-28). Defaults match the
# real limits so an unset env cannot silently grant more headroom than exists.
_DEFAULT_MAX_CALLS_PER_SECOND = 2
_DEFAULT_DAILY_BUDGET = 1000

# element14's own documented per-call maximum for numberOfResults. Caps
# search() so an unbounded limit cannot request an enormous response.
_MAX_RESULTS_PER_CALL = 50


class Element14DailyBudgetExhausted(Exception):
    """The local daily call budget is spent.

    Deliberately an exception rather than an empty result: SupplierChain
    treats {} as "no supplier has this part" and would write that to the
    cache, turning a quota problem into permanently-wrong part data.
    """

# JB is the primary site; Melbourne overrides via ELEMENT14_STORE_ID.
_DEFAULT_STORE = "my.element14.com"

# element14 attribute labels that carry mounting information.
#
# CORRECTED 2026-08-28 against live responses: element14 has NO "Mounting
# Type" attribute at all. It uses category-specific package labels instead —
# "Resistor Case / Package", "IC Case / Package", "Capacitor Case / Package"
# and so on. Matching only "mounting type" found nothing on any real part.
#
# Rather than enumerate every category's label, any label ending in
# "case / package" (or "package"/"case style") is treated as the package
# field. The value is then run through DigiKey's normaliser, which already
# recognises package names like "0402 [1005 Metric]" -> SMD via its
# "package / case" handling.
_MOUNTING_ATTRIBUTE_SUFFIXES = ("case / package", "case/package", "package", "case style")
_MOUNTING_ATTRIBUTE_LABELS = ("mounting type", "mounting")

# Package strings that imply surface mount even though the DigiKey normaliser
# would not recognise them — element14 reports bare package codes, not the
# descriptive "Surface Mount" text DigiKey uses.
_SMD_PACKAGE_HINTS = (
    "metric", "soic", "sot", "qfn", "qfp", "bga", "dfn", "csp", "smd", "smt",
    "0201", "0402", "0603", "0805", "1206", "1210", "2010", "2512",
)
_TH_PACKAGE_HINTS = ("dip", "pdip", "to-92", "to-220", "radial", "axial", "through")

# productStatus -> Oskar's DigiKey-shaped lifecycle vocabulary.
#
# NO_LONGER_STOCKED is deliberately NOT mapped to "Obsolete": it means
# element14 stopped stocking the part, which says nothing about whether the
# manufacturer still makes it. Mapping it to Obsolete would drive false EOL
# alerts on parts that are perfectly available elsewhere.
_LIFECYCLE_MAP = {
    "STOCKED": "Active",
    "DIRECT_SHIP": "Active",
    "NO_LONGER_MANUFACTURED": "Obsolete",
    "NO_LONGER_STOCKED": "Not Stocked",
}


def _map_lifecycle(product_status: str | None) -> str:
    """Map element14's productStatus to Oskar's lifecycle vocabulary.

    An unrecognised status returns "" rather than a guess — a wrong lifecycle
    value feeds EOL alerting, so silence beats invention.
    """
    if not product_status:
        return ""
    return _LIFECYCLE_MAP.get(str(product_status).strip().upper(), "")


def _extract_lead_time_weeks(stock: dict[str, Any] | None) -> int | None:
    """stock.leastLeadTime (days) -> whole weeks.

    Rounds UP. A lead time understated by rounding down is the one that
    causes a missed build; overstating it merely prompts an earlier order.
    """
    if not stock:
        return None
    days = stock.get("leastLeadTime")
    if days is None:
        return None
    return math.ceil(int(days) / 7)


def _package_from_value(raw_value: str) -> str | None:
    """Classify a bare package string (e.g. "0402 [1005 Metric]", "SOIC").

    element14 reports package CODES, where DigiKey reports descriptive text
    ("Surface Mount"). The DigiKey normaliser is tried first so shared
    vocabulary stays in one place; these hints only cover what it cannot
    recognise on its own.
    """
    v = raw_value.strip().lower()
    if not v:
        return None
    if any(h in v for h in _TH_PACKAGE_HINTS):
        return "TH"
    if any(h in v for h in _SMD_PACKAGE_HINTS):
        return "SMD"
    return None


def _extract_mounting_type(attributes: list[dict[str, Any]] | None) -> str | None:
    """Derive TH/SMD from element14's category-specific package attribute.

    element14 has no mounting-type field; it exposes "<Category> Case /
    Package" instead (verified against live responses 2026-08-28). Returns
    None when nothing recognisable is present — a wrong TH/SMD value is worse
    than an absent one, since S9-3's field feeds real engineering decisions.
    """
    for attr in attributes or []:
        label = str(attr.get("attributeLabel", "")).strip().lower()
        value = str(attr.get("attributeValue", ""))

        is_mounting_label = label in _MOUNTING_ATTRIBUTE_LABELS
        is_package_label = any(label.endswith(s) for s in _MOUNTING_ATTRIBUTE_SUFFIXES)
        if not (is_mounting_label or is_package_label):
            continue

        # Prefer the shared DigiKey vocabulary, then fall back to package-code
        # hints for the bare codes element14 actually returns.
        normalised = _normalise_mounting_type(value)
        if normalised and normalised != "OTHER":
            return normalised
        from_package = _package_from_value(value)
        if from_package:
            return from_package
    return None


def _rohs_compliant(product: dict[str, Any]) -> bool | None:
    """RoHS status code -> True / False / None.

    CORRECTED 2026-08-28 against the live API. The real code for a compliant
    part is "Y-EX" (compliant under an Annex III exemption), not "YES" as the
    field documentation implied. Matching only "YES" reported every compliant
    part as NON-compliant — worse than reporting nothing, because a false
    compliance failure looks like a real finding.

    element14 publishes no authoritative code list, so the rule is: any
    Y-prefixed code is compliant, N-prefixed is not, anything else is
    unknown. The raw code is preserved separately (rohs_status_code) so a
    human can inspect what was actually returned rather than trusting this
    reduction.

    None is meaningfully different from False: unknown compliance is not the
    same as known non-compliance.
    """
    code = product.get("rohsStatusCode")
    if code is None:
        return None
    normalised = str(code).strip().upper()
    if not normalised:
        return None
    if normalised.startswith("Y"):
        return True
    if normalised.startswith("N"):
        return False
    return None


def _price_breaks(product: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {"from": p.get("from"), "to": p.get("to"), "cost": p.get("cost")}
        for p in product.get("prices", []) or []
    ]


def _unit_price(breaks: list[dict[str, Any]]) -> float | None:
    """The qty-1 price specifically, not whichever break comes first.

    Consumers read unit_price as the single-unit price; element14 does not
    guarantee break ordering, so the lowest `from` is selected explicitly.
    """
    if not breaks:
        return None
    first = min(breaks, key=lambda b: b.get("from") or 0)
    return first.get("cost")


def _is_retryable(exc: BaseException) -> bool:
    return isinstance(exc, (httpx.ConnectError, httpx.TimeoutException))


class Element14Adapter(SupplierAdapter):
    """element14 / Farnell adapter — API key auth, circuit breaker."""

    def __init__(self) -> None:
        api_key = os.getenv("ELEMENT14_API_KEY")
        if not api_key:
            # Fail at construction, not on the first lookup. SupplierChain
            # swallows adapter exceptions and falls through, so a
            # misconfigured adapter that only fails mid-chain degrades
            # silently and looks like "element14 has no data for anything".
            raise RuntimeError(
                "ELEMENT14_API_KEY is not set — Element14Adapter cannot be constructed."
            )
        self._api_key = api_key
        self._store_id = os.getenv("ELEMENT14_STORE_ID", _DEFAULT_STORE)
        self._http: httpx.AsyncClient | None = None

        # Rate-limit state. element14 sends no quota headers, so both limits
        # are tracked locally — see the module docstring.
        self._max_calls_per_second = int(
            os.getenv("ELEMENT14_MAX_CALLS_PER_SECOND", str(_DEFAULT_MAX_CALLS_PER_SECOND))
        )
        self._daily_budget = int(
            os.getenv("ELEMENT14_DAILY_CALL_BUDGET", str(_DEFAULT_DAILY_BUDGET))
        )
        # Monotonic timestamps of recent calls, for the sliding 1s window.
        self._call_times: deque[float] = deque()
        self._calls_today = 0
        self._budget_day = self._utc_day()
        # Serialises the throttle check so concurrent callers cannot each see
        # a clear window and fire together, breaching the per-second cap.
        self._throttle_lock = asyncio.Lock()

    @staticmethod
    def _utc_day() -> str:
        return datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")

    def _reset_budget_if_new_day(self) -> None:
        today = self._utc_day()
        if today != self._budget_day:
            log.info(
                "element14.daily_budget_reset",
                previous_day=self._budget_day,
                calls_used=self._calls_today,
            )
            self._budget_day = today
            self._calls_today = 0

    async def _await_rate_limit_slot(self) -> None:
        """Block until a call may be made, or raise if the day's budget is gone.

        The daily check happens BEFORE any sleeping — there is no point
        throttling into a budget that is already exhausted, and the refusal
        must not consume a call.
        """
        async with self._throttle_lock:
            self._reset_budget_if_new_day()

            if self._calls_today >= self._daily_budget:
                log.warning(
                    "element14.daily_budget_exhausted",
                    calls_today=self._calls_today,
                    budget=self._daily_budget,
                )
                raise Element14DailyBudgetExhausted(
                    f"element14 daily call budget exhausted "
                    f"({self._calls_today}/{self._daily_budget} used today) — "
                    "refusing further calls until UTC midnight."
                )

            # Sliding 1-second window: drop anything older than 1s, then wait
            # only if the window is still full.
            now = time.monotonic()
            while self._call_times and now - self._call_times[0] >= 1.0:
                self._call_times.popleft()

            if len(self._call_times) >= self._max_calls_per_second:
                wait_for = 1.0 - (now - self._call_times[0])
                if wait_for > 0:
                    log.debug("element14.throttled", wait_seconds=round(wait_for, 3))
                    await asyncio.sleep(wait_for)
                    now = time.monotonic()
                    while self._call_times and now - self._call_times[0] >= 1.0:
                        self._call_times.popleft()

            self._call_times.append(time.monotonic())
            self._calls_today += 1

    @property
    def supplier_id(self) -> str:
        return "element14"

    # ------------------------------------------------------------------

    async def open(self) -> None:
        """Create the shared connection pool. Matches NexarAdapter's lifecycle
        so main.py can treat every supplier adapter identically."""
        self._http = httpx.AsyncClient(
            timeout=httpx.Timeout(connect=5.0, read=15.0, write=10.0, pool=5.0),
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
        )

    async def close(self) -> None:
        if self._http:
            await self._http.aclose()
            self._http = None

    def _client(self) -> httpx.AsyncClient:
        # Lazily construct if open() was not called — keeps unit tests and any
        # script usage working without a lifespan, while main.py still gets a
        # properly pooled client via open().
        if self._http is None:
            self._http = httpx.AsyncClient(
                timeout=httpx.Timeout(connect=5.0, read=15.0, write=10.0, pool=5.0),
                limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
            )
        return self._http

    def _base_params(self) -> dict[str, Any]:
        return {
            "callInfo.apiKey": self._api_key,
            "callInfo.responseDataFormat": "JSON",
            "storeInfo.id": self._store_id,
            # "large" is the response group that carries prices, stock and
            # attributes together — "medium" omits the attributes needed for
            # mounting type, and separate calls would triple the request count.
            "resultsSettings.responseGroup": "large",
        }

    async def _get(self, params: dict[str, Any]) -> dict[str, Any]:
        """Rate-limited entry point. Every API call goes through here.

        The guard runs before the circuit breaker and retry logic on purpose:
        a retry storm is exactly the burst that would breach the per-second
        cap, so each retry attempt must take its own slot rather than
        bypassing the throttle.
        """
        await self._await_rate_limit_slot()
        return await self._raw_get(params)

    @_circuit_breaker
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception(_is_retryable),
        reraise=True,
    )
    async def _raw_get(self, params: dict[str, Any]) -> dict[str, Any]:
        resp = await self._client().get(_BASE_URL, params=params)
        resp.raise_for_status()
        return resp.json()

    @staticmethod
    def _products(payload: dict[str, Any]) -> list[dict[str, Any]]:
        """Extract products regardless of which envelope element14 used.

        CORRECTED 2026-08-28 against the live API: the top-level key depends
        on the SEARCH TYPE, which the documentation describes nowhere near the
        term prefixes it documents.

            manuPartNum: -> manufacturerPartNumberSearchReturn
            any:         -> keywordSearchReturn

        Reading only keywordSearchReturn made every MPN lookup return {},
        silently — {} is a legitimate "not found", so nothing would have
        surfaced this short of calling the real API.
        """
        for envelope in (
            "manufacturerPartNumberSearchReturn",
            "keywordSearchReturn",
            "premierFarnellPartNumberReturn",
        ):
            block = payload.get(envelope)
            if block:
                return block.get("products", []) or []
        return []

    def _to_part(self, product: dict[str, Any]) -> dict[str, Any]:
        breaks = _price_breaks(product)
        stock = product.get("stock") or {}
        return {
            "description": product.get("displayName", ""),
            "manufacturer": product.get("brandName", ""),
            "category": "",  # element14 exposes category only via a separate call
            "lifecycle": _map_lifecycle(product.get("productStatus")),
            "mounting_type": _extract_mounting_type(product.get("attributes")),
            "element14_sku": product.get("sku", ""),
            "country_of_origin": product.get("countryOfOrigin", ""),
            "rohs_compliant": _rohs_compliant(product),
            # The raw code is kept alongside the boolean because element14
            # publishes no authoritative code list — "Y-EX" (exemption) and a
            # plain "Y" both reduce to True but mean different things to a
            # compliance reviewer.
            "rohs_status_code": product.get("rohsStatusCode", ""),
            "lead_time_weeks": _extract_lead_time_weeks(stock),
            "unit_price": _unit_price(breaks),
            "price_breaks": breaks,
            # Real parts carry an MOQ and their price breaks start there, not
            # at 1 — found in the live response, absent from the documented
            # field list. Useful for quoting.
            "moq": product.get("translatedMinimumOrderQuality"),
            "quantity_available": stock.get("level"),
        }

    # ------------------------------------------------------------------
    # SupplierAdapter interface
    # ------------------------------------------------------------------

    async def get_part(self, part_number: str) -> dict[str, Any]:
        """Look up one MPN.

        Uses the manuPartNum: term prefix, not any: — a keyword search would
        return loosely-related parts and silently mis-populate a description
        with a neighbouring part's text.
        """
        params = self._base_params() | {
            "term": f"manuPartNum:{part_number.strip()}",
            "resultsSettings.offset": 0,
            "resultsSettings.numberOfResults": 1,
        }
        payload = await self._get(params)
        products = self._products(payload)
        if not products:
            return {}
        return self._to_part(products[0])

    async def search(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        # One search is one API call regardless of numberOfResults, so the cap
        # is about response size, not budget — but an unbounded limit invites
        # an enormous payload. Clamped to element14's own per-call maximum.
        params = self._base_params() | {
            "term": f"any:{query.strip()}",
            "resultsSettings.offset": 0,
            "resultsSettings.numberOfResults": min(limit, _MAX_RESULTS_PER_CALL),
        }
        payload = await self._get(params)
        return [self._to_part(p) for p in self._products(payload)]

    async def get_pricing(self, part_number: str, quantity: int = 1) -> dict[str, Any]:
        params = self._base_params() | {
            "term": f"manuPartNum:{part_number.strip()}",
            "resultsSettings.offset": 0,
            "resultsSettings.numberOfResults": 1,
        }
        payload = await self._get(params)
        products = self._products(payload)
        if not products:
            return {
                "part_number": part_number,
                "quantity": quantity,
                "unit_price": None,
                "quantity_available": None,
            }

        product = products[0]
        breaks = _price_breaks(product)
        unit_price = _price_for_quantity(breaks, quantity)
        stock = product.get("stock") or {}
        return {
            "part_number": part_number,
            "quantity": quantity,
            "unit_price": unit_price,
            "quantity_available": stock.get("level"),
            "price_breaks": breaks,
            "lead_time_weeks": _extract_lead_time_weeks(stock),
        }

    async def health_check(self) -> bool:
        try:
            params = self._base_params() | {
                "term": "any:resistor",
                "resultsSettings.offset": 0,
                "resultsSettings.numberOfResults": 1,
            }
            await self._get(params)
            return True
        except Exception:
            return False


def _price_for_quantity(
    breaks: list[dict[str, Any]], quantity: int
) -> float | None:
    """The cost of the break whose range covers `quantity`.

    Falls back to the lowest break when the quantity sits below the first
    range — element14's first break normally starts at 1, but a part with a
    minimum order quantity starts higher, and returning None there would read
    as "no price available" for a part that plainly has one.
    """
    if not breaks:
        return None
    for b in sorted(breaks, key=lambda x: x.get("from") or 0):
        low = b.get("from") or 0
        high = b.get("to")
        if quantity >= low and (high is None or quantity <= high):
            return b.get("cost")
    ordered = sorted(breaks, key=lambda x: x.get("from") or 0)
    if quantity < (ordered[0].get("from") or 0):
        return ordered[0].get("cost")
    return ordered[-1].get("cost")
