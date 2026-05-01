"""
AIProvider Protocol — OSKAR adapter layer (ADR-010).

Mirrors the IdentityProvider / ERPAdapter / SupplierAdapter pattern.
Stage 1: only NoOpAIProvider is active.
Stage 2: OllamaProvider, AnthropicProvider, AzureOpenAIProvider.

No external packages — only stdlib typing, dataclasses, re, unicodedata.

Prompt injection defence
------------------------
Customer-supplied BOM data (MPN names, component descriptions) flows into AI prompts
in Stage 2. A supplier could embed adversarial text in a description field.

The human-in-the-loop requirement (Non-Negotiable #2) is the primary defence —
no AI output can reach Movex without explicit human approval — but we also sanitise
inputs at the Protocol layer so injection attempts never reach the model.

ALL Stage 2 provider implementations MUST call `sanitize_for_prompt()` on every
string sourced from external data (uploaded BOMs, customer-supplied descriptions,
MPN fields) before including it in a prompt. This is a mandatory Protocol contract,
documented in ADR-010.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

# Patterns that commonly appear in prompt injection attempts.
# This list targets the most effective injection vectors; it is not exhaustive.
# Human review (Non-Negotiable #2) is the defence of last resort.
_INJECTION_PATTERNS = re.compile(
    r"(?i)"                           # case-insensitive
    r"(ignore\s+(all\s+)?previous|"   # "Ignore previous instructions"
    r"disregard\s+(all\s+)?prior|"    # "Disregard prior instructions"
    r"you\s+are\s+now|"               # "You are now DAN"
    r"new\s+instruction[s]?|"         # "New instructions:"
    r"system\s*:\s*|"                 # "System:" role injection
    r"<\s*/?(?:system|human|assistant|user|prompt|context)[^>]*>|"  # XML role tags
    r"\[\s*INST\s*\]|"                # Llama instruct markers
    r"###\s*instruction|"             # Alpaca/Mistral instruction blocks
    r"\bDAN\b|"                       # "Do Anything Now" jailbreak keyword
    r"act\s+as\s+if\s+you\s+are)"     # "Act as if you are..."
)

_MAX_SANITIZED_LEN = 500             # hard cap — no field needs more than this in a prompt


def sanitize_for_prompt(text: str, max_len: int = _MAX_SANITIZED_LEN) -> str:
    """Sanitise external text before including it in an AI prompt.

    Applies three layers of defence (in order):
    1. Unicode normalisation — NFKC resolves homoglyph substitutions (ɪɢɴᴏʀᴇ → IGNORE).
    2. Control-character stripping — removes null bytes, ESC, and other non-printable
       characters that could confuse tokenisers.
    3. Injection-pattern removal — strips known prompt-injection phrases and role markers.
    4. Length cap — enforces `max_len` so a large payload cannot flood the context window.

    This is a best-effort defence. The primary protection is Non-Negotiable #2:
    no AI suggestion reaches Movex without explicit human approval.
    """
    # 1. Normalise unicode (resolves homoglyphs and canonical equivalents)
    text = unicodedata.normalize("NFKC", text)

    # 2. Strip control characters (keep tab and newline for readability)
    text = "".join(
        ch for ch in text
        if ch in ("\t", "\n") or (unicodedata.category(ch) not in ("Cc", "Cf"))
    )

    # 3. Remove injection patterns (replace with a safe placeholder)
    text = _INJECTION_PATTERNS.sub("[FILTERED]", text)

    # 4. Enforce length cap
    return text[:max_len]


@dataclass(frozen=True)
class MPNStatus:
    mpn: str
    lifecycle: str           # 'active' | 'eol' | 'nrnd' | 'unknown'
    eol_date: str | None
    suggested_alternative: str | None
    lead_time_weeks: int | None
    packaging_options: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class AISuggestion:
    suggestion_type: str     # 'description' | 'ecn_title' | 'mpn_alt' | 'bom_risk'
    content: str
    confidence: float        # 0.0–1.0
    model: str               # 'noop' | 'ollama/llama3.2' | 'claude-sonnet-4-6'
    prompt_hash: str         # SHA-256 hex of prompt — prompt itself never stored


@runtime_checkable
class AIProvider(Protocol):
    """Protocol for all AI capability providers in OSKAR.

    Implementations: NoOpAIProvider (Stage 1), OllamaProvider, AnthropicProvider (Stage 2).
    Swap providers via AI_PROVIDER_CLASS env var — callers never change.
    Non-Negotiable #2: AI assists; humans decide. No provider may commit to Movex directly.
    """

    def suggest_description(self, raw: str, max_len: int = 30) -> AISuggestion:
        """Sanitise and shorten a component description to fit Movex's 30-char limit."""
        ...

    def check_mpn_status(self, mpns: list[str]) -> list[MPNStatus]:
        """Return lifecycle status for each MPN. One MPNStatus per input MPN."""
        ...

    def draft_ecn_title(self, description: str) -> AISuggestion:
        """Draft a concise ECN title from a change description."""
        ...

    def detect_bom_risks(self, items: list[dict]) -> list[AISuggestion]:
        """Detect EOL, NRND, MSL, and supply-risk issues across a BOM item list."""
        ...
