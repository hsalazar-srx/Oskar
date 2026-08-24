# Coming from Stargile

If you have raised ECNs in Stargile, most of what you know still applies. The *process* has not
changed: someone raises a change, the right people review it, and it goes into Movex. What has
changed is how much of that you have to do by hand.

This chapter is the fastest way in. Read it, then go to your role's chapter.

---

## The five differences that matter most

### 1. One ECN covers everything

In Stargile you raised **separate ECNs** for items, routings, BOM changes and MPNs. A single
real-world change routinely meant three or four ECNs to keep in step.

In Oskar, one ECN carries all four. The ECN detail screen has a tab for each, and they are
approved together as one change.

**Unlearn:** don't raise a second ECN because your change touches both the BOM and the routing.
Use the tabs.

### 2. It works in a normal browser

Stargile needed Internet Explorer 9. Oskar works in Chrome, Edge, Firefox and Safari, and it
works on a laptop away from your desk.

### 3. Approvers are worked out for you

In Stargile you picked a distribution list by name, and there was nothing checking that the list
you chose matched the boxes you had ticked. Choose the wrong list and the ECN went to the wrong
people — silently.

In Oskar you tick what the change *affects*, and Oskar works out who has to approve from that.
Tick "Routing / process change" and the Production Manager is added automatically.

**Unlearn:** you no longer choose your approvers. If you think the wrong people were added, the
fix is to correct the change scope, not to reassign the list.

### 4. Movex is written for you

In Stargile you created the item in Movex yourself, then raised the ECN to record that you had.
The ECN was paperwork *after* the fact.

In Oskar the ECN is the mechanism. When the Document Controller approves, **Oskar writes the
change into Movex** — items, BOM lines, routing operations, MPN aliases. You do not re-key
anything, and the two can't drift apart.

**Unlearn:** do not create the item in Movex first. Raise the ECN and let it do the write.

### 5. Two people can't quietly overwrite each other

In Stargile, two ECNs against the same part number would both go through, and the second silently
overwrote the first.

Oskar takes a snapshot of the BOM when you submit, and re-checks it at the Document Controller's
gate. If someone else changed the same lines in between, the DC is shown the conflict and has to
resolve it before anything is written.

---

## Also fixed

- **BOM upload no longer accepts duplicate sequence numbers.** Stargile took them and corrupted
  the data; Oskar rejects the file and tells you which row.
- **No currency field on MPN uploads.** It was mandatory in Stargile and never used. It's gone.
- **Manufacturer name only.** Stargile wanted both a manufacturer code and a name. Oskar needs
  the name.
- **You can't upload to a finished ECN.** Stargile let you add items to a completed ECN, where
  they quietly went nowhere.

---

## Terminology

| Stargile | Oskar |
|---|---|
| ECN status numbers (13 of them) | 10 statuses with plain-English names — see the [Glossary](02-glossary.md) |
| Distribution list | Change scope — you tick what the change affects, Oskar picks the people |
| DMR path typed as text | Attachments on the ECN itself |
| Separate item / route / BOM / MPN ECNs | One ECN, four tabs |

---

## What has genuinely gone away

Some Stargile habits have no Oskar equivalent because the underlying problem was removed:

- **Typing DMR paths.** Files attach to the ECN.
- **Manually keeping parallel ECNs in step.** There is only one.
- **Checking Movex afterwards to see whether your change landed.** Oskar shows you the write
  status, and tells the DC if it failed.

---

## What is not in Oskar yet

Being straight about the gaps, so you're not hunting for something that isn't there:

- **Transmittals and document distribution** are not yet in Oskar. Continue as you do today.
- **MTS upload** is unchanged — Oskar does not push to MTS.
- **MPN purge / end-dating** is not automated.

If your work depends on any of these, raise it — knowing which gaps hurt most is how they get
prioritised.

---

## The switchover

**Oskar and Stargile will not run side by side.** The plan is:

1. **A two-week drain.** Finish the ECNs you have open in Stargile. Don't start new ones there.
2. **Cutover day.** Stargile goes read-only. Every new ECN is raised in Oskar.
3. **Anything still open in Stargile** is either completed there or cancelled and re-raised in
   Oskar. Nothing is migrated mid-workflow — a half-approved ECN cannot be moved across without
   losing the approvals already given.

Your closed Stargile records remain available for audit. They are not being deleted.

**During the drain, get an Oskar login and raise one practice ECN.** Ten minutes then is worth
more than an hour of reading on cutover day.

---

## Where to go next

| You are | Read |
|---|---|
| An engineer raising changes | [Raising an ECN](03-raising-an-ecn.md) |
| An approver | [Approving an ECN](04-approving-an-ecn.md) |
| A Document Controller | [The Document Controller](05-document-controller.md) |

If you can't sign in on day one, that's an access question, not an Oskar question — see
[Access and onboarding](12-access-and-onboarding.md).
