"""
OSKAR — FastAPI authentication dependencies (ADR-006, ADR-007)

get_current_user:  Extracts Bearer token → validates JWT → checks jti_blocklist table.
                   Raises 401 on any failure. Returns a CurrentUser dataclass.

require_group:     Factory that returns a dependency requiring a specific AD group in the JWT.
                   Raises 403 if the user is not in the group.

DB session:        Uses SQLAlchemy async session injected via FastAPI dependency.
                   JTI blocklist is a single PK lookup — sub-millisecond at 50-user scale.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

import sqlalchemy as sa
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.jwt import TokenError, decode_access_token
from src.db import get_session  # async session factory — defined in src/db.py

_bearer = HTTPBearer(auto_error=True)


@dataclass(frozen=True)
class CurrentUser:
    username: str
    display_name: str
    email: str | None
    groups: list[str]
    jti: str


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(_bearer)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> CurrentUser:
    """Validate the Bearer JWT and check the JTI blocklist.

    Raises 401 if:
    - Token is missing or malformed
    - Signature is invalid or token is expired
    - alg:none or wrong token type
    - JTI is in the blocklist (user logged out)
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = decode_access_token(credentials.credentials)
    except TokenError:
        raise credentials_exception

    jti: str = payload["jti"]
    username: str = payload["sub"]

    # JTI blocklist check — one PK lookup (ADR-007: PostgreSQL replaces Redis)
    row = await session.execute(
        sa.text("SELECT 1 FROM jti_blocklist WHERE jti = :jti"),
        {"jti": jti},
    )
    if row.first() is not None:
        raise credentials_exception

    return CurrentUser(
        username=username,
        display_name=payload.get("name", username),
        email=payload.get("email"),
        groups=payload.get("groups", []),
        jti=jti,
    )


def require_group(group_name: str):
    """Dependency factory — raises 403 if the user is not in the required AD group.

    Usage:
        @router.post("/ecn/{id}/approve")
        async def approve(
            user: Annotated[CurrentUser, Depends(require_group("OSKAR-Approvers"))],
        ): ...
    """
    async def _check(
        user: Annotated[CurrentUser, Depends(get_current_user)],
    ) -> CurrentUser:
        if group_name not in user.groups:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires group: {group_name}",
            )
        return user

    return _check


# ── Convenience aliases ───────────────────────────────────────────────────────

RequireEngineer = Depends(require_group("OSKAR-Engineers"))
RequireApprover = Depends(require_group("OSKAR-Approvers"))
RequireAdmin    = Depends(require_group("OSKAR-Admins"))
