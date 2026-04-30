# OSKAR Context Engineering — Analysis Summary

**Status**: Analysis Complete — Awaiting Phase 0 v2.0 Build
**Date**: 2025-XX-XX
**Version**: 2.0 (Git-Native + Hermes-Inspired)
**Source**: Analysis of coleam00/context-engineering-intro, gsd-build/gsd-2, NousResearch/hermes-agent

---

## 1. Context

### 1.1 What We Are Building

**OSKAR** — Engineering Intelligence Platform — is a 24-week modernisation programme to replace two legacy systems:

| Legacy System | Technology | Replaced By |
|---|---|---|
| **Stargate** (ECN management) | Java + Movex MI API | OSKAR ECN module |
| **PLMServer** (BOM + Supplier) | PHP + MySQL | OSKAR BOM module + Supplier Intelligence |

**Target stack**: Python/FastAPI, PostgreSQL 16, Redis 7, Celery, Docker on Windows Server. Integrates with Movex/M3 ERP and future IFS ERP.

**Compliance**: ISO 13485 (medical devices), RoHS/REACH (environmental), ISO 9001 (quality), OWASP/NIST (security).

### 1.2 The Core Problem

Execution layer drift: the AI does not automatically follow the specified process, task structure, or recording conventions unless explicitly prompted. Every task requires re-specification of conventions. The gap is at the **specification layer**, not the tooling layer.

### 1.3 The Motivation

> Creating structure around prompting and using it as an engineering tool to create value.

The goal is a context engineering harness that enforces process automatically — not through reminders, but through structure.

---

## 2. Research Sources

### 2.1 Coleam00 — Context Engineering Intro
**Repository**: `github.com/coleam00/context-engineering-intro`

| Strength | Limitation |
|---|---|
| Multi-level CLAUDE.md enforcement | No execution engine — relies entirely on LLM compliance |
| PRP (Project Requirements & Plan) workflow | No state machine or progress tracking |
| Examples/ folder for reference implementations | No learning loop — static documentation only |
| Slash command pattern | No progressive disclosure |
| Works with any LLM | No bounded memory — context bloat risk |

### 2.2 GSD-2 — Guided Semantic Development
**Repository**: `github.com/gsd-build/gsd-2`

| Strength | Limitation |
|---|---|
| `/gsd auto` — autonomous execution loop | **Fundamentally incompatible with human-in-the-loop requirement** |
| Disk-based state machine | No human approval gate before execution |
| Verification commands with auto-fix retries | No ISO 13485 or compliance concept |
| Phase gate validation | Skills are not first-class — no progressive disclosure |
| Never auto-modify rules | No bounded memory discipline |
| Context pressure monitor | No external skill directory support |

### 2.3 Hermes Agent
**Repository**: `github.com/NousResearch/hermes-agent`

| Strength | Limitation |
|---|---|
| **Agent-curated skills** via `skill_manage` tool | No human approval gate before code generation |
| **Bounded memory** — MEMORY.md (2,200 chars), USER.md (1,375 chars) | No ISO 13485 or manufacturing compliance concept |
| **Progressive disclosure** — skills load on-demand | No git integration |
| **Session search** — FTS5 + LLM summarisation | No manufacturing guardrails |
| **External skill directories** | No Scenario Driven Development |
| **Skills Hub** | No human-in-the-loop checkpoint concept |
| Multi-model native | — |

---

## 3. Comparative Analysis

| Dimension | Coleam00 | GSD-2 | Hermes | OSKAR v2.0 |
|---|---|---|---|---|
| **Execution mode** | LLM compliance | Autonomous | Agent-led | Human-in-the-loop |
| **Learning mechanism** | Manual docs | Auto-modify | Agent-authored skills | Git commits + agent skills + curated synthesis |
| **Memory management** | Static files | Incremental files | Bounded MEMORY.md + USER.md | Bounded MEMORY.md + archive `ai/` |
| **Context loading** | Full load | Per-phase | Frozen snapshot + progressive | Tiered progressive |
| **Skills** | Not native | Not native | First-class, agent-curated | First-class, Hermes-style tiers |
| **Session search** | None | None | FTS5 + LLM | TBD (existing stack?) |
| **Context files** | CLAUDE.md only | Not documented | `.hermes.md`, `AGENTS.md`, `CLAUDE.md` | `.claude/CLAUDE.md` + skills |
| **Manufacturing guardrails** | None | None | None | Built-in non-negotiables |
| **Git integration** | No | Worktree isolation | No | First-class (commit template + tags) |
| **Human approval** | Implicit | Errors only | Implicit | Explicit checkpoints |

---

## 4. Key Decisions

### 4.1 Philosophy

> Git history IS the transaction log. The `ai/` folder is a curated intelligence layer derived from git history, not a parallel record of it.

Standardised commit messages with `WHY`/`RISK`/`REF` fields make git log a queryable institutional knowledge base.

### 4.2 Human-in-the-Loop is Non-Negotiable

ISO 13485 requires non-repudiable human approvals. ERP push operations cannot be performed autonomously.

