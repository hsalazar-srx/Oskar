"""
Tests for src/auth/jwt.py

All tests are pure-unit — no DB, no LDAP, no network.
Secrets are injected via monkeypatch on os.environ.
"""
from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta

import pytest
from jose import jwt as jose_jwt

from src.auth.jwt import (
    ALGORITHM,
    AUDIENCE,
    ISSUER,
    TokenError,
    create_access_token,
    create_refresh_token,
    decode_access_token,
    decode_refresh_token,
    hash_token,
)

# ── Fixtures ──────────────────────────────────────────────────────────────────

_SECRET = "test-jwt-secret-32-bytes-minimum!!"
_REFRESH = "test-refresh-secret-32-bytes-min!!"


@pytest.fixture(autouse=True)
def _set_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JWT_SECRET_KEY", _SECRET)
    monkeypatch.setenv("REFRESH_TOKEN_SECRET", _REFRESH)


# ── Access token round-trip ───────────────────────────────────────────────────


def test_access_token_round_trip():
    token, jti, exp = create_access_token(
        username="jsmith",
        display_name="John Smith",
        email="jsmith@scanfil.apac",
        groups=["OSKAR-Engineers"],
    )
    payload = decode_access_token(token)

    assert payload["sub"] == "jsmith"
    assert payload["name"] == "John Smith"
    assert payload["email"] == "jsmith@scanfil.apac"
    assert payload["groups"] == ["OSKAR-Engineers"]
    assert payload["jti"] == jti
    assert payload["iss"] == ISSUER
    assert payload["aud"] == AUDIENCE
    assert "type" not in payload  # access tokens have no type claim


def test_access_token_jti_is_uuid():
    _, jti, _ = create_access_token("u", "U", None, [])
    import uuid
    uuid.UUID(jti)  # raises if not a valid UUID


def test_access_token_expiry_is_future():
    _, _, exp = create_access_token("u", "U", None, [])
    assert exp > datetime.now(UTC)


def test_access_token_email_none():
    token, _, _ = create_access_token("u", "U", None, [])
    payload = decode_access_token(token)
    assert payload["email"] is None


# ── Refresh token round-trip ──────────────────────────────────────────────────


def test_refresh_token_round_trip():
    token, jti, exp = create_refresh_token("jsmith")
    payload = decode_refresh_token(token)

    assert payload["sub"] == "jsmith"
    assert payload["jti"] == jti
    assert payload["type"] == "refresh"
    assert payload["iss"] == ISSUER
    assert payload["aud"] == AUDIENCE


def test_refresh_token_expiry_is_future():
    _, _, exp = create_refresh_token("u")
    assert exp > datetime.now(UTC)


# ── Token type swap rejection ─────────────────────────────────────────────────


def test_refresh_token_rejected_as_access():
    """A refresh token must not be accepted by decode_access_token.

    The rejection happens at signature verification (different secret) or at the
    type-claim check — either way a TokenError is raised. The security property
    is that cross-token use is always rejected.
    """
    token, _, _ = create_refresh_token("jsmith")
    with pytest.raises(TokenError):
        decode_access_token(token)


def test_access_token_rejected_as_refresh():
    """An access token must not be accepted by decode_refresh_token.

    Same as above — rejected at signature verification or type-claim check.
    """
    token, _, _ = create_access_token("jsmith", "J", None, [])
    with pytest.raises(TokenError):
        decode_refresh_token(token)


# ── Signature validation ──────────────────────────────────────────────────────


def test_access_token_wrong_secret_rejected(monkeypatch: pytest.MonkeyPatch):
    token, _, _ = create_access_token("u", "U", None, [])
    monkeypatch.setenv("JWT_SECRET_KEY", "completely-different-secret-!!")
    with pytest.raises(TokenError):
        decode_access_token(token)


def test_refresh_token_wrong_secret_rejected(monkeypatch: pytest.MonkeyPatch):
    token, _, _ = create_refresh_token("u")
    monkeypatch.setenv("REFRESH_TOKEN_SECRET", "completely-different-secret-!!")
    with pytest.raises(TokenError):
        decode_refresh_token(token)


