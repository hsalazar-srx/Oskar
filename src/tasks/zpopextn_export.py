"""
OSKAR — ZPOPEXTN replacement export (Slice C, ADR-012 Decision 5 / R7).

Stargile's PurchaseExtensionNightJob wrote the current default MPN per item to
a physical DB2/M3 table, ZPOPEXTN, which Purchasing's PO-print process read
directly. That table dies when Stargile is decommissioned — R7 (ADR-012
Decision 5) makes providing a working successor Oskar's own responsibility,
not something to leave for Purchasing to chase, and requires it to ship
*before* the ZECNMPMS migration plan's cutover step freezes Stargile's MPN
screens (see ai/tasks/oskar-iteration-2.md "ZECNMPMS migration plan" step 5).

JUDGMENT CALL (the plan only says "minimal replacement job" — flagged in the
final Slice C report, needs real Purchasing sign-off before go-live, not
settled by this implementation alone):

  Format: a CSV file, not a new database table — even though ZPOPEXTN itself
  was a table, which would arguably be the more faithful successor (readable
  directly by whatever downstream tooling Purchasing builds, no separate
  delivery mechanism to sort out). A new *Postgres* table was ruled out for a
  concrete, hard reason, not just a preference: this Slice C task's own file
  boundaries explicitly list `alembic/versions/0025_item_mpns.py` as the only
  migration file in scope — adding an 0026+ migration for a ZPOPEXTN table
  would violate that boundary outright (separately, 0026-0029 are also
  pre-assigned to Slice D/E/E0 in the plan, which would collide at merge
  time even if the boundary allowed it). A CSV avoids needing any new
  migration at all, at the cost of being a weaker successor than a table
  would have been — that tradeoff is the judgment call, and it's worth
  revisiting in Slice D/E once migration ownership isn't split across
  parallel worktrees.

  Delivery mechanism: NOT decided here. ZPOPEXTN_EXPORT_PATH (env var,
  default exports/zpopextn_default_mpns.csv) controls where the file lands;
  whether Purchasing's real successor process reads this path directly, or
  the file needs to move over SFTP/shared-drive/etc., is exactly the kind of
  detail that needs a real conversation with Purchasing before the Stargile
  MPN-screens-read-only cutover step — this implementation intentionally
  keeps that surface small (one env var) so wiring it to the real mechanism
  later is a config change, not a code change.

  "Current default" rule matches src.services.bom.mpn_master.is_current_default:
  is_default AND (end_effective_date IS NULL OR end_effective_date >= today) —
  expressed here as one SQL WHERE clause (bulk export) rather than a Python
  predicate per row.

Follows the Celery-asyncio-boundary pattern used elsewhere in Slice C
(scripts/migrate_zecnmpms.py, scripts/add_manufacturer_synonym.py): async
business logic in export_default_mpns_async(), asyncio.run() wrapper for the
Celery task. This uses async SQLAlchemy (asyncpg) rather than the sync
psycopg2-in-executor pattern seen in src/tasks/ecn_notifications.py /
audit_checkpoint.py — a deliberate choice to stay consistent with the rest of
Slice C's DB access (mpn_master.py etc.), which is all asyncpg-based, rather
than introducing a third DB-access flavour for one task.
"""
from __future__ import annotations

import asyncio
import csv
import os
from pathlib import Path

import sqlalchemy as sa
import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.tasks.celery_app import celery_app

log = structlog.get_logger(__name__)

_DEFAULT_EXPORT_PATH = os.environ.get("ZPOPEXTN_EXPORT_PATH", "exports/zpopextn_default_mpns.csv")

_COLUMNS = [
    "item_number", "supplier_number", "mpn", "manufacturer_canonical",
    "price", "currency", "moq", "spq", "distributor_number", "distributor_name",
]


async def export_default_mpns_async(
    session: AsyncSession, output_path: str | Path | None = None
) -> int:
    """Write the current default-MPN extract Purchasing's PO print needs.

    Returns the row count written. Creates the output path's parent
    directory if it doesn't exist yet.
    """
    path = Path(output_path or _DEFAULT_EXPORT_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)

    result = await session.execute(
        sa.text(
            f"SELECT {', '.join(_COLUMNS)} FROM item_mpns "
            "WHERE is_default AND (end_effective_date IS NULL OR end_effective_date >= CURRENT_DATE) "
            "ORDER BY item_number, supplier_number"
        )
    )
    rows = result.mappings().all()

    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({col: row[col] for col in _COLUMNS})

    log.info("zpopextn_export.written", path=str(path), row_count=len(rows))
    return len(rows)


async def _run_export() -> int:
    db_url = os.environ.get(
        "DATABASE_URL", "postgresql+asyncpg://oskar:oskar_dev@localhost:5432/oskar"
    ).replace("?ssl=disable", "")
    if "ssl=" not in db_url:
        db_url += "?ssl=disable"

    engine = create_async_engine(db_url, echo=False, pool_size=2)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False, autocommit=False)
    try:
        async with factory() as session:
            return await export_default_mpns_async(session)
    finally:
        await engine.dispose()


@celery_app.task(name="src.tasks.zpopextn_export.export_default_mpns")
def export_default_mpns() -> int:
    """Celery beat task — nightly ZPOPEXTN-equivalent default-MPN export.

    Successor to Stargile's PurchaseExtensionNightJob. Tests always call
    export_default_mpns_async() directly, never this wrapper.
    """
    return asyncio.run(_run_export())
