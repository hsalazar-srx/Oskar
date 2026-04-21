# Skill: /oskar-session-protocol
**Tier:** 1 — Session lifecycle
**MAS skills:** `knowledge/decision-graph`, `knowledge/assumption-monitor`

## Purpose
Structured start/end protocol for every OSKAR development session.
Prevents context drift and ensures open items are never silently dropped.

---

## Session Start

1. Read `ai/04-pre-decisions.md` — check open items table. Any resolved since last session?
2. Read `ai/memory/03-oskar-architecture.md` — confirm current deployment target (Linux VM vs WSL2).
3. State the session goal in one sentence.
4. Identify which Non-Negotiables apply to today's work (from `CLAUDE.md`).

## Session End

1. List what was decided or changed today.
2. For each decision: does it affect any `ai/` file? If yes — update it now, not later.
3. Any new open items discovered? Add to `ai/04-pre-decisions.md` open items table.
4. Generate a commit message using `/oskar-commit-template` for any `ai/` file changes.
5. One sentence: what is the next session's first task?

---

## State File
Maintain `oskar-state.md` in the project root for cross-session continuity:

```markdown
# OSKAR Session State
**Last updated:** YYYY-MM-DD
**Current sprint:** Phase 0 / Sprint N
**Active track:** Track A / Track B

## In Progress
- [ ] task

## Next Session
- First task: ...

## Blocked On
- item → owner → expected by
```

Update `oskar-state.md` at every session end.
