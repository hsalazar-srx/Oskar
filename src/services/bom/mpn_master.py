"""
OSKAR — MPN master service (Slice C, ADR-012 D3).

item_mpns (migration 0025) is Oskar's MPN master, replacing Stargile ZECNMPMS.
Keyed like ZECNMPMS: (item_number, supplier_number, mpn). This module owns:

  normalize_manufacturer() / is_current_default()
    Pure logic (no DB, no I/O) — TDD mechanics classifies manufacturer
    normalisation as pure unit logic alongside the compare engine and explode
    math (ai/tasks/oskar-iteration-2.md "TDD mechanics (cross-slice)").

  load_synonyms() / get_item_mpn() / upsert_item_mpn()
    DB-touching helpers shared by scripts/migrate_zecnmpms.py (batch load),
    the movex_write_complete workflow hook (src/services/ecn/workflow.py,
    ecn_mpns -> item_mpns), and scripts/add_manufacturer_synonym.py.

What "current default" means, and who checks which half of it:
  The business rule is: is_default=True AND (there's no end date, OR the end
  date hasn't passed yet). That's two conditions joined by "AND (this OR that)".

  The database can only cheaply/statically enforce the first condition — "no
  end date" — via the partial unique index uq_item_mpns_current_default
  (migration 0025), which only indexes rows where end_effective_date IS NULL.
  It can't enforce "hasn't passed yet" because that depends on *today's*
  date, which isn't a fixed value an index can check.

  So the "hasn't passed yet" half is checked in Python instead, by
  is_current_default() below — e.g. a browse/search screen calls it when
  deciding which MPN to show as "the" default for an item.

  Example: item LF200010/SUP001 has MPN "A" as the current default
  (is_default=True, end_effective_date=NULL). An engineer now sets MPN "B" as
  the new default. upsert_item_mpn(..., mpn="B", is_default=True) does two
  things in one call: it first UPDATEs row "A" to set its end_effective_date
  to yesterday (closing it out), then INSERTs/UPDATEs row "B" as the new
  NULL-end-dated default. Without that first step, inserting "B" would
  violate uq_item_mpns_current_default (two NULL-end-dated defaults for the
  same item+supplier at once). Callers never have to do this two-step
  sequence by hand.
"""
from __future__ import annotations

import datetime
import json
import uuid
from dataclasses import dataclass
from typing import Any, Mapping

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class NormalizeResult:
    canonical: str
    matched: bool  # False = miss; canonical is the trimmed raw value, passed through


@dataclass
class ItemMPN:
    """One row from item_mpns."""
    id: str
    item_number: str
    supplier_number: str
    mpn: str
    manufacturer_name: str | None
    manufacturer_canonical: str | None
    is_default: bool
    end_effective_date: datetime.date | None
    from_date: datetime.date | None
    to_date: datetime.date | None
    source_ecn: str | None
    price: float | None
    currency: str | None
    moq: int | None
    spq: int | None
    distributor_number: str | None
    distributor_name: str | None
    legacy_extra: dict | None
    source_system: str
    migrated_at: datetime.datetime | None
    created_at: datetime.datetime
    updated_at: datetime.datetime


# ── Pure logic ────────────────────────────────────────────────────────────────

def normalize_manufacturer(raw: str | None, synonyms: Mapping[str, str]) -> NormalizeResult:
    """Raw manufacturer string -> canonical name via `synonyms`.

    `synonyms` keys must already be upper-cased (as manufacturer_synonyms.raw_string
    is stored, and as load_synonyms() returns them) — this function upper-cases
    and trims `raw` the same way before lookup, so the two line up.

    Miss = pass through the trimmed raw value unchanged (never raises, never
    blocks) — the caller is responsible for logging misses to the migration's
    review file (ADR-012 Decision 8, R5 fix-forward via
    scripts/add_manufacturer_synonym.py).
    """
    if not raw or not raw.strip():
        return NormalizeResult(canonical="", matched=False)
    trimmed = raw.strip()
    canonical = synonyms.get(trimmed.upper())
    if canonical is not None:
        return NormalizeResult(canonical=canonical, matched=True)
    return NormalizeResult(canonical=trimmed, matched=False)


def is_current_default(
    is_default: bool,
    end_effective_date: datetime.date | None,
    *,
    today: datetime.date | None = None,
) -> bool:
    """Default rule: is_default AND (end_effective_date IS NULL OR >= today)."""
    if not is_default:
        return False
    if end_effective_date is None:
        return True
    return end_effective_date >= (today or datetime.date.today())


# ── DB-touching helpers ──────────────────────────────────────────────────────

async def load_synonyms(session: AsyncSession) -> dict[str, str]:
    """Load the full manufacturer_synonyms table as {raw_string: canonical_name}.

    Loaded once per caller (migration batch, workflow hook) rather than
    queried per-row — manufacturer_synonyms is small (~1000s of rows) and this
    avoids an N+1 query pattern.
    """
    result = await session.execute(
        sa.text("SELECT raw_string, canonical_name FROM manufacturer_synonyms")
    )
    return {row.raw_string: row.canonical_name for row in result}


_SELECT_COLUMNS = (
    "id, item_number, supplier_number, mpn, manufacturer_name, manufacturer_canonical, "
    "is_default, end_effective_date, from_date, to_date, source_ecn, price, currency, "
    "moq, spq, distributor_number, distributor_name, legacy_extra, source_system, "
    "migrated_at, created_at, updated_at"
)


