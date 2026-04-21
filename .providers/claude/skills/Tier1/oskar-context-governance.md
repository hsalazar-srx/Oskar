# Skill: /oskar-context-governance
**Tier:** 1 — Session governance
**MAS skill:** `knowledge/decision-graph` + `knowledge/assumption-monitor`

## Purpose
Sprint review checkpoint for the OSKAR `ai/` context layer. Ensures the four `ai/` files
reflect current architectural reality. Applies the MAS decision-graph and assumption-monitor
skills scoped to OSKAR decisions.

## Steps

1. Read all four `ai/` files:
   - `ai/memory/01-manufacturing-context.md`
   - `ai/memory/02-movex-erp-authority.md`
   - `ai/memory/03-oskar-architecture.md`
   - `ai/04-pre-decisions.md`

2. For each file, assess: Is this still accurate? What is stale or missing?

3. Check `ai/04-pre-decisions.md` open items table — have any been resolved this sprint?
   Update the table if so.

4. Flag any architectural decision made during the sprint that is NOT yet recorded.
   Use the `decision-graph` skill to create an ADR for any unrecorded type-1 or type-2 decision.

5. Propose surgical edits to stale sections. Do not rewrite entire files.

## 20% Staleness Rule
If more than 20% of any `ai/` file is outdated, that is a sprint review blocker.
Do not mark the sprint review complete until it is corrected.

## OSKAR-specific decisions to watch
- Redis eliminated (ADR-007) — PRE-2 superseded; verify no Redis refs survive in docs
- Auth provider changes (PRE-3)
- ERP adapter scope changes (IFSAdapter status)
- Linux VM vs WSL2 resolution (pending Manal)
- Container registry provisioning (pending Marriat)
- IQ/OQ/PQ sign-off owner (pending Karen)
