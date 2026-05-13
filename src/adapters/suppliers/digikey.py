"""
OSKAR DigiKeyAdapter — primary supplier for part description lookup (S3-3)

OAuth2 client-credentials flow against DigiKey Product Information API v4.
Primary use: get_part(mpn) → description → ecn_items.item_name auto-population.

Credentials (environment variables):
  DIGIKEY_CLIENT_ID      — DigiKey developer app client ID
  DIGIKEY_CLIENT_SECRET  — DigiKey developer app client secret
  DIGIKEY_BASE_URL       — Default: https://api.digikey.com
                           Sandbox: https://sandbox-api.digikey.com

Rate limit: 1,000 requests/day (free tier). Local supplier_part_cache table
means most MPN lookups are served from PostgreSQL, not from this API.

Circuit breaker: opens after 5 consecutive failures, 60 s recovery window.
Token: cached in-process, refreshed proactively 60 s before expiry.
"""

from __future__ import annotations

import os
import time
from typing import Any

import httpx
import pybreaker
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from src.adapters.suppliers.base import SupplierAdapter

_circuit_breaker = pybreaker.CircuitBreaker(
    fail_max=5,
    reset_timeout=60,
    name="digikey-api",
)


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


class DigiKeyAdapter(SupplierAdapter):
    """Production DigiKey adapter — OAuth2, circuit breaker, in-process token cache."""

    _TOKEN_URL = "https://api.digikey.com/v1/oauth2/token"

    def __init__(self) -> None:
        self._client_id = os.environ["DIGIKEY_CLIENT_ID"]
        self._client_secret = os.environ["DIGIKEY_CLIENT_SECRET"]
        self._base_url = os.getenv("DIGIKEY_BASE_URL", "https://api.digikey.com").rstrip("/")
        self._access_token: str | None = None
        self._token_expiry: float = 0.0
        self._http: httpx.AsyncClient | None = None

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
            self._TOKEN_URL,
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
    # Internal GET helper
    # ------------------------------------------------------------------

    @_retry_dec()
    async def _get(self, path: str, **kwargs: Any) -> httpx.Response:
        with _circuit_breaker:
            token = await self._ensure_token()
            resp = await self._client.get(
                f"{self._base_url}{path}",
                headers={
                    "Authorization": f"Bearer {token}",
                    "X-DIGIKEY-Client-Id": self._client_id,
                },
                **kwargs,
            )
            resp.raise_for_status()
            return resp

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
            resp = await self._get(
                f"/products/v4/search/{part_number}/productdetails",
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return {}
            raise
        payload = resp.json()
        product = payload.get("Product", {})
        return {
            "description": product.get("Description", {}).get("DetailedDescription", ""),
            "manufacturer": product.get("Manufacturer", {}).get("Name", ""),
            "category": product.get("Category", {}).get("Name", ""),
            "lifecycle": product.get("ProductStatus", {}).get("Status", ""),
            "digikey_part_number": product.get("DigiKeyPartNumber", ""),
            "unit_price": product.get("UnitPrice"),
            "quantity_available": product.get("QuantityAvailable"),
        }

    async def search(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        resp = await self._get(
            "/products/v4/search/keyword",
            params={"keywords": query, "limit": limit, "offset": 0},
        )
        return resp.json().get("Products", [])

    async def get_pricing(self, part_number: str, quantity: int = 1) -> dict[str, Any]:
        resp = await self._get(f"/products/v4/search/{part_number}/productdetails")
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
