"""
Router-level handling of LDAPDirectoryError (src/auth/providers.py).

A directory fault means Oskar does not KNOW the user's groups — it does not mean
the user has none. Surfacing it as 401/403 sends a user to raise a permissions
ticket against AD while the real fault is the DC being unreachable, which is the
exact "silence looks like success" trap that docs/robustness-plan-uat-readiness.md
exists to close.

These tests pin the contract: a directory fault is 503, never 401/403/500.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.auth.dependencies import CurrentUser, get_current_user
from src.auth.providers import LDAPDirectoryError, LDAPIdentityProvider
from src.db import get_session
from src.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _override_session():
    app.dependency_overrides[get_session] = lambda: AsyncMock()
    yield
    app.dependency_overrides.clear()


def _provider(**kwargs) -> MagicMock:
    """A provider mock whose named methods raise LDAPDirectoryError."""
    p = MagicMock()
    for name, exc in kwargs.items():
        getattr(p, name).side_effect = exc
    return p


class TestLoginSurfacesDirectoryFaultAs503:

    def test_unreachable_directory_is_503_not_401(self, client: TestClient):
        """The critical case: an outage must not read as 'wrong password'."""
        p = _provider(authenticate=LDAPDirectoryError("connection refused"))
        with patch("src.routers.auth.get_identity_provider", return_value=p):
            r = client.post("/api/v1/auth/login", json={"username": "u", "password": "p"})
        assert r.status_code == 503

    def test_bad_credentials_still_401(self, client: TestClient):
        """The normal failure must keep its existing meaning."""
        p = MagicMock()
        p.authenticate.return_value = False
        with patch("src.routers.auth.get_identity_provider", return_value=p):
            r = client.post("/api/v1/auth/login", json={"username": "u", "password": "bad"})
        assert r.status_code == 401

    def test_group_lookup_failure_after_valid_bind_is_503(self, client: TestClient):
        """Credentials were fine but roles are unknown — issuing a token with an
        empty groups claim would silently strip the user's permissions."""
        p = MagicMock()
        p.authenticate.return_value = True
        p.get_groups.side_effect = LDAPDirectoryError("chain-walk rejected")
        with patch("src.routers.auth.get_identity_provider", return_value=p):
            r = client.post("/api/v1/auth/login", json={"username": "u", "password": "p"})
        assert r.status_code == 503

    def test_503_body_does_not_leak_directory_internals(self, client: TestClient):
        """DNs, server URIs and bind errors must not reach an unauthenticated caller."""
        p = _provider(authenticate=LDAPDirectoryError(
            "bind failed for CN=svc-oskar-ldap,DC=srxglobal,DC=com at ldaps://srxdc01:636"
        ))
        with patch("src.routers.auth.get_identity_provider", return_value=p):
            r = client.post("/api/v1/auth/login", json={"username": "u", "password": "p"})
        body = r.text.lower()
        assert "svc-oskar-ldap" not in body
        assert "srxdc01" not in body
        assert "dc=srxglobal" not in body


class TestAdminGroupListingSurfacesDirectoryFault:

    def test_group_enumeration_failure_is_503_not_empty_list(self, client: TestClient):
        """An empty list here reads as 'nobody is in any role', which for a DC
        checking who can approve is actively misleading."""
        app.dependency_overrides[get_current_user] = lambda: CurrentUser(
            username="dc", display_name="DC", email=None,
            groups=["ecn-doc-controller"], jti="j",
        )
        # Must be a real LDAPIdentityProvider — the router isinstance-checks the
        # provider before enumerating, so a bare MagicMock takes the "unsupported
        # provider" branch and returns [] without ever calling the method.
        p = MagicMock(spec=LDAPIdentityProvider)
        p.list_application_groups.side_effect = LDAPDirectoryError("ldap down")
        with patch("src.routers.admin.get_identity_provider", return_value=p):
            r = client.get("/api/v1/admin/ldap-groups")
        assert r.status_code == 503
