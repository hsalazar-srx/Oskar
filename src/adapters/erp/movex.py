"""
OSKAR MovexRestAdapter

Calls movex-rest-api (.NET 8) for all M3/Movex data access and write operations.
movex-rest-api exposes unversioned /api routes — this adapter is the only place
in OSKAR that knows about that URL structure.

Configuration (all from environment — never hardcoded):
    MOVEX_API_URL  — e.g. http://movex-rest-api:80/api  (Docker internal network)
    MOVEX_API_KEY  — API key header for movex-rest-api
    MOVEX_CONO     — Company number: 300=dev/UAT, 100=production (PRE-12)

Resilience (F-4, F-5):
    - Shared httpx.AsyncClient with connection pool (keep-alive, configurable limits)
    - tenacity retry: 3 attempts, exponential backoff, on transient HTTP errors only
    - pybreaker circuit breaker: opens after 5 consecutive failures, 60s recovery window

MSID check:
    Movex MI returns HTTP 200 even on errors — the MSID field in the response body
    indicates the actual outcome. Non-blank MSID = error. Callers must always check.
    See ai/memory/09-known-risks-and-pitfalls.md §4.

Write methods are called by Celery workers only (ADR-005 Transactional Outbox).
Never call write methods from FastAPI request handlers.
"""

from __future__ import annotations

import os
from typing import Any

import httpx
import pybreaker
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from src.adapters.erp.base import ERPAdapter

# ---------------------------------------------------------------------------
# Resilience configuration
# ---------------------------------------------------------------------------

# Circuit breaker: opens after 5 consecutive failures; resets after 60 seconds.
# Shared across all MovexRestAdapter instances (module-level singleton).
_circuit_breaker = pybreaker.CircuitBreaker(
    fail_max=5,
    reset_timeout=60,
    name="movex-rest-api",
)


def _is_transient(exc: BaseException) -> bool:
    """Return True for errors that warrant a retry.

    Retries on: connection errors, timeouts, and 5xx responses.
    Does NOT retry on: 4xx client errors (bad request, not found, unauthorised).
    """
    if isinstance(exc, httpx.TimeoutException):
        return True
    if isinstance(exc, httpx.ConnectError):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code >= 500
    return False


