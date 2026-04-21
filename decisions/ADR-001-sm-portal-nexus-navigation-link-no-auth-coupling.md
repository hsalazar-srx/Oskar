---
id: ADR-001
decision: SM-Portal navigates to OSKAR via a link tile — no auth coupling between the two systems
status: accepted
date: 2026-04-08
reversibility: type-2-reversible
review_date: 2026-10-08
author: Hector Salazar
---

# ADR-001 — SM-Portal → OSKAR Navigation: Link Tile, No Auth Coupling

## Decision

SM-Portal serves as the primary entry point for Scanfil APAC engineers. A navigation tile
in the SM-Portal frontend links to `oskar.srxglobal.local` and opens it in a new browser tab.
OSKAR authenticates the engineer independently via LDAP using the same Windows AD credentials.
There is no token sharing, session bridging, or SSO between SM-Portal and OSKAR.

## Context

Engineers use SM-Portal daily for M3 data, invoices, and exchange rates. OSKAR (ECN, BOM,
Supplier Intelligence) is a separate platform that engineers need to access as part of their
workflow. The question arose: should users navigate to OSKAR through SM-Portal, or directly?

Two options were evaluated:

**Option A — Navigation link (chosen):**
SM-Portal frontend includes a "OSKAR" tile/menu item. Clicking it opens
`oskar.srxglobal.local` in a new tab. Engineers authenticate with the same AD credentials
via OSKAR's LDAP flow. Two separate sessions, no auth sharing.

**Option B — SM-Portal as SSO gateway:**
SM-Portal authenticates the user via Windows Negotiate, then issues a token that OSKAR
trusts. OSKAR embedded or proxied through SM-Portal. Single session.

## Rationale

Option A chosen because:

1. **Auth mechanisms are incompatible.** SM-Portal uses Windows Negotiate (NTLM/Kerberos)
   on .NET 8 / IIS. OSKAR uses JWT + LDAP on Python / Docker / Linux. Kerberos inside Docker
   containers is a documented support problem. Auth bridging adds complexity with no user
   experience benefit that justifies the engineering cost at this stage.

2. **Zero implementation cost.** A navigation tile in the SM-Portal React frontend is a
   single component addition. Option B requires a token exchange protocol, shared secret
   management, and testing across two auth stacks.

3. **Same credentials, transparent to engineers.** Engineers use their Windows AD username
   and password for both systems. OSKAR authenticates via LDAP bind — the credential set is
   identical. The only difference is a separate login step on first OSKAR access per session
   (mitigated by the 8-hour JWT expiry).

4. **Preserves architectural independence.** OSKAR and SM-Portal can be deployed, updated,
   and maintained independently. An SM-Portal outage does not block OSKAR access.

5. **Reversible.** If SSO becomes a priority in a future phase, it can be implemented as a
   planned architectural change. Option A does not foreclose Option B.

## Consequences

- Engineers authenticate twice if they switch between SM-Portal and OSKAR in a session.
  Accepted — 8-hour JWT expiry means re-auth once per working day at most.
- SM-Portal frontend requires one new navigation tile component pointing to
  `oskar.srxglobal.local` (opens in new tab). No SM-Portal backend changes required.
- Shared Tailwind design tokens between SM-Portal and OSKAR frontend ensure visual coherence
  despite separate auth and deployment architecture.

## Assumptions

- Engineers access both systems from the same workstation on the corporate network.
- 8-hour JWT expiry on OSKAR matches the typical working day without requiring re-auth.
- AD credentials are stable across a session.

## Alternatives Rejected

- **Option B (SSO/token bridging):** Engineering cost disproportionate to UX benefit at
  this stage. Kerberos inside Docker is unsupported. Revisit post-Phase 1 if engineers
  find the dual-auth UX unacceptable.

## Implementation

**SM-Portal frontend (`c:/Projects/SM-Portal/frontend/`):**
Add a navigation tile/menu item linking to `oskar.srxglobal.local`.
Opens in a new tab (`target="_blank" rel="noopener noreferrer"`).
No backend changes required.

**OSKAR:** No changes required. Standard LDAP auth flow handles engineer login.
