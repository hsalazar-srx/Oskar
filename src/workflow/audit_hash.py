"""Canonical SHA-256 hash for ecn_transition_history rows (ADR-004).

Single source of truth for hash construction. Imported by:
  - ECNWorkflowMachine (src/workflow/machine.py)
  - Celery outbox worker (src/tasks/movex_outbox.py)
  - Audit checkpoint task (src/tasks/audit_checkpoint.py)

The hash covers every field written to ecn_transition_history except
sha256_self itself. sort_keys=True and ensure_ascii=True are mandatory
for determinism across Python versions and locales.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone


def compute_transition_hash(
    *,
    record_id: str,
    ecn_id: str,
    from_status: int | None,
    to_status: int,
    action: str,
    actor_username: str,
    actor_role: str | None,
    notes: str | None,
    movex_payload: dict | None,
    agent_provenance: dict | None,
    sha256_prev: str | None,
    created_at: datetime,
) -> str:
    """Return the SHA-256 hex digest for a transition history row.

    All arguments are keyword-only to prevent positional ordering mistakes
    between callers.  created_at must be timezone-aware UTC.
    """
    if created_at.tzinfo is None:
        raise ValueError("created_at must be timezone-aware UTC")

    payload = {
        "id": record_id,
        "ecn_id": ecn_id,
        "from_status": from_status,
        "to_status": to_status,
        "action": action,
        "actor_username": actor_username,
        "actor_role": actor_role,
        "notes": notes,
        "movex_payload": movex_payload,
        "agent_provenance": agent_provenance,
        "sha256_prev": sha256_prev,
        "created_at": created_at.astimezone(timezone.utc).isoformat(),
    }
    canonical = json.dumps(payload, sort_keys=True, default=str, ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
