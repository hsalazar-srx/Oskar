#!/usr/bin/env python3
"""
Verify Oskar's AD integration against the REAL directory.

Every LDAP test in the suite mocks ldap3. They prove the filter is built
correctly and the response is parsed correctly; they cannot prove that AD
accepts that filter, that the service account can read the Application Roles
OU, or that nested membership resolves. Only this script can.

That gap is not hypothetical. srxglobal.com nests Business Function groups
(grp-*) INTO the Application Role groups (ecn-*), so a quality manager reaches
ecn-approver via grp-quality-manager rather than directly. Oskar previously read
the user's own memberOf attribute, which returns direct membership only — such a
user came back with NO roles and was locked out while AD looked correctly
configured. The chain-walk (LDAP_MATCHING_RULE_IN_CHAIN) fixes that, and this
script is what proves the fix works against the real DC.

Usage
-----
    python scripts/ldap_verify.py                     # all checks
    python scripts/ldap_verify.py --user ecn_appr_d   # one specific user

Environment (same variables the app uses — see .env.example):
    LDAP_SERVER, LDAP_PORT, LDAP_BASE_DN, LDAP_BIND_DN, LDAP_BIND_PW
    LDAP_USE_TLS=false     for plain LDAP on 389 during the test window

    LDAP_VERIFY_NESTED_USER   a user whose ECN role comes ONLY via nesting
    LDAP_VERIFY_DIRECT_USER   a user added directly (e.g. an ecn-doc-controller)

Exit codes
----------
    0  every check passed
    1  a check failed — a real problem
    2  refused to run (missing configuration) — nothing was verified
"""
from __future__ import annotations

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

APP_ROLE_PREFIX = "ecn-"
BUSINESS_FN_PREFIX = "grp-"

_passed = 0
_failed = 0


def _ok(label: str, detail: str = "") -> None:
    global _passed
    _passed += 1
    print(f"  [PASS] {label}" + (f" — {detail}" if detail else ""))


def _fail(label: str, detail: str) -> None:
    global _failed
    _failed += 1
    print(f"  [FAIL] {label} — {detail}")


def _refuse(reason: str) -> int:
    print(f"\n  REFUSED — {reason}")
    print("  Nothing was verified. This is not a pass.\n")
    return 2


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user", help="verify group resolution for one username")
    args = parser.parse_args()

    required = ["LDAP_SERVER", "LDAP_BASE_DN", "LDAP_BIND_DN", "LDAP_BIND_PW"]
    missing = [v for v in required if not os.environ.get(v)]
    if missing:
        return _refuse(f"missing environment: {', '.join(missing)}")

    from src.auth.providers import LDAPDirectoryError, LDAPIdentityProvider

    server = os.environ["LDAP_SERVER"]
    tls = os.getenv("LDAP_USE_TLS", "true").lower() != "false"
    print("\n" + "=" * 72)
    print("  Oskar — live Active Directory verification")
    print("=" * 72)
    print(f"  server   : {server}  ({'LDAPS' if tls else 'PLAIN LDAP — pre-go-live only'})")
    print(f"  base DN  : {os.environ['LDAP_BASE_DN']}")
    print(f"  bind DN  : {os.environ['LDAP_BIND_DN']}")
    print()

    if not tls:
        print("  NOTE: LDAP_USE_TLS=false — credentials cross the network in the")
        print("        clear. Acceptable for the test window only; ADR-006 requires")
        print("        LDAPS on 636 before go-live.\n")

    provider = LDAPIdentityProvider()
    started = time.time()

    # --- 1. Service account can bind and read -----------------------------
    print("  1. Service account")
    probe = args.user or os.getenv("LDAP_VERIFY_DIRECT_USER") or ""
    if not probe:
        return _refuse("set --user, LDAP_VERIFY_DIRECT_USER or LDAP_VERIFY_NESTED_USER")
    try:
        dn = provider._find_user_dn(probe)
        if dn:
            _ok("bind + user search", f"resolved {probe} → {dn}")
        else:
            _fail("bind + user search",
                  f"bound OK but no user named {probe!r} exists — check the username")
            return _report(started)
    except LDAPDirectoryError as exc:
        _fail("bind + user search", str(exc))
        return _report(started)

    # --- 2. Group resolution ---------------------------------------------
    print("\n  2. Group resolution (chain-walk)")
    targets = [
        ("nested", os.getenv("LDAP_VERIFY_NESTED_USER")),
        ("direct", os.getenv("LDAP_VERIFY_DIRECT_USER")),
    ]
    if args.user:
        targets = [("specified", args.user)]

    for kind, username in targets:
        if not username:
            print(f"  [SKIP] {kind}-membership user not configured — UNVERIFIED")
            continue
        try:
            groups = provider.get_groups(username)
        except LDAPDirectoryError as exc:
            _fail(f"{kind} membership ({username})", str(exc))
            continue

        if not groups:
            _fail(
                f"{kind} membership ({username})",
                "resolved to NO roles. If this user should hold one, the chain-walk "
                "is not matching — check the Application Roles OU path and that the "
                "service account can read it",
            )
            continue

        leaked = [g for g in groups if g.startswith(BUSINESS_FN_PREFIX)]
        if leaked:
            _fail(f"{kind} membership ({username})",
                  f"Business Function groups leaked into roles: {leaked}")
            continue

        non_ecn = [g for g in groups if not g.startswith(APP_ROLE_PREFIX)]
        if non_ecn:
            print(f"  [WARN] {username} holds non-ECN application roles: {non_ecn}")

        _ok(f"{kind} membership ({username})", f"roles: {sorted(groups)}")

    # --- 3. Email attribute ----------------------------------------------
    print("\n  3. Email attribute")
    for _, username in targets:
        if not username:
            continue
        try:
            email = provider.get_email(username)
        except LDAPDirectoryError as exc:
            _fail(f"mail ({username})", str(exc))
            continue
        if email:
            _ok(f"mail ({username})", email)
        else:
            _fail(
                f"mail ({username})",
                "mail attribute is EMPTY — Oskar skips notifications for this user "
                "silently. Ask for it to be populated (any value; test mail is caught "
                "locally)",
            )

    # --- 4. Role enumeration for the admin view ---------------------------
    print("\n  4. Application Roles enumeration")
    try:
        groups = provider.list_application_groups()
    except LDAPDirectoryError as exc:
        _fail("enumerate Application Roles", str(exc))
        return _report(started)

    ecn_groups = [g for g in groups if g["cn"].startswith(APP_ROLE_PREFIX)]
    if not ecn_groups:
        _fail("enumerate Application Roles",
              f"found {len(groups)} groups but none named {APP_ROLE_PREFIX}* — "
              "wrong OU, or the service account cannot read it")
    else:
        _ok("enumerate Application Roles",
            f"{len(ecn_groups)} ECN groups: "
            + ", ".join(f"{g['cn']}({len(g['members'])})" for g in sorted(
                ecn_groups, key=lambda g: g["cn"])))
        for g in ecn_groups:
            if not g["members"]:
                print(f"  [WARN] {g['cn']} has no effective members — "
                      "nobody can action that role")

    return _report(started)


def _report(started: float) -> int:
    elapsed = time.time() - started
    print("\n" + "-" * 72)
    if _failed:
        print(f"  NOT READY — {_failed} failed, {_passed} passed  ({elapsed:.1f}s)")
        print("-" * 72 + "\n")
        return 1
    print(f"  READY — {_passed} checks passed  ({elapsed:.1f}s)")
    print("-" * 72 + "\n")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\ninterrupted")
        sys.exit(1)
