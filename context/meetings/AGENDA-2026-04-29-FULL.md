# OSKAR Platform — Stakeholder Review Meeting
**Date:** 2026-04-29
**Attendees:** Karen (IT GM) · Branko (Lead Engineer / UAT Lead) · Nick (Production Manager) · Hector (Development Lead)
**Duration:** 90 minutes
**Location:** TBC
**Supporting docs (this folder):** ECN-WORKFLOW-DIAGRAM · STARGILE-VS-OSKAR · VSM-RESOLUTION-MAP · POC-SCOPE-FOR-KAREN · OPEN-QUESTIONS-CAPTURE

---

## Meeting Objective

This is a **dual-purpose session**:
1. **Karen** — strategic alignment: confirm POC go/no-go criteria, timeline, and compliance posture
2. **Branko + Nick** — engineering validation: confirm the ECN workflow design reflects operational reality, surface any gaps before Sprint 2 starts

**The goal is not to present. It is to leave with signed-off POC scope and confirmed ground truth from the people who live the process.**

---

## Why Karen's Attendance Matters

The original meeting was engineering-only. Karen being in the room changes the decision authority in the room. Three things that required email follow-up can now be resolved live:
- POC go/no-go criteria (what Karen needs to see before sanctioning go-live)
- Timeline to production (June/July 2026 target)
- IQ/OQ/PQ sign-off chain confirmation (Karen = system/process owner)

---

## Agenda

| Time | Segment | Lead | Audience Focus |
|------|---------|------|---------------|
| 0:00 | **1. Context set — why we're here** | Hector | All |
| 0:07 | **2. Strategic brief — QSDC framing** | Hector | Karen |
| 0:17 | **3. VSM walkthrough — what we know about your pain** | Hector | Branko + Nick |
| 0:35 | **4. ECN workflow validation** | Hector + Branko | Branko (lead) |
| 0:55 | **5. POC scope alignment** | Hector | All |
| 1:10 | **6. Open questions capture** | All | All |
| 1:20 | **7. Close + next actions** | Hector | All |

---

## Segment 1 — Context Set (7 min)

**Purpose:** Establish shared vocabulary and frame the session.

Opening statement (2 minutes — say this verbatim or close to it):

> "Stargile is already decided — it's going away for infrastructure reasons. What I've done over the last two months is analyse the full Stargile source code — 424 files — and reconstruct exactly how it works, what it gets right, and where it causes problems. I've also studied the 2019 Melbourne VSM from Branko and Nick's team, which maps every step engineers go through for a BOM upload.
>
> What I want to do today is three things: show Karen where the project stands and what the compliance posture looks like; show Branko and Nick how much of their VSM pain OSKAR eliminates and where we still have gaps; and get the open questions answered so Sprint 2 starts on solid ground."

Then show the **scorecard** (from the Gap Analysis doc or spoken):
- 8 Stargile issues: fully eliminated
- 7: partially addressed
- 7: in Oskar scope, not yet built
- 3 critical ISO 13485 risks: being closed in Sprint 2

---

## Segment 2 — Strategic Brief for Karen (10 min)

**Reference doc:** `POC-SCOPE-FOR-KAREN.md`

Cover these four points. Keep each to 2 minutes. Don't go deeper unless Karen asks:

### 2.1 What is being replaced and why
- Stargile (Java, IE9-only, no audit trail) → OSKAR ECN module
- PLMServer (PHP, MySQL) → OSKAR BOM module (Iteration 2)
- Both systems are in active use; cutover target: June/July 2026 for ECN

### 2.2 QSDC framing (one slide worth of content)

| QSDC | How OSKAR delivers |
|------|-------------------|
| **Quality** | ISO 13485 SHA-256 audit chain; no post-completion edits; duplicate sequence validation |
| **Satisfaction** | Engineers get one screen instead of 4 templates; no IE9; no Movex manual login for item creation |
| **Delivery** | Parallel approval block replaces sequential; overdue escalation prevents stuck ECNs |
| **Cost** | Replaces two legacy systems; engineering time savings on BOM upload estimated at 2–4 hours per new product |

### 2.3 Sprint status
- Sprint 1 complete: auth, ECN CRUD, workflow state machine, 48 automated tests passing
- Sprint 2: Celery Movex writes, parallel approval block, email notifications
- POC target: June/July 2026 (Branko + Nick UAT window)

### 2.4 Karen's decisions needed today
- Confirm IQ/OQ/PQ sign-off chain (see Segment 6)
- Confirm go-live go/no-go criteria: what does Karen need to see in POC to approve production deployment?
- Confirm DBCHK_OpenECN job disable date (must coordinate with Infrastructure)

---

