"""
OSKAR — src.services.bom.comparisons — bom_comparisons persistence (Slice D,
ADR-012 D5, migration 0027).

Save/history for a compare run. Sides are DESCRIPTORS ({type: erp|snapshot|
upload, ...identifying fields}) — never a local BOM mirror.

Why a descriptor, not a stored copy of the lines (worth stating the actual
reasoning, not just citing the plan): this is an explicit, user-confirmed
decision (plan "User-confirmed decisions" #2: "BOM reads: extend the
external movex-rest-api — no local BOM mirror"), and it is the right call on
its own merits, not just because it's mandated:
  1. Movex is Oskar's declared single source of truth throughout (see
     project_oskar_ifs_scope memory) — a general live-updating mirror
     creates a second "truth" that can silently drift, reopening exactly
     the staleness risk the plan already names and mitigates elsewhere
     (R8: "stale snapshot vs edited change lines" -> "re-capture on
     resubmit; DC gate always re-fetches live").
  2. A disciplined, purpose-scoped alternative to a general mirror already
     exists: bom_snapshots (D2, migration 0026) — an explicit, timestamped,
     reason-tagged, SHA-256-hash-verified point-in-time capture, not a
     live-updating cache that silently claims to represent current Movex
     state. A comparison's descriptor can point at
     {"type": "snapshot", "snapshot_id": ...} to reference one.
  3. Re-viewing/re-exporting a saved comparison whose side is
     {"type": "erp", ...} re-resolves against LIVE Movex at view/export
     time (via the same ERPAdapter call Slice A/B already wired) — which is
     what a diff tool's users actually want ("what does the BOM look like
     now"), not a frozen copy that silently goes stale with no invalidation
     policy of its own.
comparison_result stores compare.py's BOMDiff, already serialised to plain
dict/JSON by the router layer (src/routers/bom.py) before it reaches this
module — comparisons.py has no dependency on compare.py's dataclasses,
matching mpn_master.py's convention of DB-touching modules working with
plain dicts, not service dataclasses, at the SQL boundary.
"""
from __future__ import annotations

import datetime
import decimal
import json
import uuid
from dataclasses import dataclass
from typing import Any, Mapping

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class BOMComparison:
    id: str
    left_descriptor: dict[str, Any]
    right_descriptor: dict[str, Any]
    comparison_result: dict[str, Any]
    cost_impact: decimal.Decimal | None
    risk_flags: list[str]
    created_by: str
    created_at: datetime.datetime


_SELECT_COLUMNS = (
    "id, left_descriptor, right_descriptor, comparison_result, cost_impact, "
    "risk_flags, created_by, created_at"
)


def _row_to_comparison(row: Mapping[str, Any]) -> BOMComparison:
    return BOMComparison(
        id=str(row["id"]),
        left_descriptor=row["left_descriptor"],
        right_descriptor=row["right_descriptor"],
        comparison_result=row["comparison_result"],
        cost_impact=row["cost_impact"],
        risk_flags=list(row["risk_flags"] or []),
        created_by=row["created_by"],
        created_at=row["created_at"],
    )


async def insert_comparison(
    session: AsyncSession,
    *,
    left_descriptor: dict[str, Any],
    right_descriptor: dict[str, Any],
    comparison_result: dict[str, Any],
    created_by: str,
    cost_impact: float | None = None,
    risk_flags: list[str] | None = None,
) -> BOMComparison:
    row_id = str(uuid.uuid4())
    params = {
        "id": row_id,
        "left_descriptor": json.dumps(left_descriptor),
        "right_descriptor": json.dumps(right_descriptor),
        "comparison_result": json.dumps(comparison_result),
        "cost_impact": cost_impact,
        "risk_flags": risk_flags or [],
        "created_by": created_by,
    }
    result = await session.execute(
        sa.text(
            "INSERT INTO bom_comparisons "
            "(id, left_descriptor, right_descriptor, comparison_result, cost_impact, "
            "risk_flags, created_by) "
            "VALUES (:id, CAST(:left_descriptor AS JSONB), CAST(:right_descriptor AS JSONB), "
            "CAST(:comparison_result AS JSONB), :cost_impact, :risk_flags, :created_by) "
            f"RETURNING {_SELECT_COLUMNS}"
        ),
        params,
    )
    row = result.mappings().first()
    return _row_to_comparison(row)


async def get_comparison(session: AsyncSession, comparison_id: str) -> BOMComparison | None:
    result = await session.execute(
        sa.text(f"SELECT {_SELECT_COLUMNS} FROM bom_comparisons WHERE id = :id"),
        {"id": comparison_id},
    )
    row = result.mappings().first()
    return _row_to_comparison(row) if row else None


async def list_comparisons(
    session: AsyncSession, *, created_by: str | None = None, limit: int = 50
) -> list[BOMComparison]:
    if created_by is not None:
        result = await session.execute(
            sa.text(
                f"SELECT {_SELECT_COLUMNS} FROM bom_comparisons WHERE created_by = :created_by "
                "ORDER BY created_at DESC LIMIT :limit"
            ),
            {"created_by": created_by, "limit": limit},
        )
    else:
        result = await session.execute(
            sa.text(
                f"SELECT {_SELECT_COLUMNS} FROM bom_comparisons "
                "ORDER BY created_at DESC LIMIT :limit"
            ),
            {"limit": limit},
        )
    return [_row_to_comparison(row) for row in result.mappings()]
