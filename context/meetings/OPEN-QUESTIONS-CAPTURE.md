# Open Questions — Capture Sheet
**Meeting:** 2026-04-29 — Karen · Branko · Nick · Hector
**Instructions:** Fill this during the meeting. These outputs directly update `ai/memory/06-ecn-requirements.md §14` and seed `system_role_users` in the database.

---

## Section A — Role Model (Highest Priority — Blocks `system_role_users` Seeding)

| Role | Code | Question | Answer (fill in meeting) |
|------|------|---------|--------------------------|
| Document Controller | DC | Who is DC today — one person or multiple? Can DC be the originator of an ECN? | |
| Senior Engineer | SE | Who is SE? | |
| Chief Engineer | CE | Is CE the same person as SE? (Self-approval risk if yes) | |
| Engineering Manager | EM | Who is EM? | |
| Quality Manager | QM | Who is QM? Melbourne only or also JB? | |
| Production Manager | PM | Nick — does PM approval actually happen for routing changes in Stargile, or is it bypassed in practice? | |
| Supply Chain / Purchasing | SC | Who covers SC? One person or a team? | |
| Finance | FN | Who is FN? Has Finance ever actually blocked an ECN on cost grounds? | |
| Cost Accountant | CA | Who is CA? Observer role only — is this person involved today in Stargile? | |
| R&D / Product Engineering | RD | Who covers RD? Do they want ECN notifications? | |
| Test Engineering | TE | Who is TE? | |
| Manufacturing Quality | MQ | Who covers MQ? | |

**AD Groups needed (confirm with Manal):**
- [ ] OSKAR-Approvers (DC, SE, CE, EM, QM, PM, SC, FN, CA)
- [ ] OSKAR-Engineers (OR, RD, TE, MQ)
- [ ] OSKAR-Admins (AD)

---

## Section B — ECN Volume and Velocity

| Question | Answer |
|----------|--------|
| How many ECNs are raised per month (Melbourne)? | |
| How many ECNs are raised per month (JB)? | |
| How many are typically in-flight at any one time? | |
| What is the typical duration from DRAFT to CLOSED? | |
| What is the longest an ECN has been stuck in flight? | |
| How many are emergency ECNs per month? | |

---

## Section C — Questionnaire Fields (ZQ01–ZQ18)

*These are 18 Yes/No and completion fields in Stargile that we don't have the business meaning for. Fill as many as possible — even partial is useful.*

| Field | Stargile Name | Business Meaning | Mandatory? | When filled? |
|-------|--------------|-----------------|-----------|-------------|
| ZQ01 | | | | |
| ZQ02 | | | | |
| ZQ03 | | | | |
| ZQ04 | | | | |
| ZQ05 | | | | |
| ZQ06 | | | | |
| ZQ07 | | | | |
| ZQ08 | | | | |
| ZQ09 | | | | |
| ZQ10 | | | | |
| ZQ11 | | | | |
| ZQ12 | | | | |
| ZQ13 | | | | |
| ZQ14 | | | | |
| ZQ15 | | | | |
| ZQ16 | | | | |
| ZQ17 | | | | |
| ZQ18 | | | | |

*If Branko can't recall them today, ask him to bring a printed Stargile ECN form to the follow-up session.*

---

## Section D — Workflow and Approval Specifics

| Question | Answer |
|----------|--------|
| Does PM approval actually happen in Stargile for routing changes, or is it always bypassed? | |
| Is there a cost threshold that triggers Finance review? What % WAPC increase? | |
| When Stargile rejects an ECN, does the whole workflow restart or only the rejecting stage? | |
| Has there been a case where preserving prior approvals after a rejection mattered? | |
| Are emergency ECNs handled through Stargile or completely ad-hoc? | |
| When it happens, who is the approving authority — just EM, or DC too? | |
| What PM involvement conditions exist beyond routing changes? | |
| Are RD/TE/MQ currently receiving ECN notifications in Stargile? | |

---

## Section E — BOM and PN Creation Specifics

| Question | Answer |
|----------|--------|
| Is Step 4 (PN creation: commodity code + sequence lookup) still the biggest time sink? | |
| How many new PNs are typically created per new product launch? | |
| What is the commodity code structure? Is there a reference list somewhere? | |
| How often does a wrong UOM get through and require a new PN? | |
| Is the auto-numbering stretch goal important enough to be a POC must-have? | |
| Has the process for PN naming changed since 2019? | |
| Are there cases where the 30-char Movex description limit is still causing rejections? | |

---

## Section F — Compliance and Karen's Decisions

| Question | Answer |
|----------|--------|
| **Karen: What are the go-live go/no-go criteria?** (What does Karen need to see to approve production deployment?) | |
| IQ/OQ/PQ sign-off chain — confirm: Karen=system, Divya=quality, Manal=infra | ☐ Confirmed |
| Who manages the DBCHK_OpenECN SQL Server Agent job on DBSRV? | |
| Is there an ISO audit scheduled for 2026 that should influence the timeline? | |
| Does the transmittal gap (ISO 13485 §7.3.6) need to be resolved before audit? | |

---

## Section G — Infrastructure (Confirm with Karen → Manal)

| Item | Current status | Hard deadline agreed |
|------|---------------|---------------------|
| Linux VM provisioned | ❌ Overdue (~2026-04-17) | |
| LDAPS confirmed | ❌ Overdue (~2026-04-24) | |
| Harbor hostname for container registry | ❌ Overdue (~2026-04-17) | |
| DBCHK_OpenECN disable plan | ⏳ Not started | |

---

## Section H — New Pain Points (Open Floor)

*"What else breaks regularly in Stargile or the BOM upload process that I haven't mentioned?"*

| Pain Point Added | Priority (H/M/L) | OSKAR scope? |
|-----------------|-----------------|-------------|
| | | |
| | | |
| | | |
| | | |
| | | |

---

## Section I — JB vs Melbourne Differences

*If both Branko (Melbourne) and potentially JB are in scope, capture any process differences:*

| Area | Melbourne process | JB process | Same or different? |
|------|-----------------|-----------|-------------------|
| ECN approval roles | | | |
| Commodity codes / PN format | | | |
| BOM upload steps | | | |
| Routing structures | | | |
| MPN consolidation process | | | |

---

## Post-Meeting Actions

| Action | Owner | Deadline |
|--------|-------|---------|
| Update `ai/memory/06-ecn-requirements.md §14` with confirmed open items | Hector | 2026-04-30 |
| Seed `system_role_users` table with confirmed role assignments | Hector | 2026-04-30 |
| Update `ecn_step_conditions` seed row with confirmed FN threshold | Hector | 2026-04-30 |
| Book Branko 1-hour walkthrough (MANAGEMENT_REVIEW + rejection model) | Branko + Hector | Book today |
| Karen escalates VM + LDAPS + Harbor to Manal (hard deadline) | Karen → Manal | Today |
| ADR-009: file attachment storage decision | Hector | 2026-04-30 |
| Draft migration `0005_poc_additions` (ecn_attachments + MPN extended fields) | Hector | 2026-05-01 |
| Capture ISO audit schedule if applicable | Karen | 2026-04-30 |