- GSD-2 autonomous execution model (`/gsd auto`) — **REJECTED ENTIRELY**
- Hermes agent-led skill creation — **ACCEPTED PARTIALLY** (agent creates skills, but checkpoints require human approval)
- `/checkpoint` MUST run before any code generation, integration change, DB schema change, or security-relevant change

### 4.3 Tiered Commit Template

| Commit type | Tier | Requirements |
|---|---|---|
| `chore`, `patch` | 1 | Title only — frictionless |
| `feat`, `fix`, `refactor`, `test`, `docs`, `perf`, `ci` | 2 | `WHAT` + `WHY` minimum |
| `arch`, `risk`, `compliance` | 3 | `ALL fields` + `Approved-by` (hook enforced) |

### 4.4 Hermes Mechanics, OSKAR Governance

| From Hermes | From OSKAR |
|---|---|
| Bounded MEMORY.md + USER.md | Manufacturing non-negotiables (Movex SOT, no direct MI, ISO 13485) |
| Agent-authored Tier 3 skills | Human-in-the-loop checkpoints |
| Progressive disclosure | Git-native audit trail |
| Session search | SDD validation (Scenario Driven Development) |
| External skill directories | Tiered commit template |

### 4.5 Skills — Three Tiers

| Tier | When loaded | Who creates | Examples |
|---|---|---|---|
| **Tier 1 — Essential** | Session start always | Humans (Phase 0) | `oskar-session-protocol`, `oskar-iso-13485`, `oskar-sdd-template` |
| **Tier 2 — Relevant** | Relevant context detected | Humans + Agent (Phase 1+) | `oskar-ecn-state-machine`, `oskar-erp-boundary` |
| **Tier 3 — Discovered** | Agent encounters pattern | **Agent creates** | `oskar-mi-gap-workaround`, `oskar-digikey-circuit-breaker` |

**Key**: Tier 3 skills are not planned in advance. They emerge from the agent experience. The harness gives the agent a place to save what it learns and a mechanism to load it back when relevant.

---

## 5. Final Architecture — OSKAR v2.0

```
C:\Projects\Oskar\
├── .claude/
│   ├── CLAUDE.md                      # Enforcement layer
│   ├── MEMORY.md                      # Agent memory — bounded (2,200 chars)
│   ├── USER.md                        # User profile — bounded (1,375 chars)
│   ├── commands/
│   │   ├── session-start.md           # Session init protocol
│   │   ├── checkpoint.md              # SDD validation checkpoint
│   │   └── log-decision.md           # Decision capture format
│   └── skills/                        # OSKAR-specific skills (Tier 1-3)
│
├── .githooks/
│   └── commit-msg                     # TIER 3 enforcement only
├── .gitmessage                        # Tiered commit template
├── .oskar/
│   ├── oskar-state.json               # Machine-readable state
│   ├── oskar-state.md                 # Human-readable state
│   └── VERIFICATION.yaml              # Verification commands per task type
├── ai/                                # Curated intelligence — static reference
│   ├── 00-project-vision.md
│   ├── 01-manufacturing-context.md
│   ├── 02-system-architecture.md
│   ├── 03-integration-contracts.md
│   ├── 04-governance-and-decisions.md
│   ├── 05-standards-security-quality.md
│   ├── 06-known-risks-and-pitfalls.md
│   ├── 07-product-roadmap.md
│   ├── 09-lessons-learned.md
│   └── 10-model-reference.md
├── prps/                              # Phase/sprint PRPs — static reference
├── examples/                          # Reference implementations
└── context/
    └── OSKAR_Platform_Strategy_v2.md
```

---

## 6. Hard Constraints — Non-Negotiables

1. **Movex is the source of truth** for committed production BOMs. OSKAR owns workflow only.
2. **No direct MI API calls**. All ERP operations go through movex-rest-api over HTTP.
3. **ISO 13485 audit trail** on ALL ECN state changes — must be logged automatically.
4. **No code without `/checkpoint`**. SDD validation template must be completed and human-approved before any code generation.
5. **ERP push confirmation**. Any push to movex-rest-api or IFS requires explicit human confirmation.
6. **No secrets in logs**. Credentials, API keys, tokens are never logged or displayed.
7. **Never auto-modify rules**. Any update to CLAUDE.md or protocols requires human review and approval.
8. **Context pressure awareness**. At high context usage, commit durable output before continuing.
9. **No autonomous execution**. `/gsd auto` and equivalent autonomous modes are explicitly prohibited.

---

## 7. Key Insights from the Analysis

### 7.1 Execution Layer Drift is a Specification Problem

The AI does not follow the process unless prompted. The solution is a **session init protocol** that runs automatically at every session start:

1. Read oskar-state.md → determine current phase and sprint
2. Read MEMORY.md → current state, known patterns, known gaps
3. Read lessons-learned (if applicable) → mistakes to avoid
4. Confirm with human → "Starting Sprint X, Phase Y. Building [description]. Correct?"

### 7.2 Git History IS the Transaction Log

