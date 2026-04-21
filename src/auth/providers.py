"""
OSKAR Authentication — IdentityProvider Protocol (PRE-3)

Two implementations:
- LDAPIdentityProvider: Production — on-prem AD via ldap3
- EntraIDProvider: Stub — Scanfil Group Entra ID push (future, post-v1)

OSKAR runs in Docker on Linux. Windows Negotiate (Kerberos/NTLM) is not available
inside Docker containers. LDAP bind to on-prem AD is the correct path.
Engineers authenticate with their Windows AD credentials via LDAP.
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
        LDAP_SERVER   — e.g. ldap://srxdc01.srxglobal.local
        LDAP_BASE_DN  — e.g. DC=srxglobal,DC=local
        LDAP_BIND_DN  — Service account for group lookups (optional)
        LDAP_BIND_PW  — Service account password (optional)
    """

    def __init__(self) -> None:
        self.server_uri = os.environ["LDAP_SERVER"]
        self.base_dn = os.environ["LDAP_BASE_DN"]
        self.bind_dn = os.getenv("LDAP_BIND_DN")
        self.bind_pw = os.getenv("LDAP_BIND_PW")

    @staticmethod
    def _make_server(server_uri: str):
        """Build a TLS-hardened ldap3 Server.

        Production: LDAP_SERVER=ldaps://srxdc01.srxglobal.local:636
        TLS: CERT_REQUIRED, CA cert from Docker secret /run/secrets/internal_ca.crt
             Falls back to system CA bundle when the secret file is absent (dev/CI).
        ADR-006 P0-1 — LDAPS mandatory; plain LDAP on 389 is a DISP Tier 1 finding.
        """
        import ssl

        import ldap3  # type: ignore[import]

        ca_file = "/run/secrets/internal_ca.crt"
        import os as _os
        ca = ca_file if _os.path.exists(ca_file) else None

        tls = ldap3.Tls(
            validate=ssl.CERT_REQUIRED,
            version=ssl.PROTOCOL_TLS_CLIENT,
            ca_certs_file=ca,
        )
        return ldap3.Server(server_uri, use_ssl=True, tls=tls, get_info=ldap3.ALL)

    def authenticate(self, username: str, password: str) -> bool:
        """Bind to LDAPS with user credentials. Return True on success."""
        try:
            import ldap3  # type: ignore[import]

            server = self._make_server(self.server_uri)
            user_dn = f"CN={username},{self.base_dn}"
            conn = ldap3.Connection(server, user=user_dn, password=password)
            return conn.bind()
        except Exception:
            return False

    def get_groups(self, username: str) -> list[str]:
        """Return CN values of AD groups the user belongs to."""
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
            # Extract CN= from each DN, e.g. "CN=OSKAR-Engineers,OU=Groups,DC=..."
            return [dn.split(",")[0].replace("CN=", "") for dn in member_of]
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


def get_identity_provider() -> IdentityProvider:
    """Factory — returns the configured provider based on AUTH_PROVIDER env var.

    AUTH_PROVIDER=ldap   → LDAPIdentityProvider (default, production)
    AUTH_PROVIDER=entra  → EntraIDProvider (stub, will raise)
    """
    provider = os.getenv("AUTH_PROVIDER", "ldap").lower()
    if provider == "ldap":
        return LDAPIdentityProvider()
    if provider == "entra":
        return EntraIDProvider()
    raise ValueError(f"Unknown AUTH_PROVIDER: {provider!r}. Valid values: ldap, entra")
