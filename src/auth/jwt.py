"""
OSKAR — JWT token management (ADR-006)

Access token:  60-minute HS256 JWT, stored in React in-memory only.
Refresh token: 8-hour HS256 JWT, issued as HttpOnly Secure SameSite=Strict cookie.
               SHA-256 hash stored in PostgreSQL `refresh_tokens` table (ADR-007).

JTI blocklist: PostgreSQL `jti_blocklist` table — one row per revoked JTI with expires_at.
               Checked on every authenticated request (PK lookup). ADR-007.

Algorithm: HS256 only. alg:none is rejected by jose at validation time.

This module is pure crypto — no DB access. Callers handle persistence.
"""
from __future__ import annotations

import hashlib
import os
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from jose import JWTError, jwt

# ── Constants ─────────────────────────────────────────────────────────────────

ALGORITHM = "HS256"
ISSUER = "oskar.scanfil.apac"
AUDIENCE = "oskar-api"

ACCESS_TOKEN_EXPIRE_MINUTES: int = int(
    os.environ.get("ACCESS_TOKEN_EXPIRE_MINUTES", "60")
)
REFRESH_TOKEN_EXPIRE_HOURS: int = int(
    os.environ.get("REFRESH_TOKEN_EXPIRE_HOURS", "8")
)


def _jwt_secret() -> str:
    secret = os.environ.get("JWT_SECRET_KEY")
    if not secret:
        raise RuntimeError("JWT_SECRET_KEY environment variable is not set")
    return secret


def _refresh_secret() -> str:
    secret = os.environ.get("REFRESH_TOKEN_SECRET")
    if not secret:
        raise RuntimeError("REFRESH_TOKEN_SECRET environment variable is not set")
    return secret


# ── Exceptions ────────────────────────────────────────────────────────────────


class TokenError(Exception):
    """Raised when a token cannot be validated."""


# ── Token creation ────────────────────────────────────────────────────────────


def create_access_token(
    username: str,
    display_name: str,
    email: str | None,
    groups: list[str],
) -> tuple[str, str, datetime]:
    """Create a signed 60-minute access token.

    Returns (token, jti, expires_at_utc).
    Caller stores nothing — JTI is only used on logout (add to blocklist).
    """
    now = datetime.now(UTC)
    exp = now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    jti = str(uuid.uuid4())

    payload: dict[str, Any] = {
        "sub": username,
        "name": display_name,
        "email": email,
        "groups": groups,
        "iat": now,
        "exp": exp,
        "jti": jti,
        "iss": ISSUER,
        "aud": AUDIENCE,
    }
    token = jwt.encode(payload, _jwt_secret(), algorithm=ALGORITHM)
    return token, jti, exp


def create_refresh_token(username: str) -> tuple[str, str, datetime]:
    """Create a signed 8-hour refresh token.

    Returns (token, jti, expires_at_utc).
    Caller stores SHA-256 hash of token in `refresh_tokens` table.
    """
    now = datetime.now(UTC)
    exp = now + timedelta(hours=REFRESH_TOKEN_EXPIRE_HOURS)
    jti = str(uuid.uuid4())

    payload: dict[str, Any] = {
        "sub": username,
        "iat": now,
        "exp": exp,
        "jti": jti,
        "iss": ISSUER,
        "aud": AUDIENCE,
        "type": "refresh",
    }
    token = jwt.encode(payload, _refresh_secret(), algorithm=ALGORITHM)
    return token, jti, exp


# ── Token validation ──────────────────────────────────────────────────────────


def decode_access_token(token: str) -> dict[str, Any]:
    """Decode and validate an access token. Raises TokenError on any failure.

    Validates: signature (HS256 only — alg:none rejected), issuer, audience,
    expiry, required claims. Does NOT check the JTI blocklist — callers must
    do that via a DB lookup after decoding.
    """
    try:
        payload = jwt.decode(
            token,
            _jwt_secret(),
            algorithms=[ALGORITHM],
            issuer=ISSUER,
            audience=AUDIENCE,
            options={"require": ["sub", "jti", "exp", "iat"]},
        )
    except JWTError as exc:
        raise TokenError(str(exc)) from exc

    if payload.get("type") == "refresh":
        raise TokenError("refresh token presented as access token")

    return payload


def decode_refresh_token(token: str) -> dict[str, Any]:
    """Decode and validate a refresh token. Raises TokenError on any failure."""
    try:
        payload = jwt.decode(
            token,
            _refresh_secret(),
            algorithms=[ALGORITHM],
            issuer=ISSUER,
            audience=AUDIENCE,
            options={"require": ["sub", "jti", "exp", "iat"]},
        )
    except JWTError as exc:
        raise TokenError(str(exc)) from exc

    if payload.get("type") != "refresh":
        raise TokenError("access token presented as refresh token")

    return payload


# ── Helpers for DB persistence (callers use these, no DB imports here) ────────


def hash_token(token: str) -> str:
    """SHA-256 hex digest of a token — stored in refresh_tokens, never the raw token."""
    return hashlib.sha256(token.encode()).hexdigest()
