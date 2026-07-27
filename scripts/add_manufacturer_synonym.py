"""
OSKAR — add_manufacturer_synonym CLI (Slice C, ADR-012 Decision 8 / R5 fix-forward).

Insert-only: raw manufacturer string + canonical name -> manufacturer_synonyms,
then re-runs every existing item_mpns row whose manufacturer_name matches that
raw string through normalize_manufacturer() again, so its manufacturer_canonical
picks up the newly-added mapping immediately.

Lets synonym misses surfaced by scripts/migrate_zecnmpms.py's review file (or
found later in normal use) get corrected same-day, without a deploy or waiting
for the Iteration 3 admin UI to land.

Usage:
    python scripts/add_manufacturer_synonym.py --raw "ST MICRO" --canonical "STMicroelectronics"

Insert-only means exactly that: if raw_string already has a mapping, this CLI
refuses (SynonymAlreadyExists) rather than silently overwriting it — correcting
an existing (wrong) canonical mapping is a different, more consequential
operation than filling in a miss, and isn't exposed here.
"""
from __future__ import annotations

import argparse
import asyncio
import os
from dataclasses import dataclass

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.services.bom.mpn_master import load_synonyms, normalize_manufacturer


class SynonymAlreadyExists(Exception):
    def __init__(self, raw_string: str):
        self.raw_string = raw_string
        super().__init__(f"manufacturer_synonyms already has a mapping for {raw_string!r}")


@dataclass
class AddSynonymResult:
    raw_string: str
    canonical_name: str
    item_mpns_updated: int


async def add_manufacturer_synonym_async(
    session: AsyncSession, *, raw: str, canonical: str, source: str = "manual"
) -> AddSynonymResult:
    """Insert one manufacturer_synonyms row, then re-normalize affected item_mpns.

    Uses INSERT ... ON CONFLICT DO NOTHING RETURNING (rather than catching the
    driver's IntegrityError) so a duplicate attempt doesn't poison the caller's
    transaction — safe to call from the CLI's own session or a test's
    db_session fixture alike.
    """
    raw_key = raw.strip().upper()
    canonical_clean = canonical.strip()

    inserted = await session.execute(
        sa.text(
            "INSERT INTO manufacturer_synonyms (raw_string, canonical_name, source) "
            "VALUES (:raw, :canonical, :source) "
            "ON CONFLICT (raw_string) DO NOTHING RETURNING raw_string"
        ),
        {"raw": raw_key, "canonical": canonical_clean, "source": source},
    )
    if inserted.first() is None:
        raise SynonymAlreadyExists(raw_key)

    synonyms = await load_synonyms(session)  # now includes the row just inserted

    affected = (
        await session.execute(
            sa.text(
                "SELECT id, manufacturer_name FROM item_mpns "
                "WHERE UPPER(TRIM(manufacturer_name)) = :raw"
            ),
            {"raw": raw_key},
        )
    ).all()

    for mpn_id, manufacturer_name in affected:
        norm = normalize_manufacturer(manufacturer_name, synonyms)
        await session.execute(
            sa.text(
                "UPDATE item_mpns SET manufacturer_canonical = :canonical, updated_at = now() "
                "WHERE id = :id"
            ),
            {"canonical": norm.canonical or None, "id": mpn_id},
        )

    return AddSynonymResult(
        raw_string=raw_key, canonical_name=canonical_clean, item_mpns_updated=len(affected)
    )


# ── CLI entrypoint ───────────────────────────────────────────────────────────

def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Insert a manufacturer synonym and re-normalize affected item_mpns rows"
    )
    parser.add_argument("--raw", required=True, help="Raw manufacturer string, e.g. 'ST MICRO'")
    parser.add_argument(
        "--canonical", required=True, help="Canonical manufacturer name, e.g. 'STMicroelectronics'"
    )
    parser.add_argument("--source", default="manual", help="Provenance tag stored on the row")
    return parser


async def _run_cli(args: argparse.Namespace) -> AddSynonymResult:
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
                return await add_manufacturer_synonym_async(
                    session, raw=args.raw, canonical=args.canonical, source=args.source
                )
    finally:
        await engine.dispose()


def main() -> None:
    args = _build_arg_parser().parse_args()
    try:
        result = asyncio.run(_run_cli(args))
    except SynonymAlreadyExists as exc:
        print(
            f"ERROR: {exc}. This CLI is insert-only — correcting an existing "
            "mapping needs a direct DB change or the future admin UI (Iteration 3)."
        )
        raise SystemExit(1)

    print(f"Added synonym: {result.raw_string!r} -> {result.canonical_name!r} (source={args.source})")
    print(f"Re-normalized {result.item_mpns_updated} existing item_mpns row(s).")


if __name__ == "__main__":
    main()