def _row_to_item_mpn(row: Mapping[str, Any]) -> ItemMPN:
    return ItemMPN(
        id=str(row["id"]),
        item_number=row["item_number"],
        supplier_number=row["supplier_number"],
        mpn=row["mpn"],
        manufacturer_name=row["manufacturer_name"],
        manufacturer_canonical=row["manufacturer_canonical"],
        is_default=row["is_default"],
        end_effective_date=row["end_effective_date"],
        from_date=row["from_date"],
        to_date=row["to_date"],
        source_ecn=str(row["source_ecn"]) if row["source_ecn"] else None,
        price=float(row["price"]) if row["price"] is not None else None,
        currency=row["currency"],
        moq=row["moq"],
        spq=row["spq"],
        distributor_number=row["distributor_number"],
        distributor_name=row["distributor_name"],
        legacy_extra=row["legacy_extra"],
        source_system=row["source_system"],
        migrated_at=row["migrated_at"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


async def get_item_mpn(
    session: AsyncSession, item_number: str, supplier_number: str, mpn: str
) -> ItemMPN | None:
    result = await session.execute(
        sa.text(
            f"SELECT {_SELECT_COLUMNS} FROM item_mpns "
            "WHERE item_number = :item_number AND supplier_number = :supplier_number "
            "AND mpn = :mpn"
        ),
        {"item_number": item_number, "supplier_number": supplier_number, "mpn": mpn},
    )
    row = result.mappings().first()
    return _row_to_item_mpn(row) if row else None


async def upsert_item_mpn(
    session: AsyncSession,
    *,
    item_number: str,
    mpn: str,
    supplier_number: str = "",
    manufacturer_name: str | None = None,
    manufacturer_canonical: str | None = None,
    is_default: bool = False,
    end_effective_date: datetime.date | None = None,
    from_date: datetime.date | None = None,
    to_date: datetime.date | None = None,
    source_ecn: str | None = None,
    price: float | None = None,
    currency: str | None = None,
    moq: int | None = None,
    spq: int | None = None,
    distributor_number: str | None = None,
    distributor_name: str | None = None,
    legacy_extra: dict | None = None,
    source_system: str = "oskar",
    migrated_at: datetime.datetime | None = None,
) -> ItemMPN:
    """Idempotent upsert on the natural key (item_number, supplier_number, mpn).

    Used by scripts/migrate_zecnmpms.py (batch load, safe to re-run — ADR-012's
    ZECNMPMS migration plan step 3) and the movex_write_complete workflow hook.

    See the module docstring for why, when is_default=True and
    end_effective_date=None, this first end-dates whatever other row
    currently holds that "current default" slot for the same
    (item_number, supplier_number) before writing the new one.
    """
    if is_default and end_effective_date is None:
        await session.execute(
            sa.text(
                "UPDATE item_mpns SET end_effective_date = CURRENT_DATE - INTERVAL '1 day', "
                "updated_at = now() "
                "WHERE item_number = :item_number AND supplier_number = :supplier_number "
                "AND mpn != :mpn AND is_default AND end_effective_date IS NULL"
            ),
            {"item_number": item_number, "supplier_number": supplier_number, "mpn": mpn},
        )

    row_id = str(uuid.uuid4())
    params = {
        "id": row_id,
        "item_number": item_number,
        "supplier_number": supplier_number,
        "mpn": mpn,
        "manufacturer_name": manufacturer_name,
        "manufacturer_canonical": manufacturer_canonical,
        "is_default": is_default,
        "end_effective_date": end_effective_date,
        "from_date": from_date,
        "to_date": to_date,
        "source_ecn": source_ecn,
        "price": price,
        "currency": currency,
        "moq": moq,
        "spq": spq,
        "distributor_number": distributor_number,
        "distributor_name": distributor_name,
        "legacy_extra": json.dumps(legacy_extra) if legacy_extra is not None else None,
        "source_system": source_system,
        "migrated_at": migrated_at,
    }
    result = await session.execute(
        sa.text(
            "INSERT INTO item_mpns "
            "(id, item_number, supplier_number, mpn, manufacturer_name, manufacturer_canonical, "
            "is_default, end_effective_date, from_date, to_date, source_ecn, price, currency, "
            "moq, spq, distributor_number, distributor_name, legacy_extra, source_system, "
            "migrated_at) "
            "VALUES (:id, :item_number, :supplier_number, :mpn, :manufacturer_name, "
            ":manufacturer_canonical, :is_default, :end_effective_date, :from_date, :to_date, "
            ":source_ecn, :price, :currency, :moq, :spq, :distributor_number, :distributor_name, "
            "CAST(:legacy_extra AS JSONB), :source_system, :migrated_at) "
            "ON CONFLICT (item_number, supplier_number, mpn) DO UPDATE SET "
            "manufacturer_name = EXCLUDED.manufacturer_name, "
            "manufacturer_canonical = EXCLUDED.manufacturer_canonical, "
            "is_default = EXCLUDED.is_default, "
            "end_effective_date = EXCLUDED.end_effective_date, "
            "from_date = EXCLUDED.from_date, "
            "to_date = EXCLUDED.to_date, "
            "source_ecn = COALESCE(EXCLUDED.source_ecn, item_mpns.source_ecn), "
            "price = EXCLUDED.price, "
            "currency = EXCLUDED.currency, "
            "moq = EXCLUDED.moq, "
            "spq = EXCLUDED.spq, "
            "distributor_number = EXCLUDED.distributor_number, "
            "distributor_name = EXCLUDED.distributor_name, "
            "legacy_extra = EXCLUDED.legacy_extra, "
            "source_system = EXCLUDED.source_system, "
            "migrated_at = COALESCE(EXCLUDED.migrated_at, item_mpns.migrated_at), "
            "updated_at = now() "
            f"RETURNING {_SELECT_COLUMNS}"
        ),
        params,
    )
    row = result.mappings().first()
    return _row_to_item_mpn(row)
