# Oskar — User Manual

Oskar is the system Scanfil APAC uses to raise, review and approve **Engineering Change Notes**
(ECNs), and to push approved changes into Movex.

It replaces **Stargile**. If you used Stargile, start with
[Coming from Stargile](11-coming-from-stargile.md) — it explains what moved, what's gone, and
which habits to unlearn.

---

## What Oskar does

An engineering change needs the right people to review it before it reaches production. Oskar
handles that end to end:

1. You raise an ECN describing what's changing and why.
2. Oskar works out **who has to approve it** from the change scope you tick.
3. Reviewers approve or reject, with the managers reviewing in parallel rather than in a queue.
4. The Document Controller does a final check.
5. **Oskar writes the change into Movex automatically** — no re-keying.
6. The Document Controller closes the ECN, and the record is kept for audit.

Movex remains the single source of truth for items, BOMs and routings. Oskar governs how changes
get into it.

---

## Which chapters do I read?

You do not need to read all of this. Find yourself below.

### I raise changes — engineer, designer, originator

[Getting started](01-getting-started.md) → [Glossary](02-glossary.md) →
**[Raising an ECN](03-raising-an-ecn.md)** → [Bulk uploads](07-bulk-uploads.md) →
[Finding ECNs](09-finding-ecns.md) → [When things go wrong](10-troubleshooting.md)

Add [BOM tools](06-bom-tools.md) if you work with bills of materials.

*About two hours, plus hands-on. Chapter 3 is the one that matters; chapter 7 is the one you'll
come back to.*

### I approve changes — Engineering Manager, Quality Manager, Production Manager, Supply Chain, Finance

[Getting started](01-getting-started.md) → [Glossary](02-glossary.md) →
**[Approving an ECN](04-approving-an-ecn.md)** → [Notifications](08-notifications.md) →
[When things go wrong](10-troubleshooting.md)

*About thirty minutes. You can skip the chapters on creating ECNs and bulk uploads entirely.*

### I am a Document Controller

Read everything, in order. The DC is the only role that touches every part of the system —
including [Admin](05a-admin.md), which nobody else needs.

### I am a Senior or Chief Engineer

[Getting started](01-getting-started.md) → [Glossary](02-glossary.md) →
[Approving an ECN](04-approving-an-ecn.md) (the Engineering Review section) →
[BOM tools](06-bom-tools.md)

### I want to understand how Oskar works, without using it day to day

[How an ECN moves through Oskar](02-glossary.md#ecn-statuses) and the workflow diagram, then skim
[Raising an ECN](03-raising-an-ecn.md) and
[The Document Controller](05-document-controller.md) — the DC gate is where the governance
actually happens.

### I am new and cannot sign in

[Access and onboarding](12-access-and-onboarding.md).

---

## All chapters

| # | Chapter | For |
|---|---|---|
| 01 | [Getting started](01-getting-started.md) | Everyone |
| 02 | [Glossary and reference](02-glossary.md) | Everyone |
| 03 | [Raising an ECN](03-raising-an-ecn.md) | Originators, engineers |
| 04 | [Approving an ECN](04-approving-an-ecn.md) | All approvers |
| 05 | [The Document Controller](05-document-controller.md) | DC |
| 05a | [Admin](05a-admin.md) | DC, Administrators |
| 06 | [BOM tools](06-bom-tools.md) | Engineers, DC |
| 07 | [Bulk uploads](07-bulk-uploads.md) | Originators, engineers |
| 08 | [Notifications](08-notifications.md) | Everyone |
| 09 | [Finding ECNs](09-finding-ecns.md) | Everyone |
| 10 | [When things go wrong](10-troubleshooting.md) | Everyone |
| 11 | [Coming from Stargile](11-coming-from-stargile.md) | Existing staff |
| 12 | [Access and onboarding](12-access-and-onboarding.md) | New starters, IT |

**[`templates/`](templates/)** — ready-to-use example spreadsheets for all four bulk uploads.

---

## Getting help

| Problem | Who |
|---|---|
| Can't sign in, or no buttons appear where you expect them | IT |
| An ECN is stuck, or a Movex write failed | Your Document Controller |
| Not sure whether something needs an ECN at all | Your Engineering Manager |
| Something in this manual is wrong or unclear | The Lead Engineer — please say so, it will be fixed |

---

*This manual describes Oskar as at August 2026. Screens change; if what you see differs from
what's written here, trust the screen and report the difference.*
