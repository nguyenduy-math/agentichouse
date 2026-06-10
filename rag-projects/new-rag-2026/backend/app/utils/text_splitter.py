"""
Structure-aware text splitter for Vietnamese policy documents.

Three-tier splitting strategy:
  1. Split at Vietnamese article boundaries ("Điều N.")
  2. Split at section markers ("=== SECTION ===")
  3. Fixed-size sliding window with sentence-boundary snapping

Carried over from graphrag-assistant with adaptations for new-rag-2026.
"""
from __future__ import annotations

import re

# Compiled patterns for performance
_DIEU = re.compile(r"(?m)^Điều \d+\.")
_SECTION = re.compile(r"(?m)^===")


def _split_on_pattern(text: str, pattern: str, max_chunk_size: int) -> list[str]:
    """
    Split text at positions matching `pattern`.
    If a resulting segment exceeds max_chunk_size, it is further split
    using the fixed-size fallback.
    """
    parts = re.split(pattern, text)
    chunks: list[str] = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if len(part) <= max_chunk_size:
            chunks.append(part)
        else:
            # Overflow: fall back to fixed-size splitting for this segment
            chunks.extend(split_text(part, max_chunk_size, max_chunk_size // 7))
    return chunks


def split_text(text: str, chunk_size: int = 2800, overlap: int = 400) -> list[str]:
    """
    Fixed-size sliding window splitter with sentence-boundary snapping.

    Snaps chunk boundaries to the nearest sentence end (., \\n\\n, . )
    only if the break point is past the halfway mark of the chunk.
    This prevents mid-sentence cuts while staying within the size limit.

    Args:
        text: Input text (already NFC-normalized)
        chunk_size: Target chunk size in characters
        overlap: Overlap between consecutive chunks in characters

    Returns:
        List of text chunks
    """
    if not text:
        return []

    if len(text) <= chunk_size:
        return [text]

    chunks: list[str] = []
    start = 0
    text_len = len(text)

    while start < text_len:
        end = min(start + chunk_size, text_len)
        chunk = text[start:end]

        if end < text_len:
            # Try to snap to a sentence boundary
            last_break = max(
                chunk.rfind(".\n"),   # Vietnamese sentence ending with newline
                chunk.rfind("\n\n"),  # paragraph break
                chunk.rfind(". "),    # inline sentence end
            )
            # Only snap if the break is past the halfway point
            if last_break > chunk_size // 2:
                end = start + last_break + 1
                chunk = text[start:end]

        chunk = chunk.strip()
        if chunk:
            chunks.append(chunk)

        start = end - overlap if end - overlap > start else end

    return chunks


def split_by_article(text: str, max_chunk_size: int = 2800) -> list[str]:
    """
    Three-tier structure-aware splitter for Vietnamese policy documents.

    Tier 1: Split at Vietnamese article boundaries ("Điều N.")
    Tier 2: Split at section markers ("=== SECTION ===")
    Tier 3 fallback: Fixed-size sliding window with sentence-boundary snapping

    Args:
        text: Input text (already NFC-normalized)
        max_chunk_size: Maximum characters per chunk

    Returns:
        List of text chunks, each ≤ max_chunk_size characters
    """
    if not text:
        return []

    # Tier 1: Vietnamese article structure
    if _DIEU.search(text):
        return _split_on_pattern(text, r"(?m)^(?=Điều \d+\.)", max_chunk_size)

    # Tier 2: Section marker structure
    if _SECTION.search(text):
        return _split_on_pattern(text, r"(?m)^(?====)", max_chunk_size)

    # Tier 3: Fixed-size sliding window fallback
    return split_text(text, max_chunk_size, max_chunk_size // 7)
