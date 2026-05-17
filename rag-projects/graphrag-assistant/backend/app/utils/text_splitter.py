from __future__ import annotations


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