## Segment 3 — VSM Walkthrough (18 min)

**Reference doc:** `VSM-RESOLUTION-MAP.md`

**Do not read through all 12 steps.** Hit the 5 highest-impact ones and let Branko/Nick redirect.

### Lead with what you already know hurts

> "I went through your 2019 VSM. Here are the five steps that look most painful based on the analysis. Tell me if I've got the priority wrong."

**Step 4 — PN creation: 5-10 minutes per part, manual sequence lookup, 30-char Movex limit**
- Show: Oskar captures the PN format and will automate sequence lookup (stretch goal for POC)
- Ask: "Is Step 4 still the single most time-consuming step in a new product launch?"

**Step 6 — BOM upload: manual SMT/TH/Mechanical/Packing classification, no error checking in Stargile**
- Show: `ecn_bom_changes.operation_number` field exists; auto-classification is a stretch goal
- Ask: "How often does a wrong operation number get through? What's the rework cost?"

**Stargile Issue #5 — Duplicate sequence numbers corrupt BOM silently (risk: wrong component ordered)**
- Show: Oskar validates and rejects duplicate sequences before submission
- State: "This was a direct medical device compliance risk. It's closed."

**Stargile Issue #14 — 4 separate ECNs required for items/routes/BOM/MPN**
- Show: Oskar unifies all four in a single ECN record
- Ask: "Roughly how many extra ECNs does this generate per new product today?"

**Stargile Issue #18 — MSL, shelf life, EOL, Do Not Buy fields missing**
- Show: Five new nullable columns on `ecn_mpns` (Sprint 2 migration)
- Ask: "Which of these is most critical for you — MSL? EOL? Do Not Buy?"

**Then open the floor:**

> "That's the five I identified as highest impact. What have I missed? What else breaks regularly?"

*Capture everything they add in the capture sheet (`OPEN-QUESTIONS-CAPTURE.md`).*

---

## Segment 4 — ECN Workflow Validation (20 min)

**Reference doc:** `ECN-WORKFLOW-DIAGRAM.md`

This is Branko's session. Let him lead. Your role is to ask questions and capture corrections.

### 4.1 Show the state machine (5 min)
Show the diagram from `ECN-WORKFLOW-DIAGRAM.md`. Walk through:
- DRAFT → SUBMITTED → DC_REVIEW → ENGINEERING_REVIEW → MANAGEMENT_REVIEW (parallel) → APPROVED → IMPLEMENTED → CLOSED
- Highlight: REJECTED, ON_HOLD, CANCELLED paths
- Highlight: Movex writes happen ONLY at APPROVED — not before

Key message: *"Statuses 50 and 60 in Stargile ('MOVEX_UPDATED_PENDING' / 'ACTION_NOTIFICATION_PENDING') are infrastructure, not user-visible states. OSKAR makes Movex the result of approval, not a separate manual step."*

### 4.2 Validate the role model (10 min)
Show the role table. Confirm each role maps to a real person today:

| Role | Question to ask |
|------|----------------|
| DC (Document Controller) | "Who is DC today — one person or a team? Can they be the originator of an ECN?" |
| SE / CE | "Is SE and CE ever the same person? If so, the self-approval rule needs to be discussed." |
| PM (Production Manager) | "Nick — does PM approval actually happen for routing changes in Stargile, or is it bypassed?" |
| SC (Supply Chain) | "Who covers SC / Purchasing? Is there one named person?" |
| FN (Finance) | "Has Finance ever blocked an ECN on cost grounds? What % WAPC delta triggers it?" |
| EM (Engineering Manager) | "Who is EM today?" |

### 4.3 Validate the parallel approval block (5 min)
Key question: *"In Stargile today, does management approval happen sequentially or simultaneously? The system we've built fires all required approvers at the same time — is that how it should work?"*

Show the approval chain diagram.

---

## Segment 5 — POC Scope Alignment (15 min)

**Reference doc:** `POC-SCOPE-FOR-KAREN.md`

### 5.1 POC must-haves (show the 7-item list)
Walk through the 7 must-have POC features:
1. End-to-end ECN with live Movex write (Celery outbox)
2. Parallel MANAGEMENT_REVIEW with conditional role skipping
3. Rejection flows (restart vs proceed)
4. Open ECN dashboard (replacing DBCHK_OpenECN)
5. File attachment on ECN
6. MPN extended fields (MSL, shelf life, EOL, Packaging, Do Not Buy)
7. "View Items" screen with live Stock on Hand from Movex

Ask: **"Is there anything on this list that doesn't matter to you? Anything missing that would make the POC a no-go?"**

### 5.2 Two data model changes happening in Sprint 2

