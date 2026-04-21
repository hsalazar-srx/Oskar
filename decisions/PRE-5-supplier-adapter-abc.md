# PRE-5 — Supplier Adapter Abstract Interface

**Status:** Accepted — Final for OSKAR v1
**Date:** 2026-04-08
**Owner:** Lead Engineer
**Type:** Architectural — type-2 reversible (add adapters incrementally)

---

## Decision

`SupplierAdapter` ABC defined in Phase 1 Track A. Phase 1 delivers:
- 1 real supplier wired (DigiKey — highest MPN coverage)
- 5 suppliers stubbed (raise `NotImplementedError`)

Per-adapter circuit breaker (`failure_threshold=5, recovery_timeout=60`).
Adding a 7th supplier = one new class file implementing the ABC.

## Rationale

Full 6-supplier implementation during ECN go-live adds untested async complexity.
Stub pattern proves the interface; real adapters added incrementally in Sprint 3+.

## Consequences

- Supplier fan-out is async parallel (`asyncio.gather`) — individual supplier failure does not block others
- Circuit breaker state is per-adapter, not shared
- Stub adapters must return a typed `SupplierResult` with `is_stub=True` flag — never raise silently
