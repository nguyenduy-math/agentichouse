"""Document discovery + text extraction (PDF / DOCX / Markdown / TXT).

Pure functions — no LightRAG coupling. Everything decodes as UTF-8 so Vietnamese
diacritics survive intact.
"""

from __future__ import annotations

import logging
from pathlib import Path

import docx
from pypdf import PdfReader

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".pdf", ".txt", ".md", ".markdown", ".docx"}


def extract_text(path: Path) -> str:
    """Extract plain text from a single supported file."""
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        reader = PdfReader(str(path))
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    if suffix == ".docx":
        document = docx.Document(str(path))
        return "\n".join(paragraph.text for paragraph in document.paragraphs)
    if suffix in {".txt", ".md", ".markdown"}:
        return path.read_text(encoding="utf-8", errors="ignore")
    raise ValueError(f"Unsupported file type: {suffix}")


def collect_documents(folder: str | Path) -> tuple[list[str], list[str], list[str]]:
    """Walk ``folder`` recursively and extract text from every supported file.

    Returns ``(texts, sources, skipped)`` where ``texts[i]`` was extracted from
    ``sources[i]``. ``skipped`` lists files that were unsupported, unreadable, or
    produced no text (e.g. scanned-image PDFs that would need OCR).
    """
    base = Path(folder)
    if not base.exists():
        raise FileNotFoundError(f"Document folder does not exist: {base}")

    texts: list[str] = []
    sources: list[str] = []
    skipped: list[str] = []

    for path in sorted(base.rglob("*")):
        if not path.is_file() or path.name == ".gitkeep":
            continue
        if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            skipped.append(str(path))
            continue
        try:
            text = extract_text(path).strip()
        except Exception as exc:  # noqa: BLE001 - log and skip unreadable files
            logger.warning("Failed to extract text from %s: %s", path, exc)
            skipped.append(str(path))
            continue
        if not text:
            logger.warning("No extractable text in %s (scanned image?) — skipped", path)
            skipped.append(str(path))
            continue
        texts.append(text)
        sources.append(str(path))

    return texts, sources, skipped
