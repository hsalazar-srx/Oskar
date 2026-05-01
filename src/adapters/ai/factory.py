"""
AIProvider factory — reads AI_PROVIDER_CLASS env var.

Default: NoOpAIProvider (no env var required).
Raises ValueError for any unknown class — prevents Stage 2 providers from being
accidentally activated before they are implemented and wired.
"""
from __future__ import annotations

import os

from .base import AIProvider
from .noop import NoOpAIProvider


def get_ai_provider() -> AIProvider:
    """Return the configured AIProvider.

    AI_PROVIDER_CLASS=NoOpAIProvider  → NoOpAIProvider (default)
    Any other value                   → ValueError (Stage 2 classes not yet implemented)
    """
    cls_name = os.getenv("AI_PROVIDER_CLASS", "NoOpAIProvider")
    if cls_name == "NoOpAIProvider":
        return NoOpAIProvider()
    raise ValueError(
        f"Unknown AI_PROVIDER_CLASS: {cls_name!r}. "
        "Stage 1 only supports 'NoOpAIProvider'. "
        "Stage 2 providers (Ollama, Anthropic) are not yet implemented."
    )
