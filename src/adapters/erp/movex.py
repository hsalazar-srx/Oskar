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
import time
from typing import Any

import httpx
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from src.adapters.erp.base import BOMNotFound, ERPAdapter

# ---------------------------------------------------------------------------
# Resilience configuration
# ---------------------------------------------------------------------------

# pybreaker 1.2.0 uses Tornado internals in call_async — incompatible with asyncio.
# Minimal async-native circuit breaker: opens after 5 consecutive failures, 60s reset.
class _AsyncCircuitBreaker:
    def __init__(self, fail_max: int = 5, reset_timeout: int = 60) -> None:
        self._fail_max = fail_max
        self._reset_timeout = reset_timeout
        self._failures = 0
        self._opened_at: float | None = None

    def _is_open(self) -> bool:
        if self._opened_at is None:
            return False
        if time.monotonic() - self._opened_at >= self._reset_timeout:
            self._failures = 0
            self._opened_at = None
            return False
        return True

    async def call_async(self, fn: Any, *args: Any, **kwargs: Any) -> Any:
        if self._is_open():
            raise RuntimeError("movex-rest-api circuit breaker is open — too many consecutive failures")
        try:
            result = await fn(*args, **kwargs)
            self._failures = 0
            return result
        except Exception:
            self._failures += 1
            if self._failures >= self._fail_max:
                self._opened_at = time.monotonic()
            raise


_circuit_breaker = _AsyncCircuitBreaker(fail_max=5, reset_timeout=60)


