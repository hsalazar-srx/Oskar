"""
OSKAR — Auth endpoints (ADR-006, ADR-007)

POST /api/v1/auth/login   — LDAPS bind → issue access token + refresh cookie
POST /api/v1/auth/refresh — validate refresh cookie → issue new access token + rotate cookie
POST /api/v1/auth/logout  — blocklist JTI + revoke refresh token hash in DB

Refresh token: HttpOnly, Secure, SameSite=Strict cookie named `oskar_refresh`.
Access token:  returned in JSON body — caller stores in memory only (never localStorage).

Security controls (ADR-006):
- Refresh token rotation: each /refresh issues a new token and revokes the old hash.
- Family detection: if a revoked refresh token is presented, all tokens for that user
  are revoked (theft signal).
- CSRF: SameSite=Strict on cookie; Origin header checked on state-mutating endpoints.
"""
from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Annotated

import sqlalchemy as sa
import structlog
from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import CurrentUser, get_current_user
from src.auth.jwt import (
    TokenError,
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    hash_token,
)
from src.auth.providers import get_identity_provider
from src.db import get_session

log = structlog.get_logger(__name__)

auth_router = APIRouter(prefix="/auth", tags=["auth"])

_REFRESH_COOKIE = "oskar_refresh"
_SECURE_COOKIE = os.environ.get("SECURE_COOKIE", "true").lower() != "false"


# ── Request / response schemas ────────────────────────────────────────────────


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


# ── Helpers ───────────────────────────────────────────────────────────────────


