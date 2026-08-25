# srxglobal.com — Active Directory Group Structure

Domain: `srxglobal.com` | DC: `srxdc01.srxglobal.com`

---

## OU Structure (Groups)

```
srxglobal.com
└── Groups
    ├── Application Roles
    └── Business Functions
```

Site OUs also present: JohorBahru, Melbourne, Penang, Managed Service Accounts.

---

## Business Functions Groups

Located under `OU=Business Functions,OU=Groups,DC=srxglobal,DC=com`

| Name | Description |
|------|-------------|
| grp-eng-manager | Engineering — Manager |
| grp-eng-product | Engineering — Product |
| grp-exec-md | Executive — Managing Director |
| grp-fin-ap | Finance — Accounts Payable |
| grp-fin-ar | Finance — Accounts Receivable |
| grp-fin-manager | Finance — Manager |
| grp-quality-manager | Quality — Manager |
| grp-quality-member | Quality — Member |

---

## Application Roles Groups

Located under `OU=Application Roles,OU=Groups,DC=srxglobal,DC=com`

All groups are **Security Group — Universal**.

| Name | Class | Distinguished Name |
|------|-------|--------------------|
| ecn-approver | group | `CN=ecn-approver,OU=Application Roles,OU=Groups,DC=srxglobal,DC=com` |
| ecn-doc-controller | group | `CN=ecn-doc-controller,OU=Application Roles,OU=Groups,DC=srxglobal,DC=com` |
| ecn-initiator | group | `CN=ecn-initiator,OU=Application Roles,OU=Groups,DC=srxglobal,DC=com` |
| mes-admin | group | `CN=mes-admin,OU=Application Roles,OU=Groups,DC=srxglobal,DC=com` |
| mes-engineers | group | `CN=mes-engineers,OU=Application Roles,OU=Groups,DC=srxglobal,DC=com` |
| mes-operator | group | `CN=mes-operator,OU=Application Roles,OU=Groups,DC=srxglobal,DC=com` |
| mes-supervisor | group | `CN=mes-supervisor,OU=Application Roles,OU=Groups,DC=srxglobal,DC=com` |
| pur-admin | group | `CN=pur-admin,OU=Application Roles,OU=Groups,DC=srxglobal,DC=com` |
| pur-approver | group | `CN=pur-approver,OU=Application Roles,OU=Groups,DC=srxglobal,DC=com` |
| pur-buyer | group | `CN=pur-buyer,OU=Application Roles,OU=Groups,DC=srxglobal,DC=com` |

### Application Prefix Key

| Prefix | Application |
|--------|-------------|
| `ecn-` | Engineering Change Note (ECN) |
| `mes-` | Manufacturing Execution System (MES) |
| `pur-` | Purchasing |

---

## Membership Model (ADR-013, 2026-08-21)

Business Function groups are **nested into** the Application Role groups. A
quality manager reaches `ecn-approver` by being in `grp-quality-manager`, not by
direct membership — so ECN access follows normal onboarding and is revoked the
same way.

| Application Role | Membership | Source |
|---|---|---|
| `ecn-initiator` | Nested | Engineering Business Function groups |
| `ecn-approver` | Nested | Manager-level Business Function groups |
| `ecn-doc-controller` | **Direct** | Named users |

`ecn-doc-controller` is the deliberate exception. Document Controller is a duty
within the ECN process rather than an org function, so there is no Business
Function group above it — and a `grp-doc-control` created solely to feed this one
role would hold exactly the same people, adding a hop and no information.

**The rule:** nest when the Business Function group would exist anyway; add
directly when it would not.

### Consequences for anyone reading membership

- **Direct `memberOf` is not sufficient.** It returns direct membership only, so
  a nested user appears to hold no roles. Resolution must walk the chain — Oskar
  uses AD's `LDAP_MATCHING_RULE_IN_CHAIN`
  (`(member:1.2.840.113556.1.4.1941:={user_dn})`), searched from the Application
  Roles OU. See `src/auth/providers.py`.
- **`ecn-doc-controller` does not imply `ecn-approver`.** They are checked
  independently: a DC in only the DC group passes the document-control gate and
  is rejected on ordinary approvals. DCs need **both**.
- **No AD group is facility-scoped.** Melbourne (D) / Johor Bahru (L) role
  assignment lives in Oskar's `system_role_users` table, which is facility-aware.
  AD answers only "can this person log in and approve at all" — which is why
  three groups serve all 13 ECN roles.

### Unmapped ECN roles (open at 2026-08-21)

Six of Oskar's 13 roles have no Business Function equivalent: CE, PM, SC, CA,
RD, TE. **PM and SC matter** — both are conditional approvers that gate real
ECNs (routing changes, new parts, lead-time changes). Either Business Function
groups get created for them, or those individuals are added directly.

A go-live question, not a UAT blocker: role testing runs through
`system_role_users` and needs no additional AD accounts.

### Verification

`scripts/ldap_verify.py` proves this model against the real DC — nested
resolution, direct resolution, no `grp-*` leaking into roles, and `mail`
populated. It runs as check #5 of `scripts/preflight_check.py`.
