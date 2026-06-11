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

        Returns CN values of groups the user belongs to, e.g. ['OSKAR-Approvers'].
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
            return ldap3.Server(server_uri, use_ssl=False, get_info=ldap3.ALL)

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
                search_filter=f"(sAMAccountName={username})",
                attributes=["distinguishedName"],
            )
            if not conn.entries:
                return None
            return str(conn.entries[0].distinguishedName.value)  # type: ignore[attr-defined]
        except Exception:
            return None

    def authenticate(self, username: str, password: str) -> bool:
        """Bind to LDAPS with user credentials. Return True on success.

        Resolves the user's full DN via sAMAccountName search first, then binds.
        Required because users sit under site OUs (JohorBahru, Melbourne, Penang).
        """
        try:
            import ldap3  # type: ignore[import]

            user_dn = self._find_user_dn(username)
            if not user_dn:
                return False
            server = self._make_server(self.server_uri)
            conn = ldap3.Connection(server, user=user_dn, password=password)
            return conn.bind()
        except Exception:
            return False

    # OU containing all ECN application role groups (srxglobal-active-directory-groups-structure.md)
    _GROUP_SEARCH_BASE = "OU=Application Roles,OU=Groups,DC=srxglobal,DC=com"

    def get_groups(self, username: str) -> list[str]:
        """Return CN values of AD groups the user belongs to.

        Searches the user's memberOf attribute and returns only groups that live
        under OU=Application Roles,OU=Groups — ECN groups are ecn-initiator,
        ecn-approver, ecn-doc-controller (docs/srxglobal-active-directory-groups-structure.md).
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
                search_filter=f"(sAMAccountName={username})",
                attributes=["memberOf"],
            )
            if not conn.entries:
                return []
            member_of: list[str] = conn.entries[0].memberOf.values  # type: ignore[attr-defined]
            # Return CN of groups that live in the Application Roles OU only
            app_role_dn_suffix = self._GROUP_SEARCH_BASE.lower()
            return [
                dn.split(",")[0].replace("CN=", "")
                for dn in member_of
                if app_role_dn_suffix in dn.lower()
            ]
        except Exception:
            return []

    def get_email(self, username: str) -> str | None:
        """Return the email address from the LDAP mail attribute for the given username.

        Uses the service account bind (LDAP_BIND_DN / LDAP_BIND_PW) — same credentials
        as get_groups(). Looks up the 'mail' attribute by sAMAccountName.

        Returns None if the user is not found, has no mail attribute set in AD,
        or on any LDAP error. Callers must handle None — skip notification, don't raise.
        """
        try:
            import ldap3  # type: ignore[import]

            server = ldap3.Server(self.server_uri, get_info=ldap3.ALL)
            conn = ldap3.Connection(
                server,
                user=self.bind_dn,
                password=self.bind_pw,
                auto_bind=True,
            )
            conn.search(
                search_base=self.base_dn,
                search_filter=f"(sAMAccountName={username})",
                attributes=["mail"],
            )
            if not conn.entries:
                return None
            mail = conn.entries[0].mail.value  # type: ignore[attr-defined]
            return str(mail) if mail else None
        except Exception:
            return None


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
            "OSKAR-Engineers",
            "OSKAR-Approvers",
            "OSKAR-Admins",
            "OSKAR-DC",
        ]

    def get_email(self, username: str) -> str | None:
        return f"{username}@srxglobal.local"


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
