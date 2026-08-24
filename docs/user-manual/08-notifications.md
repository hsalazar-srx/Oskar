# Notifications

Oskar emails you when it needs something from you, and chases you if you don't respond. You do
not have to keep checking the app.

All emails come from Oskar with a subject beginning **`[OSKAR]`**, so they are easy to filter
into a folder — though see the warning at the end of this chapter before you do.

---

## When you get an email

| Email | Goes to | When |
|---|---|---|
| **Action required** | The person whose approval is needed | An ECN reaches a stage where you have to act |
| **ECN rejected** | The originator | A reviewer rejects it, with their reason included |
| **Action overdue** | The person who owes the action, **and their Engineering Manager** | 48 hours after the action was assigned |
| **URGENT — severely overdue** | The **Document Controller** | 96 hours, and only at Management Review |
| **Open ECN summary** | Document Controllers | Once a day |

---

## The overdue chase

Oskar checks every six hours for approvals that have been sitting too long.

**At 48 hours**, it emails the person who owes the action *and copies their Engineering Manager*.
The email names the ECN, the stage, the role, and how many hours it has been waiting.

**At 96 hours**, if the ECN is at Management Review, the Document Controller is emailed as well.

Two things worth knowing:

- **Your manager is copied on the first chase, not the second.** The 48-hour email already goes to
  the EM. If you want to avoid your manager being emailed, respond within two working days.
- **Because the check runs every six hours, an email arrives within six hours of the threshold**,
  not exactly on it. A 48-hour chase may land at 51 hours.

---

## The daily summary

Document Controllers receive one email a day listing every open ECN for **their plant**:
ECN number, title, status, originator, age in days, and who it is waiting on.

Melbourne DCs see only Melbourne ECNs; Johor Bahru DCs see only Johor Bahru ECNs. If you cover
both plants you will receive two emails.

This is the replacement for the old nightly Stargile report.

---

## What Oskar does not email you about

- **Approvals you are not required for.** If your role was skipped because the change scope didn't
  call for it, you hear nothing. That is intended, not an oversight.
- **Observer roles.** R&D, Test Engineering and Manufacturing Quality are notified at defined
  points only, and are never asked to approve.
- **Someone else's approval landing.** Only the person who owes the *next* action is told.
- **Successful Movex writes.** Silence means it worked. Failures are surfaced to the Document
  Controller in the app.

---

## ⚠️ If you are not getting emails

Oskar looks up your email address from Active Directory. **If your AD account has no email
address recorded, Oskar skips the notification silently** — no error, no bounce, nothing in your
inbox. From your side it simply looks as though the system never asked you.

The tell-tale sign is that you find out about ECNs waiting on you only by opening Oskar and
seeing them in your list.

If that happens, **ask IT to check the `mail` attribute on your AD account**. This is not
something you or the Document Controller can fix from inside Oskar.

Other things to check first:

- Look in your junk folder, and whether a rule is filing `[OSKAR]` mail somewhere you don't watch
- Confirm with your DC that you are actually assigned to the role on that ECN — see
  [Access and onboarding](12-access-and-onboarding.md)

---

## A caution about filtering

It is tempting to file all `[OSKAR]` mail into a subfolder. Be careful: the overdue chase copies
your Engineering Manager at 48 hours, so a filter that hides these from you does not hide them
from your manager.

If you would rather work from the app than the inbox, use the **Require my action** card on the
ECN list instead — see [Finding ECNs](09-finding-ecns.md).
