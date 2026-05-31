"""PDF scanning tool — extracts text from a PDF file using LangChain."""

import base64
import os
import tempfile
from pathlib import Path


def scan_pdf(file_path: str = "", base64_pdf: str = "") -> str:
    """
    Extract text from a PDF file.

    Args:
        file_path: Absolute or relative path to the PDF file.
        base64_pdf: Base64-encoded PDF content (used when file_path is not provided).

    Returns:
        Extracted text content, or an error message.
    """
    try:
        from langchain_community.document_loaders import PyPDFLoader
    except ImportError:
        return "Error: langchain-community is not installed. Run: pip install langchain-community pypdf"

    tmp_path = None

    try:
        if base64_pdf:
            # Decode base64 → temp file
            pdf_bytes = base64.b64decode(base64_pdf)
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                tmp.write(pdf_bytes)
                tmp_path = tmp.name
            target_path = tmp_path

        elif file_path:
            target_path = str(Path(file_path).expanduser().resolve())
            if not os.path.exists(target_path):
                return f"Error: File not found — {file_path}"
            if not target_path.lower().endswith(".pdf"):
                return f"Error: File does not appear to be a PDF — {file_path}"
        else:
            return "Error: Provide either file_path or base64_pdf."

        loader = PyPDFLoader(target_path)
        pages = loader.load()

        if not pages:
            return "Warning: No text extracted — the PDF may be empty or image-only."

        texts = []
        for i, page in enumerate(pages, start=1):
            content = page.page_content.strip()
            if content:
                texts.append(f"--- Page {i} ---\n{content}")

        return "\n\n".join(texts) if texts else "Warning: No readable text found in the PDF."

    except Exception as exc:
        return f"Error processing PDF: {exc}"

    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)
