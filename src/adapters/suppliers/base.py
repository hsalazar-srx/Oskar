"""
OSKAR SupplierAdapter ABC (PRE-5)

Abstract base class for all supplier API integrations.
One concrete implementation per supplier. Adding a 7th supplier = one new class file.
Per-adapter circuit breaker pattern — one supplier outage does not affect others.

Implementations (3 real + 4 stubs):
- DigiKeyAdapter    ← primary; OAuth2, live quota headers
- NexarAdapter      ← secondary breadth; free tier is 100 parts LIFETIME
- Element14Adapter  ← price breaks + lead time + compliance, my./au. stores
- MouserAdapter     ← Stub
- RSComponentsAdapter ← Stub (RS publishes no public API — likely
                        unimplementable; see stubs.py)
- ArrowAdapter      ← Stub (poor on terms — forbids caching, revokes creds)
- AvnetAdapter      ← Stub

Selection rationale for all of the above: docs/supplier-api-landscape.md.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class SupplierAdapter(ABC):
    """Abstract base for all supplier API adapters."""

    @property
    @abstractmethod
    def supplier_id(self) -> str:
        """Unique identifier for this supplier (e.g. 'digikey', 'mouser')."""
        ...

    @abstractmethod
    async def search(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        """Search supplier catalogue by part number or description."""
        ...

    @abstractmethod
    async def get_part(self, part_number: str) -> dict[str, Any]:
        """Fetch full part detail by supplier part number."""
        ...

    @abstractmethod
    async def get_pricing(self, part_number: str, quantity: int = 1) -> dict[str, Any]:
        """Fetch pricing and availability for a part at a given quantity."""
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """Return True if the supplier API is reachable."""
        ...
