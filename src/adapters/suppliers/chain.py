"""
OSKAR SupplierChain — serial lookup with split-TTL PostgreSQL cache (S3-3,
revised Iteration 3)

Lookup order for ECN module part description population:
  1. Local PostgreSQL supplier_part_cache — zero API calls on a full hit
  2. DigiKeyAdapter                 — primary, authoritative, 1,000 req/day free
  3. NexarAdapter                   — secondary breadth; free tier is 100 parts
                                      LIFETIME (see nexar.py — not per month)
  4. Remaining stubs (Iteration 3)  — not called in ECN module; reserved for
                                       Supplier Intelligence fan-out

The chain stops at the first non-empty result and writes it to the cache.
If all suppliers return empty the caller receives {} and prompts the engineer
to enter the description manually.

── Why the cache is split by field class ───────────────────────────────────

Two independent reasons, either sufficient on its own:

1. LICENSING. DigiKey's user agreement §5.1(e) prohibits using the API "to
   update or create your own database of information" (verified verbatim
   2026-08-27, https://developer.digikey.com/api-user-agreement).
   Octopart/Nexar cap caching at 24h; Element14 and Arrow carry near-identical
   clauses. A 30-day persistent store of price and stock is the worst-exposed
   shape of that. Descriptive data (what a part IS) is a materially weaker
   claim than commercial data (what it COSTS today).

   Splitting does not by itself make this compliant — see
   docs/supplier-api-landscape.md §3. It removes the indefensible part while
   a written variance is sought. Mitigation, not resolution.

2. CORRECTNESS, independent of the above. 30-day-old pricing is simply wrong
   and stock is wrong within hours, while descriptions are stable for years.
   One TTL cannot be right for both.

So descriptive fields keep the long TTL and commercial fields get a short one
with their own independent clock. A row whose descriptive half is fresh but
whose commercial half has expired is a PARTIAL hit: the description is served
without a round trip, and the stale price is simply not returned.

Config:
  SUPPLIER_CACHE_TTL_DAYS             — descriptive TTL (default 30 days)
  SUPPLIER_COMMERCIAL_CACHE_TTL_HOURS — commercial TTL (default 24h, hard
                                        ceiling 24h, 0 disables entirely)
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from src.adapters.suppliers.base import SupplierAdapter

# Fields whose caching the distributor terms actually object to, and which go
# stale fastest. Source of truth for the classification — migration 0033's
# scrub list is kept in sync with this.
COMMERCIAL_FIELDS: frozenset[str] = frozenset({
    "unit_price",
    "quantity_available",
    "price_breaks",
    "moq",
    "currency",
})

# Descriptive fields — what a part IS. Stable for years.
#
# lifecycle is deliberately here rather than in COMMERCIAL_FIELDS: it moves on
# the order of months, and it is the field EOL alerting depends on. Giving it
# a 24h TTL would make that feature hammer the API for data that barely
# changes.
#
# lead_time_weeks is a genuine judgment call and sits here on purpose. It is
# supplier-quoted like a price, but it moves on the order of weeks, and the
# feature that consumes it (lead-time-spike alerting) needs a baseline to
# compare against — a 24h TTL would leave nothing to detect a spike FROM.
# It is also not commercially sensitive in the way price and stock are.
DESCRIPTIVE_FIELDS: frozenset[str] = frozenset({
    "description",
    "manufacturer",
    "category",
    "lifecycle",
    "mounting_type",
    "digikey_part_number",
    "nexar_mpn",
    "element14_sku",
    "country_of_origin",
    "rohs_compliant",
    "lead_time_weeks",
})

# Octopart's documented 24h ceiling is the tightest limit found across the
# APIs in use, so it is the safe default and the hard cap for all of them.
_COMMERCIAL_TTL_CEILING_HOURS = 24


def _descriptive_ttl_days() -> int:
    return int(os.getenv("SUPPLIER_CACHE_TTL_DAYS", "30"))


def _commercial_ttl_hours() -> int:
    """Commercial TTL in hours, clamped to the 24h ceiling.

    Clamped rather than trusted: a misconfiguration here is a terms
    violation, not a performance tweak. 0 disables commercial caching.
    """
    raw = int(os.getenv("SUPPLIER_COMMERCIAL_CACHE_TTL_HOURS", "24"))
    return max(0, min(raw, _COMMERCIAL_TTL_CEILING_HOURS))


def split_cache_payload(
    data: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Split an adapter result into (descriptive, commercial) for storage.

    Unclassified keys default to DESCRIPTIVE: an unknown field is far more
    likely to be an attribute than a price, and defaulting the other way
    would silently expire real data after 24h.
    """
    descriptive: dict[str, Any] = {}
    commercial: dict[str, Any] = {}
    for key, value in data.items():
        if key in COMMERCIAL_FIELDS:
            commercial[key] = value
        else:
            descriptive[key] = value
    return descriptive, commercial


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
        """Return the cached entry if its DESCRIPTIVE half is within TTL.

        Commercial fields are attached only if their own independent clock is
        also fresh. A fresh-descriptive/stale-commercial row is a partial hit:
        the caller gets the description without a round trip and does not get
        a month-old price.
        """
        cutoff = datetime.now(tz=timezone.utc) - timedelta(days=_descriptive_ttl_days())
        row = await self._session.execute(
            sa.text(
                "SELECT description, manufacturer, category, lifecycle, "
                "supplier_id, raw_json, commercial_json, commercial_cached_at "
                "FROM supplier_part_cache "
                "WHERE mpn = :mpn AND cached_at >= :cutoff"
            ),
            {"mpn": mpn.strip(), "cutoff": cutoff},
        )
        r = row.first()
        if not r:
            return None
        # raw_json / commercial_json are jsonb columns — asyncpg/SQLAlchemy
        # already deserialize them to dicts, unlike a plain text column.
        # json.loads() here would only be correct for a string, and raises
        # TypeError on the dict we actually get back.
        result: dict[str, Any] = {
            "description": r[0],
            "manufacturer": r[1],
            "category": r[2],
            "lifecycle": r[3],
            "supplier_id": r[4],
            **(r[5] or {}),
        }

        commercial, commercial_at = r[6], r[7]
        if commercial and commercial_at and self._commercial_is_fresh(commercial_at):
            result.update(commercial)

        return result

    @staticmethod
    def _commercial_is_fresh(commercial_cached_at: datetime) -> bool:
        ttl_hours = _commercial_ttl_hours()
        if ttl_hours == 0:
            return False
        # Rows written before migration 0033 (or by a driver returning naive
        # datetimes) must not blow up the comparison.
        if commercial_cached_at.tzinfo is None:
            commercial_cached_at = commercial_cached_at.replace(tzinfo=timezone.utc)
        cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=ttl_hours)
        return commercial_cached_at >= cutoff

    async def _cache_set(
        self, mpn: str, supplier_id: str, data: dict[str, Any]
    ) -> None:
        """Upsert a cache entry, storing the two field classes separately.

        raw_json holds DESCRIPTIVE data only — it previously held the whole
        adapter payload, price included, which is precisely the persistent
        commercial store the distributor terms object to.
        """
        descriptive, commercial = split_cache_payload(data)
        await self._session.execute(
            sa.text(
                "INSERT INTO supplier_part_cache "
                "(mpn, supplier_id, description, manufacturer, category, lifecycle, "
                " raw_json, commercial_json, cached_at, commercial_cached_at) "
                "VALUES (:mpn, :supplier_id, :description, :manufacturer, :category, "
                " :lifecycle, :raw_json, :commercial_json, NOW(), "
                " CASE WHEN :has_commercial THEN NOW() ELSE NULL END) "
                "ON CONFLICT (mpn) DO UPDATE SET "
                "supplier_id = EXCLUDED.supplier_id, "
                "description = EXCLUDED.description, "
                "manufacturer = EXCLUDED.manufacturer, "
                "category = EXCLUDED.category, "
                "lifecycle = EXCLUDED.lifecycle, "
                "raw_json = EXCLUDED.raw_json, "
                # Only advance the commercial half when this write actually
                # carried commercial data — otherwise a description-only
                # refresh would reset the price clock without new prices.
                "commercial_json = COALESCE(EXCLUDED.commercial_json, supplier_part_cache.commercial_json), "
                "commercial_cached_at = COALESCE(EXCLUDED.commercial_cached_at, supplier_part_cache.commercial_cached_at), "
                "cached_at = EXCLUDED.cached_at"
            ),
            {
                "mpn": mpn.strip(),
                "supplier_id": supplier_id,
                "description": data.get("description", ""),
                "manufacturer": data.get("manufacturer", ""),
                "category": data.get("category", ""),
                "lifecycle": data.get("lifecycle", ""),
                "raw_json": json.dumps(descriptive),
                "commercial_json": json.dumps(commercial) if commercial else None,
                "has_commercial": bool(commercial),
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