def _retry_decorator() -> Any:
    """tenacity retry: 3 attempts, exponential backoff starting at 1s, max 10s."""
    return retry(
        retry=retry_if_exception(_is_transient),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------


class MovexRestAdapter(ERPAdapter):
    """Production ERP adapter — calls movex-rest-api over HTTP.

    Lifecycle: create once at application startup (lifespan context), close on shutdown.
    The shared AsyncClient maintains a connection pool to movex-rest-api — do not
    create a new client per request.

    Usage (in FastAPI lifespan):
        adapter = MovexRestAdapter()
        await adapter.open()
        ...
        await adapter.close()
    """

    def __init__(self) -> None:
        self.base_url = os.environ["MOVEX_API_URL"].rstrip("/")
        self.api_key = os.getenv("MOVEX_API_KEY")
        self.cono = os.environ["MOVEX_CONO"]   # '300' dev/UAT | '100' production (PRE-12)
        self._headers: dict[str, str] = {}
        if self.api_key:
            self._headers["X-Api-Key"] = self.api_key
        self._client: httpx.AsyncClient | None = None

    async def open(self) -> None:
        """Open the shared connection pool. Call once at application startup."""
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers=self._headers,
            timeout=httpx.Timeout(connect=5.0, read=30.0, write=10.0, pool=5.0),
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        )

    async def close(self) -> None:
        """Close the shared connection pool. Call once at application shutdown."""
        if self._client:
            await self._client.aclose()
            self._client = None

    @property
    def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError(
                "MovexRestAdapter not initialised. Call await adapter.open() at startup."
            )
        return self._client

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @_retry_decorator()
    async def _get(self, path: str, **kwargs: Any) -> httpx.Response:
        """GET with retry + circuit breaker."""
        with _circuit_breaker:
            resp = await self._http.get(path, **kwargs)
            resp.raise_for_status()
            return resp

    @_retry_decorator()
    async def _post(self, path: str, **kwargs: Any) -> httpx.Response:
        """POST with retry + circuit breaker."""
        with _circuit_breaker:
            resp = await self._http.post(path, **kwargs)
            resp.raise_for_status()
            return resp

    # ------------------------------------------------------------------
    # Read methods
    # ------------------------------------------------------------------

    async def get_item(self, item_number: str) -> dict[str, Any]:
        resp = await self._get(f"/items/{item_number}")
        return resp.json()

    async def get_item_facility(self, item_number: str, facility: str) -> dict[str, Any]:
        resp = await self._get(f"/items/{item_number}/facility/{facility}")
        return resp.json()

    async def get_routing_operations(
        self, item_number: str, facility: str, structure_type: str = "001"
    ) -> list[dict[str, Any]]:
        """List active routing ops via PDS002MI.LstOperation (GET, no FDAT/OPNO).

        Returns the records list from the response, or [] if the product has no ops.
        """
        resp = await self._get(
            f"/PDS002MI/LstOperation",
            params={
                "CONO": self.cono,
                "FACI": facility,
                "PRNO": item_number,
                "STRT": structure_type,
            },
        )
        payload = resp.json()
        data = payload.get("data", {})
        return data.get("records", [])

    async def get_bom(self, item_number: str, bom_type: str = "M") -> dict[str, Any]:
        resp = await self._get(f"/bom/{item_number}", params={"type": bom_type})
        return resp.json()

    async def search_items(self, query: str, limit: int = 50) -> list[dict[str, Any]]:
        resp = await self._get("/items", params={"q": query, "limit": limit})
        return resp.json()

    async def get_ecn(self, ecn_id: str) -> dict[str, Any]:
        resp = await self._get(f"/ecn/{ecn_id}")
        return resp.json()

    async def health_check(self) -> bool:
        try:
            resp = await self._http.get("/health", timeout=5.0)
            return resp.status_code == 200
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Write methods — Celery workers only (ADR-005)
    # ------------------------------------------------------------------

    async def create_product(
        self,
        item_number: str,
        item_name: str,
        unit_of_measure: str,
        product_group: str,
        procurement_group: str,
        *,
        item_template: str | None = None,
        responsible_engineer: str | None = None,
        buyer: str | None = None,
        idempotency_key: str,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "cono": self.cono,
            "itno": item_number,
            "itds": item_name,
            "unms": unit_of_measure,
            "itcl": product_group,
            "prgp": procurement_group,
        }
        if item_template:
            payload["atpl"] = item_template
        if responsible_engineer:
            payload["resp"] = responsible_engineer
        if buyer:
            payload["buye"] = buyer

        resp = await self._post(
            "/mi/PDS001MI/AddProduct",
            json=payload,
            headers={"Idempotency-Key": idempotency_key},
        )
        return resp.json()

    async def add_bom_component(
        self,
        parent_item: str,
        component_item: str,
        quantity: float,
        unit_of_measure: str,
        operation_number: int,
        from_date: int,
        *,
        bom_type: str = "M",
        idempotency_key: str,
    ) -> dict[str, Any]:
        resp = await self._post(
            "/mi/PDS002MI/AddComponent",
            json={
                "cono": self.cono,
                "faci": "L",          # facility — will be parameterised Sprint 2
                "prno": parent_item,
                "mseq": str(operation_number),
                "mtno": component_item,
                "opno": operation_number,
                "fdat": from_date,    # YYYYMMDD integer
                "cnqt": quantity,
                "unms": unit_of_measure,
                "boms": bom_type,
            },
            headers={"Idempotency-Key": idempotency_key},
        )
        return resp.json()

    async def delete_bom_component(
        self,
        parent_item: str,
        component_item: str,
        operation_number: int,
        from_date: int,
        *,
        bom_type: str = "M",
        idempotency_key: str,
    ) -> dict[str, Any]:
        resp = await self._post(
            "/mi/PDS002MI/DeleteComponent",
            json={
                "cono": self.cono,
                "prno": parent_item,
                "mtno": component_item,
                "opno": operation_number,
                "fdat": from_date,    # YYYYMMDD integer
                "boms": bom_type,
            },
            headers={"Idempotency-Key": idempotency_key},
        )
        return resp.json()

    async def update_routing_operation(
        self,
        item_number: str,
        operation_number: int,
        *,
        operation_description: str | None = None,
        work_centre: str | None = None,
        run_time: float | None = None,
        idempotency_key: str,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "cono": self.cono,
            "prno": item_number,
            "opno": operation_number,
        }
        if operation_description:
            payload["opds"] = operation_description
        if work_centre:
            payload["plgr"] = work_centre
        if run_time is not None:
            payload["piti"] = run_time

        resp = await self._post(
            "/mi/PDS002MI/UpdateOperation",
            json=payload,
            headers={"Idempotency-Key": idempotency_key},
        )
        return resp.json()

    async def add_routing_operation(
        self,
        item_number: str,
        operation_number: int,
        operation_description: str,
        work_centre: str,
        run_time: float,
        *,
        idempotency_key: str,
    ) -> dict[str, Any]:
        resp = await self._post(
            "/mi/PDS002MI/AddOperation",
            json={
                "cono": self.cono,
                "prno": item_number,
                "opno": operation_number,
                "opds": operation_description,
                "plgr": work_centre,
                "piti": run_time,
            },
            headers={"Idempotency-Key": idempotency_key},
        )
        return resp.json()

    async def add_item_alias(
        self,
        item_number: str,
        alias_number: str,
        alias_type: str,
        *,
        manufacturer: str | None = None,
        is_default: bool = False,
        idempotency_key: str,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "cono": self.cono,
            "itno": item_number,
            "popn": alias_number,
            "alwt": alias_type,
            "deflt": "1" if is_default else "0",
        }
        if manufacturer:
            payload["mfno"] = manufacturer

        resp = await self._post(
            "/mi/MMS025MI/AddAlias",
            json=payload,
            headers={"Idempotency-Key": idempotency_key},
        )
        return resp.json()

    async def create_drawing(
        self,
        item_number: str,
        drawing_number: str,
        *,
        idempotency_key: str,
    ) -> dict[str, Any]:
        # NOTE: MPDDOC implementation path unconfirmed (PRE-12 investigation item).
        # This calls a custom endpoint that @developer-dotnet must implement.
        # See ai/memory/02-movex-erp-authority.md §6 MPDDOC note.
        resp = await self._post(
            "/ecn/drawing",
            json={
                "cono": self.cono,
                "itno": item_number,
                "dwno": drawing_number,
            },
            headers={"Idempotency-Key": idempotency_key},
        )
        return resp.json()
