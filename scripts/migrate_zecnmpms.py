"""
OSKAR — ZECNMPMS -> item_mpns migration CLI (Slice C, ADR-012 D3).

Usage:
    python scripts/migrate_zecnmpms.py --input path/to/zecnmpms.csv --dry-run
    python scripts/migrate_zecnmpms.py --input path/to/zecnmpms.csv --report out.txt
    python scripts/migrate_zecnmpms.py --from-api http://localhost:8100 --cono 300

--from-api points at movex-rest-api's M-1 endpoint (GET /api/mpm/export) — or,
until that lands on the real service, scripts/movex_stub.py serving the same
contract from tests/fixtures/bom/zecnmpms_sample.csv:

    uvicorn scripts.movex_stub:app --port 8100
    python scripts/migrate_zecnmpms.py --from-api http://localhost:8100

Loads via src.services.bom.zecnmpms_transform (pure transform) and
src.services.bom.mpn_master.upsert_item_mpn (idempotent natural-key upsert —
safe to re-run, per the ZECNMPMS migration plan step 3). Business/DB logic
lives in migrate_zecnmpms_async(); main() is the sync asyncio.run() wrapper
(Celery-asyncio-boundary pattern, developer-python.yaml) even though this is
a standalone script rather than a Celery task — tests call
migrate_zecnmpms_async() directly, never main().
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import datetime
import os
from dataclasses import dataclass
from pathlib import Path

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.services.bom.mpn_master import load_synonyms, upsert_item_mpn
from src.services.bom.zecnmpms_transform import (
    DefaultFlagViolation,
    DuplicateCollapse,
    transform_batch,
)


@dataclass
class MigrationReport:
    total_input_rows: int
    loaded_rows: int
    dry_run: bool
    duplicate_collapses: list[DuplicateCollapse]
    manufacturer_misses: list[str]
    default_flag_violations: list[DefaultFlagViolation]

    def to_text(self) -> str:
        lines = [
            f"ZECNMPMS migration report ({'DRY RUN — nothing written' if self.dry_run else 'LOADED'})",
            f"  input rows:              {self.total_input_rows}",
            f"  rows after dedup:        {self.loaded_rows}",
            f"  duplicate natural keys:  {len(self.duplicate_collapses)}",
            f"  manufacturer misses:     {len(self.manufacturer_misses)}",
            f"  default-flag violations: {len(self.default_flag_violations)}",
        ]
        if self.duplicate_collapses:
            lines.append("")
            lines.append("  -- duplicate natural keys (last occurrence wins) --")
            for d in self.duplicate_collapses:
                lines.append(f"    {d.natural_key} — {d.occurrences} occurrences")
        if self.manufacturer_misses:
            lines.append("")
            lines.append("  -- manufacturer synonym misses (review; fix via scripts/add_manufacturer_synonym.py) --")
            for m in self.manufacturer_misses:
                lines.append(f"    {m!r}")
        if self.default_flag_violations:
            lines.append("")
            lines.append("  -- default-flag violations (resolve manually — Stargile data quality) --")
            for v in self.default_flag_violations:
                lines.append(
                    f"    {v.item_number}/{v.supplier_number}: "
                    f"{v.mpn_count} MPNs marked default (last-processed wins)"
                )
        return "\n".join(lines)


# ── Row sources ──────────────────────────────────────────────────────────────

def load_rows_from_csv(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


async def _fetch_all_pages(
    client: httpx.AsyncClient, *, cono: str, limit: int = 1000
) -> list[dict]:
    """Page through M-1 (GET /api/mpm/export) until exhausted.

    Split out from load_rows_from_api() so tests can inject an httpx.AsyncClient
    backed by httpx.ASGITransport(app=scripts.movex_stub.create_app()) — a
    genuine in-process exercise of the real stub's contract, not a mock of
    this function's own behaviour.
    """
    rows: list[dict] = []
    offset = 0
    while True:
        resp = await client.get(
            "/api/mpm/export", params={"cono": cono, "offset": offset, "limit": limit}
        )
        resp.raise_for_status()
        body = resp.json()["data"]
        records = body["records"]
        rows.extend(records)
        offset += limit
        if not records or offset >= body["total"]:
            break
    return rows


def _build_headers() -> dict[str, str]:
    """X-API-Key from MOVEX_API_KEY, same convention as MovexRestAdapter.

    scripts/movex_stub.py requires no auth (harmless to send the header
    anyway), but the real movex-rest-api does — --from-api 401s against it
    without this, discovered live 2026-08-03.
    """
    api_key = os.environ.get("MOVEX_API_KEY")
    return {"X-API-Key": api_key} if api_key else {}


async def load_rows_from_api(base_url: str, cono: str) -> list[dict]:
    async with httpx.AsyncClient(
        base_url=base_url, timeout=30.0, headers=_build_headers()
    ) as client:
        return await _fetch_all_pages(client, cono=cono)


# ── Core migration ───────────────────────────────────────────────────────────

async def migrate_zecnmpms_async(
    session: AsyncSession,
    raw_rows: list[dict],
    *,
    dry_run: bool = False,
    batch_size: int = 1000,
) -> MigrationReport:
    """Transform + (optionally) load raw ZECNMPMS rows into item_mpns.

    Idempotent: re-running with the same input upserts on the natural key
    (item_number, supplier_number, mpn) rather than inserting duplicates.
    Does not commit — the caller owns the transaction (matches OSKAR's
    "get_session() owns the transaction" convention; the real CLI entrypoint
    below wraps this in session.begin(), tests reuse the db_session fixture's
    own transaction).
    """
    synonyms = await load_synonyms(session)
    result = transform_batch(raw_rows, synonyms)

    if not dry_run:
        migrated_at = datetime.datetime.now(datetime.timezone.utc)
        for start in range(0, len(result.rows), batch_size):
            for row in result.rows[start : start + batch_size]:
                await upsert_item_mpn(
                    session,
                    item_number=row.item_number,
                    mpn=row.mpn,
                    supplier_number=row.supplier_number,
                    manufacturer_name=row.manufacturer_name,
                    manufacturer_canonical=row.manufacturer_canonical,
                    is_default=row.is_default,
                    from_date=row.from_date,
                    to_date=row.to_date,
                    price=row.price,
                    currency=row.currency,
                    moq=row.moq,
                    spq=row.spq,
                    distributor_number=row.distributor_number,
                    distributor_name=row.distributor_name,
                    legacy_extra=row.legacy_extra or None,
                    source_system=row.source_system,
                    migrated_at=migrated_at,
                )

    return MigrationReport(
        total_input_rows=len(raw_rows),
        loaded_rows=len(result.rows),
        dry_run=dry_run,
        duplicate_collapses=result.duplicate_collapses,
        manufacturer_misses=result.manufacturer_misses,
        default_flag_violations=result.default_flag_violations,
    )


# ── CLI entrypoint ───────────────────────────────────────────────────────────

def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Migrate Stargile ZECNMPMS into Oskar item_mpns")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--input", type=Path, help="Path to a ZECNMPMS CSV export")
    source.add_argument(
        "--from-api", metavar="BASE_URL",
        help="movex-rest-api (or scripts/movex_stub.py) base URL, e.g. http://localhost:8100",
    )
    parser.add_argument(
        "--cono", default=os.environ.get("MOVEX_CONO", "300"),
        help="Movex company number (--from-api only; default from MOVEX_CONO env var)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Transform + report only, write nothing")
    parser.add_argument("--report", type=Path, help="Write the report to this path (default: stdout only)")
    parser.add_argument("--batch-size", type=int, default=1000)
    return parser


async def _run_cli(args: argparse.Namespace) -> MigrationReport:
    if args.input:
        raw_rows = load_rows_from_csv(args.input)
    else:
        raw_rows = await load_rows_from_api(args.from_api, args.cono)

    db_url = os.environ.get(
        "DATABASE_URL", "postgresql+asyncpg://oskar:oskar_dev@localhost:5432/oskar"
    ).replace("?ssl=disable", "")
    if "ssl=" not in db_url:
        db_url += "?ssl=disable"

    engine = create_async_engine(db_url, echo=False, pool_size=2)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False, autocommit=False)
    try:
        async with factory() as session:
            async with session.begin():
                report = await migrate_zecnmpms_async(
                    session, raw_rows, dry_run=args.dry_run, batch_size=args.batch_size
                )
    finally:
        await engine.dispose()
    return report


def main() -> None:
    args = _build_arg_parser().parse_args()
    report = asyncio.run(_run_cli(args))
    text = report.to_text()
    if args.report:
        args.report.write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
