"""
OSKAR — Admin endpoints

POST   /api/v1/admin/ecn-digest                       — On-demand ECN digest trigger (DC-only)
GET    /api/v1/admin/roles                            — List system_role_users (DC-only)
POST   /api/v1/admin/roles                            — Add user to role (DC-only)
DELETE /api/v1/admin/roles/{id}                        — Soft-remove role assignment (DC-only)
GET    /api/v1/admin/customer-role-defaults            — List per-customer SE/PM candidates (DC-only)
POST   /api/v1/admin/customer-role-defaults            — Add a candidate (DC-only)
PATCH  /api/v1/admin/customer-role-defaults/{id}/default — Mark candidate as the default (DC-only)
DELETE /api/v1/admin/customer-role-defaults/{id}       — Soft-remove a candidate (DC-only)
"""
from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import CurrentUser, get_current_user
from src.auth.providers import DevIdentityProvider, LDAPIdentityProvider, get_identity_provider
from src.db import get_session
from src.services.admin import (
    AdminService,
    DuplicateRoleUser,
    RoleUserNotFound,
)
from src.tasks.ecn_notifications import send_ecn_digest

admin_router = APIRouter(prefix="/admin", tags=["admin"])

_DC_GROUP = "ecn-doc-controller"

_VALID_ROLE_IDS = frozenset(
    {"DC", "OR", "SE", "CE", "EM", "QM", "PM", "SC", "FN", "AD", "CA", "RD", "TE", "MQ"}
)


def _require_dc(user: CurrentUser) -> None:
    if _DC_GROUP not in user.groups:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only Document Controllers may access this endpoint.",
        )


# ── LDAP groups (read-only) ───────────────────────────────────────────────────

@admin_router.get("/ldap-groups", status_code=status.HTTP_200_OK)
async def list_ldap_groups(
    user: CurrentUser = Depends(get_current_user),
) -> list[dict[str, Any]]:
    """Return all Application Roles groups from LDAP with their members.

    Queries AD live. Returns an empty list (not an error) if LDAP is
    unavailable or the provider does not support group enumeration
    (e.g. DevIdentityProvider in local dev).
    """
    _require_dc(user)
    provider = get_identity_provider()
    if isinstance(provider, (LDAPIdentityProvider, DevIdentityProvider)):
        return provider.list_application_groups()
    return []


# ── ECN digest (existing) ─────────────────────────────────────────────────────

@admin_router.post("/ecn-digest", status_code=status.HTTP_202_ACCEPTED)
async def trigger_ecn_digest(
    user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    _require_dc(user)
    send_ecn_digest.delay()
    return {"status": "queued"}


# ── Role users ────────────────────────────────────────────────────────────────

class RoleUserCreateBody(BaseModel):
    facility: str = "D"
    role_id: str
    username: str
    display_name: str | None = None
    email: str | None = None
    notes: str | None = None

    @field_validator("role_id")
    @classmethod
    def validate_role_id(cls, v: str) -> str:
        if v not in _VALID_ROLE_IDS:
            raise ValueError(f"Unknown role_id: {v}")
        return v


@admin_router.get("/roles", status_code=status.HTTP_200_OK)
async def list_role_users(
    facility: str | None = Query(default=None),
    role_id: str | None = Query(default=None),
    user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    _require_dc(user)
    svc = AdminService(session)
    return await svc.list_role_users(facility=facility, role_id=role_id)


@admin_router.post("/roles", status_code=status.HTTP_201_CREATED)
async def add_role_user(
    body: RoleUserCreateBody,
    user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    _require_dc(user)
    svc = AdminService(session)
    try:
        return await svc.add_role_user(
            facility=body.facility,
            role_id=body.role_id,
            username=body.username,
            display_name=body.display_name,
            email=body.email,
            notes=body.notes,
            added_by=user.username,
        )
    except DuplicateRoleUser as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@admin_router.delete("/roles/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_role_user(
    entry_id: str,
    user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Response:
    _require_dc(user)
    svc = AdminService(session)
    try:
        await svc.remove_role_user(entry_id=entry_id, removed_by=user.username)
    except RoleUserNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ── Customer role defaults (SE/PM per customer) ───────────────────────────────

_CRD_ROLE_IDS = frozenset({"SE", "PM"})


class CustomerRoleDefaultCreateBody(BaseModel):
    cuno: str
    role_id: str
    username: str
    customer_name: str | None = None
    display_name: str | None = None
    email: str | None = None
    is_default: bool = False
    notes: str | None = None

    @field_validator("role_id")
    @classmethod
    def validate_role_id(cls, v: str) -> str:
        if v not in _CRD_ROLE_IDS:
            raise ValueError(f"customer_role_defaults only supports SE/PM, got: {v}")
        return v


@admin_router.get("/customer-role-defaults", status_code=status.HTTP_200_OK)
async def list_customer_role_defaults(
    cuno: str | None = Query(default=None),
    role_id: str | None = Query(default=None),
    user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    _require_dc(user)
    svc = AdminService(session)
    return await svc.list_customer_role_defaults(cuno=cuno, role_id=role_id)


@admin_router.post("/customer-role-defaults", status_code=status.HTTP_201_CREATED)
async def add_customer_role_default(
    body: CustomerRoleDefaultCreateBody,
    user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    _require_dc(user)
    svc = AdminService(session)
    try:
        return await svc.add_customer_role_default(
            cuno=body.cuno,
            role_id=body.role_id,
            username=body.username,
            customer_name=body.customer_name,
            display_name=body.display_name,
            email=body.email,
            is_default=body.is_default,
            notes=body.notes,
            added_by=user.username,
        )
    except DuplicateRoleUser as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@admin_router.patch("/customer-role-defaults/{entry_id}/default", status_code=status.HTTP_200_OK)
async def set_customer_role_default(
    entry_id: str,
    cuno: Annotated[str, Query()],
    role_id: Annotated[str, Query()],
    user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    _require_dc(user)
    svc = AdminService(session)
    try:
        return await svc.set_customer_role_default(entry_id=entry_id, cuno=cuno, role_id=role_id)
    except RoleUserNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@admin_router.delete("/customer-role-defaults/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_customer_role_default(
    entry_id: str,
    user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Response:
    _require_dc(user)
    svc = AdminService(session)
    try:
        await svc.remove_customer_role_default(entry_id=entry_id, removed_by=user.username)
    except RoleUserNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
