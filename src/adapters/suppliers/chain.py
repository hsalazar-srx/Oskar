"""
OSKAR SupplierChain — serial lookup with PostgreSQL cache (S3-3)

Lookup order for ECN module part description population:
  1. Local PostgreSQL supplier_part_cache (30-day TTL) — zero API calls on hit
  2. DigiKeyAdapter                 — primary, authoritative, 1,000 req/day free
  3. NexarAdapter                   — secondary breadth, 100 parts/month free
  4. Remaining stubs (Iteration 3)  — not called in ECN module; reserved for
                                       Supplier Intelligence fan-out

The chain stops at the first non-empty result and writes it to the cache.
If all suppliers return empty the caller receives {} and prompts the engineer
to enter the description manually.

Cache TTL is controlled by SUPPLIER_CACHE_TTL_DAYS (default: 30).
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from src.adapters.suppliers.base import SupplierAdapter


def _ttl_days() -> int:
    return int(os.getenv("SUPPLIER_CACHE_TTL_DAYS", "30"))


class SupplierChain:
    """Serial supplier lookup with PostgreSQL cache.

    Usage:
        chain = SupplierChain(session, [digikey_adapter, nexar_adapter])
        result = await chain.get_part("LM741CN")
    """

    def __init__(
        self,
        session: AsyncSession,
        adapters: list[SupplierAdapter],
    ) -> None:
        self._session = session
        self._adapters = adapters

    # ------------------------------------------------------------------
    # Cache helpers
    # ------------------------------------------------------------------

    async def _cache_get(self, mpn: str) -> dict[str, Any] | None:
        """Return cached entry if present and within TTL, else None."""
        cutoff = datetime.now(tz=timezone.utc) - timedelta(days=_ttl_days())
        row = await self._session.execute(
            sa.text(
                "SELECT description, manufacturer, category, lifecycle, "
                "supplier_id, raw_json "
                "FROM supplier_part_cache "
                "WHERE mpn = :mpn AND cached_at >= :cutoff"
            ),
            {"mpn": mpn.strip(), "cutoff": cutoff},
        )
        r = row.first()
        if not r:
            return None
        return {
            "description": r[0],
            "manufacturer": r[1],
            "category": r[2],
            "lifecycle": r[3],
            "supplier_id": r[4],
            **(json.loads(r[5]) if r[5] else {}),
        }

    async def _cache_set(
        self, mpn: str, supplier_id: str, data: dict[str, Any]
    ) -> None:
        """Upsert a cache entry."""
        await self._session.execute(
            sa.text(
                "INSERT INTO supplier_part_cache "
                "(mpn, supplier_id, description, manufacturer, category, lifecycle, raw_json, cached_at) "
                "VALUES (:mpn, :supplier_id, :description, :manufacturer, :category, :lifecycle, :raw_json, NOW()) "
                "ON CONFLICT (mpn) DO UPDATE SET "
                "supplier_id = EXCLUDED.supplier_id, "
                "description = EXCLUDED.description, "
                "manufacturer = EXCLUDED.manufacturer, "
                "category = EXCLUDED.category, "
                "lifecycle = EXCLUDED.lifecycle, "
                "raw_json = EXCLUDED.raw_json, "
                "cached_at = EXCLUDED.cached_at"
            ),
            {
                "mpn": mpn.strip(),
                "supplier_id": supplier_id,
                "description": data.get("description", ""),
                "manufacturer": data.get("manufacturer", ""),
                "category": data.get("category", ""),
                "lifecycle": data.get("lifecycle", ""),
                "raw_json": json.dumps(data),
            },
        )

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def get_part(self, mpn: str) -> dict[str, Any]:
        """Return part data for mpn, using cache then supplier chain.

        Returns {} if no supplier has a record for this MPN.
        The caller is responsible for truncating description to 30 chars
        before writing to ecn_items.item_name.
        """
        cached = await self._cache_get(mpn)
        if cached is not None:
            return cached

        for adapter in self._adapters:
            try:
                result = await adapter.get_part(mpn)
            except Exception:
                # One supplier failing does not stop the chain
                continue
            if result:
                await self._cache_set(mpn, adapter.supplier_id, result)
                return result

        return {}
