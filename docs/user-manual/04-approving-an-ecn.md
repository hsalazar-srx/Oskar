# Approving an ECN

For Engineering Managers, Quality Managers, Production Managers, Supply Chain, Finance, Cost
Accountants, and Senior or Chief Engineers.

---

## Finding what needs you

Two ways, and you don't need both:

- **Email.** Oskar emails you when an ECN needs your approval, and chases you at 48 hours —
  copying your Engineering Manager. See [Notifications](08-notifications.md).
- **The worklist.** Click the **Require my action** card on the ECN list. That is the definitive
  answer to "what's waiting on me?"

---

## Why you were asked

You are asked for one of two reasons.

**You are a mandatory approver.** Engineering Manager and Quality Manager are asked on *every*
ECN, no exceptions.

**The change scope pulled you in.** The originator ticked something that requires your judgement:

| If they ticked… | You are asked, as… |
|---|---|
| Routing / process change, or work centre / run-time change | Production Manager |
| New parts, changed parts, supplier lead time, or add/update an MPN | Supply Chain |
| Regulatory / compliance impact | Quality Manager (mandatory review) |
| BOM structure change | Engineering Manager |

If the scope doesn't apply to you, Oskar marks your step **skipped** and never notifies you. You
will see `skipped` against roles that weren't needed — that is normal, not an oversight.

---

## Management Review happens in parallel

This is the biggest difference from a traditional approval chain, and the thing most worth
understanding.

![Management Review with three roles pending and two skipped](images/ecn-mgmt-review.png)

Everyone required at Management Review is asked **at the same time**. You are not waiting for the
person above you, and nobody is waiting for you before they can start.

In the screenshot: Engineering Manager, Production Manager and Quality Manager are all `pending`
simultaneously. Finance and Supply Chain are `skipped` — this change affected neither.

**The ECN moves on by itself once the last required approval lands.** Nobody has to push it. If
you are the last of three to approve, clicking Approve advances the whole ECN to the Document
Controller.

---

## Reviewing the change

Before you approve, the detail screen gives you everything you need:

- **The header** — what's changing and why, in the originator's words, plus the scope pills
  showing what it touches.
- **The tabs** — Items, Routing, BOM Changes and MPNs. This is the substance. Check the tab that
  matches your area: a Production Manager should be reading **Routing**; Supply Chain should be
  reading **Items** and **MPNs**.
- **Notes & Comments** — ask a question here rather than by email, so the answer stays attached
  to the ECN and the next reviewer can see it.

### What to check

| Your role | Worth checking |
|---|---|
| Engineering Manager | Is the change technically sound? Is the BOM impact understood? |
| Quality Manager | Regulatory impact, customer qualification, whether controlled documents need revising |
| Production Manager | Can the line actually run this? Are routing times realistic? |
| Supply Chain | Are the new parts sourceable? Do lead times work? Is the default MPN right? |
| Finance | Cost impact against the threshold |
| Senior / Chief Engineer | The whole technical package, before it reaches management |

---

## Approving

The action buttons sit at the bottom of the Workflow panel.

**Approve** — records your approval for *your* role. If other roles are still pending, the ECN
stays at Management Review until they are done.

**Reject** — sends it back to the originator. **A reason is mandatory** and Oskar will not let you
proceed without one. Write something the originator can act on: *"obtain coating compatibility
report from the supplier and resubmit"* is useful; *"not acceptable"* is not.

Rejecting is not a failure of the process — it is the process working. A rejected ECN can be
revised and resubmitted, and it returns to Engineering Review so the change is re-checked from the
top.

---

## You cannot approve your own ECN

If you raised it, you cannot approve it, even where you legitimately hold the role. Oskar blocks
self-approval outright — it is a quality requirement, not a configuration choice.

If you are the only person in your role and you need to raise a change yourself, the Document
Controller can assign that role to someone else for that ECN. Ask them.

---

## Engineering Review — for Senior and Chief Engineers

Senior and Chief Engineers act one stage earlier, at **Engineering Review**, before management
sees the ECN at all. This is the technical gate: the change should be right before managers are
asked to sign it off.

The button reads **"Approve — send to Management Review"**. Either role can act; you do not both
need to.

---

## The Cost Accountant is different

The Cost Accountant reviews cost impact but **has no veto**. You will be asked, and your view is
recorded, but the ECN does not stop for you. If you have a real objection, raise it in the
comments and speak to the Engineering Manager or Document Controller.

---

## After you approve

Once everyone required has approved, the ECN goes to the **Document Controller** for a final check
before anything is written into Movex.

![The Document Controller's gate, with all approvals in](images/ecn-dc-approval.png)

Notice the three roles now marked `approved` and the two still `skipped` — the same ECN as before,
one stage further on. The Document Controller's button reads **"DC Approve — send to Movex"**,
which is the point of no return: after that, Oskar starts writing to the ERP.

You will not hear about the ECN again unless it is rejected later and resubmitted — or you are a
Manufacturing Quality observer, who is notified when it closes.

---

## If you cannot see an Approve button

In order of likelihood:

1. **You have already approved.** Check the Workflow panel — your row will say `approved`.
2. **You are not assigned to that role on this ECN.** Role assignment is per ECN and per plant.
3. **You raised it.** Self-approval is blocked.
4. **It is not at your stage yet.** A Senior Engineer cannot approve at Management Review.
5. **Your access groups are wrong** — a question for IT rather than the DC. See
   [Access and onboarding](12-access-and-onboarding.md).

More detail in [When things go wrong](10-troubleshooting.md).
