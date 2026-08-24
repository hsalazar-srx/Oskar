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
    LDAPDirectoryError,
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
        assert "ecn-initiator" in groups
        assert "ecn-approver" in groups
        assert "ecn-admin" in groups
        assert "ecn-doc-controller" in groups

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

    def test_authenticate_returns_false_when_dn_not_found(self):
        p = self._make()
        with patch.object(p, "_find_user_dn", return_value=None):
            assert p.authenticate("user", "pw") is False

    def test_find_user_dn_raises_on_exception(self):
        p = self._make()
        with patch("ldap3.Connection", side_effect=Exception("network")):
            with pytest.raises(LDAPDirectoryError):
                p._find_user_dn("user")


# ---------------------------------------------------------------------------
# LDAPIdentityProvider.get_groups — nested group resolution
#
# Manal's AD model (2026-08-21): Business Function groups (grp-*) are nested
# INTO the Application Role groups (ecn-*). A user is a member of
# grp-quality-manager, which is itself a member of ecn-approver.
#
# The previous implementation read the user's own memberOf attribute, which
# returns DIRECT membership only — under nesting it returns nothing for such a
# user, locking them out while AD looks correctly configured.
#
# These tests pin the LDAP_MATCHING_RULE_IN_CHAIN behaviour that replaces it.
# ---------------------------------------------------------------------------

MATCHING_RULE_IN_CHAIN = "1.2.840.113556.1.4.1941"


class _FakeEntry:
    """Minimal stand-in for an ldap3 entry exposing .cn.value / .distinguishedName.value."""

    def __init__(self, cn: str = "", dn: str = ""):
        self.cn = MagicMock(value=cn)
        self.distinguishedName = MagicMock(value=dn)


class TestGetGroupsNestedResolution:
    """get_groups() must resolve membership through nested groups, not just direct."""

    def _make(self) -> LDAPIdentityProvider:
        with patch.dict(os.environ, {
            "LDAP_SERVER": "ldaps://test.local:636",
            "LDAP_BASE_DN": "DC=srxglobal,DC=com",
            "LDAP_BIND_DN": "CN=svc-oskar-ldap,DC=srxglobal,DC=com",
            "LDAP_BIND_PW": "pw",
        }):
            return LDAPIdentityProvider()

    def _patch_conn(self, provider, group_entries, user_dn="CN=u,OU=Melbourne,DC=srxglobal,DC=com"):
        """Patch ldap3 so the group search returns `group_entries`. Returns the mock conn."""
        conn = MagicMock()
        conn.entries = group_entries
        cm = patch.multiple(
            "ldap3",
            Server=MagicMock(),
            Connection=MagicMock(return_value=conn),
        )
        find_dn = patch.object(provider, "_find_user_dn", return_value=user_dn)
        return cm, find_dn, conn

    def test_resolves_group_the_user_reaches_only_via_nesting(self):
        """The core case: user is in grp-quality-manager, nested into ecn-approver.

        Direct memberOf would return only grp-quality-manager (which lives in
        Business Functions and is filtered out) — leaving the user with no roles.
        """
        p = self._make()
        entries = [_FakeEntry(
            "ecn-approver",
            "CN=ecn-approver,OU=Application Roles,OU=Groups,DC=srxglobal,DC=com",
        )]
        cm, find_dn, _ = self._patch_conn(p, entries)
        with cm, find_dn:
            assert p.get_groups("qmuser") == ["ecn-approver"]

    def test_uses_matching_rule_in_chain_filter(self):
        """The search filter must use the AD chain-walk OID against the user's DN."""
        p = self._make()
        user_dn = "CN=qmuser,OU=Melbourne,DC=srxglobal,DC=com"
        cm, find_dn, conn = self._patch_conn(p, [], user_dn=user_dn)
        with cm, find_dn:
            p.get_groups("qmuser")

        _, kwargs = conn.search.call_args
        assert MATCHING_RULE_IN_CHAIN in kwargs["search_filter"]
        assert user_dn in kwargs["search_filter"]

    def test_searches_only_the_application_roles_ou(self):
        """Business Function groups must never be returned as Oskar roles."""
        p = self._make()
        cm, find_dn, conn = self._patch_conn(p, [])
        with cm, find_dn:
            p.get_groups("qmuser")

        _, kwargs = conn.search.call_args
        assert kwargs["search_base"] == (
            "OU=Application Roles,OU=Groups,DC=srxglobal,DC=com"
        )

    def test_direct_membership_still_resolves(self):
        """ecn-doc-controller has no Business Function parent — users are added
        directly. The chain-walk matches those at depth zero."""
        p = self._make()
        entries = [
            _FakeEntry("ecn-doc-controller",
                       "CN=ecn-doc-controller,OU=Application Roles,OU=Groups,DC=srxglobal,DC=com"),
            _FakeEntry("ecn-approver",
                       "CN=ecn-approver,OU=Application Roles,OU=Groups,DC=srxglobal,DC=com"),
        ]
        cm, find_dn, _ = self._patch_conn(p, entries)
        with cm, find_dn:
            assert set(p.get_groups("dcuser")) == {"ecn-doc-controller", "ecn-approver"}

    def test_user_with_no_application_roles_returns_empty(self):
        p = self._make()
        cm, find_dn, _ = self._patch_conn(p, [])
        with cm, find_dn:
            assert p.get_groups("nobody") == []

    def test_unresolvable_user_raises_without_searching(self):
        """No DN means no chain-walk is possible — don't search with a blank DN,
        and don't report the user as simply having no roles."""
        p = self._make()
        conn = MagicMock()
        with patch.multiple("ldap3", Server=MagicMock(), Connection=MagicMock(return_value=conn)):
            with patch.object(p, "_find_user_dn", return_value=None):
                with pytest.raises(LDAPDirectoryError):
                    p.get_groups("ghost")
        conn.search.assert_not_called()

    def test_dn_special_characters_are_escaped_in_the_filter(self):
        """A DN containing filter metacharacters must not break or inject."""
        p = self._make()
        user_dn = r"CN=O\'Brien (Eng),OU=Melbourne,DC=srxglobal,DC=com"
        cm, find_dn, conn = self._patch_conn(p, [], user_dn=user_dn)
        with cm, find_dn:
            p.get_groups("obrien")

        _, kwargs = conn.search.call_args
        f = kwargs["search_filter"]
        assert r"\28Eng\29" in f                         # ( and ) escaped
        assert f.count("(") == 1 and f.count(")") == 1   # only the filter's own parens

    def test_raises_on_ldap_error(self):
        p = self._make()
        with patch("ldap3.Server", side_effect=Exception("ldap down")):
            with patch.object(p, "_find_user_dn", return_value="CN=u,DC=x,DC=y"):
                with pytest.raises(LDAPDirectoryError):
                    p.get_groups("user")


