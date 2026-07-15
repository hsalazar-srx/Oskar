"""OSKAR — AdminService: system_role_users CRUD."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

_VALID_ROLE_IDS = frozenset(
    {"DC", "OR", "SE", "CE", "EM", "QM", "PM", "SC", "FN", "AD", "CA", "RD", "TE", "MQ"}
)


class DuplicateRoleUser(Exception):
    pass


class RoleUserNotFound(Exception):
    pass


class OutboxEntryNotFound(Exception):
    pass


class OutboxEntryNotRetryable(Exception):
    pass


_RETRYABLE_STATES = frozenset({"failed", "abandoned"})


class AdminService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── Role users ────────────────────────────────────────────────────────

    async def list_role_users(
        self,
        *,
        facility: str | None = None,
        role_id: str | None = None,
    ) -> list[dict[str, Any]]:
        sql = (
            "SELECT id, facility, role_id, username, display_name, email, "
            "is_active, added_by, added_at, removed_by, removed_at, notes "
            "FROM system_role_users WHERE removed_at IS NULL"
        )
        params: dict[str, Any] = {}
        if facility:
            sql += " AND facility = :facility"
            params["facility"] = facility
        if role_id:
            sql += " AND role_id = :role_id"
            params["role_id"] = role_id
        sql += " ORDER BY facility, role_id, added_at"
        result = await self._session.execute(sa.text(sql), params)
        return [dict(r._mapping) for r in result.fetchall()]

    async def add_role_user(
        self,
        *,
        facility: str,
        role_id: str,
        username: str,
        display_name: str | None = None,
        email: str | None = None,
        notes: str | None = None,
        added_by: str,
    ) -> dict[str, Any]:
        if role_id not in _VALID_ROLE_IDS:
            raise ValueError(f"Unknown role_id: {role_id}")
        try:
            result = await self._session.execute(
                sa.text("""
                    INSERT INTO system_role_users
                        (facility, role_id, username, display_name, email, notes, added_by)
                    VALUES
                        (:facility, :role_id, :username, :display_name, :email, :notes, :added_by)
                    RETURNING id, facility, role_id, username, display_name, email,
                              is_active, added_by, added_at, removed_by, removed_at, notes
                """),
                {
                    "facility": facility,
                    "role_id": role_id,
                    "username": username,
                    "display_name": display_name,
                    "email": email,
                    "notes": notes,
                    "added_by": added_by,
                },
            )
            await self._session.commit()
            return dict(result.fetchone()._mapping)
        except Exception as exc:
            await self._session.rollback()
            if "uq_system_role_users" in str(exc):
                raise DuplicateRoleUser(
                    f"{username} already has role {role_id} in {facility}"
                ) from exc
            raise

    async def remove_role_user(self, *, entry_id: str, removed_by: str) -> None:
        result = await self._session.execute(
            sa.text("""
                UPDATE system_role_users
                SET removed_at = :now, removed_by = :removed_by
                WHERE id = :id AND removed_at IS NULL
                RETURNING id
            """),
            {"id": entry_id, "now": datetime.now(timezone.utc), "removed_by": removed_by},
        )
        await self._session.commit()
        if result.rowcount == 0:
            raise RoleUserNotFound(f"{entry_id} not found or already removed")

    # ── Customer role defaults (SE/PM per customer) ──────────────────────────

    async def list_customer_role_defaults(
        self,
        *,
        cuno: str | None = None,
        role_id: str | None = None,
    ) -> list[dict[str, Any]]:
        sql = (
            "SELECT id, cuno, customer_name, role_id, username, display_name, email, "
            "is_default, source, is_active, added_by, added_at, removed_by, removed_at, notes "
            "FROM customer_role_defaults WHERE removed_at IS NULL"
        )
        params: dict[str, Any] = {}
        if cuno:
            sql += " AND cuno = :cuno"
            params["cuno"] = cuno
        if role_id:
            sql += " AND role_id = :role_id"
            params["role_id"] = role_id
        sql += " ORDER BY customer_name, role_id, added_at"
        result = await self._session.execute(sa.text(sql), params)
        return [dict(r._mapping) for r in result.fetchall()]

    async def add_customer_role_default(
        self,
        *,
        cuno: str,
        role_id: str,
        username: str,
        customer_name: str | None = None,
        display_name: str | None = None,
        email: str | None = None,
        is_default: bool = False,
        notes: str | None = None,
        added_by: str,
    ) -> dict[str, Any]:
        if role_id not in {"SE", "PM"}:
            raise ValueError(f"customer_role_defaults only supports SE/PM, got: {role_id}")
        try:
            if is_default:
                await self._session.execute(
                    sa.text("""
                        UPDATE customer_role_defaults
                        SET is_default = FALSE
                        WHERE cuno = :cuno AND role_id = :role_id AND removed_at IS NULL
                    """),
                    {"cuno": cuno, "role_id": role_id},
                )
            result = await self._session.execute(
                sa.text("""
                    INSERT INTO customer_role_defaults
                        (cuno, customer_name, role_id, username, display_name, email,
                         is_default, source, notes, added_by)
                    VALUES
                        (:cuno, :customer_name, :role_id, :username, :display_name, :email,
                         :is_default, 'manual', :notes, :added_by)
                    RETURNING id, cuno, customer_name, role_id, username, display_name, email,
                              is_default, source, is_active, added_by, added_at, removed_by,
                              removed_at, notes
                """),
                {
                    "cuno": cuno,
                    "customer_name": customer_name,
                    "role_id": role_id,
                    "username": username,
                    "display_name": display_name,
                    "email": email,
                    "is_default": is_default,
                    "notes": notes,
                    "added_by": added_by,
                },
            )
            await self._session.commit()
            return dict(result.fetchone()._mapping)
        except Exception as exc:
            await self._session.rollback()
            if "uq_crd_cuno_role_username" in str(exc):
                raise DuplicateRoleUser(
                    f"{username} already has role {role_id} for customer {cuno}"
                ) from exc
            raise

    async def set_customer_role_default(
        self, *, entry_id: str, cuno: str, role_id: str,
    ) -> dict[str, Any]:
        """Mark one candidate as the default SE/PM for a customer; unsets any other default."""
        await self._session.execute(
            sa.text("""
                UPDATE customer_role_defaults
                SET is_default = FALSE
                WHERE cuno = :cuno AND role_id = :role_id AND removed_at IS NULL
            """),
            {"cuno": cuno, "role_id": role_id},
        )
        result = await self._session.execute(
            sa.text("""
                UPDATE customer_role_defaults
                SET is_default = TRUE
                WHERE id = :id AND removed_at IS NULL
                RETURNING id, cuno, customer_name, role_id, username, display_name, email,
                          is_default, source, is_active, added_by, added_at, removed_by,
                          removed_at, notes
            """),
            {"id": entry_id},
        )
        await self._session.commit()
        row = result.fetchone()
        if row is None:
            raise RoleUserNotFound(f"{entry_id} not found or already removed")
        return dict(row._mapping)

    async def remove_customer_role_default(self, *, entry_id: str, removed_by: str) -> None:
        result = await self._session.execute(
            sa.text("""
                UPDATE customer_role_defaults
                SET removed_at = :now, removed_by = :removed_by
                WHERE id = :id AND removed_at IS NULL
                RETURNING id
            """),
            {"id": entry_id, "now": datetime.now(timezone.utc), "removed_by": removed_by},
        )
        await self._session.commit()
        if result.rowcount == 0:
            raise RoleUserNotFound(f"{entry_id} not found or already removed")

    # ── Movex outbox recovery (S9-4) ─────────────────────────────────────────

    async def list_movex_outbox(
        self,
        *,
        state: str | None = None,
        facility: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """List movex_outbox entries joined with ECN context, newest first.

        Defaults to failed/abandoned only (the DC Recovery view) when no
        state filter is given — completed/pending/processing entries are
        noise for this screen and can be requested explicitly if needed.
        """
        sql = (
            "SELECT o.id, o.ecn_id, e.ecn_number, e.facility, o.ecn_item_id, "
            "o.mi_transaction, o.state, o.attempt_count, o.max_attempts, "
            "o.next_retry_at, o.last_error, o.completed_at, o.created_at, o.updated_at "
            "FROM movex_outbox o "
            "JOIN ecn_instances e ON e.id = o.ecn_id "
            "WHERE 1=1"
        )
        params: dict[str, Any] = {"limit": limit}
        if state:
            sql += " AND o.state = :state"
            params["state"] = state
        else:
            sql += " AND o.state IN ('failed', 'abandoned')"
        if facility:
            sql += " AND e.facility = :facility"
            params["facility"] = facility
        sql += " ORDER BY o.updated_at DESC LIMIT :limit"
        result = await self._session.execute(sa.text(sql), params)
        return [dict(r._mapping) for r in result.fetchall()]

    async def retry_movex_outbox_entry(self, *, entry_id: str, actor_username: str) -> dict[str, Any]:
        """Reset a failed/abandoned outbox entry to pending and re-dispatch it.

        attempt_count is reset to 0 — chk_outbox_not_requeued forbids a
        'pending' row with attempt_count >= max_attempts, and an abandoned
        entry is otherwise silently skipped by process_outbox_entry's
        idempotency guard (terminal-state check). A DC-triggered retry is a
        deliberate new attempt cycle, not a continuation of the abandoned one.
        """
        row = await self._session.execute(
            sa.text("SELECT id, state FROM movex_outbox WHERE id = :id"),
            {"id": entry_id},
        )
        entry = row.first()
        if entry is None:
            raise OutboxEntryNotFound(entry_id)
        if entry[1] not in _RETRYABLE_STATES:
            raise OutboxEntryNotRetryable(
                f"Outbox entry {entry_id} is in state '{entry[1]}' — only "
                f"{sorted(_RETRYABLE_STATES)} entries can be retried."
            )

        result = await self._session.execute(
            sa.text("""
                UPDATE movex_outbox
                SET state = 'pending', attempt_count = 0, next_retry_at = NULL, updated_at = now()
                WHERE id = :id
                RETURNING id, ecn_id, mi_transaction, state
            """),
            {"id": entry_id},
        )
        await self._session.commit()
        updated = dict(result.fetchone()._mapping)

        from src.tasks.movex_outbox import process_outbox_entry
        process_outbox_entry.apply_async(args=[entry_id])

        return updated
