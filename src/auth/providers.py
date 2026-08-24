"""
OSKAR Authentication — IdentityProvider Protocol (PRE-3)

Two implementations:
- LDAPIdentityProvider: Production — on-prem AD via ldap3
- EntraIDProvider: Stub — Scanfil Group Entra ID push (future, post-v1)

OSKAR runs in Docker on Linux. Windows Negotiate (Kerberos/NTLM) is not available
inside Docker containers. LDAP bind to on-prem AD is the correct path.
Engineers authenticate with their Windows AD credentials via LDAP.

Domain: srxglobal.com  |  DC: srxdc01.srxglobal.com
Groups live under: OU=Application Roles,OU=Groups,DC=srxglobal,DC=com
ECN groups: ecn-initiator, ecn-approver, ecn-doc-controller
"""

from __future__ import annotations

import os
from typing import Protocol, runtime_checkable

import structlog

log = structlog.get_logger(__name__)


class LDAPDirectoryError(RuntimeError):
    """The directory could not be consulted — the answer is unknown, not empty.

    Raised when AD is unreachable, the service account cannot bind, the search
    is rejected, or a user's DN cannot be resolved. Callers must not treat this
    as "the user has no groups": that conflation is what makes a DC outage look
    to the user like a permissions problem, sending them to raise a ticket
    against AD while the real fault is infrastructure.

    A user who genuinely holds no Application Roles still returns [], and an
    absent mail attribute still returns None — those are real answers.
    """


@runtime_checkable
class IdentityProvider(Protocol):
    """Protocol defining the authentication interface for OSKAR.

    Any implementation must provide authenticate(), get_groups(), and get_email().
    Swap providers by changing the concrete class — no caller changes required.
    """

    def authenticate(self, username: str, password: str) -> bool:
        """Validate credentials. Return True if valid, False otherwise."""
        ...

    def get_groups(self, username: str) -> list[str]:
        """Return AD group memberships for the given username.

        Returns CN values of groups the user belongs to, e.g. ['ecn-approver'].
        Returns empty list on any error — callers treat that as no group membership.
        """
        ...

    def get_email(self, username: str) -> str | None:
        """Return the email address for the given username from the LDAP mail attribute.

        Used by notification dispatch (ai/memory/06-ecn-requirements.md §7).
        Returns None if the user has no mail attribute set or on any LDAP error.
        Callers must handle None gracefully — skip notification rather than raise.
        """
        ...


