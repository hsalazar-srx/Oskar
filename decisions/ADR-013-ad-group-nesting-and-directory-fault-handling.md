# ADR-013 — AD Group Nesting, Chain-Walk Resolution, and Directory-Fault Handling

**Status:** Accepted
**Date:** 2026-08-21
**Owner:** Lead Engineer
**Reviewed by:** Manal (IT / AD owner) — group model; Lead Engineer — implementation
**Type:** Architectural — authentication and authorisation (amends ADR-003, ADR-006)

---

## Context

`srxglobal.com` carries two group tiers, both created for this programme and
already anticipating MES and Purchasing as further tenants:

- **`OU=Business Functions`** — `grp-eng-manager`, `grp-quality-manager`,
  `grp-fin-manager`, `grp-eng-product`, `grp-exec-md`, `grp-fin-ap`,
  `grp-fin-ar`, `grp-quality-member`. Org-shaped.
- **`OU=Application Roles`** — `ecn-*`, `mes-*`, `pur-*`. App-shaped.

Oskar reads only the three `ecn-*` groups. ADR-003's split holds: AD answers the
coarse question (*can this person log in and approve at all?*), and
`system_role_users` answers the fine, facility-aware one (*is this person the QM
for Melbourne?*). Three groups therefore serve all 13 ECN roles, and no AD group
is or should be facility-scoped.

Two questions had to be settled before UAT could run against real AD:

1. Do users go into the `ecn-*` groups directly, or do Business Function groups
   nest into them?
2. What happens when the directory cannot be reached at all?

The Lead Engineer's initial position on (1) was direct membership — at ~50 users
and one tenant application, nesting `grp-quality-manager` into `ecn-approver`
produces two groups holding identical people, and the indirection buys nothing
until a second application reads the same Business Function group. **Manal's
counter-position prevailed:** establishing the convention with the first tenant
is how it sticks; retrofitting it across three applications later makes the first
two permanent exceptions.

Question (2) surfaced while reading the auth path for (1). Every method in
`LDAPIdentityProvider` ended `except Exception: return []` / `return None`,
making a DC outage, an expired service-account password, or a rejected search
indistinguishable from "this user has no roles" — the same
silence-looks-like-success shape as I2-19 and I2-21
(`docs/robustness-plan-uat-readiness.md`). Nesting makes it materially worse: it
adds failure modes (chain-walk unsupported, Application Roles OU unreadable by
the service account) that all present as an empty group list.

---

## Decisions

**1. Business Function groups nest into `ecn-initiator` and `ecn-approver`.**
ECN access follows normal onboarding — a new quality manager gains approval
rights as part of joining `grp-quality-manager`, and loses them the same way.
The specific mapping is Manal's to set; Oskar reads whatever the Application
Roles OU contains and does not hard-code any Business Function group name.

**2. `ecn-doc-controller` takes users directly.** Document Controller is a duty
within the ECN process, not an org function. A `grp-doc-control` group would
exist solely to feed this one role, with membership identical to it — a wrapper
carrying no information. The general rule: **nest when the Business Function
group would exist anyway; add directly when it would not.**

**3. Group resolution walks the nesting chain.** `get_groups()` no longer reads
the user's `memberOf` attribute — that returns *direct* membership only, so a
nested user resolved to no roles and was locked out while AD looked correctly
configured. It now searches the Application Roles OU with AD's
`LDAP_MATCHING_RULE_IN_CHAIN` extended match
(`(member:1.2.840.113556.1.4.1941:={user_dn})`). Direct membership still
resolves — the chain matches it at depth zero — which is what decision 2 relies
on. Searching *from* that OU is also what keeps `grp-*` groups out of the JWT
groups claim.

**4. A directory fault is distinguishable from an empty result.**
`LDAPDirectoryError` is raised when the directory cannot be consulted. "This
user genuinely holds no roles" still returns `[]`, and an unset `mail` attribute
still returns `None` — those are real answers. Routers map the error to **503**,
never 401/403:

| Situation | Response |
|---|---|
| DC unreachable at login | 503 — *not* 401 "invalid credentials" |
| Group lookup fails after a valid bind | 503 — login refused rather than issuing a token with an empty groups claim, which would silently strip the user's permissions for the life of the token |
| Admin group listing, directory down | 503 — an empty list reads as "nobody holds any role" |
| Genuinely no roles / unset `mail` | unchanged |