# ---------------------------------------------------------------------------
# LDAPDirectoryError — infrastructure failure must not look like "no groups"
#
# Every LDAP method used to swallow exceptions and return an empty result. That
# made a DC outage, an expired service-account password, or a filter AD rejects
# indistinguishable from "this user legitimately has no roles" — the user got a
# clean 403 and filed a permissions ticket while the real fault was the DC.
#
# Nesting makes this materially worse: there are now more ways to fail
# (chain-walk unsupported, Application Roles OU renamed or unreadable by the
# service account) that all present as an empty group list.
#
# Directory faults now raise LDAPDirectoryError. "Genuinely no groups" stays [].
# ---------------------------------------------------------------------------

class TestLDAPDirectoryErrorSeparatesFailureFromEmpty:

    def _make(self) -> LDAPIdentityProvider:
        with patch.dict(os.environ, {
            "LDAP_SERVER": "ldaps://test.local:636",
            "LDAP_BASE_DN": "DC=srxglobal,DC=com",
            "LDAP_BIND_DN": "CN=svc-oskar-ldap,DC=srxglobal,DC=com",
            "LDAP_BIND_PW": "pw",
        }):
            return LDAPIdentityProvider()

    def test_get_groups_raises_when_directory_unreachable(self):
        p = self._make()
        with patch("ldap3.Server", side_effect=Exception("connection refused")):
            with patch.object(p, "_find_user_dn", return_value="CN=u,DC=srxglobal,DC=com"):
                with pytest.raises(LDAPDirectoryError):
                    p.get_groups("qmuser")

    def test_get_groups_returns_empty_for_a_user_with_no_roles(self):
        """The legitimate empty case must stay empty — not raise."""
        p = self._make()
        conn = MagicMock()
        conn.entries = []
        with patch.multiple("ldap3", Server=MagicMock(), Connection=MagicMock(return_value=conn)):
            with patch.object(p, "_find_user_dn", return_value="CN=u,DC=srxglobal,DC=com"):
                assert p.get_groups("nobody") == []

    def test_get_groups_raises_when_user_dn_cannot_be_resolved(self):
        """_find_user_dn returning None is ambiguous — it means either 'no such
        user' or 'the lookup itself failed'. Treat it as a directory fault rather
        than silently granting the user zero roles."""
        p = self._make()
        with patch.object(p, "_find_user_dn", return_value=None):
            with pytest.raises(LDAPDirectoryError):
                p.get_groups("ghost")

    def test_get_email_raises_when_directory_unreachable(self):
        p = self._make()
        with patch("ldap3.Server", side_effect=Exception("ldap down")):
            with pytest.raises(LDAPDirectoryError):
                p.get_email("qmuser")

    def test_get_email_returns_none_when_mail_attribute_is_unset(self):
        """An absent mail attribute is a real answer, not a failure."""
        p = self._make()
        entry = MagicMock()
        entry.mail = MagicMock(value=None)
        conn = MagicMock()
        conn.entries = [entry]
        with patch.multiple("ldap3", Server=MagicMock(), Connection=MagicMock(return_value=conn)):
            assert p.get_email("qmuser") is None

    def test_authenticate_still_returns_false_on_bad_credentials(self):
        """authenticate() keeps its boolean contract — a failed bind is a normal
        answer, not an outage."""
        p = self._make()
        conn = MagicMock()
        conn.bind = MagicMock(return_value=False)
        with patch.multiple("ldap3", Server=MagicMock(), Connection=MagicMock(return_value=conn)):
            with patch.object(p, "_find_user_dn", return_value="CN=u,DC=srxglobal,DC=com"):
                assert p.authenticate("qmuser", "wrongpw") is False

    def test_authenticate_raises_when_dn_lookup_fails(self):
        """A DC outage during DN resolution must propagate, not become False."""
        p = self._make()
        with patch.object(
            p, "_find_user_dn", side_effect=LDAPDirectoryError("connection refused")
        ):
            with pytest.raises(LDAPDirectoryError):
                p.authenticate("qmuser", "pw")

    def test_authenticate_raises_when_bind_itself_fails(self):
        """A DC outage must not be reported to the user as 'invalid credentials'."""
        p = self._make()
        with patch.object(p, "_find_user_dn", return_value="CN=u,DC=srxglobal,DC=com"):
            with patch("ldap3.Server", side_effect=Exception("connection refused")):
                with pytest.raises(LDAPDirectoryError):
                    p.authenticate("qmuser", "pw")

    def test_list_application_groups_raises_when_directory_unreachable(self):
        p = self._make()
        with patch("ldap3.Server", side_effect=Exception("ldap down")):
            with pytest.raises(LDAPDirectoryError):
                p.list_application_groups()
