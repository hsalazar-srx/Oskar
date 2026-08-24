# When things go wrong

Organised by symptom — find what you are seeing, not what you think is causing it.

Most entries end with "ask your Document Controller", and that is genuinely the right answer.
The DC has recovery tools nobody else does.

---

## I can't sign in

**"Invalid username or password"**

Check the obvious first: caps lock, and that you are using your **network** password, not an old
Oskar-specific one. There isn't one — Oskar uses your Windows credentials.

If you are certain the password is right, the message can be misleading. Oskar reports some
connection and configuration problems using the same wording, so a directory or network fault can
look like a wrong password. If a colleague can sign in and you cannot, it is probably your account;
if nobody can, it is not.

**Ask IT if:** you are sure the credentials are right, or several people are affected at once.

---

## I'm signed in, but I can't see anything / can't do anything

You are authenticated but not authorised. Oskar hides actions you cannot take rather than greying
them out, so a missing button and a missing permission look identical.

**Ask IT to confirm** you are in the right access groups. There are three, and which you need
depends on your job — see [Access and onboarding](12-access-and-onboarding.md).

A specific trap for **Document Controllers**: you need **two** groups. If you can DC-approve but
get refused on ordinary approvals, that is exactly this.

---

## There's no Approve button

In order of likelihood:

1. **You've already approved.** Check the Workflow panel — your row will say `approved`.
2. **You're not assigned to that role on this ECN.** Roles are assigned per ECN *and* per plant.
   The Melbourne QM is not automatically the Johor Bahru QM.
3. **You raised the ECN.** Self-approval is blocked and cannot be overridden.
4. **It isn't at your stage.** A Senior Engineer cannot approve at Management Review.
5. **Your step was skipped.** If the change scope didn't call for your role, your row says
   `skipped` and there is nothing to approve.

**Ask your DC if:** none of these fit. They can reassign roles on an ECN.

---

## I got an email but there's nothing to do

Usually one of:

- **Someone else got there first.** On a parallel review another approver may have rejected the
  ECN after your email went out.
- **It's a notification, not a request.** Observers (R&D, Test Engineering, Manufacturing Quality)
  are told what happened; they are not asked to act.
- **The ECN moved on.** The chase email fires up to six hours after the threshold, so it can arrive
  just after you actioned it.

Open the ECN and read its status. If it says Closed or Rejected, no action is needed.

---

## I'm not getting emails at all

**This is the one to chase, because Oskar fails silently here.**

Oskar takes your email address from Active Directory. If your AD account has no address recorded,
**Oskar skips the notification without any error** — nothing bounces, nothing is logged where you
would see it. From your side it just looks as though the system never asked you.

The tell-tale sign: you only discover ECNs waiting on you by opening Oskar and finding them.

**Ask IT to check the `mail` attribute on your AD account.** Neither you nor your DC can fix this
from inside Oskar.

Before that, rule out the boring causes: junk folder, and any rule filing `[OSKAR]` mail into a
folder you don't watch.

---

## My upload was rejected

The preview marks problems per row, and the row numbers match your spreadsheet (counting the header
as row 1).

| Message | Cause |
|---|---|
| Missing required column | A required header is absent or misspelled — compare with the example files in [`templates/`](templates/) |
| "Could not parse the uploaded file" | Not a valid `.xlsx` or `.csv`. Often a `.xls` renamed, or a Google Sheets export |
| "The file contains no data rows" | Only a header row, or your data starts below a blank row |
| File exceeds the 1 MB limit | Split it, or save as `.csv` — much smaller than `.xlsx` |
| Duplicate row | The same key appears twice. Oskar checks within your file as well as against the ECN |
| Value too long | Over the column's maximum — `Item Name` is only 30 characters |
| "item_number ... was not found on this ECN" | The item isn't on the ECN yet. **Upload items before routing, BOM changes or MPNs.** |

**Do not export and re-upload.** The export format is deliberately different from the upload
format and will be rejected — see [Bulk uploads](07-bulk-uploads.md).

---

## I can't edit my ECN any more

**Once submitted, an ECN is locked.** That is intended: reviewers must be able to trust that what
they approved is what gets built.

You can edit again if it is **rejected** back to you.

For BOM changes specifically, the lock message is: *"BOM changes cannot be edited once the ECN has
reached DC_APPROVED (DC role only)"* — after that point only the Document Controller can adjust
them.

**Need a change to a submitted ECN?** Either ask a reviewer to reject it back to you, or ask the DC.
Don't raise a duplicate ECN.

---

## My ECN is stuck at "Approved"

"Approved" means the DC has released it and **Oskar is writing to Movex**. It should advance to
"Movex Updated" within a few minutes, on its own.

If it hasn't after, say, fifteen minutes, a write has failed. Oskar retries automatically, but
persistent failures need attention.

**Tell your DC.** They have **Admin → Movex Write Recovery**, which shows the failure and the error
Movex returned, with a Retry button.

**This is not a silent failure.** Oskar knows the write didn't land and deliberately will not
advance the ECN. What it cannot do is fix the cause.

---

## My ECN is stuck at "Movex Updated"

This is not stuck — **it is waiting for a Document Controller to close it**. Nothing closes
automatically.

The change is already live in Movex. Only the paperwork is open.

**Ask your DC to close it**, once any post-implementation checklist is done.

---

## The BOM Browser says "No BOM found"

- **Check the item number** — they are case-sensitive and easy to mistype.
- **Check the facility.** An item can exist at Melbourne and not Johor Bahru.
- **The item may genuinely have no BOM.** A purchased component has no structure of its own.
- **Movex may be unreachable.** If nothing at all returns a BOM, tell your DC.

---

## "Where used" is empty

Usually correct rather than broken. A top-level assembly isn't a component of anything, so nothing
uses it.

If you expected results for a component, check the facility, and whether the parent BOMs are still
active — expired lines don't count as "used".

---

## Something changed underneath my ECN

If someone else modified the same BOM lines between your submission and the DC's approval, Oskar
detects it and shows the DC a conflict rather than silently overwriting.

You may be asked to review and resubmit. This is the system protecting your colleague's change and
yours — in Stargile, the second change silently overwrote the first.

---

## Who to ask

| Problem | Who |
|---|---|
| Can't sign in; no buttons anywhere; not getting emails | **IT** |
| Stuck ECN; failed Movex write; need a role reassigned; need something unlocked | **Your Document Controller** |
| Whether a change needs an ECN at all; what scope to tick | **Your Engineering Manager** |
| Something in this manual is wrong or unclear | **The Lead Engineer** — please say so |

When reporting a problem, include **the ECN number** and **what you were trying to do**. It saves
a round trip.
