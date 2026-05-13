"""
OSKAR NexarAdapter — secondary supplier for part description lookup (S3-3)

GraphQL API aggregating DigiKey, Mouser, Arrow, Avnet in one call.
Called when DigiKeyAdapter returns no result for an MPN.

Pricing tiers:
  Free tier    — 100 matched parts/month
  Standard 2025 — 2,000 matched parts/month at $100/month

Credentials (environment variables):
  NEXAR_CLIENT_ID     — Nexar app client ID
  NEXAR_CLIENT_SECRET — Nexar app client secret

OAuth2 token endpoint: https://identity.nexar.com/connect/token
GraphQL endpoint:      https://api.nexar.com/graphql

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
    name="nexar-api",
)

_GRAPHQL_URL = "https://api.nexar.com/graphql"
_TOKEN_URL = "https://identity.nexar.com/connect/token"

# Minimal query — only fields needed for S3-3 description population.
# Iteration 3 will extend this query for pricing + availability fan-out.
_PART_QUERY = """
query SupplyPartDescription($mpn: String!) {
  supplyParts(q: $mpn, limit: 1) {
    hits
    results {
      part {
        mpn
        shortDescription
        manufacturer { name }
        category { name }
        specs { attribute { name } displayValue }
        sellers(includeBrokers: false) {
          company { name }
          offers {
            inventoryLevel
            prices { quantity price currency }
          }
        }
      }
    }
  }
}
"""

_SEARCH_QUERY = """
query SupplySearch($q: String!, $limit: Int!) {
  supplyParts(q: $q, limit: $limit) {
    hits
    results {
      part {
        mpn
        shortDescription
        manufacturer { name }
      }
    }
  }
}
"""


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


class NexarAdapter(SupplierAdapter):
    """Production Nexar adapter — GraphQL, OAuth2, circuit breaker, in-process token cache."""

    def __init__(self) -> None:
        self._client_id = os.environ["NEXAR_CLIENT_ID"]
        self._client_secret = os.environ["NEXAR_CLIENT_SECRET"]
        self._access_token: str | None = None
        self._token_expiry: float = 0.0
        self._http: httpx.AsyncClient | None = None

    async def open(self) -> None:
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
            raise RuntimeError("NexarAdapter not initialised — call await adapter.open()")
        return self._http

    @property
    def supplier_id(self) -> str:
        return "nexar"

    # ------------------------------------------------------------------
    # OAuth2 token management
    # ------------------------------------------------------------------

    async def _ensure_token(self) -> str:
        if self._access_token and time.monotonic() < self._token_expiry - 60:
            return self._access_token
        resp = await self._client.post(
            _TOKEN_URL,
            data={
                "grant_type": "client_credentials",
                "client_id": self._client_id,
                "client_secret": self._client_secret,
            },
        )
        resp.raise_for_status()
        payload = resp.json()
        self._access_token = payload["access_token"]
        self._token_expiry = time.monotonic() + int(payload.get("expires_in", 86400))
        return self._access_token

    # ------------------------------------------------------------------
    # Internal GraphQL helper
    # ------------------------------------------------------------------

    @_retry_dec()
    async def _query(self, query: str, variables: dict[str, Any]) -> dict[str, Any]:
        with _circuit_breaker:
            token = await self._ensure_token()
            resp = await self._client.post(
                _GRAPHQL_URL,
                json={"query": query, "variables": variables},
                headers={"Authorization": f"Bearer {token}"},
            )
            resp.raise_for_status()
            payload = resp.json()
            if "errors" in payload:
                # GraphQL errors are application-layer — not retried
                raise httpx.HTTPStatusError(
                    str(payload["errors"]),
                    request=resp.request,
                    response=resp,
                )
            return payload.get("data", {})

    # ------------------------------------------------------------------
    # SupplierAdapter interface
    # ------------------------------------------------------------------

    async def get_part(self, part_number: str) -> dict[str, Any]:
        """Fetch part detail by MPN via Nexar GraphQL.

        Returns a normalised dict matching DigiKeyAdapter.get_part() shape:
          description  — shortDescription (use for ecn_items.item_name)
          manufacturer — manufacturer name
          category     — Nexar category name

        Returns {} when hits == 0 (part not in Nexar catalogue).
        """
        data = await self._query(_PART_QUERY, {"mpn": part_number})
        results = data.get("supplyParts", {}).get("results", [])
        if not results:
            return {}
        part = results[0].get("part", {})
        return {
            "description": part.get("shortDescription", ""),
            "manufacturer": part.get("manufacturer", {}).get("name", ""),
            "category": part.get("category", {}).get("name", ""),
            "lifecycle": "",   # Nexar does not surface lifecycle status in free tier
            "nexar_mpn": part.get("mpn", ""),
            "unit_price": None,   # pricing available — Iteration 3 will use sellers[]
            "quantity_available": None,
        }

    async def search(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        data = await self._query(_SEARCH_QUERY, {"q": query, "limit": limit})
        results = data.get("supplyParts", {}).get("results", [])
        return [r.get("part", {}) for r in results]

    async def get_pricing(self, part_number: str, quantity: int = 1) -> dict[str, Any]:
        data = await self._query(_PART_QUERY, {"mpn": part_number})
        results = data.get("supplyParts", {}).get("results", [])
        if not results:
            return {"part_number": part_number, "quantity": quantity, "unit_price": None}
        part = results[0].get("part", {})
        unit_price = None
        for seller in part.get("sellers", []):
            for offer in seller.get("offers", []):
                for price in offer.get("prices", []):
                    if price.get("quantity", 1) <= quantity:
                        unit_price = price.get("price")
                        break
        return {
            "part_number": part_number,
            "quantity": quantity,
            "unit_price": unit_price,
            "quantity_available": None,
        }

    async def health_check(self) -> bool:
        try:
            data = await self._query(
                "query { supplyParts(q: \"test\", limit: 1) { hits } }",
                {},
            )
            return "supplyParts" in data
        except Exception:
            return False
