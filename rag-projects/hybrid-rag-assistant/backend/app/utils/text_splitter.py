from __future__ import annotations

import re

_DIEU = re.compile(r"(?m)^Điều \d+\.")
_SECTION = re.compile(r"(?m)^===.+===")


def split_by_article(text: str, max_chunk_size: int = 2800) -> list[str]:
    """Split Vietnamese policy documents at natural section boundaries.

    Tier 1: 'Điều N.' article boundaries (policy docs).
    Tier 2: '=== SECTION ===' chapter boundaries (procedures, handbook).
    Fallback: sentence-aware fixed-size split for docs with neither pattern.
    """
    if not text.strip():
        return []
    if _DIEU.search(text):
        return _split_on_pattern(text, r"(?m)^(?=Điều \d+\.)", max_chunk_size)
    if _SECTION.search(text):
        return _split_on_pattern(text, r"(?m)^(?====)", max_chunk_size)
    return split_text(text, max_chunk_size, max_chunk_size // 7)


def _split_on_pattern(text: str, pattern: str, max_chunk_size: int) -> list[str]:
    parts = [p.strip() for p in re.split(pattern, text) if p.strip()]
    chunks: list[str] = []
    for part in parts:
        if len(part) <= max_chunk_size:
            chunks.append(part)
        else:
            current = ""
            for para in re.split(r"\n\n+", part):
                if not current:
                    current = para
                elif len(current) + 2 + len(para) <= max_chunk_size:
                    current += "\n\n" + para
                else:
                    chunks.append(current)
                    current = para
            if current:
                chunks.append(current)
    return chunks


def split_text(text: str, chunk_size: int = 2800, chunk_overlap: int = 400) -> list[str]:
    if not text.strip():
        return []

    chunks: list[str] = []
    start = 0
    text_len = len(text)

    while start < text_len:
        end = start + chunk_size
        chunk = text[start:end]

        if end < text_len:
            last_break = max(
                chunk.rfind(".\n"),
                chunk.rfind("\n\n"),
                chunk.rfind(". "),
            )
            if last_break > chunk_size // 2:
                end = start + last_break + 1
                chunk = text[start:end]

        chunk = chunk.strip()
        if chunk:
            chunks.append(chunk)

        start = end - chunk_overlap

    return chunks
