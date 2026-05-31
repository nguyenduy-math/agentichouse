"""PDF scanning tool — converts PDF pages to images, then extracts claim fields
using a vision LLM (Gemini or Siliconflow, configured via VISION_PROVIDER env var).

Returns structured JSON with extracted_fields and a Vietnamese summary_text.
"""

from __future__ import annotations

import base64
import json
import os
import tempfile
from pathlib import Path


def scan_pdf(file_path: str = "", base64_pdf: str = "") -> str:
    """
    Extract insurance claim fields from a PDF using a vision LLM.

    Args:
        file_path:  Absolute or relative path to a local PDF file.
        base64_pdf: Base64-encoded PDF content (used when file_path is absent).

    Returns:
        JSON string with keys:
          - "extracted_fields": dict of claim fields (see claim_schema.py)
          - "summary_text": human-readable Vietnamese summary
        On error, returns a JSON string with key "error".
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        return json.dumps({"error": "pymupdf is not installed. Run: pip install pymupdf"})

    tmp_path: str | None = None

    try:
        # ------------------------------------------------------------------
        # Resolve the PDF source
        # ------------------------------------------------------------------
        if base64_pdf:
            pdf_bytes = base64.b64decode(base64_pdf)
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                tmp.write(pdf_bytes)
                tmp_path = tmp.name
            target_path = tmp_path

        elif file_path:
            target_path = str(Path(file_path).expanduser().resolve())
            if not os.path.exists(target_path):
                return json.dumps({"error": f"File not found — {file_path}"})
            if not target_path.lower().endswith(".pdf"):
                return json.dumps({"error": f"File does not appear to be a PDF — {file_path}"})
        else:
            return json.dumps({"error": "Provide either file_path or base64_pdf."})

        # ------------------------------------------------------------------
        # Convert first 2 PDF pages to images via PyMuPDF
        # ------------------------------------------------------------------
        doc = fitz.open(target_path)
        if doc.page_count == 0:
            return json.dumps({"error": "PDF has no pages."})

        page_images: list[bytes] = []
        for page_num in range(min(2, doc.page_count)):
            page = doc.load_page(page_num)
            # Render at 2× zoom for better OCR quality
            mat = fitz.Matrix(2.0, 2.0)
            pix = page.get_pixmap(matrix=mat, alpha=False)
            page_images.append(pix.tobytes("png"))

        doc.close()

        if not page_images:
            return json.dumps({"error": "Could not render any PDF pages to images."})

        # ------------------------------------------------------------------
        # Call vision provider — send pages one at a time, merge results
        # ------------------------------------------------------------------
        from tools.vision_provider import get_provider  # local import keeps startup fast

        provider = get_provider()
        merged_fields: dict = {}

        for img_bytes in page_images:
            result = provider.extract_claim_fields(img_bytes, "image/png")
            # Later pages may fill in fields missing from earlier pages
            for key, val in result.items():
                if val is not None and not merged_fields.get(key):
                    merged_fields[key] = val

        # ------------------------------------------------------------------
        # Build Vietnamese summary
        # ------------------------------------------------------------------
        summary_text = _build_summary(merged_fields)

        return json.dumps(
            {"extracted_fields": merged_fields, "summary_text": summary_text},
            ensure_ascii=False,
        )

    except Exception as exc:
        return json.dumps({"error": f"Error processing PDF: {exc}"})

    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FIELD_LABELS = {
    "claim_type":     "Loại bảo hiểm",
    "name":           "Họ tên",
    "dob":            "Ngày sinh",
    "insurance_id":   "Mã BHXH",
    "policy_number":  "Số hợp đồng",
    "hospital":       "Bệnh viện",
    "visit_date":     "Ngày khám",
    "admission_date": "Ngày nhập viện",
    "discharge_date": "Ngày xuất viện",
    "event_date":     "Ngày xảy ra sự kiện",
    "diagnosis":      "Chẩn đoán",
    "diagnosis_code": "Mã ICD-10",
    "total_cost":     "Tổng chi phí (VNĐ)",
    "patient_paid":   "Bệnh nhân tự trả (VNĐ)",
    "bank_account":   "Tài khoản ngân hàng",
    "notes":          "Ghi chú",
}


def _build_summary(fields: dict) -> str:
    """Build a Vietnamese summary string from extracted fields."""
    # Skip internal parse-error keys
    found = [
        f"- {label}: {fields[key]}"
        for key, label in _FIELD_LABELS.items()
        if fields.get(key) is not None
    ]
    if found:
        return (
            "Tôi đã đọc tài liệu và tìm thấy các thông tin sau:\n"
            + "\n".join(found)
            + "\n\nBạn có muốn điền vào form không?"
        )
    return (
        "Tôi đã đọc tài liệu nhưng không tìm thấy thông tin bảo hiểm nào. "
        "Bạn có thể nhập thông tin thủ công."
    )