Brief and non-technical:
- New `ecn_attachments` table (file uploads directly on ECN)
- 5 new fields on MPN records (MSL, shelf life, EOL, packaging, Do Not Buy)

Ask: **"Are there other MPN fields you track today in spreadsheets that should be in here?"**

### 5.3 Timeline check

| Milestone | Target | Owner |
|-----------|--------|-------|
| Sprint 2 complete (Celery, parallel approvals, email) | May 2026 | Hector |
| File attachment + MPN fields migration | May 2026 | Hector |
| POC demo ready (all 7 must-haves) | June 2026 | Hector |
| Branko + Nick UAT window | June/July 2026 | Branko + Nick |
| Go-live (Stargile read-only) | July 2026 | All |
| Linux VM provisioned | **Required now** | Manal |
| LDAPS confirmation | **Required now** | Manal |

Escalate the VM + LDAPS items explicitly. These are blocking Sprint 2 deployment.

---

## Segment 6 — Open Questions Capture (10 min)

**Reference doc:** `OPEN-QUESTIONS-CAPTURE.md`

Work through the capture sheet. Highest priority items:

| # | Question | Critical for |
|---|---------|-------------|
| 1 | Who is the DC today — one person or multiple? | Auto-assignment at ECN creation |
| 2 | ZQ01–ZQ18 field meanings — what are these 18 questionnaire fields for? | `questionnaire_data JSONB` schema |
| 3 | FN cost threshold — what % WAPC delta triggers Finance review? | `ecn_step_conditions` seed data |
| 4 | Restart vs Proceed rejection preference — which should be the default? | UI design |
| 5 | IQ/OQ/PQ sign-off chain — confirmed: Karen (system), Divya (quality), Manal (infra) | C-2 compliance track |
| 6 | Karen's go/no-go criteria for POC | Production approval gate |
| 7 | DBCHK_OpenECN disable date — who manages the SQL Server Agent job on DBSRV? | Go-live checklist |

*Do not skip item 6. This is the most important output from Karen in the room.*

---

## Segment 7 — Close + Next Actions (10 min)

### Decisions to confirm before leaving

| Decision | Owner | By when |
|----------|-------|---------|
| ADR-009: File attachment storage (local volume for POC) | Hector | Today |
| Sprint 2 start date | Hector | Today |
| Branko 1-hour workflow walkthrough (before Sprint 2) | Branko + Hector | Book date today |
| LDAPS + VM escalation to Manal | Hector → Karen | Today |
| DBCHK_OpenECN disable notification to Infrastructure | Karen | Before go-live |

### What you're taking home

Fill the output capture table in `OPEN-QUESTIONS-CAPTURE.md`. These are the deliverables:
- Confirmed role assignments → seed `system_role_users` table
- ZQ01–ZQ18 field definitions → `questionnaire_data` JSONB schema
- FN threshold → `ecn_step_conditions` seed row update
- Additional VSM pain points not in the analysis → potential Sprint 3+ scope
- Karen's go/no-go criteria → written into IQ/OQ/PQ sign-off document

---

## Handle These Carefully

**If Karen asks "when is this going live?"**
> "We're targeting late June–early July for the ECN module. That's dependent on Manal's Linux VM and LDAPS — both are overdue. Once I have the VM, I can give you a firm date."

**If Branko asks about IFS migration**
> "OSKAR is designed with an ERP adapter layer — the Movex integration and a future IFS integration are separate code paths. When the IFS migration happens, we update the adapter. Zero OSKAR rework."

**If Nick asks about MTS integration (Steps 11–12 from the VSM)**
> "MTS integration is outside OSKAR scope for v1 — that's a production planning system boundary. What OSKAR does is make the BOM that feeds MTS more accurate and traceable. If the MTS integration becomes a priority, we can scope it as Iteration 4."

**If someone asks "what about Stargile ECNs that are still open?"**
> "Two-week drain period before go-live. Engineers push open ECNs to completion. Anything not closed gets cancelled in Stargile and re-raised in OSKAR. Stargile goes read-only — not off immediately. Historical ECNs are imported as closed records."

**Do NOT raise:**
- Project rename considerations
- IFS migration timeline details beyond the adapter answer above
- OpenBao secrets vault (post-go-live item)

---

## What Success Looks Like

You leave the meeting with:
- [ ] Karen's confirmed go/no-go criteria for the POC (written down)
- [ ] Role table populated with real names for all 9 active roles
- [ ] FN cost threshold confirmed
- [ ] ZQ01–ZQ18 field list started (even partial)
- [ ] Branko's 1-hour walkthrough booked
- [ ] VM + LDAPS escalated to Karen
- [ ] At least one new pain point captured that wasn't in the VSM or Stargile issues list
