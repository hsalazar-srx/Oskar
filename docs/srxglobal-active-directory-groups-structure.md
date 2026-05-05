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
| `ecn-` | Engineering Change Notice (ECN) |
| `mes-` | Manufacturing Execution System (MES) |
| `pur-` | Purchasing |