```bash
git log --grep="RISK" --all           # All risky decisions
git log --grep="13485" --all         # Compliance-relevant changes
git log --since="2025-01-01"         # Recent decisions
git blame -- src/ecn/adapter.py      # Why was this written this way?
```

Git tags mark phase gates: `phase1-discovery-gate`, `phase2-architecture-gate`, etc.

### 7.3 The `ai/` Folder is the Archive, Not the Log

- **MEMORY.md** — bounded (2,200 chars), always in context, agent-curated
- **`ai/` folder** — long-term reference, updated at defined cadence (sprint review), not session-by-session

### 7.4 Agent-Curated Skills Close the Learning Loop

The agent discovers a pattern → saves it as a skill → future sessions load it automatically. Phase 0 pre-writes Tier 1 skills. The agent writes Tier 3 skills during implementation.

### 7.5 Progressive Disclosure Prevents Context Bloat

The session starts with MEMORY.md (bounded, always loaded) and Tier 1 skills. Tier 2 and Tier 3 skills load progressively based on context.

---

## 8. Changes from v1.0 to v2.0

| OSKAR v1.0 | OSKAR v2.0 | Why |
|---|---|---|
| Unbounded `ai/` folder | Bounded MEMORY.md + archive `ai/` | Prevents context bloat, enforces curation |
| `ai/08-execution-log.md` | **Dropped** — git log IS the log | Session search (Hermes) replaces manual logging |
| `ai/09-lessons-learned.md` — manual retrospective log | Curated synthesis from git + session search | Agent discovers; human synthesises |
| All `ai/` files loaded at session start | **Progressive disclosure** — only relevant skills load | Token efficiency, relevance |
| Slash commands only | **Skills as slash commands** | Hermes-native pattern, discoverable |
| Everything pre-written by humans | **Tier 3 skills — agent-authored** during Phase 1+ | Learning loop closes — agent teaches future sessions |
| Workspace skills as external reference | **External skill directories** | No duplication, workspace knowledge propagates |

---

## 9. Phase 0 Build — What to Create

### Tier 1 Skills (Pre-written in Phase 0)

| Skill | Purpose | Key Content |
|---|---|---|
| `oskar-session-protocol.md` | Session init enforcement | Step-by-step session start protocol |
| `oskar-erp-boundary.md` | ERP integration rules | Movex SOT, no direct MI, movex-rest-api only |
| `oskar-iso-13485.md` | Compliance requirements | Audit trail rules, approval requirements |
| `oskar-sdd-template.md` | Validation checkpoint | SDD scenarios, rollback, risk check |
| `oskar-commit-guide.md` | Commit protocol | Tiered template summary, hook enforcement |

### Tier 2 Skills (Revealed During Phase 1)

Created when the agent first implements: ECN state machine, BOM workflow, ERP adapter, supplier adapter.

### Tier 3 Skills (Agent-Authored During Implementation)

Created when the agent encounters a non-trivial pattern: MI gap workaround, DigiKey circuit breaker, IFS mock pattern, M3 lookup pattern.

---

## 10. Outstanding Questions

| Question | Impact | Priority |
|---|---|---|
| Does the current AI stack support dynamic skill creation? | Determines whether Tier 3 agent-authored skills are achievable | High |
| Is there an existing session search capability? | Determines how to implement cross-session recall | High |
| State machine format — JSON / Markdown / Hybrid? | Affects `.oskar/` implementation | Medium |
| External skill directory support? | Determines workspace skill integration | Medium |

---

## 11. References

| Source | Location | Key Takeaway |
|---|---|---|
| OSKAR Platform Strategy v2 | `C:\Projects\SuperTool\context\OSKAR_Platform_Strategy_v2.md` | Full programme scope, architecture, risks |
| Context Engineering Intro | `github.com/coleam00/context-engineering-intro` | CLAUDE.md enforcement, PRP pattern |
| GSD-2 | `github.com/gsd-build/gsd-2` | State machine, verification commands, phase gates |
| Hermes Agent | `github.com/NousResearch/hermes-agent` | Bounded memory, agent skills, progressive disclosure |
| Workspace CLAUDE.md | `C:\Projects\.claude\CLAUDE.md` | Inherited enforcement rules |
| Workspace skills | `C:\Projects\.github\skills\` | Shared workspace skills |
| Knowledge Vault | `C:\Projects\Knowledge-Management\` | `/m3-lookup`, `/adr`, `/runbook` skills |

---

## 12. Next Steps

1. **Resolve outstanding questions** — AI stack skill creation, session search capability
2. **Build Phase 0 v2.0** — Create full directory structure, skills, CLAUDE.md, commit template, state machine
3. **Validate harness** — Run `/session-start`, `/checkpoint` manually; verify hook enforcement
4. **Begin Phase 1** — MI gap analysis (Track A), ECN/BOM spec (Track B), adapter interfaces (Track C)
5. **Observe agent behaviour** — Identify first Tier 3 skill creation opportunities
6. **Update workspace manifests** — Register OSKAR skills and agents in `C:\Projects\.github\`
