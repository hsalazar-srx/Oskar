# Skill: /oskar-iso-compliance
**Tier:** 1 — Compliance and audit
**MAS skills:** `knowledge/compliance-tracker`, `architecture/audit-logging-framework`, `security/security-auditor`

## Purpose
ISO 13485 IQ/OQ/PQ checklist for OSKAR iterations. Audit chain review. Gate-check before
sign-off. Applies MAS compliance-tracker scoped to OSKAR medical device manufacturing context.

---

## IQ/OQ/PQ Structure Per Iteration

### IQ — Installation Qualification
Confirms the system is installed as specified.

- [ ] Docker Compose stack deployed on target environment (Linux VM or WSL2 with documented risk acceptance)
- [ ] All environment variables set and validated (no hardcoded secrets)
- [ ] PostgreSQL 16 running, schema migrations applied
- [ ] PostgreSQL Celery broker tables present (`kombu_message`, `celery_taskmeta`) — ADR-007: Redis eliminated
- [ ] IIS reverse proxy configured with ADCS certificate (Manal sign-off)
- [ ] LDAP connectivity verified against on-prem AD
- [ ] Backup procedure documented and test restore executed (Manal sign-off)
- [ ] Container image pulled from registry (ACR or GHCR)
- [ ] **Sign-off owner: [TBD — Karen to confirm]** ← blocking item

### OQ — Operational Qualification
Confirms the system operates within defined limits.

- [ ] All `/api/v1/` endpoints return expected responses for nominal inputs
- [ ] Authentication: valid LDAP credentials → JWT issued; invalid credentials → 401
- [ ] ECN approval chain advances correctly through all configured approvers
- [ ] SHA-256 audit chain produces valid hash chain (verify with test harness)
- [ ] `jti_blocklist` and `refresh_tokens` tables present and accessible (ADR-007: Redis session store replaced)
- [ ] Celery task queue processes supplier API calls (1 real adapter + 5 stubs)
- [ ] Email notification sent on ECN status change (SMTP relay confirmed)
- [ ] Staging environment mirrors production (port 8001 stack)

### PQ — Performance Qualification
Confirms the system performs under expected production load.

- [ ] ECN workflow: create → submit → approve → release completes in < 5 seconds end-to-end
- [ ] 10 concurrent ECN submissions handled without error
- [ ] PostgreSQL query time for ECN list (100 records) < 500ms
- [ ] Celery worker processes 100 task dispatches/minute sustained without queue backlog (PostgreSQL broker)
- [ ] IIS proxy handles 50 concurrent requests without 5xx errors

---

## Audit Chain Verification Checklist

For every ECN that reaches `status=released`:

- [ ] SHA-256 chain is unbroken from ECN creation to release
- [ ] Each link contains: event_id, timestamp, actor (LDAP-verified), agent_suggestion, human_decision, movex_commit
- [ ] `sha256_prev` of each record matches `sha256_self` of the preceding record
- [ ] No gap in chain sequence numbers

---

## Sign-off Conflict Note
**ISO 13485 requires the sign-off owner to be independent of the system author.**
The Lead Engineer cannot sign their own IQ/OQ/PQ. Karen has been asked to confirm
the named sign-off owner. This is a blocking gate condition for Iteration 1 go-live.
Track in `ai/04-pre-decisions.md` open items until resolved.
