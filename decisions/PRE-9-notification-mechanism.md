# PRE-9 — Notification Mechanism

**Status:** Accepted (mechanism) — Configuration deferred
**Date:** 2026-04-08
**Owner:** Lead Engineer
**Type:** Architectural — type-2 reversible

---

## Decision

Email (SMTP via corporate Exchange relay) as primary notification channel.
`NotificationChannel` abstract interface allows Teams webhook to be added later without core changes.

## What Is Deferred

- **SMTP configuration details** (host, port, sender address) — confirm with infrastructure closer to deployment
- **ECN notification recipients per status** — derive from Stargile source code analysis first (`ai/memory/05-stargile-ecn-reference.md`), then validate with Branko once a working POC exists

## Consequences

- `aiosmtplib` is in `requirements.txt` — async SMTP ready for Sprint 2
- SMTP config injected via `.env` (never hardcoded)
- Notification recipient logic will be defined in Track B (ECN Behavioural Spec) before Sprint 2
