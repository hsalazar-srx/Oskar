"""
OSKAR IFSAdapter — STUB ONLY (OSKAR v1)

IFS ERP integration is explicitly out of scope for OSKAR v1.
Confirmed by Karen (IT GM) 2026-04-07.

This stub exists to satisfy the ERPAdapter interface and to signal
that IFS wiring is intentionally deferred — not forgotten.

Do NOT:
- Wire this adapter to any production code path in v1
- Design OSKAR data models against IFS field names or semantics
- Remove this file — its presence documents the deferred decision

Activate when: IFS migration timeline is confirmed and OSKAR v2 scoping begins.
"""

from __future__ import annotations

from typing import Any

from src.adapters.erp.base import ERPAdapter

_NOT_IMPLEMENTED_MSG = (
    "IFSAdapter is a stub in OSKAR v1. "
    "IFS integration is out of scope until OSKAR v2. "
    "Use MovexRestAdapter for all ERP access."
)


class IFSAdapter(ERPAdapter):
    """Stub IFS adapter — all methods raise NotImplementedError."""

    # ------------------------------------------------------------------
    # Read methods
    # ------------------------------------------------------------------

    async def get_item(self, item_number: str) -> dict[str, Any]:
        raise NotImplementedError(_NOT_IMPLEMENTED_MSG)

    async def get_item_facility(self, item_number: str, facility: str) -> dict[str, Any]:
        raise NotImplementedError(_NOT_IMPLEMENTED_MSG)

    async def get_bom(self, item_number: str, bom_type: str = "M") -> dict[str, Any]:
        raise NotImplementedError(_NOT_IMPLEMENTED_MSG)

    async def search_items(self, query: str, limit: int = 50) -> list[dict[str, Any]]:
        raise NotImplementedError(_NOT_IMPLEMENTED_MSG)

    async def get_ecn(self, ecn_id: str) -> dict[str, Any]:
        raise NotImplementedError(_NOT_IMPLEMENTED_MSG)

    async def health_check(self) -> bool:
        return False  # Stub always reports unhealthy — not a failure, by design

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
        raise NotImplementedError(_NOT_IMPLEMENTED_MSG)

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
        raise NotImplementedError(_NOT_IMPLEMENTED_MSG)

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
        raise NotImplementedError(_NOT_IMPLEMENTED_MSG)

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
        raise NotImplementedError(_NOT_IMPLEMENTED_MSG)

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
        raise NotImplementedError(_NOT_IMPLEMENTED_MSG)

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
        raise NotImplementedError(_NOT_IMPLEMENTED_MSG)

    async def create_drawing(
        self,
        item_number: str,
        drawing_number: str,
        *,
        idempotency_key: str,
    ) -> dict[str, Any]:
        raise NotImplementedError(_NOT_IMPLEMENTED_MSG)
