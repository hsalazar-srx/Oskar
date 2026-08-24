# Glossary and reference

Everything in this chapter is a lookup. Read it once to get oriented, then come back when you
meet a term you don't recognise.

---

## ECN statuses

An ECN has exactly one status at a time. The **label** column is what you see on screen — the
code in brackets appears in exports and in the API.

| Label on screen | What it means | Who acts next |
|---|---|---|
| **Draft** `0` | Being written. Only the originator can see it in their list as work-in-progress, and only they can edit it. | Originator |
| **Eng Review** `30` | Submitted. A Senior or Chief Engineer is checking the technical content. | SE or CE |
| **Mgmt Review** `40` | Under parallel review — several managers are asked at once, and each approves independently. | EM, QM, and any conditional roles |
| **DC Approved** `25` | Everyone required has approved. Waiting on the Document Controller's final gate. | Document Controller |
| **Approved** `50` | The DC has released it. Oskar is now writing the changes into Movex. | Nobody — the system is working |
| **Movex Updated** `60` | Every Movex write succeeded. The change is live in the ERP. | Document Controller, to close it |
| **Closed** `70` | Finished. The record is kept for audit. | Nobody — terminal |
| **Rejected** `65` | Sent back with a reason. The originator can revise and resubmit. | Originator |
| **Cancelled** `80` | Abandoned deliberately. Cannot be reopened. | Nobody — terminal |
| **On Hold** `90` | Paused by the DC or an Administrator. Returns to whatever status it was in before the hold. | DC or Administrator |

> **Why the numbers jump around.** `DC Approved` is 25 even though it comes *after* Mgmt Review
> (40). The codes reflect an earlier design; two old statuses (10 and 20) were removed and their
> numbers deliberately never reused, so historical records stay unambiguous. The order on screen
> is the real order.

---

## Roles

Oskar has 14 role codes. Most people hold one; a Document Controller often holds two.

### Always required

| Code | Name | What they do |
|---|---|---|
| `OR` | Originator | Raises the ECN, fills it in, submits it, and resubmits it if rejected. |
| `SE` | Senior Engineer | Technical review at Eng Review. |
| `CE` | Chief Engineer | Alternative to SE, and the escalation route for harder changes. |
| `EM` | Engineering Manager | Approves at Mgmt Review. Always required. |
| `QM` | Quality Manager | Approves at Mgmt Review. Always required. |
| `DC` | Document Controller | The final gate before anything reaches Movex, and the only role that closes an ECN. |

### Required only in certain conditions

These are added automatically when the ECN's change scope calls for them. If the condition
doesn't apply, the step is skipped and that person is never notified.

| Code | Name | Added when |
|---|---|---|
| `PM` | Production Manager | The ECN changes routing or operations |
| `SC` | Supply Chain | The ECN adds new parts or affects lead times |
| `FN` | Finance | The cost change exceeds the configured threshold |
| `CA` | Cost Accountant | Reviews cost impact. Has **no veto** — cannot block the ECN. |

### Notified, but never asked to approve

| Code | Name | Notified when |
|---|---|---|
| `RD` | R&D / Product Engineering | The change affects their product family |
| `TE` | Test Engineering | The ECN updates a controlled document |
| `MQ` | Manufacturing Quality | The ECN reaches Closed |

### Administration

| Code | Name | What they do |
|---|---|---|
| `AD` | Administrator | Places ECNs on hold, resumes them, and overrides role assignments. No approval authority. |

> **Being in a role is not the same as having access.** Your role decides what you're *asked* to
> do on a particular ECN. Whether you can sign in at all is controlled separately by Active
> Directory groups — see [Access and onboarding](12-access-and-onboarding.md).

---

## Change scope

When you create an ECN you tick the boxes describing what the change touches. **These
determine who has to approve it**, so they are worth getting right — see
[Raising an ECN](03-raising-an-ecn.md).

| Scope | Effect |
|---|---|
| New parts | Supply Chain review |
| Change to existing parts | Supply Chain review |
| BOM structure change | Engineering Manager review |
| Routing / process change | Production Manager review |
| Work centre or run-time change | Production Manager review |
| Supplier lead time affected | Supply Chain review |
| Drawing or document update | Test Engineering notified |
| Add or update an MPN | Supply Chain review |
| Regulatory / compliance impact | Mandatory Quality Manager review |

---

## Facilities

| Code | Plant |
|---|---|
| `D` | Melbourne — the default |
| `L` | Johor Bahru |

Facility matters more than it looks. Role assignments are **per plant**: the Quality Manager for
Melbourne and the Quality Manager for Johor Bahru are different people, and Oskar picks the right
one based on the ECN's facility.

---

## Terms

**BOM** — Bill of Materials. The structured list of components that make up an assembly,
including quantity and which operation consumes each part.

**Component** — a part that appears *inside* a BOM. The assembly it belongs to is the **parent
item**.

**Controlled document** — a drawing, work instruction, test spec or similar whose revisions must
be tracked for quality compliance.

**ECN** — Engineering Change Notice. The formal record that a product design, bill of materials,
or manufacturing process has been changed, who approved it, and when it took effect. It is both a
workflow and an audit record: quality standards require that changes to a released product are
reviewed and approved before they take effect, by people qualified to judge the impact.

**Effectivity** — when a change takes effect. Every item on an ECN needs one, and Oskar will not
let you submit without it.

**MPN** — Manufacturer Part Number. The manufacturer's own code for a component, as distinct from
your internal item number. One item can have several MPNs from different manufacturers; one is
marked the default for purchasing.

**Movex** (also **M3**) — the ERP system that runs the business. Movex is the **single source of
truth** for items, BOMs and routings. Oskar does not replace it: Oskar governs *how changes get
into* Movex. Once an ECN is approved, Oskar writes the change into Movex automatically.

**Operation** — a single step in manufacturing a part, performed at a work centre. Routing is the
ordered set of operations.

**Outbox** — the queue Oskar uses to write approved changes into Movex. If a write fails it is
retried automatically; persistent failures are visible to the DC in the admin console. You will
only encounter the term when something has gone wrong.

**Routing** — the sequence of manufacturing operations for an item: which work centre, how long
to set up, how long to run.

**Stargile** — the legacy system Oskar replaces. See
[Coming from Stargile](11-coming-from-stargile.md).

**Work centre** — the machine, cell or station where an operation is performed.

---

## Acronyms you may meet

| Term | Meaning |
|---|---|
| CPN | Customer Part Number — the customer's code for a part you also number internally |
| IPN | Internal Part Number — your own item number |
| MPN | Manufacturer Part Number |
| BOM | Bill of Materials |
| ECN | Engineering Change Notice |
| ERP | Enterprise Resource Planning — the business system, here Movex/M3 |
| EOL | End of Life — a component the manufacturer has discontinued |
| NRND | Not Recommended for New Designs — still available, but avoid designing it in |
| WAPC | Weighted Average Purchase Cost |

> ⚠️ **IPN, CPN and WAPC are used in the system but never defined anywhere in it.** The meanings
> above are the working definitions used by this manual and should be confirmed with Engineering
> before anyone relies on them.
