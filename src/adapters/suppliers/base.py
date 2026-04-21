"""
OSKAR SupplierAdapter ABC (PRE-5)

Abstract base class for all supplier API integrations.
One concrete implementation per supplier. Adding a 7th supplier = one new class file.
Per-adapter circuit breaker pattern — one supplier outage does not affect others.

Implementations (Phase 1: 1 real + 5 stubs):
- DigiKeyAdapter    ← Wire first (DigiKey OAuth confirmed in Branko session)
- MouserAdapter     ← Stub
- RS ComponentsAdapter  ← Stub
- Arrow Adapter     ← Stub
- AvnetAdapter      ← Stub
- Future6Adapter    ← Stub placeholder
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
