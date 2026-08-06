"""
OSKAR — src.services.bom.snapshots — bom_snapshots persistence (Slice D,
ADR-012 D2, migration 0026).

Point-in-time JSONB line array + SHA-256 content hash. Three consumers per
D2: comparison inputs (Slice D — this module), ECN concurrency baseline
(Slice E — dc_approve re-fetch-and-diff against the submit-time snapshot),
and history (browsable list, any slice). Slice D only ever writes
reason='compare'/'manual' rows; 'ecn_submit' is Slice E's concern, but the
CHECK constraint (migration 0026) already allows it so Slice E needs no
further schema change.

content_hash() is pure (no DB, no I/O) — see its docstring and
tests/services/bom/test_snapshots.py for the key-order-independence /
line-order-significance rule.

insert_snapshot()/get_snapshot()/list_snapshots() are the DB-touching half,
following the same sa.text()-with-positional-params convention as
src/services/bom/mpn_master.py. Covered by tests/integration/test_bom_snapshots.py
(real Postgres via migration 0026) — see that file if Postgres was
unreachable when this slice's suite ran; the tests are written to the real
schema regardless.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import uuid
from dataclasses import dataclass
from typing import Any, Mapping

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession


def content_hash(lines: list[dict[str, Any]]) -> str:
    """SHA-256 hex digest of `lines`, canonicalised so key ordering WITHIN
    each line dict never affects the hash (json.dumps(..., sort_keys=True)),
    while line ORDER in the list is preserved and DOES affect the hash — see
    module docstring / test_snapshots.py for why line order is treated as
    semantically significant."""
    canonical = json.dumps(lines, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass
class BOMSnapshot:
    id: str
    item_number: str
    facility: str
    structure_type: str
    level_mode: str
    lines: list[dict[str, Any]]
    line_count: int
    content_hash: str
    reason: str
    ecn_id: str | None
    captured_by: str
    captured_at: datetime.datetime


_SELECT_COLUMNS = (
    "id, item_number, facility, structure_type, level_mode, lines, line_count, "
    "content_hash, reason, ecn_id, captured_by, captured_at"
)


def _row_to_snapshot(row: Mapping[str, Any]) -> BOMSnapshot:
    return BOMSnapshot(
        id=str(row["id"]),
        item_number=row["item_number"],
        facility=row["facility"],
        structure_type=row["structure_type"],
        level_mode=row["level_mode"],
        lines=row["lines"],
        line_count=row["line_count"],
        content_hash=row["content_hash"],
        reason=row["reason"],
        ecn_id=str(row["ecn_id"]) if row["ecn_id"] else None,
        captured_by=row["captured_by"],
        captured_at=row["captured_at"],
    )


async def insert_snapshot(
    session: AsyncSession,
    *,
    item_number: str,
    facility: str,
    lines: list[dict[str, Any]],
    reason: str,
    captured_by: str,
    structure_type: str = "001",
    level_mode: str = "single",
    ecn_id: str | None = None,
) -> BOMSnapshot:
    """Insert a new bom_snapshots row. content_hash is computed here, not
    accepted as a caller-supplied value, so it can never drift out of sync
    with `lines`."""
    row_id = str(uuid.uuid4())
    params = {
        "id": row_id,
        "item_number": item_number,
        "facility": facility,
        "structure_type": structure_type,
        "level_mode": level_mode,
        "lines": json.dumps(lines, default=str),
        "line_count": len(lines),
        "content_hash": content_hash(lines),
        "reason": reason,
        "ecn_id": ecn_id,
        "captured_by": captured_by,
    }
    result = await session.execute(
        sa.text(
            "INSERT INTO bom_snapshots "
            "(id, item_number, facility, structure_type, level_mode, lines, line_count, "
            "content_hash, reason, ecn_id, captured_by) "
            "VALUES (:id, :item_number, :facility, :structure_type, :level_mode, "
            "CAST(:lines AS JSONB), :line_count, :content_hash, :reason, :ecn_id, :captured_by) "
            f"RETURNING {_SELECT_COLUMNS}"
        ),
        params,
    )
    row = result.mappings().first()
    return _row_to_snapshot(row)


async def get_snapshot(session: AsyncSession, snapshot_id: str) -> BOMSnapshot | None:
    result = await session.execute(
        sa.text(f"SELECT {_SELECT_COLUMNS} FROM bom_snapshots WHERE id = :id"),
        {"id": snapshot_id},
    )
    row = result.mappings().first()
    return _row_to_snapshot(row) if row else None


async def list_snapshots(
    session: AsyncSession,
    *,
    item_number: str,
    facility: str,
    limit: int = 50,
) -> list[BOMSnapshot]:
    result = await session.execute(
        sa.text(
            f"SELECT {_SELECT_COLUMNS} FROM bom_snapshots "
            "WHERE item_number = :item_number AND facility = :facility "
            "ORDER BY captured_at DESC LIMIT :limit"
        ),
        {"item_number": item_number, "facility": facility, "limit": limit},
    )
    return [_row_to_snapshot(row) for row in result.mappings()]
