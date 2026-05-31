"""Image scanning tool — extracts insurance claim fields from a JPG/PNG image
using the configured vision LLM provider (same as pdf_tool).

Returns the same JSON shape as scan_pdf:
  { "extracted_fields": {...}, "summary_text": "..." }
"""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path

from tools.pdf_tool import _build_summary  # reuse summary builder

# Supported MIME types by file extension
_EXT_TO_MIME: dict[str, str] = {
    ".jpg":  "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png":  "image/png",
    ".webp": "image/webp",
    ".gif":  "image/gif",
}


def scan_image(file_path: str = "", base64_image: str = "", mime_type: str = "") -> str:
    """
    Extract insurance claim fields from an image file using a vision LLM.

    Args:
        file_path:    Absolute or relative path to a local image (JPG/PNG/…).
        base64_image: Base64-encoded image content (used when file_path is absent).
        mime_type:    MIME type of the image (required when base64_image is used,
                      e.g. "image/jpeg"). Auto-detected from file extension otherwise.

    Returns:
        JSON string with keys:
          - "extracted_fields": dict of claim fields
          - "summary_text": human-readable Vietnamese summary
        On error, returns a JSON string with key "error".
    """
    try:
        # ------------------------------------------------------------------
        # Resolve image bytes and MIME type
        # ------------------------------------------------------------------
        if base64_image:
            try:
                img_bytes = base64.b64decode(base64_image)
            except Exception as exc:
                return json.dumps({"error": f"Invalid base64_image: {exc}"})
            if not mime_type:
                mime_type = "image/jpeg"  # safe default

        elif file_path:
            resolved = str(Path(file_path).expanduser().resolve())
            if not os.path.exists(resolved):
                return json.dumps({"error": f"File not found — {file_path}"})

            ext = Path(resolved).suffix.lower()
            if ext not in _EXT_TO_MIME:
                return json.dumps({
                    "error": f"Unsupported image format '{ext}'. Supported: {list(_EXT_TO_MIME)}"
                })

            mime_type = _EXT_TO_MIME[ext]
            with open(resolved, "rb") as f:
                img_bytes = f.read()

        else:
            return json.dumps({"error": "Provide either file_path or base64_image."})

        # ------------------------------------------------------------------
        # Call vision provider
        # ------------------------------------------------------------------
        from tools.vision_provider import get_provider

        provider = get_provider()
        fields = provider.extract_claim_fields(img_bytes, mime_type)

        summary_text = _build_summary(fields)

        return json.dumps(
            {"extracted_fields": fields, "summary_text": summary_text},
            ensure_ascii=False,
        )

    except Exception as exc:
        return json.dumps({"error": f"Error processing image: {exc}"})
