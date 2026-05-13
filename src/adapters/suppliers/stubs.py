"""
OSKAR Supplier Adapter Stubs (PRE-5)

Stub adapters for suppliers not yet integrated. Each raises NotImplementedError.
Stubs satisfy the SupplierAdapter ABC so the Iteration 3 fan-out can be wired
without changing call sites.

Production adapters already implemented (S3-3):
  - DigiKeyAdapter  (src/adapters/suppliers/digikey.py)
  - NexarAdapter    (src/adapters/suppliers/nexar.py)

Remaining stubs — wire in Iteration 3 (Supplier Intelligence module).
"""

from __future__ import annotations

from typing import Any

from src.adapters.suppliers.base import SupplierAdapter

_STUB_MSG = "{supplier} adapter is a stub in OSKAR v1. Wire in Iteration 3."


class _SupplierStub(SupplierAdapter):
    """Generic stub base — override supplier_id only."""

    async def search(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        raise NotImplementedError(_STUB_MSG.format(supplier=self.supplier_id))

    async def get_part(self, part_number: str) -> dict[str, Any]:
        raise NotImplementedError(_STUB_MSG.format(supplier=self.supplier_id))

    async def get_pricing(self, part_number: str, quantity: int = 1) -> dict[str, Any]:
        raise NotImplementedError(_STUB_MSG.format(supplier=self.supplier_id))

    async def health_check(self) -> bool:
        return False  # Stubs always report unhealthy — by design, not a failure


class MouserAdapter(_SupplierStub):
    @property
    def supplier_id(self) -> str:
        return "mouser"


class RSComponentsAdapter(_SupplierStub):
    @property
    def supplier_id(self) -> str:
        return "rs-components"


class ArrowAdapter(_SupplierStub):
    @property
    def supplier_id(self) -> str:
        return "arrow"


class AvnetAdapter(_SupplierStub):
    @property
    def supplier_id(self) -> str:
        return "avnet"


class Future6Adapter(_SupplierStub):
    """Placeholder for a sixth supplier — replace when supplier is confirmed."""

    @property
    def supplier_id(self) -> str:
        return "future6-placeholder"
