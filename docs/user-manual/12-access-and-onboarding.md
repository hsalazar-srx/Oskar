# Access and onboarding

How people get into Oskar, and what to do when someone joins, changes role, or leaves.

This chapter is for **new starters** who cannot sign in, **Document Controllers** diagnosing why a
colleague has no buttons, and **IT** setting accounts up.

---

## There is no Oskar password

Oskar uses your **normal network credentials** — the same username and password as Windows. There
is nothing separate to set up, remember or reset.

If your network password changes, Oskar follows automatically.

---

## Two things control what you can do

This is the single most useful idea in this chapter, and the source of most confusion.

| | Set by | Controls | Where |
|---|---|---|---|
| **Access group** | IT | Whether you can sign in, and broadly what kind of thing you can do | Active Directory |
| **Role assignment** | Document Controller | Whether *you* are asked on *this* ECN, at *this* plant | Oskar, Admin → ECN Role Assignments |

**Both must be right.** They fail in different, easily-confused ways:

- Wrong access group → you sign in but see no buttons anywhere, on every ECN
- Missing role assignment → everything looks normal, but you are never asked to do anything

If a colleague says "Oskar isn't working", establishing which of these it is takes about ten
seconds and saves a lot of guessing.

---

## The three access groups

| Group | Gives you |
|---|---|
| `ecn-initiator` | Raise ECNs, view items and BOMs |
| `ecn-approver` | Action approval steps |
| `ecn-doc-controller` | The Document Controller gate |

You can hold more than one. An engineering manager who raises changes *and* approves them needs
both `ecn-initiator` and `ecn-approver`.

### ⚠️ Document Controllers need two groups

`ecn-doc-controller` does **not** include `ecn-approver`. Oskar checks them independently.

A Document Controller with only the DC group can pass the DC gate but is **rejected on ordinary
approvals**. It looks like a bug and is not — it is a missing group membership.

This is the most common access misconfiguration. If you are setting up a DC, add both.

---

## How you get into a group

You do not usually get added to `ecn-initiator` or `ecn-approver` individually. Instead they are
granted through the group that reflects your **job** — engineering, quality, production, and so on.

The practical consequence: **Oskar access arrives with normal onboarding**. A new quality manager
gets ECN approval rights as part of being set up as a quality manager, with no separate Oskar
request. When someone leaves, removing their normal access removes Oskar too.

`ecn-doc-controller` is the exception and is granted directly, because Document Controller is a
duty within the ECN process rather than a job title.

---

## New starter checklist

For whoever is onboarding someone into an ECN-facing role:

**1. IT — access**
- Confirm they are in the right access group(s) for their job
- For a Document Controller, confirm **both** `ecn-doc-controller` and `ecn-approver`
- **Confirm their email address is recorded in Active Directory.** Without it Oskar silently sends
  them nothing — see below

**2. Document Controller — role assignment**
- Add them in **Admin → ECN Role Assignments**, under their role
- **Pick the right facility.** Melbourne (`D`) and Johor Bahru (`L`) are separate. Someone covering
  both must be added twice.
- Decide whether they are the default assignee. **The first person listed for a role at a facility
  is the default**; later entries are backups.

**3. Them — orientation**
- [Getting started](01-getting-started.md), then their role's chapter
- If they used Stargile, [Coming from Stargile](11-coming-from-stargile.md) first

---

## ⚠️ The email address is not optional

Oskar reads your email address from Active Directory. **If it is missing, Oskar skips your
notifications entirely** — no error, no bounce, nothing anywhere you would see it.

The person simply never hears that an ECN is waiting on them, and finds out only by opening Oskar.

There is no way to fix this from inside Oskar. **Ask IT to check the `mail` attribute on the
account.** It is worth confirming during onboarding rather than discovering it when an ECN has sat
untouched for a week.

---

## When someone changes role

Both halves need attention:

- **IT** — update their access groups if the new role needs different ones
- **Document Controller** — remove them from their old role in Admin, add them to the new one

Removing them from a role does not affect ECNs already in flight, and never erases past approvals,
which stay in the audit trail permanently.

---

## When someone leaves

**Do the role assignment removal, not just the AD one.** Disabling the AD account stops them
signing in, but their name stays on the Oskar roster — and if they were the *default* assignee for
a role, new ECNs will keep being assigned to someone who cannot act.

The damaging case is Document Controllers. If the only DC for a plant leaves and is not replaced in
Admin, **every ECN at that plant stalls at the DC gate** with nobody able to approve. There is no
warning; ECNs simply stop moving.

Checklist:

1. IT disables the account
2. DC removes them from every role in **Admin → ECN Role Assignments**
3. DC checks each role they held still has someone — especially at their facility
4. DC reassigns any in-flight ECN currently waiting on them

---

## Diagnosing an access problem

| Symptom | Likely cause | Who fixes it |
|---|---|---|
| Can't sign in at all | Network credentials, or no access group | IT |
| Signs in, no buttons anywhere | Not in any `ecn-*` group | IT |
| Can DC-approve but not approve normally | Missing `ecn-approver` alongside `ecn-doc-controller` | IT |
| Everything looks normal, never asked to do anything | Not on the role roster, or wrong facility | Document Controller |
| Assigned to ECNs but gets no emails | Missing `mail` attribute in AD | IT |
| Was fine, now isn't | Group membership changed, or removed from a role | Check both |

**Document Controllers can check the first three themselves**: **Admin → Active Directory Groups**
shows who is in each group, read live. That tells you whether it is an IT problem or yours before
you raise a ticket.

---

## What Oskar deliberately will not do

- **Let you approve your own ECN**, however senior you are or how many roles you hold
- **Grant access by role assignment alone** — being on the roster does not let you sign in
- **Tell an unauthenticated visitor anything** about whether a username exists

These are quality and security requirements, not settings.