The 503 body is deliberately generic; DNs, server URIs and bind errors go to the
log, never to an unauthenticated caller.

Notification dispatch is the one place that still degrades rather than failing —
one unreachable lookup must not abort an escalation run for every other
recipient — but each failure is now logged at ERROR with its consequence, rather
than vanishing.

**5. The boundary is verified against the real DC, not a mock.**
`scripts/ldap_verify.py` (preflight check #5) proves what mocked tests
structurally cannot: that AD accepts the chain-walk filter, that the service
account can read the Application Roles OU, that **nested** membership resolves,
that direct membership still resolves, that no `grp-*` group leaks into the
roles claim, and that `mail` is populated. It warns on any ECN role with no
effective members.

This requires test accounts whose ECN access comes *only* through nesting
(`LDAP_VERIFY_NESTED_USER`) and one added directly
(`LDAP_VERIFY_DIRECT_USER`). Without both, the check reports SKIP → INCOMPLETE
and exits non-zero: a boundary that was not checked is never reported as
working.

---

## Consequences

**Positive**

- Oskar access is granted and revoked by normal joiner/leaver process rather
  than a per-user ticket — which matters most for the DC gate, where a departed
  approver stalls every ECN behind them.
- The convention is established with the first tenant, so MES and Purchasing
  inherit it rather than becoming exceptions.
- A DC outage now reads as an outage. Previously it reached the user as "invalid
  credentials" or a clean 403, sending them to raise a permissions ticket against
  AD while the real fault was infrastructure.
- Switching a role between nested and direct membership is an AD-side change
  with no Oskar deploy — the chain-walk resolves both.

**Negative / accepted**

- **Login is slower.** The chain-walk costs more than reading an attribute, and
  `get_groups()` now calls `_find_user_dn()` first, making a login five LDAP
  connections rather than four. Acceptable at ~50 users; **not yet measured
  against the real DC.** Connection reuse is the obvious fix if it bites.
- **Debugging is indirect.** "Why can this person approve?" is a chain walk, not
  one lookup. Mitigated by `list_application_groups()` showing *effective*
  membership resolved through nesting — it previously filtered members by
  `objectClass=user` and would have shown `ecn-approver` as empty once nesting
  was in place.
- **A coarse grant is easy to make carelessly.** Nesting a broad Business
  Function group grants ECN rights to everyone in it, including future joiners
  nobody reviewed. Acceptable only because the `ecn-*` groups are coarse gates;
  the sharp authority stays in `system_role_users`. It would not be acceptable
  if AD carried the 13 fine-grained roles.
- **A directory outage now blocks login outright** rather than issuing a
  permission-less token. This is the intended trade: a token with an empty groups
  claim is worse than a clear 503, because it looks like a permissions problem
  for as long as the token lives.

**Open**

- Six of the 13 ECN roles have no Business Function equivalent — CE, PM, SC, CA,
  RD, TE. PM and SC matter: both are conditional approvers that gate real ECNs
  (routing changes, new parts, lead-time changes). Either Business Function
  groups are created for them, or those individuals are added directly. **A
  go-live question, not a UAT blocker** — UAT role testing runs through
  `system_role_users` and needs no additional AD accounts.
- LDAPS on 636 remains required by ADR-006. Plain LDAP on 389
  (`LDAP_USE_TLS=false`) is permitted for the test window only, and puts the
  service account and every user password on the wire in the clear.
- The service account must be a **conventional account, not a gMSA** — Oskar
  binds with DN + password, which a gMSA cannot provide.

---

## References

- `src/auth/providers.py` — `LDAPDirectoryError`, `get_groups()`,
  `list_application_groups()`
- `scripts/ldap_verify.py` · `scripts/preflight_check.py` (check #5)
- `tests/auth/test_providers.py` · `tests/routers/test_auth_directory_errors.py`
- `docs/srxglobal-active-directory-groups-structure.md` — the real OU layout
- ADR-003 (RBAC hybrid AD/Postgres) — the coarse/fine split this preserves
- ADR-006 (LDAPS + JWT refresh) — LDAPS requirement, unchanged
- `docs/robustness-plan-uat-readiness.md` — why boundary verification exists
