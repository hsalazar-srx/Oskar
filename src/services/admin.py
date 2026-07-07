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
