# Oskar Platform — Engineer Onboarding Workshop

**Date:** _(fill in)_  
**Facilitator:** Hector Salazar  
**Duration:** 4 hours (half-day) + optional 1-hour hands-on lab  
**Audience:** Software engineers joining the Oskar project  
**Location / Meeting link:** _(fill in)_

---

## Pre-Workshop Checklist (Facilitator)

- [ ] Ensure every attendee has VPN + AD credentials
- [ ] Confirm PostgreSQL dev instance is reachable (`apac-plm-ops.srxglobal.local:5432`)
- [ ] Confirm backend + frontend dev stack starts cleanly (`docker compose -f docker/docker-compose.dev.yml up`)
- [ ] Share `workshop/04-LAB-GUIDE.md` with attendees 24 h before
- [ ] Send `.env.example` → each attendee fills in their local secrets via `dotnet user-secrets` (backend) or `.env.local` (frontend)

---

## Agenda

| # | Time | Block | Resource |
|---|------|-------|----------|
| 1 | 00:00–00:15 | Welcome & context — why Oskar exists | `01-SLIDE-OUTLINE.md` §1 |
| 2 | 00:15–00:45 | System architecture deep-dive | `02-DIAGRAMS.md` |
| 3 | 00:45–01:15 | ECN domain & workflow walk-through | `03-ECN-WALKTHROUGH.md` |
| — | 01:15–01:30 | **Break** | |
| 4 | 01:30–02:00 | Data model & compliance controls | `05-DATA-MODEL-REFERENCE.md` |
| 5 | 02:00–02:30 | Backend internals (FastAPI, Celery, adapters) | `01-SLIDE-OUTLINE.md` §4 |
| 6 | 02:30–03:00 | Frontend internals (React, SSE, role-based UI) | `01-SLIDE-OUTLINE.md` §5 |
| — | 03:00–03:15 | **Break** | |
| 7 | 03:15–03:45 | Development workflow, ADRs, testing | `01-SLIDE-OUTLINE.md` §6 |
| 8 | 03:45–04:00 | Security, compliance, known risks | `01-SLIDE-OUTLINE.md` §7 |
| — | 04:00–05:00 | **Optional hands-on lab** | `04-LAB-GUIDE.md` |

---

## Learning Objectives

By the end of this workshop, every engineer will be able to:

1. Explain what an ECN is, why it exists in manufacturing, and how Oskar differs from Stargile
2. Trace an ECN from DRAFT → CLOSED through all approval gates
3. Identify which role is responsible for each step and what the compliance requirements are
4. Navigate the codebase: find a router, service, adapter, and migration
5. Write a workflow transition test using `ECNWorkflowMachine` and pytest fixtures
6. Use the API via curl/Swagger to create an ECN, submit it, and approve a role step
7. Understand where secrets live (user-secrets / Key Vault) and what never to hardcode

---

## Materials Index

| File | Purpose |
|------|---------|
| `00-WORKSHOP-AGENDA.md` | This file — schedule & objectives |
| `01-SLIDE-OUTLINE.md` | Presentation speaker notes (7 sections) |
| `02-DIAGRAMS.md` | Mermaid architecture diagrams (system context, state machine, data flow, deployment) |
| `03-ECN-WALKTHROUGH.md` | Step-by-step ECN lifecycle narrative |
| `04-LAB-GUIDE.md` | Hands-on lab exercises with commands |
| `05-DATA-MODEL-REFERENCE.md` | Table reference card + ERD |
| `06-API-CHEATSHEET.md` | curl quick-reference for all key endpoints |

---

## Questions to Prime Discussion

Distribute these before the workshop to get engineers thinking:

1. What would happen if an ECN was written to Movex before all approvers had signed off?
2. Why is the approval routing driven by a database table rather than hardcoded `if` statements?
3. How does the system guarantee that an auditor can reconstruct the full history of an ECN two years later?
4. What happens if the Celery worker crashes between writing the `movex_outbox` row and making the MI call?
5. How does the frontend know which action buttons to show without re-fetching the full approval state on every click?