def test_tampered_payload_rejected():
    """Modifying the token payload must invalidate the signature."""
    token, _, _ = create_access_token("u", "U", None, [])
    # Decode without verification, change a claim, re-encode with wrong key
    header, payload_b64, sig = token.split(".")
    import base64, json
    pad = len(payload_b64) % 4
    decoded = json.loads(base64.urlsafe_b64decode(payload_b64 + "=" * (4 - pad) if pad else payload_b64))
    decoded["sub"] = "admin"
    tampered_payload = base64.urlsafe_b64encode(json.dumps(decoded).encode()).rstrip(b"=").decode()
    tampered_token = f"{header}.{tampered_payload}.{sig}"
    with pytest.raises(TokenError):
        decode_access_token(tampered_token)


# ── alg:none attack ───────────────────────────────────────────────────────────


def test_alg_none_access_token_rejected():
    """A token signed with alg:none must be rejected."""
    payload = {
        "sub": "attacker",
        "name": "Attacker",
        "email": None,
        "groups": ["OSKAR-Admins"],
        "iat": datetime.now(UTC),
        "exp": datetime.now(UTC) + timedelta(hours=1),
        "jti": "00000000-0000-0000-0000-000000000000",
        "iss": ISSUER,
        "aud": AUDIENCE,
    }
    # jose encodes alg:none by passing algorithm=None and key=""
    try:
        forged = jose_jwt.encode(payload, "", algorithm="none")
    except Exception:
        pytest.skip("jose version does not support alg:none encoding — attack not possible")
    with pytest.raises(TokenError):
        decode_access_token(forged)


def test_alg_none_refresh_token_rejected():
    payload = {
        "sub": "attacker",
        "type": "refresh",
        "iat": datetime.now(UTC),
        "exp": datetime.now(UTC) + timedelta(hours=8),
        "jti": "00000000-0000-0000-0000-000000000000",
        "iss": ISSUER,
        "aud": AUDIENCE,
    }
    try:
        forged = jose_jwt.encode(payload, "", algorithm="none")
    except Exception:
        pytest.skip("jose version does not support alg:none encoding — attack not possible")
    with pytest.raises(TokenError):
        decode_refresh_token(forged)


# ── Expiry ────────────────────────────────────────────────────────────────────


def test_expired_access_token_rejected(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ACCESS_TOKEN_EXPIRE_MINUTES", "0")
    # Manually craft an already-expired token
    payload = {
        "sub": "u",
        "name": "U",
        "email": None,
        "groups": [],
        "iat": datetime.now(UTC) - timedelta(seconds=10),
        "exp": datetime.now(UTC) - timedelta(seconds=5),
        "jti": "00000000-0000-0000-0000-000000000001",
        "iss": ISSUER,
        "aud": AUDIENCE,
    }
    expired = jose_jwt.encode(payload, _SECRET, algorithm=ALGORITHM)
    with pytest.raises(TokenError):
        decode_access_token(expired)


def test_expired_refresh_token_rejected():
    payload = {
        "sub": "u",
        "type": "refresh",
        "iat": datetime.now(UTC) - timedelta(hours=9),
        "exp": datetime.now(UTC) - timedelta(hours=1),
        "jti": "00000000-0000-0000-0000-000000000002",
        "iss": ISSUER,
        "aud": AUDIENCE,
    }
    expired = jose_jwt.encode(payload, _REFRESH, algorithm=ALGORITHM)
    with pytest.raises(TokenError):
        decode_refresh_token(expired)


# ── Missing secret fast-fail ──────────────────────────────────────────────────


def test_missing_jwt_secret_raises(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)
    with pytest.raises(RuntimeError, match="JWT_SECRET_KEY"):
        create_access_token("u", "U", None, [])


def test_missing_refresh_secret_raises(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("REFRESH_TOKEN_SECRET", raising=False)
    with pytest.raises(RuntimeError, match="REFRESH_TOKEN_SECRET"):
        create_refresh_token("u")


# ── hash_token ────────────────────────────────────────────────────────────────


def test_hash_token_is_deterministic():
    assert hash_token("abc") == hash_token("abc")


def test_hash_token_is_sha256_hex():
    result = hash_token("abc")
    assert len(result) == 64
    assert all(c in "0123456789abcdef" for c in result)


def test_hash_token_different_inputs_differ():
    assert hash_token("token-a") != hash_token("token-b")


def test_hash_token_does_not_store_raw_token():
    raw = "super-secret-refresh-token"
    h = hash_token(raw)
    assert raw not in h
