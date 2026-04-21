# OSKAR — Manufacturing and Organisational Context

> **PROVIDER-AGNOSTIC — Non-Negotiable #12**
> This file contains no tool-specific syntax. It is readable and actionable by any LLM tool
> (Claude, Cursor, Copilot, Ollama, or none). If content is Claude Code-specific, it belongs
> in `.providers/claude/` — not here.

---

## 1. Company — Scanfil APAC (JB, Malaysia)

| Fact | Detail |
|------|--------|
| Company name | Scanfil APAC |
| Scope | Australia and Malaysia branches (formerly SRXGlobal Australia + SRXGlobal Malaysia). Previous entities include Suzhou (China) and Penang operations. |
| Primary OSKAR site | Johor Bahru (JB), Malaysia |
| Headcount | ~170 personnel (JB) + Penang CPO — OSKAR user base ~50 (engineering team) |
| Floor area | ~6,150 m² |
| Certifications — Australia (Melbourne) | ISO 9001:2015 · ISO 13485:2016 · ISO 14001:2015 |
| Certifications — Malaysia (JB) | BS EN ISO 9001:2015 · BS EN ISO 14001:2015 · BS EN ISO 13485:2016 · IATF 16949:2016 |
| SMT lines | 4 lines, expansion planned |
| Markets | Industrial, Automotive, Cleantech, Medical devices |
| Parent group | Scanfil Group (Finnish-listed EMS, ~797 MEUR turnover 2025, 16 sites, 10 countries) |
| Acquisition | Scanfil Group acquired SRXGlobal in 2024, absorbing the Australia and Malaysia branches into Scanfil APAC |

---

## 2. Scanfil Group Context

- **QSDC framework:** All decisions and KPIs framed as Quality, Satisfaction, Delivery, Cost.
- **SCI methodology:** Scanfil Continuous Improvement — Lean/Six Sigma culture.
- **Group IT contact:** Maarit (Scanfil Group ICT) — leverage for shared infrastructure, Azure subscription, security frameworks, cross-site alignment.
- **ERP direction:** IFS migration planned for JB site (date TBD). Movex/M3 is current ERP and remains SSoT for OSKAR v1.
- **Dream Factory mandate:** JB is expected to become a Dream Factory site. This is a Group-level expectation, not a local aspiration.

---

## 3. Dream Factory 2026 Roadmap

| Item | Schedule | OSKAR Relationship |
|------|----------|-------------------|
| Shopfloor Digitalisation | 2026 Q1 | ECN module provides engineering change traceability |
| Big Data / Power BI Advanced | 2026 Q2 | PostgreSQL event data (LISTEN/NOTIFY path) feeds real-time engineering events into BI (ADR-007: Redis eliminated; upgrade path documented) |
| Modernisation Shopfloor Upgrade | 2026 Q2 | BOM module provides version-controlled BOM data |
| AI Solution for AOI Inspection | 2026 Q2–Q3 | MAS agent architecture scales to AOI integration |
| EDI and RPA for Smart Office | 2026 Q4 | OSKAR platform (FastAPI, PostgreSQL, Celery) is the backend for EDI/RPA |
| Lean and Six Sigma Culture | 2026 Q4 | Audit trail and ECN efficiency data feeds CI metrics |

---

## 4. Stakeholder Map

| Name | Role | Primary Interest | OSKAR Engagement |
|------|------|-----------------|-----------------|
| Christian Kesten | Regional GM / VP APAC | Dream Factory delivery, OTD KPI | Phase gate reviews — frame OSKAR as Dream Factory pillar |
| Karen | IT General Manager | Stable systems, budget control, DISP compliance | Strategy approval; IQ/OQ/PQ sign-off owner (TBD) |
| Bryan | Regional Integration Engineer | OTD, integration architecture | Architecture review; ERP adapter design |
| Branko | Lead Engineer | ECN/BOM process; engineering workflow | SME — validate POC once built. Do not approach for requirements gathering; process is fully documented from Stargile source code and prior session transcripts (2016, 2018). |
| Nick | Production Manager | OTD, shopfloor reliability | SME — validate POC once built. Engage post-POC alongside Branko. |
| Manal | Infrastructure Manager | Server stability, network, certificates | Docker host; backup/DR owner; staging environment owner |
| Maarit | Scanfil Group ICT | Group alignment, Azure, security | Azure subscription; DISP compliance; cross-site templates |

---

## 5. QSDC Framing (use in all stakeholder communication)

Always express OSKAR value in QSDC terms, not technology terms:

| QSDC | OSKAR Contribution |
|------|-------------------|
| **Quality** | ISO 13485 audit chain; immutable SHA-256 ECN history; human-in-the-loop approval |
| **Satisfaction** | Engineer workflow — ECN processing time reduced; BOM accuracy improved |
| **Delivery** | OTD impact — faster engineering change propagation to production |
| **Cost** | Replaces two legacy systems; foundation prevents future duplication |

---

## 6. Current Systems Being Replaced

| System | Technology | Function | Status |
|--------|-----------|---------|--------|
| Stargile | Java | ECN (Engineering Change Notice) management | Mandatory decommission — target ~June/July 2026 | Purchase Planners Workbench
| PLMServer | PHP | BOM management + Supplier Intelligence | Mandatory decommission — same timeline | 

Both systems are in active use. OSKAR must provide functional equivalence before cutover. No hard date mandated by management as of 2026-04-07 — Karen confirmed "the quicker the better."

---

## 7. Key Business Rules

- **Movex/M3 is the Single Source of Truth — always, without exception.** OSKAR is the workflow and intelligence overlay. It never competes with Movex data. The ECN DB is not part of Movex but is the SSOT for ECN Management and Product Lifecycle Management is the frontend to Movex data
- **Human-in-the-loop is non-negotiable.** No engineering change may be committed to Movex without explicit human approval. AI assists; humans decide.
- **ISO 13485 traceability required.** Every ECN, BOM change, and supplier signal that influences an engineering decision must be traceable from AI suggestion → human decision → Movex commit.
- **ISO 27001 compliance** Is part of the scope (todo)
- **IFS migration is out of scope for OSKAR v1.** Confirmed by Karen 2026-04-07. IFSAdapter = stub only. Design against Movex semantics throughout.
