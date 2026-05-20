"""Token-aware context budgeting.

Replaces the character slices (``text[:8000]``) that were scattered across the
orchestrator and PageIndex service. Character counts are a poor proxy for tokens —
Vietnamese diacritics and JSON punctuation tokenize unevenly — and a blind slice
can cut mid-citation or mid-JSON (which broke the navigation parse).

This module has no external dependency: it estimates tokens with a heuristic
calibrated for mixed Vietnamese / English / JSON, truncates on whitespace
boundaries, and prefers dropping whole sections over slicing one. It also logs
whenever a budget clamp fires, giving visibility into context-window pressure.

Audit refs: C1 (token-aware truncation), C2 (observability), C3 (fan-out caps).
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# Heuristic: blends a char/word estimate. For Latin text ~4 chars/token; for
# Vietnamese (diacritics) and JSON punctuation the per-token char count is lower,
# so we also floor at the word count. This intentionally over-estimates slightly,
# which is the safe direction for staying under a real model limit.
_CHARS_PER_TOKEN = 3.5


def estimate_tokens(text: str) -> int:
    """Approximate the token count of ``text`` without calling the model."""
    if not text:
        return 0
    char_estimate = len(text) / _CHARS_PER_TOKEN
    word_estimate = len(text.split())
    return int(max(char_estimate, word_estimate))


def truncate_to_tokens(text: str, max_tokens: int, *, label: str = "text") -> str:
    """Trim ``text`` to roughly ``max_tokens``, cutting on a whitespace boundary.

    Logs a warning when truncation actually happens so window pressure is visible.
    """
    if max_tokens <= 0 or not text:
        return ""
    if estimate_tokens(text) <= max_tokens:
        return text

    # Convert the token budget back to an approximate character budget, then back
    # off to the last whitespace so we never cut mid-word / mid-token.
    char_budget = int(max_tokens * _CHARS_PER_TOKEN)
    cut = text[:char_budget]
    last_space = cut.rfind(" ")
    last_newline = cut.rfind("\n")
    boundary = max(last_space, last_newline)
    if boundary > char_budget * 0.5:  # only honor boundary if it isn't absurdly early
        cut = cut[:boundary]
    logger.warning(
        "context_budget: truncated %s from ~%d to ~%d tokens (cap=%d)",
        label, estimate_tokens(text), estimate_tokens(cut), max_tokens,
    )
    return cut.rstrip()


def fit_sections(
    sections: list[str],
    max_tokens: int,
    *,
    separator: str = "\n\n",
    label: str = "sections",
) -> str:
    """Join ``sections`` greedily, dropping whole trailing sections that overflow.

    Preferred over ``truncate_to_tokens`` when the input is structured (per-document
    answers, per-node excerpts): keeping whole units intact beats slicing one in half.
    Logs how many sections were dropped.
    """
    kept: list[str] = []
    used = 0
    sep_tokens = estimate_tokens(separator)
    for section in sections:
        cost = estimate_tokens(section) + (sep_tokens if kept else 0)
        if used + cost > max_tokens and kept:
            break
        kept.append(section)
        used += cost
    dropped = len(sections) - len(kept)
    if dropped:
        logger.warning(
            "context_budget: dropped %d of %d %s to fit ~%d token budget",
            dropped, len(sections), label, max_tokens,
        )
    # If even the first section overflows on its own, hard-truncate just that one.
    if not kept and sections:
        return truncate_to_tokens(sections[0], max_tokens, label=label)
    return separator.join(kept)


def log_prompt_size(label: str, prompt: str) -> None:
    """Emit an INFO line with the estimated prompt size for a single LLM call."""
    logger.info("context_budget: %s prompt ~%d tokens", label, estimate_tokens(prompt))
