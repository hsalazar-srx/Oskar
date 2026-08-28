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


# Future6Adapter was the unnamed sixth-supplier placeholder. It is now a real
# adapter: Element14Adapter (src/adapters/suppliers/element14.py), chosen over
# the named stubs above because it is the only free, self-service API covering
# price breaks + lead time + compliance together, with native my./au.
# storefronts. See docs/supplier-api-landscape.md §4.
#
# On the remaining stubs, from that same research (2026-08-27):
#   - RSComponentsAdapter — RS publishes NO public API (account-gated PunchOut
#     only). This stub is very likely unimplementable as written; confirm with
#     the RS account manager before anyone budgets work for it.
#   - ArrowAdapter — poor choice on TERMS, not capability: explicitly forbids
#     caching, revokes credentials for it, and publishes no rate limit at all.
#   - AvnetAdapter — most complex auth (subscription key AND OAuth2) for no
#     data the others lack.
#   - MouserAdapter — plausible, but every figure about it is unverified;
#     Mouser blocks automated fetching of its own terms and docs.
