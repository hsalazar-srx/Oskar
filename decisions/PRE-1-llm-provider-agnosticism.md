# PRE-1 — LLM Provider Agnosticism

**Status:** Accepted — Final for OSKAR v1
**Date:** 2026-04-08
**Owner:** Lead Engineer
**Type:** Architectural — type-1 (hard to reverse once ai/ content accumulates)

---

## Decision

Two-layer structure. `ai/` is provider-neutral. `.providers/` is thin and swappable.

No tool-specific syntax inside any `ai/` file. Claude Code instructions, skill files,
and `/skill` invocations belong in `.providers/claude/` only.

## Rationale

OSKAR is a 3–5 year platform. Claude pricing will change. In-house AI Lab direction is
already stated. Building `ai/` provider-neutral costs nothing and positions it as a RAG
corpus and fine-tuning dataset for a future in-house model.

## Consequences

- All `ai/01` through `ai/05` and `ai/memory/` files must remain vendor-neutral markdown
- Claude-specific syntax (skills, agents, slash commands) stays in `.providers/claude/`
- Adding a new LLM provider = create `.providers/openai-compatible/` or equivalent
