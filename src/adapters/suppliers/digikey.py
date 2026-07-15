"""
OSKAR DigiKeyAdapter — primary supplier for part description lookup (S3-3)

OAuth2 client-credentials flow against DigiKey Product Information API v4.
Primary use: get_part(mpn) → description → ecn_items.item_name auto-population.

Credentials (environment variables):
  DIGIKEY_CLIENT_ID      — DigiKey developer app client ID
  DIGIKEY_CLIENT_SECRET  — DigiKey developer app client secret
  DIGIKEY_BASE_URL       — Default: https://api.digikey.com
                           Sandbox: https://sandbox-api.digikey.com

Rate limit: DigiKey reports its own live quota on every response via the
x-ratelimit-limit / x-ratelimit-remaining headers — there is no fixed
documented number to hardcode (sandbox and production tiers differ, and
DigiKey can change plan limits without notice). This adapter reads those
headers after every real API call, logs them, and refuses further calls
once x-ratelimit-remaining drops below DIGIKEY_RATE_LIMIT_BUFFER (default
20) until DigiKey's own window resets. Local supplier_part_cache table
means most MPN lookups are served from PostgreSQL, not from this API.

Circuit breaker: opens after 5 consecutive failures, 60 s recovery window.
Token: cached in-process, refreshed proactively 60 s before expiry.
"""

from __future__ import annotations

import os
import time
from typing import Any
from urllib.parse import quote

import httpx
import pybreaker
import structlog
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from src.adapters.suppliers.base import SupplierAdapter

log = structlog.get_logger(__name__)


class DigiKeyQuotaExhausted(Exception):
    """Raised when DigiKey's own reported quota (x-ratelimit-remaining) has
    dropped below the configured safety buffer. Caller (SupplierChain) treats
    this the same as any other adapter failure and falls through to Nexar."""

_circuit_breaker = pybreaker.CircuitBreaker(
    fail_max=5,
    reset_timeout=60,
    name="digikey-api",
)


async def _call_with_breaker(cb: pybreaker.CircuitBreaker, coro_fn: Any, *args: Any, **kwargs: Any) -> Any:
    """Run an async callable through a pybreaker CircuitBreaker.

    pybreaker's CircuitBreaker supports neither the context-manager protocol
    (`with cb:`) nor genuinely async `call_async` (it requires tornado, which
    is not installed) — both would raise/hang if used directly here. Instead
    this drives the breaker's state machine by hand, mirroring exactly what
    the synchronous `CircuitBreaker.call()` does internally:
      1. `before_call` raises CircuitBreakerError when open (or flips to
         half-open after the reset timeout has elapsed);
      2. `_handle_error`/`_handle_success` record the outcome — these (not
         the lower-level `on_failure`/`on_success`) are what actually
         increment/reset the failure counter and notify listeners.
    """
    cb.state.before_call(coro_fn, *args, **kwargs)
    try:
        result = await coro_fn(*args, **kwargs)
    except BaseException as exc:
        cb.state._handle_error(exc)
        raise
    else:
        cb.state._handle_success()
        return result


def _is_transient(exc: BaseException) -> bool:
    if isinstance(exc, (httpx.TimeoutException, httpx.ConnectError)):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code >= 500
    return False


def _retry_dec() -> Any:
    return retry(
        retry=retry_if_exception(_is_transient),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )


# DigiKey Product Information API v4 "Parameters" array carries attribute
# name/value pairs per part, e.g. {"ParameterText": "Mounting Type",
# "ValueText": "Surface Mount, MOSFET"}. Values are free text — normalise to
# Oskar's fixed mounting_type set (TH | SMD | MECHANICAL | OTHER).
_MOUNTING_TYPE_PARAM_NAMES = {"mounting type", "package / case"}

_SMD_HINTS = ("surface mount", "smd", "smt")
_TH_HINTS = ("through hole", "thru-hole", "through-hole", "tht")
_MECHANICAL_HINTS = (
    "mechanical", "hardware", "connector", "standoff", "fastener",
    "screw", "nut", "washer", "bracket", "enclosure",
)


