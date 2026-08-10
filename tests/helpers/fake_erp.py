"""FakeERPAdapter — full ERPAdapter implementation backed by tests/fixtures/bom/*.json.

Slice 0 (ADR-012) test infrastructure. Complements, does not replace, the existing
tests/routers/*.py pattern of patch.object(MovexRestAdapter, "<method>", new_callable=
AsyncMock) for router-level tests — this class is for BOM service-layer tests (Slice A/B
onward) that need a fully working adapter returning realistic, mutually consistent
fixture data across multiple calls in one test.

get_bom routes by item_number through _BOM_FIXTURES; unknown item numbers raise
BOMNotFound (mirrors MovexRestAdapter's 404 -> BOMNotFound contract without
needing a real httpx.Response to build an httpx.HTTPStatusError from). BOMNotFound
subclasses LookupError, so pytest.raises(LookupError) still matches.

Every other ERPAdapter method is not yet stubbed — it raises NotImplementedError,
same pattern as src/adapters/erp/ifs.py, so a test that incidentally calls an
unstubbed method fails loudly instead of silently getting a meaningless canned
value back. Fill a method in with real fixture-backed behaviour only when a test
actually needs it. health_check is the one exception: it must not raise per
ERPAdapter's own docstring ("Must not raise — catch all exceptions").
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.adapters.erp.base import BOMNotFound, ERPAdapter

_FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "bom"

_BOM_FIXTURES = {
    "LF100001": "single_level.json",
    "LF100002": "expired_lines.json",
    "LF900001": "large_500.json",
}

_BOM_INDENTED_FIXTURES = {
    "LF100001": "multi_level.json",
}

_WHERE_USED_FIXTURES = {
    "LF200010": "where_used.json",
}

_NOT_STUBBED_MSG = (
    "FakeERPAdapter.{name} not stubbed — add fixture-backed behaviour when a test needs it"
)


class FakeERPAdapter(ERPAdapter):
    def __init__(self, fixtures_dir: Path | None = None) -> None:
        self._fixtures_dir = fixtures_dir or _FIXTURES_DIR

    # ------------------------------------------------------------------
    # Read methods
    # ------------------------------------------------------------------

    async def get_item(self, item_number: str) -> dict[str, Any]:
        raise NotImplementedError(_NOT_STUBBED_MSG.format(name="get_item"))

    async def get_item_facility(self, item_number: str, facility: str) -> dict[str, Any]:
        raise NotImplementedError(_NOT_STUBBED_MSG.format(name="get_item_facility"))

    async def get_bom(
        self,
        item_number: str,
        facility: str,
        *,
        structure_type: str = "001",
        bom_type: str = "M",
        effective_on: str | None = None,
    ) -> dict[str, Any]:
        filename = _BOM_FIXTURES.get(item_number)
        if filename is None:
            raise BOMNotFound(f"no BOM fixture for item_number={item_number!r}")
        return json.loads((self._fixtures_dir / filename).read_text())

    async def get_bom_indented(
        self,
        item_number: str,
        facility: str,
        *,
        structure_type: str = "001",
        max_depth: int = 12,
    ) -> dict[str, Any]:
        filename = _BOM_INDENTED_FIXTURES.get(item_number)
        if filename is None:
            raise BOMNotFound(f"no indented BOM fixture for item_number={item_number!r}")
        return json.loads((self._fixtures_dir / filename).read_text())

    async def get_where_used(
        self,
        component_number: str,
        facility: str,
        *,
        effective_on: str | None = None,
    ) -> dict[str, Any]:
        filename = _WHERE_USED_FIXTURES.get(component_number)
        if filename is None:
            raise BOMNotFound(f"no where-used fixture for component_number={component_number!r}")
        return json.loads((self._fixtures_dir / filename).read_text())

    async def get_routing_operations(
        self, item_number: str, facility: str, structure_type: str = "001"
    ) -> list[dict[str, Any]]:
        raise NotImplementedError(_NOT_STUBBED_MSG.format(name="get_routing_operations"))

    async def lookup_by_alias(
        self,
        popn: str,
        cuno: str | None = None,
    ) -> list[dict[str, Any]]:
        raise NotImplementedError(_NOT_STUBBED_MSG.format(name="lookup_by_alias"))

    async def get_next_itno_sequence(self, prefix: str) -> int:
        raise NotImplementedError(_NOT_STUBBED_MSG.format(name="get_next_itno_sequence"))

    async def search_items(self, query: str, limit: int = 50) -> list[dict[str, Any]]:
        raise NotImplementedError(_NOT_STUBBED_MSG.format(name="search_items"))

    async def get_ecn(self, ecn_id: str) -> dict[str, Any]:
        raise NotImplementedError(_NOT_STUBBED_MSG.format(name="get_ecn"))

    async def list_open_orders(
        self, item_numbers: list[str], facility: str
    ) -> list[dict[str, Any]]:
        raise NotImplementedError(_NOT_STUBBED_MSG.format(name="list_open_orders"))

    async def health_check(self) -> bool:
        return True

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
        raise NotImplementedError(_NOT_STUBBED_MSG.format(name="create_product"))

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
        bom_type: str = "M",
        idempotency_key: str,
    ) -> dict[str, Any]:
        raise NotImplementedError(_NOT_STUBBED_MSG.format(name="add_bom_component"))

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
        raise NotImplementedError(_NOT_STUBBED_MSG.format(name="delete_bom_component"))

    async def update_bom_component(
        self,
        parent_item: str,
        component_item: str,
        operation_number: int,
        from_date: int,
        to_date: int,
        *,
        facility: str = "D",
        bom_type: str = "M",
        idempotency_key: str,
    ) -> dict[str, Any]:
        raise NotImplementedError(_NOT_STUBBED_MSG.format(name="update_bom_component"))

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
        raise NotImplementedError(_NOT_STUBBED_MSG.format(name="update_routing_operation"))

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
        raise NotImplementedError(_NOT_STUBBED_MSG.format(name="add_routing_operation"))

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
        raise NotImplementedError(_NOT_STUBBED_MSG.format(name="add_item_alias"))