def _uppercase_keys(d: dict[str, Any]) -> dict[str, Any]:
    """Normalise one record/head dict's top-level keys to uppercase.

    The real movex-rest-api BOM endpoints (B-1/B-2/B-3) return lowercase JSON
    keys ("prno", "mseq", "mtno", ...) — verified live 2026-07-31 against
    localhost:5000, item LFRMR241-7278 — not the uppercase M3-MI-style keys
    the contract doc and every downstream consumer (src/services/bom/
    browse.py, explode.py, FakeERPAdapter, all Slice A-C fixtures/tests)
    assumed. This is movex-rest-api's own established, consistent convention
    (get_next_itno_sequence already reads lowercase "next_seq" from
    /parts/next-sequence) — Oskar's contract doc was wrong, not the service.
    Normalising here, once, at the adapter boundary, means nothing
    downstream needs to change.
    """
    return {k.upper(): v for k, v in d.items()}


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
            self._headers["X-API-Key"] = self.api_key
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
        async def _call() -> httpx.Response:
            resp = await self._http.get(path, **kwargs)
            resp.raise_for_status()
            return resp
        return await _circuit_breaker.call_async(_call)

    @_retry_decorator()
    async def _post(self, path: str, **kwargs: Any) -> httpx.Response:
        """POST with retry + circuit breaker."""
        async def _call() -> httpx.Response:
            resp = await self._http.post(path, **kwargs)
            resp.raise_for_status()
            return resp
        return await _circuit_breaker.call_async(_call)

    # ------------------------------------------------------------------
    # Read methods
    # ------------------------------------------------------------------

    async def lookup_by_alias(
        self,
        popn: str,
        cuno: str | None = None,
    ) -> list[dict[str, Any]]:
        """Reverse alias lookup via custom DB2 endpoint GET /api/parts/search-alias.

        No M3 MI program supports POPN→ITNO direction (confirmed 2026-05-11).
        movex-rest-api queries MVXCDTA.MITPOP directly:
          SELECT TRIM(MPITNO), TRIM(MPPOPN), TRIM(MPALWT), TRIM(MPALWQ), TRIM(MPE0PA)
          FROM MVXCDTA.MITPOP
          WHERE MPCONO=@cono AND MPPOPN=@popn [AND MPE0PA=@e0pa]
        """
        params: dict[str, str] = {
            "cono": self.cono,
            "popn": popn.strip(),
        }
        if cuno:
            params["e0pa"] = cuno.strip()
        resp = await self._get("/parts/search-alias", params=params)
        payload = resp.json()
        return payload.get("data", {}).get("records", [])

    async def get_next_itno_sequence(self, prefix: str) -> int:
        """Next available sequence via GET /api/parts/next-sequence.

        movex-rest-api queries MAX(TRIM(MMITNO)) FROM MVXCDTA.MITMAS
        WHERE MMCONO=@cono AND MMITNO LIKE @prefix||'%', returns next_seq integer.
        Returns 1 when no items with this prefix exist.
        """
        resp = await self._get(
            "/parts/next-sequence",
            params={"cono": self.cono, "prefix": prefix},
        )
        payload = resp.json()
        return int(payload.get("data", {}).get("next_seq", 1))

    async def list_customers(self) -> list[dict[str, Any]]:
        """List active Movex customers via GET /api/customers/list.

        movex-rest-api queries MVXCDTA.OCUSMA WHERE OKCONO=@cono AND OKSTAT='20',
        returns records with CUNO (4-digit numeric customer code) and NAME.
        """
        resp = await self._get("/customers/list", params={"cono": self.cono})
        payload = resp.json()
        return payload.get("data", {}).get("records", [])

    async def get_item(self, item_number: str) -> dict[str, Any]:
        """Fetch item master record via MMS200MI.GetItmBasic (generic MI transaction route).

        Returns a dict with keys: STAT, ITNO, ITDS (item name ≤30 chars), ITTY, UNMS.
        Returns {} when the item does not exist.

        Uses POST, not GET (fixed 2026-08-25). The generic MI passthrough route
        rejects GET outright — movex-rest-api answers
        `{"success":false,"error":"Transaction is not configured for GET. Use
        POST with a JSON body."}` with HTTP 400, verified live against CONO=300.
        Every other MI call in this adapter already POSTs; this method was the
        only one issuing a GET, so it could never have succeeded against the
        real service.

        It went unnoticed because its only caller until now was parts.py's
        autofill preview, which swallows ERP errors on the dry_run path
        (`movex_item = None`) and degrades silently rather than failing. The
        ADR-014 parent-existence check is the first caller that depends on a
        real answer, which is what surfaced it.

        Not-found is reported by this route as HTTP 422 with
        `{"success": false, "error": "Item number X does not exist"}`, not as a
        404 — also verified live. 404, 422 and a 200-with-success-false are all
        treated as "not found" and return {}, so callers have one contract.
        """
        try:
            resp = await self._post(
                "/MMS200MI/GetItmBasic",
                json={"CONO": self.cono, "ITNO": item_number.strip()},
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in (404, 422):
                return {}
            raise
        payload = resp.json()
        # A 200 with success=false is possible on this passthrough route; treat
        # it the same as not-found rather than returning a falsey envelope that
        # a caller might read as a real item.
        if payload.get("success") is False:
            return {}
        return payload.get("data", payload)

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

    async def get_bom(
        self,
        item_number: str,
        facility: str,
        *,
        structure_type: str = "001",
        bom_type: str = "M",
        effective_on: str | None = None,
    ) -> dict[str, Any]:
        """B-1: GET /api/bom/{itno}?cono&faci&strt&effectiveOn.

        bom_type has no B-1 query-param equivalent (see base.py docstring) —
        accepted only for ERP-neutral interface parity, never sent here.
        Raises BOMNotFound on HTTP 404 (no MPDHED head record).
        """
        params: dict[str, Any] = {
            "cono": self.cono,
            "faci": facility,
            "strt": structure_type,
        }
        if effective_on:
            params["effectiveOn"] = effective_on
        try:
            resp = await self._get(f"/bom/{item_number}", params=params)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                raise BOMNotFound(
                    f"No BOM found for item_number={item_number!r} facility={facility!r} "
                    f"structure_type={structure_type!r}"
                ) from exc
            raise
        payload = resp.json()
        data = payload.get("data", {})
        if "head" in data:
            data["head"] = _uppercase_keys(data["head"])
        if "records" in data:
            data["records"] = [_uppercase_keys(r) for r in data["records"]]
        return payload

    async def get_bom_indented(
        self,
        item_number: str,
        facility: str,
        *,
        structure_type: str = "001",
        max_depth: int = 12,
    ) -> dict[str, Any]:
        """B-2: GET /api/bom/{itno}/indented?cono&faci&strt&levl."""
        resp = await self._get(
            f"/bom/{item_number}/indented",
            params={
                "cono": self.cono,
                "faci": facility,
                "strt": structure_type,
                "levl": max_depth,
            },
        )
        payload = resp.json()
        data = payload.get("data", {})
        if "records" in data:
            data["records"] = [_uppercase_keys(r) for r in data["records"]]
        return payload

    async def get_where_used(
        self,
        component_number: str,
        facility: str,
        *,
        effective_on: str | None = None,
    ) -> dict[str, Any]:
        """B-3: GET /api/bom/where-used/{mtno}?cono&faci&effectiveOn."""
        params: dict[str, Any] = {"cono": self.cono, "faci": facility}
        if effective_on:
            params["effectiveOn"] = effective_on
        resp = await self._get(f"/bom/where-used/{component_number}", params=params)
        payload = resp.json()
        data = payload.get("data", {})
        if "records" in data:
            data["records"] = [_uppercase_keys(r) for r in data["records"]]
        return payload

    async def search_items(self, query: str, limit: int = 50) -> list[dict[str, Any]]:
        resp = await self._get("/items", params={"q": query, "limit": limit})
        return resp.json()

    async def get_ecn(self, ecn_id: str) -> dict[str, Any]:
        resp = await self._get(f"/ecn/{ecn_id}")
        return resp.json()

    async def list_open_orders(
        self, item_numbers: list[str], facility: str
    ) -> list[dict[str, Any]]:
        """Open MOs for the given item numbers via PMS100MI.Select.

        Selects all MOs with WHST 10–40 (planned/released/started) for the facility,
        then filters to the provided item_numbers in Python.
        """
        if not item_numbers:
            return []
        resp = await self._post(
            "/PMS100MI/Select",
            json={
                "CONO": self.cono,
                "FACF": facility,
                "FACT": facility,
                "STSF": "10",
                "STST": "40",
            },
        )
        payload = resp.json()
        records: list[dict[str, Any]] = payload.get("data", {}).get("records", [])
        item_set = {n.strip().upper() for n in item_numbers}
        return [r for r in records if str(r.get("PRNO", "")).strip().upper() in item_set]

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
            "/PDS001MI/AddProduct",
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
        facility: str = "D",
        structure_type: str = "001",
        sequence_number: int | None = None,
        bom_type: str = "M",
        idempotency_key: str,
    ) -> dict[str, Any]:
        """PDS002MI.AddComponent.

        Field names and casing verified against the real transaction config
        (movex-rest-api transactions/PDS002MI.json, 2026-08-11) — this
        method was never live-tested before (AddComponent didn't exist on
        movex-rest-api until recently) and had three real bugs, all fixed
        here:

          1. Payload keys were lowercase (cono/prno/mtno/...). The generic MI
             passthrough (Controllers/TransactionController.cs's
             ExecuteTransaction -> TransactionStringBuilder.ResolveFieldValue)
             does a case-SENSITIVE Dictionary.ContainsKey(field.Name) lookup
             against the real field names, which are uppercase (CONO, PRNO,
             MTPL, ...) — confirmed by add_routing_operation's own payload,
             the one BOM/routing write method already live-verified. A
             docstring on this method previously claimed BOM writes use "the
             same lowercase convention" as the custom DB2 read endpoints
             (B-1/B-2/B-3) — that conflated genuinely-lowercase READ
             response JSON with M3 MI transaction WRITE field names, which
             are always uppercase regardless of program. Every key below is
             now the real field name.
          2. Component item number's real field is MTPL, not MTNO (MTNO is
             only the field's *description*, "Component Item Number
             (MTNO)") — was sent as "mtno", matching neither.
          3. unms/boms didn't correspond to any real AddComponent field at
             all (the real U/M field is PEUN; there is no BOM-type field on
             this transaction). structure_type (STRT, required) and a real
             sequence_number (MSEQ, required — distinct from OPNO, the
             operation number) were both missing entirely; MSEQ was
             previously set to str(operation_number), silently conflating
             two unrelated fields. sequence_number now comes from
             ecn_bom_changes.sequence_number (via _queue_bom_changes_outbox)
             — falls back to operation_number only if the caller has none,
             matching the previous (imperfect but non-crashing) behaviour
             for existing rows authored before this field was wired up.
             bom_type is kept as a parameter for interface symmetry with the
             rest of Oskar's BOM code (compare engine, DB columns) but is
             not sent — Movex has no equivalent field on this transaction.

        facility (R9, ADR-012): parameterised from the ECN's actual
        facility, matching add_routing_operation/update_routing_operation.
        Defaults to 'D' only for backward compatibility with any caller
        that predates this fix — _queue_bom_changes_outbox always passes
        the ECN's real facility explicitly.
        """
        resp = await self._post(
            "/PDS002MI/AddComponent",
            json={
                "CONO": self.cono,
                "FACI": facility,
                "PRNO": parent_item,
                "STRT": structure_type,
                "MSEQ": sequence_number if sequence_number is not None else operation_number,
                "OPNO": operation_number,
                "FDAT": from_date,    # YYYYMMDD integer
                "MTPL": component_item,
                "CNQT": quantity,
                "PEUN": unit_of_measure,
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
        facility: str = "D",
        structure_type: str = "001",
        sequence_number: int | None = None,
        bom_type: str = "M",
        idempotency_key: str,
    ) -> dict[str, Any]:
        """PDS002MI.Delete (component variant — this one program's Delete
        transaction handles both BOM-component and routing-operation delete
        via MSEQ vs OPNO, per its real field descriptions: "MSEQ: Sequence
        Number (use for component delete)").

        Not on _queue_bom_changes_outbox's dispatch path today — D6 always
        closes via UpdateComponent rather than physically deleting — so this
        method had never actually been exercised. Live-verified 2026-08-11
        against real movex-rest-api (CONO=300, item LFAM050001) while
        confirming add_bom_component's fix, turning up three real bugs here
        too, all fixed:

          1. There is no "DeleteComponent" transaction on movex-rest-api —
             checked transactions/PDS002MI.json directly; the real, only
             delete transaction is named "Delete". The old path would 404.
          2. Payload keys were lowercase, matching the same wrong assumption
             fixed in add_bom_component (see that method's docstring for the
             full explanation) — the real MI field-name match is
             case-sensitive and uppercase.
          3. FDAT is required in practice even though the transaction config
             marks it optional. Live-tested directly: a real Delete call
             with MSEQ but no FDAT returned {"success": false, "error":
             "Sequence number ... does not exist"} for an MSEQ confirmed to
             exist via a direct B-1 read moments earlier; adding FDAT (part
             of MPDMAT's real 7-field key, CONO+FACI+PRNO+STRT+MSEQ+OPNO+
             FDAT, per analysis/PDS002MI-routing-analysis.md) made the
             identical call succeed, and the line's removal was confirmed
             via a second B-1 read.
        """
        resp = await self._post(
            "/PDS002MI/Delete",
            json={
                "CONO": self.cono,
                "FACI": facility,
                "PRNO": parent_item,
                "STRT": structure_type,
                "MSEQ": sequence_number if sequence_number is not None else operation_number,
                "FDAT": from_date,    # YYYYMMDD integer — required in practice, see docstring
            },
            headers={"Idempotency-Key": idempotency_key},
        )
        return resp.json()

    async def update_bom_component(
        self,
        parent_item: str,
        component_item: str,
        operation_number: int,
        from_date: int,
        to_date: int,
        *,
        facility: str = "D",
        structure_type: str = "001",
        sequence_number: int | None = None,
        bom_type: str = "M",
        idempotency_key: str,
    ) -> dict[str, Any]:
        """PDS002MI.UpdateComponent (W-1) — DEAD CODE, not called anywhere.

        NOT ON THE DISPATCH TABLE (see _dispatch_mi_call, movex_outbox.py)
        and never queued by _queue_bom_changes_outbox (workflow.py) as of
        I2-19 (2026-08-11). Kept only for reference and in case a future
        movex-rest-api fix makes TDAT worth revisiting — do not wire this
        back into the dispatch path without a fresh live-OQ pass confirming
        TDAT actually persists.

        Why it was retired: W-1 is deployed on movex-rest-api and its key/
        lookup/general-update mechanism was confirmed working via live
        testing against CONO=300 — but the ONE field this method exists to
        write, TDAT, was confirmed BROKEN: the call returned success
        ({"success": true}, raw M3 response "OK"), yet TDAT was unchanged on
        read-back (via both B-1 and a direct GetComponent call), reproduced
        3 times across 2 separate test lines, including with a minimal
        payload (only the key fields + TDAT, nothing else). Isolated as
        TDAT-specific, not a general UpdateComponent problem: an identical
        call updating CNQT instead (1.0 -> 5.0) succeeded and was confirmed
        via read-back on the same line. Also ruled out: field-name vs.
        position-number key lookup (both gave the same wrong result), JSON
        type of the TDAT value (numeric vs. string, same result), and
        interference from neighbouring optional fields (OPNO/MTPL/CNQT
        present or absent, same result). RPG source (analysis/PDS002MI.txt,
        RCOM14) shows Q2TDAT is moved to DCTDAT unconditionally alongside
        every other field — the C# payload-building layer also looked
        correct for TDAT's configured position/length. The bug is most
        likely inside PDS002BE (the underlying M3 API program the MI
        transaction calls), not visible in the RPG source available here —
        needs the movex-rest-api owner's own investigation.

        Instead, per the movex-rest-api team's own suggestion (confirmed
        against Stargile's real source, which never used UpdateComponent/
        TDAT for BOM lines either), Oskar now closes lines via
        delete_bom_component (PDS002MI.Delete, live-verified working) —
        see workflow.py's _queue_bom_changes_outbox docstring for the
        current CHANGE/DELETE model.

        Field names/casing (CONO/FACI/PRNO/STRT/MSEQ/OPNO/FDAT/MTPL/TDAT)
        are confirmed correct against the real, configured transaction
        (transactions/PDS002MI.json, "Field positions MiTest-verified
        2026-08-11") — MSEQ is the required key field (not OPNO/FDAT, which
        are optional per the config but were needed in practice to resolve
        a specific line during testing, same as Delete's FDAT requirement).

        from_date identifies which existing MPDMAT line to close (part of
        its key: CONO+FACI+PRNO+STRT+MSEQ+OPNO+FDAT, per
        analysis/PDS002MI-routing-analysis.md) — to_date is the TDAT
        value that would be written, if this method were ever reactivated.
        """
        resp = await self._post(
            "/PDS002MI/UpdateComponent",
            json={
                "CONO": self.cono,
                "FACI": facility,
                "PRNO": parent_item,
                "STRT": structure_type,
                "MSEQ": sequence_number if sequence_number is not None else operation_number,
                "OPNO": operation_number,
                "FDAT": from_date,    # YYYYMMDD integer — identifies the line being closed
                "TDAT": to_date,      # YYYYMMDD integer — BROKEN on movex-rest-api as of 2026-08-11, see docstring
            },
            headers={"Idempotency-Key": idempotency_key},
        )
        return resp.json()

    async def update_routing_operation(
        self,
        item_number: str,
        facility: str,
        operation_number: int,
        *,
        structure_type: str = "001",
        work_centre: str | None = None,
        run_time: float | None = None,
        idempotency_key: str,
    ) -> dict[str, Any]:
        """PDS002MI.UpdateOperation. Note: this transaction has no description
        field (PLGR/PITI only) — operation_description is not sent to Movex.

        PITI must be an all-numeric-character string with no decimal point —
        M3 stores run time as minutes * 100 (confirmed via live write:
        PITI="545" -> stored/returned as 54500 by LstOperation)."""
        payload: dict[str, Any] = {
            "CONO": self.cono,
            "FACI": facility,
            "PRNO": item_number,
            "STRT": structure_type,
            "OPNO": operation_number,
        }
        if work_centre:
            payload["PLGR"] = work_centre
        if run_time is not None:
            payload["PITI"] = str(round(run_time * 100))

        resp = await self._post(
            "/PDS002MI/UpdateOperation",
            json=payload,
            headers={"Idempotency-Key": idempotency_key},
        )
        return resp.json()

    async def add_routing_operation(
        self,
        item_number: str,
        facility: str,
        operation_number: int,
        work_centre: str,
        run_time: float,
        *,
        operation_description: str | None = None,
        structure_type: str = "001",
        idempotency_key: str,
    ) -> dict[str, Any]:
        """PDS002MI.AddOperation.

        OPDS (operation description) is REQUIRED by M3, despite
        transactions/PDS002MI.json marking it `required: false`. Live-verified
        2026-08-18 against CONO=300: the previous payload (CONO/FACI/PRNO/STRT/
        OPNO/PLGR/PITI, no OPDS) failed with
            {"success": false, "error": "Operation description must be entered"}
        and the identical call with OPDS added succeeded (MSID "000"). This is
        the same config-vs-reality mismatch already documented for FDAT on
        Delete — the transaction config's `required` flags cannot be trusted
        as the source of truth for what M3 actually enforces.

        This method's docstring previously asserted "this transaction has no
        description field (PLGR/PITI only)", which is why
        _queue_routing_operations_outbox dropped operation_description on the
        floor. That claim was wrong: every AddOperation Oskar dispatched would
        have failed, retried 10x, abandoned, and paged the EM.

        PITI must be an all-numeric-character string with no decimal point —
        M3 stores run time as minutes * 100 (confirmed via live write:
        PITI="545" -> stored/returned as 54500 by LstOperation). Sending a
        float (e.g. 1.0) is rejected with "Field 'PITI' must contain only
        numeric characters (0-9)".

        Note the created row has FDAT=0 unless one is supplied — relevant when
        deleting it again, since Delete matches on the full key including FDAT.
        """
        resp = await self._post(
            "/PDS002MI/AddOperation",
            json={
                "CONO": self.cono,
                "FACI": facility,
                "PRNO": item_number,
                "STRT": structure_type,
                "OPNO": operation_number,
                "PLGR": work_centre,
                "PITI": str(round(run_time * 100)),
                # Fall back to a non-empty placeholder rather than omitting the
                # field: M3 rejects a blank OPDS outright, so an ECN whose
                # routing row has no description must still produce a valid
                # write instead of a guaranteed 10-retry failure.
                "OPDS": (operation_description or f"Operation {operation_number}")[:30],
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
            "/MMS025MI/AddAlias",
            json=payload,
            headers={"Idempotency-Key": idempotency_key},
        )
        return resp.json()