class LDAPIdentityProvider:
    """Production identity provider — on-prem Active Directory via ldap3.

    Configuration via environment variables:
        LDAP_SERVER   — e.g. ldaps://srxdc01.srxglobal.com:636
        LDAP_BASE_DN  — e.g. DC=srxglobal,DC=com
        LDAP_BIND_DN  — Service account DN for group lookups (svc-oskar-ldap)
        LDAP_BIND_PW  — Service account password
    """

    def __init__(self) -> None:
        self.server_uri = os.environ["LDAP_SERVER"]
        self.base_dn = os.environ["LDAP_BASE_DN"]
        self.bind_dn = os.getenv("LDAP_BIND_DN")
        self.bind_pw = os.getenv("LDAP_BIND_PW")

    @staticmethod
    def _make_server(server_uri: str):
        """Build an ldap3 Server.

        Production: LDAP_SERVER=ldaps://srxdc01.srxglobal.com:636, LDAP_USE_TLS=true (default)
        TLS: CERT_REQUIRED, CA cert from Docker secret /run/secrets/internal_ca.crt
             Falls back to system CA bundle when the secret file is absent (dev/CI).
        ADR-006 P0-1 — LDAPS mandatory; plain LDAP on 389 is a DISP Tier 1 finding.

        Staging override: LDAP_USE_TLS=false + LDAP_SERVER=ldap://... uses plain LDAP on 389.
        Remove once Manal enables LDAPS on the DC.
        """
        import os as _os
        import ssl

        import ldap3  # type: ignore[import]

        use_tls = _os.getenv("LDAP_USE_TLS", "true").lower() != "false"

        if not use_tls:
            return ldap3.Server(server_uri, use_ssl=False, get_info=ldap3.NONE)

        ca_file = "/run/secrets/internal_ca.crt"
        ca = ca_file if _os.path.exists(ca_file) else None

        tls = ldap3.Tls(
            validate=ssl.CERT_REQUIRED,
            version=ssl.PROTOCOL_TLS_CLIENT,
            ca_certs_file=ca,
        )
        return ldap3.Server(server_uri, use_ssl=True, tls=tls, get_info=ldap3.ALL)

    def _find_user_dn(self, username: str) -> str | None:
        """Look up the user's full DN via sAMAccountName using the service account.

        Users are distributed across site OUs (JohorBahru, Melbourne, Penang) under
        DC=srxglobal,DC=com — a flat CN={user},DC=... bind would fail for most accounts.

        Returns None when the directory answered and holds no such user.
        Raises LDAPDirectoryError when the directory could not be consulted.
        """
        try:
            import ldap3  # type: ignore[import]

            server = self._make_server(self.server_uri)
            conn = ldap3.Connection(
                server,
                user=self.bind_dn,
                password=self.bind_pw,
                auto_bind=True,
            )
            conn.search(
                search_base=self.base_dn,
                search_filter=f"(sAMAccountName={self._escape_filter_value(username)})",
                attributes=["distinguishedName"],
            )
        except Exception as exc:
            log.error("ldap.find_user_dn.failed", username=username, error=str(exc))
            raise LDAPDirectoryError(
                f"Directory lookup failed for {username!r}: {exc}"
            ) from exc

        if not conn.entries:
            return None
        return str(conn.entries[0].distinguishedName.value)  # type: ignore[attr-defined]

    def authenticate(self, username: str, password: str) -> bool:
        """Bind to LDAPS with user credentials. Return True on success.

        Resolves the user's full DN via sAMAccountName search first, then binds.
        Required because users sit under site OUs (JohorBahru, Melbourne, Penang).

        Returns False for a genuine credential failure — wrong password, or no
        such user. Raises LDAPDirectoryError when the directory itself could not
        be reached, so an outage is never reported to the user as bad credentials.
        """
        import ldap3  # type: ignore[import]

        user_dn = self._find_user_dn(username)  # raises LDAPDirectoryError
        if not user_dn:
            return False

        try:
            server = self._make_server(self.server_uri)
            conn = ldap3.Connection(server, user=user_dn, password=password)
            return bool(conn.bind())
        except Exception as exc:
            log.error("ldap.authenticate.failed", username=username, error=str(exc))
            raise LDAPDirectoryError(
                f"Directory bind failed for {username!r}: {exc}"
            ) from exc

    # OU containing all ECN application role groups (srxglobal-active-directory-groups-structure.md)
    _GROUP_SEARCH_BASE = "OU=Application Roles,OU=Groups,DC=srxglobal,DC=com"

    # AD extended match that walks the full nesting chain (LDAP_MATCHING_RULE_IN_CHAIN).
    # Required because Business Function groups are nested INTO the Application Role
    # groups — see the get_groups() docstring.
    _MATCHING_RULE_IN_CHAIN = "1.2.840.113556.1.4.1941"

    @staticmethod
    def _escape_filter_value(value: str) -> str:
        """Escape RFC 4515 filter metacharacters in a DN before interpolation."""
        for raw, escaped in (
            ("\\", "\\5c"),   # must be first — later escapes emit backslashes
            ("(", "\\28"),
            (")", "\\29"),
            ("*", "\\2a"),
            ("\0", "\\00"),
        ):
            value = value.replace(raw, escaped)
        return value

    def get_groups(self, username: str) -> list[str]:
        """Return CN values of the Application Role groups this user holds.

        Resolves membership through nesting. srxglobal.com nests Business Function
        groups (grp-eng-manager, grp-quality-manager, …) INTO the Application Role
        groups (ecn-initiator, ecn-approver), so a quality manager reaches
        ecn-approver via grp-quality-manager rather than by direct membership.

        Reading the user's own memberOf attribute would return direct membership
        only — such a user would come back with no roles and be locked out while
        AD looked correctly configured. Instead this searches the Application Roles
        OU for groups whose membership chain contains the user, using AD's
        LDAP_MATCHING_RULE_IN_CHAIN extended match.

        Direct membership still resolves — the chain matches it at depth zero —
        which is what ecn-doc-controller relies on (a process duty with no
        Business Function group above it).

        Searching from the Application Roles OU is also what confines the result
        to Oskar's own roles: grp-* groups live in Business Functions and are
        never returned as roles.

        A user who genuinely holds no Application Roles returns []. A directory
        that could not be consulted raises LDAPDirectoryError — the two must stay
        distinguishable, or an outage reaches the user as a permissions error.
        """
        import ldap3  # type: ignore[import]

        user_dn = self._find_user_dn(username)  # raises LDAPDirectoryError
        if not user_dn:
            raise LDAPDirectoryError(
                f"Cannot resolve a DN for {username!r} — group membership is unknown"
            )

        try:
            server = self._make_server(self.server_uri)
            conn = ldap3.Connection(
                server,
                user=self.bind_dn,
                password=self.bind_pw,
                auto_bind=True,
            )
            conn.search(
                search_base=self._GROUP_SEARCH_BASE,
                search_filter=(
                    f"(member:{self._MATCHING_RULE_IN_CHAIN}:="
                    f"{self._escape_filter_value(user_dn)})"
                ),
                attributes=["cn"],
            )
        except Exception as exc:
            log.error("ldap.get_groups.failed", username=username, error=str(exc))
            raise LDAPDirectoryError(
                f"Group lookup failed for {username!r}: {exc}"
            ) from exc

        return [str(entry.cn.value) for entry in conn.entries]

    def get_email(self, username: str) -> str | None:
        """Return the email address from the LDAP mail attribute for the given username.

        Uses the service account bind (LDAP_BIND_DN / LDAP_BIND_PW) — same credentials
        as get_groups(). Looks up the 'mail' attribute by sAMAccountName.

        Returns None when the directory answered and the user has no mail attribute
        (or does not exist) — callers skip the notification, which is correct.

        Raises LDAPDirectoryError when the directory could not be consulted.
        Notification callers should catch it and log, so an unreachable DC shows
        up as a warning rather than silently sending nothing.
        """
        try:
            import ldap3  # type: ignore[import]

            server = self._make_server(self.server_uri)
            conn = ldap3.Connection(
                server,
                user=self.bind_dn,
                password=self.bind_pw,
                auto_bind=True,
            )
            conn.search(
                search_base=self.base_dn,
                search_filter=f"(sAMAccountName={self._escape_filter_value(username)})",
                attributes=["mail"],
            )
        except Exception as exc:
            log.error("ldap.get_email.failed", username=username, error=str(exc))
            raise LDAPDirectoryError(
                f"Email lookup failed for {username!r}: {exc}"
            ) from exc

        if not conn.entries:
            return None
        mail = conn.entries[0].mail.value  # type: ignore[attr-defined]
        return str(mail) if mail else None

    def list_application_groups(self) -> list[dict]:
        """Return all groups under OU=Application Roles with their members.

        Each entry: { cn, distinguished_name, members: [{username, display_name, email}] }

        Members are resolved through nesting — a group's `member` attribute holds
        the DNs of nested Business Function groups as well as users, so listing
        only direct user members would show ecn-approver as empty once nesting is
        in place. Each role's effective membership is instead resolved with the
        same chain-walk get_groups() uses, which is what makes "who can approve?"
        answerable from one screen rather than by walking the tree in ADUC.

        Raises LDAPDirectoryError when the directory could not be consulted.
        """
        try:
            import ldap3  # type: ignore[import]

            server = self._make_server(self.server_uri)
            conn = ldap3.Connection(
                server,
                user=self.bind_dn,
                password=self.bind_pw,
                auto_bind=True,
            )
            conn.search(
                search_base=self._GROUP_SEARCH_BASE,
                search_filter="(objectClass=group)",
                attributes=["cn", "distinguishedName"],
            )
            role_groups = [
                (str(e.cn.value), str(e.distinguishedName.value)) for e in conn.entries
            ]

            groups = []
            for cn, dn in role_groups:
                # Effective members: every user whose membership chain reaches this
                # group, at any depth. Matches direct members at depth zero.
                conn.search(
                    search_base=self.base_dn,
                    search_filter=(
                        f"(&(objectClass=user)"
                        f"(memberOf:{self._MATCHING_RULE_IN_CHAIN}:="
                        f"{self._escape_filter_value(dn)}))"
                    ),
                    attributes=["sAMAccountName", "displayName", "mail"],
                )
                members = [
                    {
                        "username": str(u.sAMAccountName.value) if u.sAMAccountName else "",
                        "display_name": str(u.displayName.value) if u.displayName else None,
                        "email": str(u.mail.value) if u.mail else None,
                    }
                    for u in conn.entries
                ]
                groups.append({"cn": cn, "distinguished_name": dn, "members": members})

            return sorted(groups, key=lambda g: g["cn"])
        except Exception as exc:
            log.error("ldap.list_application_groups.failed", error=str(exc))
            raise LDAPDirectoryError(f"Group enumeration failed: {exc}") from exc