def _normalise_mounting_type(raw_value: str) -> str | None:
    """Map a free-text DigiKey parameter value to TH | SMD | MECHANICAL | OTHER."""
    v = raw_value.strip().lower()
    if not v:
        return None
    if any(h in v for h in _MECHANICAL_HINTS):
        return "MECHANICAL"
    if any(h in v for h in _SMD_HINTS):
        return "SMD"
    if any(h in v for h in _TH_HINTS):
        return "TH"
    return "OTHER"


def _extract_mounting_type(product: dict[str, Any]) -> str | None:
    """Scan the Product.Parameters array for a mounting-type-equivalent attribute."""
    for param in product.get("Parameters", []) or []:
        name = str(param.get("ParameterText", "")).strip().lower()
        if name in _MOUNTING_TYPE_PARAM_NAMES:
            normalised = _normalise_mounting_type(str(param.get("ValueText", "")))
            if normalised:
                return normalised
    return None


class DigiKeyAdapter(SupplierAdapter):
    """Production DigiKey adapter — OAuth2, circuit breaker, in-process token cache."""

    def __init__(self) -> None:
        self._client_id = os.environ["DIGIKEY_CLIENT_ID"]
        self._client_secret = os.environ["DIGIKEY_CLIENT_SECRET"]
        self._base_url = os.getenv("DIGIKEY_BASE_URL", "https://api.digikey.com").rstrip("/")
        # Token endpoint must match the configured host — sandbox credentials are
        # only valid against sandbox-api.digikey.com/v1/oauth2/token, not production.
        # A hardcoded production URL here would 401 every sandbox app forever.
        self._token_url = f"{self._base_url}/v1/oauth2/token"
        self._access_token: str | None = None
        self._token_expiry: float = 0.0
        self._http: httpx.AsyncClient | None = None
        # DigiKey's own last-reported quota state (from x-ratelimit-* response
        # headers). None until the first real API call this process has made.
        self._rate_limit: int | None = None
        self._rate_limit_remaining: int | None = None
        self._rate_limit_buffer = int(os.getenv("DIGIKEY_RATE_LIMIT_BUFFER", "20"))

    async def open(self) -> None:
        """Open the shared connection pool. Call once at application startup."""
        self._http = httpx.AsyncClient(
            timeout=httpx.Timeout(connect=5.0, read=15.0, write=10.0, pool=5.0),
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
        )

    async def close(self) -> None:
        if self._http:
            await self._http.aclose()
            self._http = None

    @property
    def _client(self) -> httpx.AsyncClient:
        if self._http is None:
            raise RuntimeError("DigiKeyAdapter not initialised — call await adapter.open()")
        return self._http

    @property
    def supplier_id(self) -> str:
        return "digikey"

    # ------------------------------------------------------------------
    # OAuth2 token management
    # ------------------------------------------------------------------

    async def _ensure_token(self) -> str:
        """Return a valid bearer token, refreshing proactively 60 s before expiry."""
        if self._access_token and time.monotonic() < self._token_expiry - 60:
            return self._access_token
        resp = await self._client.post(
            self._token_url,
            data={
                "grant_type": "client_credentials",
                "client_id": self._client_id,
                "client_secret": self._client_secret,
            },
        )
        resp.raise_for_status()
        payload = resp.json()
        self._access_token = payload["access_token"]
        self._token_expiry = time.monotonic() + int(payload.get("expires_in", 3600))
        return self._access_token

    # ------------------------------------------------------------------
    # Quota tracking — sourced entirely from DigiKey's own response headers
    # ------------------------------------------------------------------

    def _record_rate_limit(self, resp: httpx.Response) -> None:
        limit = resp.headers.get("x-ratelimit-limit")
        remaining = resp.headers.get("x-ratelimit-remaining")
        if limit is None or remaining is None:
            return
        self._rate_limit = int(limit)
        self._rate_limit_remaining = int(remaining)
        log.info(
            "digikey.rate_limit",
            limit=self._rate_limit,
            remaining=self._rate_limit_remaining,
            base_url=self._base_url,
        )

    def _check_quota(self) -> None:
        if (
            self._rate_limit_remaining is not None
            and self._rate_limit_remaining < self._rate_limit_buffer
        ):
            log.warning(
                "digikey.quota_exhausted",
                remaining=self._rate_limit_remaining,
                buffer=self._rate_limit_buffer,
                base_url=self._base_url,
            )
            raise DigiKeyQuotaExhausted(
                f"DigiKey quota nearly exhausted ({self._rate_limit_remaining} "
                f"remaining, buffer={self._rate_limit_buffer}) — refusing further "
                f"calls against {self._base_url} until DigiKey's window resets."
            )

    # ------------------------------------------------------------------
    # Internal GET helper
    # ------------------------------------------------------------------

    @_retry_dec()
    async def _get(self, path: str, **kwargs: Any) -> httpx.Response:
        self._check_quota()

        async def _do_request() -> httpx.Response:
            token = await self._ensure_token()
            resp = await self._client.get(
                f"{self._base_url}{path}",
                headers={
                    "Authorization": f"Bearer {token}",
                    "X-DIGIKEY-Client-Id": self._client_id,
                },
                **kwargs,
            )
            self._record_rate_limit(resp)
            resp.raise_for_status()
            return resp

        return await _call_with_breaker(_circuit_breaker, _do_request)

    # ------------------------------------------------------------------
    # SupplierAdapter interface
    # ------------------------------------------------------------------

    async def get_part(self, part_number: str) -> dict[str, Any]:
        """Fetch part detail by manufacturer part number (MPN).

        Returns a normalised dict:
          description  — product description (use for ecn_items.item_name, ≤30 chars enforced by caller)
          manufacturer — manufacturer name
          category     — DigiKey product category
          lifecycle    — product lifecycle status string

        Returns {} if the MPN is not found in the DigiKey catalogue (HTTP 404).
        Raises on non-404 errors — caller catches and falls through to Nexar.
        """
        try:
            # MPNs routinely contain '/', '+', '#' (e.g. "LM741CN/NOPB") — these
            # must be percent-encoded or DigiKey's router treats them as extra
            # path segments and 404s before the request ever reaches the API
            # (a different, indistinguishable-looking 404 from "MPN not found").
            resp = await self._get(
                f"/products/v4/search/{quote(part_number, safe='')}/productdetails",
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return {}
            raise
        payload = resp.json()
        product = payload.get("Product", {})
        # v4's productdetails response has no top-level DigiKeyPartNumber — the
        # DigiKey-assigned part number only exists per-package inside
        # ProductVariations (e.g. "LM741CNNS/NOPB-ND" for the Tube variation).
        # Use the first variation as the representative DigiKey part number.
        variations = product.get("ProductVariations", []) or []
        digikey_part_number = variations[0].get("DigiKeyProductNumber", "") if variations else ""
        return {
            "description": product.get("Description", {}).get("DetailedDescription", ""),
            "manufacturer": product.get("Manufacturer", {}).get("Name", ""),
            "category": product.get("Category", {}).get("Name", ""),
            "lifecycle": product.get("ProductStatus", {}).get("Status", ""),
            "digikey_part_number": digikey_part_number,
            "unit_price": product.get("UnitPrice"),
            "quantity_available": product.get("QuantityAvailable"),
            "mounting_type": _extract_mounting_type(product),
        }

    async def search(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        resp = await self._get(
            "/products/v4/search/keyword",
            params={"keywords": query, "limit": limit, "offset": 0},
        )
        return resp.json().get("Products", [])

    async def get_pricing(self, part_number: str, quantity: int = 1) -> dict[str, Any]:
        resp = await self._get(f"/products/v4/search/{quote(part_number, safe='')}/productdetails")
        product = resp.json().get("Product", {})
        unit_price = None
        for br in product.get("StandardPricing", []):
            if br.get("BreakQuantity", 1) <= quantity:
                unit_price = br.get("UnitPrice")
        return {
            "part_number": part_number,
            "quantity": quantity,
            "unit_price": unit_price,
            "quantity_available": product.get("QuantityAvailable"),
        }

    async def health_check(self) -> bool:
        try:
            await self._get("/products/v4/search/categories")
            return True
        except Exception:
            return False
