"""
OSKAR ERP Adapter Interface

Decouples OSKAR business logic from any specific ERP system.
All ERP access goes through this interface — no direct DB2 calls from business logic.

Implementations:
- MovexRestAdapter: Production — calls movex-rest-api (.NET 8)
- IFSAdapter: Stub — raises NotImplementedError (out of scope for OSKAR v1)

CONO environment mapping (PRE-12):
  MOVEX_CONO=300  — development, staging, all UAT/OQ test cases
  MOVEX_CONO=100  — production only
CONO is read from the MOVEX_CONO env var at adapter startup and injected into every MI
call. It is never passed by callers and never hardcoded in this file.

Write methods (ADR-005, Phase 2 gate F-2):
All 7 ECN write operations are defined here before any business logic is written.
Celery workers call these methods via the Transactional Outbox — never FastAPI handlers.
Every write method accepts an idempotency_key that maps to movex_outbox.idempotency_key.
Callers must always check the MSID field in the response dict — non-blank means error
even when the HTTP status is 200 (known Movex MI behaviour, ai/memory/09 §4).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class ERPAdapter(ABC):
    """Abstract base for all ERP adapters.

    Read methods — used during ECN authoring and pre-validation.
    Write methods — called only by Celery workers via the Transactional Outbox (ADR-005).
    """

    # ------------------------------------------------------------------
    # Read methods
    # ------------------------------------------------------------------

    @abstractmethod
    async def get_item(self, item_number: str) -> dict[str, Any]:
        """Fetch item master record by item number (MMS200MI.GetItmBasic / MITMAS).

        Used to validate that an item exists before it is added to an ECN.
        Raises on item not found or connection failure.
        """
        ...

    @abstractmethod
    async def get_item_facility(self, item_number: str, facility: str) -> dict[str, Any]:
        """Fetch facility-specific item data (MMS200MI.GetItmFac).

        Returns item status, cost, and warehouse balance for the given item + facility.
        Used during cost review display and pre-validation at APPROVED.
        """
        ...

    @abstractmethod
    async def get_bom(self, item_number: str, bom_type: str = "M") -> dict[str, Any]:
        """Fetch the live BOM structure for an item from Movex.

        Used for BOM concurrency detection at DC_REVIEW: the result is stored as
        ecn_bom_changes.movex_snapshot_at_review and compared before the APPROVED write.
        bom_type: 'M' = manufacturing BOM (default).
        """
        ...

    @abstractmethod
    async def get_routing_operations(
        self, item_number: str, facility: str, structure_type: str = "001"
    ) -> list[dict[str, Any]]:
        """Fetch all active routing operations for a product (PDS002MI.LstOperation).

        Pre-flight read before any AddOperation / UpdateOperation write.
        Call without OPNO or FDAT — uses the 4-field key (CONO+FACI+PRNO+STRT) so
        all operations are returned from the start of the index (confirmed 2026-05-08,
        see movex-rest-api/analysis/PDS002MI-routing-analysis.md).
        Returns a list of MPDOPE row dicts. Each dict has at minimum:
          OPNO (int), OPDS (str), PLGR (str), PITI (float), SETI (float),
          FDAT (int YYYYMMDD), TDAT (int YYYYMMDD).
        Raises on connection failure. Returns [] if no operations exist.
        """
        ...

    @abstractmethod
    async def lookup_by_alias(
        self,
        popn: str,
        cuno: str | None = None,
    ) -> list[dict[str, Any]]:
        """Reverse alias lookup: customer P/N → Scanfil APAC ITNO(s) via MVXCDTA.MITPOP.

        No M3 MI program supports this direction (MMS025MI.GetAlias/LstAlias both
        require ITNO as input — confirmed 2026-05-11). Implemented as a custom
        parameterised DB2 endpoint on movex-rest-api: GET /api/mitpop/search.

        Args:
            popn: Customer/manufacturer part number (MITPOP.MPPOPN). Stripped before call.
            cuno: Optional customer/partner code (MITPOP.MPE0PA). Narrows results.

        Returns:
            List of MITPOP row dicts, each with: ITNO, POPN, ALWT, ALWQ, E0PA.
            Returns [] when POPN has no alias in MITPOP — this is the no_match case,
            not an error. Caller maps list length to full_match / partial_match / no_match.

        Raises:
            httpx.HTTPStatusError: on non-transient 4xx/5xx from movex-rest-api.
            pybreaker.CircuitBreakerError: when the circuit breaker is open.
        """
        ...

    @abstractmethod
    async def get_next_itno_sequence(
        self,
        prefix: str,
    ) -> int:
        """Return the next available 4-digit sequence number for an item number prefix.

        Queries MVXCDTA.MITMAS for the highest MMITNO matching '{prefix}%' via
        custom DB2 endpoint GET /api/mitmas/next-sequence, then returns max_seq + 1.
        CONO is injected by the adapter from its own configuration — callers must not pass it.

        Args:
            prefix: 6-char prefix, e.g. 'LFLM05' (LF + 2-char CUNO + 2-digit commodity).

        Returns:
            Next integer sequence number (1-based). Caller zero-pads to 4 digits.
            Returns 1 when no items with this prefix exist yet.

        Raises:
            httpx.HTTPStatusError: on non-transient 4xx/5xx from movex-rest-api.
            pybreaker.CircuitBreakerError: when the circuit breaker is open.
        """
        ...

    @abstractmethod
    async def search_items(self, query: str, limit: int = 50) -> list[dict[str, Any]]:
        """Search item master by description or item number prefix (MMS200MI.GetItmBasic).

        Used by the ECN item search UI. Returns a list of matching item records.
        """
        ...

    @abstractmethod
    async def get_ecn(self, ecn_id: str) -> dict[str, Any]:
        """Fetch ECN document header (MPDOCHEAD).

        Used for read-only reference during ECN authoring.
        """
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """Return True if the ERP connection is healthy.

        Called by /api/v1/health/ready. Must not raise — catch all exceptions and
        return False so the health endpoint can report degraded status with a 503.
        """
        ...

    # ------------------------------------------------------------------
    # Write methods — Celery workers only (ADR-005)
    # ------------------------------------------------------------------

    @abstractmethod
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
        """Create a new item header in Movex (PDS001MI.AddProduct).

        Called at APPROVED→IMPLEMENTED for each ecn_items row where is_new_item=TRUE.
        CONO is injected by the adapter — do not pass it here.
        Returns the full MI response dict. Caller must check MSID — non-blank = error.
        idempotency_key maps to movex_outbox.idempotency_key; prevents duplicate calls on retry.
        """
        ...

    @abstractmethod
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
        """Add a component line to a BOM (PDS002MI.AddComponent).

        from_date is an YYYYMMDD integer (Movex DB2 numeric date format).
        Pre-validate from_date against ecn_bom_changes.movex_snapshot_at_review before calling.
        Returns MI response. Caller must check MSID.
        """
        ...

    @abstractmethod
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
        """Remove a component line from a BOM (PDS002MI.DeleteComponent).

        from_date is an YYYYMMDD integer (Movex DB2 numeric date format).
        Returns MI response. Caller must check MSID.
        """
        ...

    @abstractmethod
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
        """Modify an existing routing operation (PDS002MI.UpdateOperation).

        All optional fields are keyword-only. Pass only the fields being changed.
        Returns MI response. Caller must check MSID.
        """
        ...

    @abstractmethod
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
        """Add a new routing step to an item (PDS002MI.AddOperation).

        Returns MI response. Caller must check MSID.
        """
        ...

    @abstractmethod
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
        """Register an MPN alias in MITPOP (MMS025MI.AddAlias).

        Called at IMPLEMENTED for each ecn_mpns row where alias_written=FALSE.
        alias_type: typically 'POPN' (purchasing part number / MPN).
        is_default maps to the CMZDEFFL field in Movex.
        Returns MI response. Caller must check MSID.
        """
        ...

    @abstractmethod
    async def create_drawing(
        self,
        item_number: str,
        drawing_number: str,
        *,
        idempotency_key: str,
    ) -> dict[str, Any]:
        """Create a drawing record in MPDDOC by copying the #TEMPLATE record.

        IMPORTANT: The implementation path is unconfirmed (PRE-12 investigation item).
        Stargile uses a direct DB2 INSERT (PreparedStatementHelper), not a standard MI
        program. The @developer-dotnet team must confirm whether movex-rest-api will
        expose this as an MI transaction or a custom /api/ecn/drawing endpoint.
        See ai/memory/02-movex-erp-authority.md §6 MPDDOC note.
        Returns the response dict. Caller must check for error indicators.
        """
        ...