class EntraIDProvider:
    """Stub — Scanfil Group Entra ID provider (post-OSKAR v1).

    Activate when Scanfil Group pushes Entra ID to JB site.
    Until then, this raises NotImplementedError on all calls.
    """

    def authenticate(self, username: str, password: str) -> bool:
        raise NotImplementedError(
            "EntraIDProvider is not wired in OSKAR v1. "
            "Use LDAPIdentityProvider for on-prem AD authentication."
        )

    def get_groups(self, username: str) -> list[str]:
        raise NotImplementedError(
            "EntraIDProvider is not wired in OSKAR v1."
        )

    def get_email(self, _username: str) -> str | None:
        raise NotImplementedError(
            "EntraIDProvider is not wired in OSKAR v1."
        )


class DevIdentityProvider:
    """Dev-only identity provider — bypasses LDAP entirely.

    ONLY active when AUTH_PROVIDER=dev. Refuses to start if ENVIRONMENT is not
    'development' to prevent accidental use in staging or production.

    DEV_USERS env var: comma-separated list of allowed usernames (default: hsalazar).
    Any username in the allowlist authenticates with any non-empty password.
    Groups are returned as a fixed set covering all OSKAR roles for easy local testing.
    """

    def __init__(self) -> None:
        env = os.getenv("ENVIRONMENT", "development").lower()
        if env not in ("development", "dev"):
            raise RuntimeError(
                "AUTH_PROVIDER=dev is only permitted when ENVIRONMENT=development. "
                f"Current ENVIRONMENT={env!r}. Set AUTH_PROVIDER=ldap for staging/production."
            )
        raw = os.getenv("DEV_USERS", "hsalazar")
        self._allowed: set[str] = {u.strip().lower() for u in raw.split(",") if u.strip()}

    def authenticate(self, username: str, password: str) -> bool:
        return username.lower() in self._allowed and bool(password)

    def get_groups(self, username: str) -> list[str]:
        # Return all OSKAR groups so any dev user can exercise all workflow paths
        return [
            "ecn-initiator",
            "ecn-approver",
            "ecn-admin",
            "ecn-doc-controller",
        ]

    def get_email(self, username: str) -> str | None:
        return f"{username}@srxglobal.local"

    def list_application_groups(self) -> list[dict]:
        base = "OU=Application Roles,OU=Groups,DC=srxglobal,DC=com"
        dev_user = {
            "username": "hsalazar",
            "display_name": "Hector Salazar",
            "email": "hector.salazar@srxglobal.com",
        }
        return [
            {"cn": "ecn-admin",          "distinguished_name": f"CN=ecn-admin,{base}",          "members": [dev_user]},
            {"cn": "ecn-approver",        "distinguished_name": f"CN=ecn-approver,{base}",        "members": [dev_user]},
            {"cn": "ecn-doc-controller",  "distinguished_name": f"CN=ecn-doc-controller,{base}",  "members": [dev_user]},
            {"cn": "ecn-initiator",       "distinguished_name": f"CN=ecn-initiator,{base}",       "members": [dev_user]},
        ]


def get_identity_provider() -> IdentityProvider:
    """Factory — returns the configured provider based on AUTH_PROVIDER env var.

    AUTH_PROVIDER=ldap   → LDAPIdentityProvider (default, production)
    AUTH_PROVIDER=entra  → EntraIDProvider (stub, will raise)
    AUTH_PROVIDER=dev    → DevIdentityProvider (local dev only, no LDAP)
    """
    provider = os.getenv("AUTH_PROVIDER", "ldap").lower()
    if provider == "ldap":
        return LDAPIdentityProvider()
    if provider == "entra":
        return EntraIDProvider()
    if provider == "dev":
        return DevIdentityProvider()
    raise ValueError(f"Unknown AUTH_PROVIDER: {provider!r}. Valid values: ldap, entra, dev")
