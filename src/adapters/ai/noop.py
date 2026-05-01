"""
NoOpAIProvider — Stage 1 pass-through implementation of AIProvider.

Always returns safe defaults. Never raises. Never calls external services.
Platform works fully without any AI infrastructure.

Activate: AI_PROVIDER_CLASS=NoOpAIProvider (default, no env var needed).
"""
from __future__ import annotations

import hashlib

from .base import AISuggestion, MPNStatus

_NOOP_HASH = hashlib.sha256(b"noop").hexdigest()
_NOOP_MODEL = "noop"


class NoOpAIProvider:
    """Pass-through AI provider — returns safe defaults, zero external calls."""

    def suggest_description(self, raw: str, max_len: int = 30) -> AISuggestion:
        return AISuggestion(
            suggestion_type="description",
            content=raw[:max_len],
            confidence=0.0,
            model=_NOOP_MODEL,
            prompt_hash=_NOOP_HASH,
        )

    def check_mpn_status(self, mpns: list[str]) -> list[MPNStatus]:
        return [
            MPNStatus(
                mpn=mpn,
                lifecycle="unknown",
                eol_date=None,
                suggested_alternative=None,
                lead_time_weeks=None,
                packaging_options=[],
            )
            for mpn in mpns
        ]

    def draft_ecn_title(self, description: str) -> AISuggestion:
        return AISuggestion(
            suggestion_type="ecn_title",
            content=description[:80],
            confidence=0.0,
            model=_NOOP_MODEL,
            prompt_hash=_NOOP_HASH,
        )

    def detect_bom_risks(self, items: list[dict]) -> list[AISuggestion]:
        return []
