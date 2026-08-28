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

Rate limits: element14 publishes no hard number, describing only a "courtesy
allowance" — unverified, and deliberately NOT modelled here with an invented
threshold. DigiKey's quota guard exists because DigiKey reports live quota in
response headers; element14 gives nothing to read, so a hardcoded limit would
be a guess dressed as a control. The circuit breaker below is the real
protection.

Caching: results flow through SupplierChain's split-TTL cache, which holds
element14's commercial fields for ≤24h. element14's terms prohibit caching
("cache, record, pre-fetch, or otherwise store any portion of the Farnell
Content") and invite contact for a variance — see the landscape doc §3.
"""

from __future__ import annotations

import math
import os
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

# JB is the primary site; Melbourne overrides via ELEMENT14_STORE_ID.
_DEFAULT_STORE = "my.element14.com"

# element14 attribute labels that carry mounting information. Kept separate
# from DigiKey's parameter names — same concept, different vocabulary.
_MOUNTING_ATTRIBUTE_LABELS = ("mounting type", "mounting", "package / case", "case style")

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


def _extract_mounting_type(attributes: list[dict[str, Any]] | None) -> str | None:
    """Scan element14's attributes[] for a mounting-type-equivalent label."""
    for attr in attributes or []:
        label = str(attr.get("attributeLabel", "")).strip().lower()
        if label in _MOUNTING_ATTRIBUTE_LABELS:
            normalised = _normalise_mounting_type(str(attr.get("attributeValue", "")))
            if normalised:
                return normalised
    return None


def _rohs_compliant(product: dict[str, Any]) -> bool | None:
    """YES/NO -> True/False; absent -> None.

    None is meaningfully different from False here: unknown compliance is not
    the same as known non-compliance, and collapsing them would let an
    unverified part read as a confirmed RoHS failure.
    """
    code = product.get("rohsStatusCode")
    if code is None:
        return None
    return str(code).strip().upper() == "YES"


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

    @_circuit_breaker
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception(_is_retryable),
        reraise=True,
    )
    async def _get(self, params: dict[str, Any]) -> dict[str, Any]:
        resp = await self._client().get(_BASE_URL, params=params)
        resp.raise_for_status()
        return resp.json()

    @staticmethod
    def _products(payload: dict[str, Any]) -> list[dict[str, Any]]:
        return payload.get("keywordSearchReturn", {}).get("products", []) or []

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
            "lead_time_weeks": _extract_lead_time_weeks(stock),
            "unit_price": _unit_price(breaks),
            "price_breaks": breaks,
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
        params = self._base_params() | {
            "term": f"any:{query.strip()}",
            "resultsSettings.offset": 0,
            "resultsSettings.numberOfResults": limit,
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
