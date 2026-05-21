"""
Unit tests for src/auth/providers.py

Covers:
  - DevIdentityProvider: authenticate, get_groups, get_email, constructor guard
  - EntraIDProvider: raises NotImplementedError on all methods
  - get_identity_provider() factory: all three branches + unknown raises
  - LDAPIdentityProvider: exception-path returns (no live LDAP needed)

All tests are pure-unit — no DB, no LDAP, no network.
"""
from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from src.auth.providers import (
    DevIdentityProvider,
    EntraIDProvider,
    LDAPIdentityProvider,
    get_identity_provider,
)


# ---------------------------------------------------------------------------
# DevIdentityProvider
# ---------------------------------------------------------------------------

class TestDevIdentityProvider:

    def _make(self, users: str = "hsalazar,testuser") -> DevIdentityProvider:
        with patch.dict(os.environ, {"ENVIRONMENT": "development", "DEV_USERS": users}):
            return DevIdentityProvider()

    def test_authenticate_valid_user_returns_true(self):
        p = self._make()
        assert p.authenticate("hsalazar", "anypassword") is True

    def test_authenticate_case_insensitive(self):
        p = self._make()
        assert p.authenticate("HSALAZAR", "pw") is True

    def test_authenticate_empty_password_returns_false(self):
        p = self._make()
        assert p.authenticate("hsalazar", "") is False

    def test_authenticate_unknown_user_returns_false(self):
        p = self._make()
        assert p.authenticate("unknown_person", "pw") is False

    def test_get_groups_returns_all_oskar_groups(self):
        p = self._make()
        groups = p.get_groups("hsalazar")
        assert "OSKAR-Engineers" in groups
        assert "OSKAR-Approvers" in groups
        assert "OSKAR-Admins" in groups
        assert "OSKAR-DC" in groups

    def test_get_email_returns_local_address(self):
        p = self._make()
        assert p.get_email("hsalazar") == "hsalazar@srxglobal.local"

    def test_constructor_raises_outside_development(self):
        with patch.dict(os.environ, {"ENVIRONMENT": "production"}):
            with pytest.raises(RuntimeError, match="AUTH_PROVIDER=dev is only permitted"):
                DevIdentityProvider()

    def test_constructor_allows_dev_alias(self):
        with patch.dict(os.environ, {"ENVIRONMENT": "dev", "DEV_USERS": "hsalazar"}):
            p = DevIdentityProvider()
            assert p.authenticate("hsalazar", "pw") is True

    def test_default_user_is_hsalazar(self):
        env = {"ENVIRONMENT": "development"}
        env.pop("DEV_USERS", None)
        with patch.dict(os.environ, env, clear=False):
            os.environ.pop("DEV_USERS", None)
            p = DevIdentityProvider()
        assert p.authenticate("hsalazar", "pw") is True


# ---------------------------------------------------------------------------
# EntraIDProvider
# ---------------------------------------------------------------------------

class TestEntraIDProvider:

    def test_authenticate_raises(self):
        p = EntraIDProvider()
        with pytest.raises(NotImplementedError):
            p.authenticate("user", "pw")

    def test_get_groups_raises(self):
        p = EntraIDProvider()
        with pytest.raises(NotImplementedError):
            p.get_groups("user")

    def test_get_email_raises(self):
        p = EntraIDProvider()
        with pytest.raises(NotImplementedError):
            p.get_email("user")


# ---------------------------------------------------------------------------
# get_identity_provider factory
# ---------------------------------------------------------------------------

class TestGetIdentityProviderFactory:

    def test_dev_provider_returned_for_dev(self):
        with patch.dict(os.environ, {"AUTH_PROVIDER": "dev", "ENVIRONMENT": "development", "DEV_USERS": "x"}):
            p = get_identity_provider()
        assert isinstance(p, DevIdentityProvider)

    def test_entra_provider_returned_for_entra(self):
        with patch.dict(os.environ, {"AUTH_PROVIDER": "entra"}):
            p = get_identity_provider()
        assert isinstance(p, EntraIDProvider)

    def test_unknown_provider_raises(self):
        with patch.dict(os.environ, {"AUTH_PROVIDER": "magic"}):
            with pytest.raises(ValueError, match="Unknown AUTH_PROVIDER"):
                get_identity_provider()

    def test_ldap_provider_construction_raises_without_env(self):
        env = {"AUTH_PROVIDER": "ldap"}
        with patch.dict(os.environ, env):
            os.environ.pop("LDAP_SERVER", None)
            with pytest.raises(KeyError):
                get_identity_provider()


# ---------------------------------------------------------------------------
# LDAPIdentityProvider — exception paths (no live LDAP)
# ---------------------------------------------------------------------------

class TestLDAPIdentityProviderExceptionPaths:

    def _make(self) -> LDAPIdentityProvider:
        with patch.dict(os.environ, {
            "LDAP_SERVER": "ldaps://test.local:636",
            "LDAP_BASE_DN": "DC=test,DC=local",
            "LDAP_BIND_DN": "CN=svc,DC=test,DC=local",
            "LDAP_BIND_PW": "pw",
        }):
            return LDAPIdentityProvider()

    def test_authenticate_returns_false_on_exception(self):
        p = self._make()
        with patch.object(p, "_find_user_dn", side_effect=Exception("connection refused")):
            assert p.authenticate("user", "pw") is False

    def test_authenticate_returns_false_when_dn_not_found(self):
        p = self._make()
        with patch.object(p, "_find_user_dn", return_value=None):
            assert p.authenticate("user", "pw") is False

    def test_get_groups_returns_empty_on_exception(self):
        p = self._make()
        with patch("ldap3.Connection", side_effect=Exception("ldap down")):
            assert p.get_groups("user") == []

    def test_get_email_returns_none_on_exception(self):
        p = self._make()
        with patch("ldap3.Server", side_effect=Exception("ldap down")):
            assert p.get_email("user") is None

    def test_find_user_dn_returns_none_on_exception(self):
        p = self._make()
        with patch("ldap3.Connection", side_effect=Exception("network")):
            result = p._find_user_dn("user")
        assert result is None
