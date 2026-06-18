"""OSKAR — ECN DB helper functions shared across service modules."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import sqlalchemy as sa
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.ecn.models import (
    ApprovalStep,
    ECNConflict,
    ECNNotFound,
    ECNPreconditionRequired,
    ECNValidationError,
    RoleAssignment,
)
from src.workflow.machine import (
    ECNModel,
    ECNStatus,
    ECNWorkflowMachine,
)

log = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# ECN number generation
# ---------------------------------------------------------------------------

def _ecn_number(facility: str, seq: int, year: int | None = None) -> str:
    y = year or datetime.now(timezone.utc).year
    return f"ECN-{y}-{facility}-{seq:04d}"


async def _next_ecn_seq(session: AsyncSession, facility: str, year: int) -> int:
    prefix = f"ECN-{year}-{facility}-%"
    row = await session.execute(
        sa.text(
            "SELECT COALESCE(MAX(CAST(SPLIT_PART(ecn_number, '-', 4) AS INTEGER)), 0) "
            "FROM ecn_instances WHERE ecn_number LIKE :prefix"
        ),
        {"prefix": prefix},
    )
    return int(row.scalar_one()) + 1


# ---------------------------------------------------------------------------
# Row loaders
# ---------------------------------------------------------------------------

async def _load_ecn_row(session: AsyncSession, ecn_id: str) -> dict[str, Any] | None:
    row = await session.execute(
        sa.text("SELECT * FROM ecn_instances WHERE id = :id"),
        {"id": ecn_id},
    )
    result = row.mappings().first()
    return dict(result) if result else None


def _row_to_ecn_model(row: dict[str, Any]) -> ECNModel:
    return ECNModel(
        id=str(row["id"]),
        ecn_number=row["ecn_number"],
        facility=row["facility"],
        status=int(row["status"]),
        pre_hold_status=int(row["pre_hold_status"]) if row["pre_hold_status"] is not None else None,
        originator_username=row["originator_username"],
        revision_number=int(row["revision_number"]),
        title=row["title"] or "",
        is_new_item=bool(row["is_new_item"]),
        routing_changes=bool(row["routing_changes"]),
        operation_changes=bool(row["operation_changes"]),
        new_parts=bool(row["new_parts"]),
        lead_time_changes=bool(row["lead_time_changes"]),
        change_to_documents=bool(row["change_to_documents"]),
        wapc_delta_pct=float(row["wapc_delta_pct"]) if row["wapc_delta_pct"] is not None else None,
        wapc_threshold_override=bool(row["wapc_threshold_override"]),
        requires_customer_approval=bool(row["requires_customer_approval"]),
        customer_approved_at=row.get("customer_approved_at"),
        regulatory_impact=bool(row["regulatory_impact"]),
        item_count=0,
    )


async def _get_role_assignments(session: AsyncSession, ecn_id: str) -> list[RoleAssignment]:
    rows = await session.execute(
        sa.text(
            "SELECT role_id, username, is_auto_assigned FROM ecn_role_assignments "
            "WHERE ecn_id = :ecn_id AND superseded_at IS NULL ORDER BY role_id"
        ),
        {"ecn_id": ecn_id},
    )
    return [
        RoleAssignment(
            role_id=r["role_id"],
            username=r["username"],
            is_auto_assigned=bool(r["is_auto_assigned"]),
        )
        for r in rows.mappings()
    ]


async def _get_approval_steps(session: AsyncSession, ecn_id: str) -> list[ApprovalStep]:
    rows = await session.execute(
        sa.text(
            "SELECT role_id, username, status, skipped, skip_reason, completed_at "
            "FROM ecn_approval_steps "
            "WHERE ecn_id = :ecn_id ORDER BY at_status, role_id"
        ),
        {"ecn_id": ecn_id},
    )
    return [
        ApprovalStep(
            role_id=r["role_id"],
            username=r["username"],
            step_status=r["status"],
            skipped=bool(r["skipped"]),
            skip_reason=r["skip_reason"],
            completed_at=r["completed_at"],
        )
        for r in rows.mappings()
    ]


async def _count_ecn_items(session: AsyncSession, ecn_id: str) -> int:
    row = await session.execute(
        sa.text("SELECT COUNT(*) FROM ecn_items WHERE ecn_id = :ecn_id"),
        {"ecn_id": ecn_id},
    )
    return int(row.scalar_one())


# ---------------------------------------------------------------------------
# Audit chain
# ---------------------------------------------------------------------------

async def _get_last_transition_hash(session: AsyncSession, ecn_id: str) -> str | None:
    row = await session.execute(
        sa.text(
            "SELECT sha256_self FROM ecn_transition_history "
            "WHERE ecn_id = :ecn_id ORDER BY created_at DESC LIMIT 1"
        ),
        {"ecn_id": ecn_id},
    )
    result = row.first()
    return result[0] if result else None


async def _write_transition_history(
    session: AsyncSession,
    machine: ECNWorkflowMachine,
    ecn_id: str,
    from_status: int | None,
    to_status: int,
    action: str,
) -> None:
    record_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc)
    sha256_self = machine.compute_transition_hash(
        record_id=record_id,
        from_status=from_status,
        to_status=to_status,
        action=action,
        created_at=created_at,
    )
    await session.execute(
        sa.text(
            "INSERT INTO ecn_transition_history "
            "(id, ecn_id, from_status, to_status, action, "
            " actor_username, actor_role, notes, movex_payload, "
            " agent_provenance, sha256_self, sha256_prev, created_at) "
            "VALUES (:id, :ecn_id, :from_status, :to_status, :action, "
            "        :actor_username, :actor_role, :notes, CAST(:movex_payload AS jsonb), "
            "        CAST(:agent_provenance AS jsonb), :sha256_self, :sha256_prev, :created_at)"
        ),
        {
            "id": record_id,
            "ecn_id": ecn_id,
            "from_status": from_status,
            "to_status": to_status,
            "action": action,
            "actor_username": machine.ctx.actor_username,
            "actor_role": machine.ctx.actor_role,
            "notes": machine.ctx.notes,
            "movex_payload": None,
            "agent_provenance": None,
            "sha256_self": sha256_self,
            "sha256_prev": machine._sha256_prev,
            "created_at": created_at,
        },
    )


# ---------------------------------------------------------------------------
# Role auto-assign
# ---------------------------------------------------------------------------

async def _auto_assign_roles(
    session: AsyncSession,
    ecn_id: str,
    facility: str,
    originator_username: str,
    assigned_by: str,
) -> None:
    await session.execute(
        sa.text(
            "INSERT INTO ecn_role_assignments "
            "(id, ecn_id, facility, role_id, username, is_auto_assigned, assigned_by) "
            "VALUES (:id, :ecn_id, :facility, 'OR', :username, TRUE, :assigned_by)"
        ),
        {
            "id": str(uuid.uuid4()),
            "ecn_id": ecn_id,
            "facility": facility,
            "username": originator_username,
            "assigned_by": "system",
        },
    )

    rows = await session.execute(
        sa.text(
            "SELECT role_id, username FROM system_role_users "
            "WHERE facility = :facility AND is_active = TRUE AND removed_at IS NULL"
        ),
        {"facility": facility},
    )
    role_users: dict[str, list[str]] = {}
    for role_id, username in rows:
        role_users.setdefault(role_id, []).append(username)

    if not role_users.get("DC"):
        raise ECNValidationError(
            f"No active Document Controller (DC) configured for facility '{facility}'. "
            "Add a DC to system_role_users before creating ECNs."
        )

    for role_id, users in role_users.items():
        if role_id == "OR":
            continue
        username = users[0] if len(users) == 1 else None
        is_auto = len(users) == 1
        await session.execute(
            sa.text(
                "INSERT INTO ecn_role_assignments "
                "(id, ecn_id, facility, role_id, username, is_auto_assigned, assigned_by) "
                "VALUES (:id, :ecn_id, :facility, :role_id, :username, :is_auto, :assigned_by) "
                "ON CONFLICT DO NOTHING"
            ),
            {
                "id": str(uuid.uuid4()),
                "ecn_id": ecn_id,
                "facility": facility,
                "role_id": role_id,
                "username": username,
                "is_auto": is_auto,
                "assigned_by": assigned_by,
            },
        )


# ---------------------------------------------------------------------------
# next_action_users (G-2)
# ---------------------------------------------------------------------------

async def _compute_next_action_users(
    session: AsyncSession,
    ecn_id: str,
    status: int,
) -> list[str]:
    if status in (ECNStatus.CLOSED, ECNStatus.CANCELLED):
        return []

    if status in (ECNStatus.DRAFT, ECNStatus.REJECTED):
        row = await session.execute(
            sa.text("SELECT originator_username FROM ecn_instances WHERE id = :id"),
            {"id": ecn_id},
        )
        r = row.first()
        return [r[0]] if r else []

    if status in (ECNStatus.IMPLEMENTED, ECNStatus.ON_HOLD):
        rows = await session.execute(
            sa.text(
                "SELECT username FROM ecn_role_assignments "
                "WHERE ecn_id = :ecn_id AND role_id = 'DC' "
                "AND superseded_at IS NULL AND username IS NOT NULL"
            ),
            {"ecn_id": ecn_id},
        )
        return [r[0] for r in rows]

    if status == ECNStatus.ENGINEERING_REVIEW:
        rows = await session.execute(
            sa.text(
                "SELECT username FROM ecn_role_assignments "
                "WHERE ecn_id = :ecn_id AND role_id IN ('SE','CE') "
                "AND superseded_at IS NULL AND username IS NOT NULL"
            ),
            {"ecn_id": ecn_id},
        )
        return [r[0] for r in rows]

    if status == ECNStatus.MANAGEMENT_REVIEW:
        rows = await session.execute(
            sa.text(
                "SELECT username FROM ecn_approval_steps "
                "WHERE ecn_id = :ecn_id AND at_status = 40 "
                "AND status = 'pending' AND skipped = FALSE AND username IS NOT NULL"
            ),
            {"ecn_id": ecn_id},
        )
        return [r[0] for r in rows]

    return []


# ---------------------------------------------------------------------------
# Optimistic locking (ADR-008)
# ---------------------------------------------------------------------------

async def _check_not_modified(
    session: AsyncSession,
    ecn_id: str,
    if_unmodified_since: datetime | None,
) -> None:
    if if_unmodified_since is None:
        raise ECNPreconditionRequired()

    row = await session.execute(
        sa.text("SELECT updated_at FROM ecn_instances WHERE id = :id FOR UPDATE"),
        {"id": ecn_id},
    )
    result = row.first()
    if result is None:
        raise ECNNotFound(ecn_id)

    current_updated_at: datetime = result[0]
    ts_check = if_unmodified_since
    if ts_check.tzinfo is None:
        ts_check = ts_check.replace(tzinfo=timezone.utc)
    if current_updated_at.tzinfo is None:
        current_updated_at = current_updated_at.replace(tzinfo=timezone.utc)

    if current_updated_at != ts_check:
        raise ECNConflict(current_updated_at)