def _set_refresh_cookie(response: Response, token: str, expires_at: datetime) -> None:
    max_age = int((expires_at - datetime.now(UTC)).total_seconds())
    response.set_cookie(
        key=_REFRESH_COOKIE,
        value=token,
        httponly=True,
        secure=_SECURE_COOKIE,
        samesite="strict",
        max_age=max_age,
        path="/api/v1/auth",  # scoped — cookie not sent on ECN requests
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(key=_REFRESH_COOKIE, path="/api/v1/auth")


async def _store_refresh_token(
    session: AsyncSession,
    token: str,
    username: str,
    expires_at: datetime,
) -> None:
    token_hash = hash_token(token)
    await session.execute(
        sa.text(
            "INSERT INTO refresh_tokens (token_hash, username, expires_at) "
            "VALUES (:h, :u, :e)"
        ),
        {"h": token_hash, "u": username, "e": expires_at},
    )


async def _revoke_refresh_token(session: AsyncSession, token: str) -> bool:
    """Mark one refresh token as revoked. Returns True if it was active."""
    token_hash = hash_token(token)
    result = await session.execute(
        sa.text(
            "UPDATE refresh_tokens SET revoked_at = now() "
            "WHERE token_hash = :h AND revoked_at IS NULL "
            "RETURNING username"
        ),
        {"h": token_hash},
    )
    return result.first() is not None


async def _revoke_all_user_tokens(session: AsyncSession, username: str) -> None:
    """Family revocation — revoke all active refresh tokens for a user."""
    await session.execute(
        sa.text(
            "UPDATE refresh_tokens SET revoked_at = now() "
            "WHERE username = :u AND revoked_at IS NULL"
        ),
        {"u": username},
    )


async def _is_refresh_token_active(session: AsyncSession, token: str) -> str | None:
    """Return username if the token hash is active, None otherwise."""
    token_hash = hash_token(token)
    row = await session.execute(
        sa.text(
            "SELECT username FROM refresh_tokens "
            "WHERE token_hash = :h AND revoked_at IS NULL AND expires_at > now()"
        ),
        {"h": token_hash},
    )
    result = row.first()
    return result[0] if result else None


async def _is_refresh_token_revoked(session: AsyncSession, token: str) -> bool:
    """True if the token hash exists but is revoked — signals token family reuse."""
    token_hash = hash_token(token)
    row = await session.execute(
        sa.text(
            "SELECT 1 FROM refresh_tokens "
            "WHERE token_hash = :h AND revoked_at IS NOT NULL"
        ),
        {"h": token_hash},
    )
    return row.first() is not None


# ── Endpoints ─────────────────────────────────────────────────────────────────


@auth_router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> TokenResponse:
    """Authenticate with AD credentials via LDAPS. Issues access + refresh tokens."""
    provider = get_identity_provider()

    if not provider.authenticate(body.username, body.password):
        log.warning("auth.login.failed", username=body.username)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    groups = provider.get_groups(body.username)
    email = provider.get_email(body.username)

    # Display name: use LDAP cn if available; fall back to username
    display_name = body.username  # providers.py can expose get_display_name() later

    access_token, _jti, access_exp = create_access_token(
        username=body.username,
        display_name=display_name,
        email=email,
        groups=groups,
    )
    refresh_token, _rjti, refresh_exp = create_refresh_token(username=body.username)

    await _store_refresh_token(session, refresh_token, body.username, refresh_exp)
    _set_refresh_cookie(response, refresh_token, refresh_exp)

    log.info("auth.login.success", username=body.username, groups=groups)

    return TokenResponse(
        access_token=access_token,
        expires_in=int((access_exp - datetime.now(UTC)).total_seconds()),
    )


@auth_router.post("/refresh", response_model=TokenResponse)
async def refresh(
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
    oskar_refresh: Annotated[str | None, Cookie()] = None,
) -> TokenResponse:
    """Exchange a valid refresh cookie for a new access token. Rotates the refresh token.

    Family detection: if the presented refresh token is already revoked,
    all tokens for that user are revoked (theft signal) and 401 is returned.
    """
    invalid = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Session expired — please log in again",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if not oskar_refresh:
        raise invalid

    # Family detection: revoked token reuse = theft signal
    if await _is_refresh_token_revoked(session, oskar_refresh):
        try:
            payload = decode_refresh_token(oskar_refresh)
            username = payload.get("sub", "unknown")
        except TokenError:
            username = "unknown"
        log.warning("auth.refresh.family_revocation", username=username)
        await _revoke_all_user_tokens(session, username)
        _clear_refresh_cookie(response)
        raise invalid

    # Validate token signature + expiry
    try:
        payload = decode_refresh_token(oskar_refresh)
    except TokenError:
        _clear_refresh_cookie(response)
        raise invalid

    username: str = payload["sub"]

    # Check DB: token must be active
    active_username = await _is_refresh_token_active(session, oskar_refresh)
    if not active_username:
        _clear_refresh_cookie(response)
        raise invalid

    # Rotate: revoke old, issue new
    await _revoke_refresh_token(session, oskar_refresh)

    provider = get_identity_provider()
    groups = provider.get_groups(username)
    email = provider.get_email(username)

    access_token, _jti, access_exp = create_access_token(
        username=username,
        display_name=username,
        email=email,
        groups=groups,
    )
    new_refresh, _rjti, refresh_exp = create_refresh_token(username=username)
    await _store_refresh_token(session, new_refresh, username, refresh_exp)
    _set_refresh_cookie(response, new_refresh, refresh_exp)

    log.info("auth.refresh.rotated", username=username)

    return TokenResponse(
        access_token=access_token,
        expires_in=int((access_exp - datetime.now(UTC)).total_seconds()),
    )


@auth_router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def logout(
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[CurrentUser, Depends(get_current_user)],
    oskar_refresh: Annotated[str | None, Cookie()] = None,
) -> None:
    """Blocklist the access token JTI and revoke the refresh token."""
    # Blocklist the access token JTI for its remaining lifetime
    await session.execute(
        sa.text(
            "INSERT INTO jti_blocklist (jti, expires_at) "
            "VALUES (:jti, now() + interval '1 hour') "  # conservative TTL
            "ON CONFLICT DO NOTHING"
        ),
        {"jti": user.jti},
    )

    if oskar_refresh:
        await _revoke_refresh_token(session, oskar_refresh)

    _clear_refresh_cookie(response)
    log.info("auth.logout", username=user.username)
