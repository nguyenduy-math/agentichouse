"""Vision LLM provider abstraction for insurance claim field extraction.

Supports two backends, switchable via VISION_PROVIDER env var:
  - "gemini"      → Google Gemini (google-generativeai SDK), model gemini-2.0-flash
  - "siliconflow" → Siliconflow OpenAI-compatible API, model Qwen3-VL-32B-Instruct

Usage:
    from tools.vision_provider import get_provider
    provider = get_provider()
    fields = provider.extract_claim_fields(image_bytes, "image/jpeg")
"""

from __future__ import annotations

import base64
import json
import os
from abc import ABC, abstractmethod

# ---------------------------------------------------------------------------
# Extraction prompt (Vietnamese, structured output)
# ---------------------------------------------------------------------------

EXTRACTION_PROMPT = """Đây là tài liệu yêu cầu bồi thường bảo hiểm y tế bằng tiếng Việt.
Hãy trích xuất các thông tin sau và trả về dạng JSON:
{
  "claim_type": "ngoại trú | nội trú | thương mại | unknown",
  "name": "...",
  "dob": "DD/MM/YYYY hoặc null",
  "insurance_id": "...",
  "policy_number": "...",
  "hospital": "...",
  "visit_date": "...",
  "admission_date": "...",
  "discharge_date": "...",
  "event_date": "...",
  "diagnosis": "...",
  "diagnosis_code": "...",
  "total_cost": số hoặc null,
  "patient_paid": số hoặc null,
  "bank_account": "...",
  "notes": "..."
}
Chỉ trả về JSON, không giải thích thêm. Nếu không tìm thấy thông tin, để null."""

# Map Vietnamese claim_type values → backend ClaimType enum values
_CLAIM_TYPE_MAP = {
    "ngoại trú": "outpatient",
    "nội trú": "inpatient",
    "thương mại": "private",
    "unknown": "unknown",
}


def _normalise_claim_type(raw: str | None) -> str | None:
    """Convert Vietnamese claim_type string to backend enum value."""
    if not raw:
        return None
    lower = raw.strip().lower()
    return _CLAIM_TYPE_MAP.get(lower, lower)


def _parse_llm_response(text: str) -> dict:
    """Parse JSON from LLM response, with fallback for markdown fences."""
    text = text.strip()
    # Strip markdown code fences if present
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(
            line for line in lines
            if not line.strip().startswith("```")
        ).strip()
    try:
        data = json.loads(text)
        # Normalise claim_type to backend enum value
        if "claim_type" in data:
            data["claim_type"] = _normalise_claim_type(data.get("claim_type"))
        return data
    except json.JSONDecodeError:
        # Return raw text wrapped so callers can surface it
        return {"_raw": text, "_parse_error": "LLM did not return valid JSON"}


# ---------------------------------------------------------------------------
# Base class
# ---------------------------------------------------------------------------

class VisionProvider(ABC):
    """Abstract vision LLM provider."""

    @abstractmethod
    def extract_claim_fields(self, image_bytes: bytes, mime_type: str) -> dict:
        """Send image to vision LLM, return extracted claim fields as dict."""


# ---------------------------------------------------------------------------
# Gemini provider
# ---------------------------------------------------------------------------

class GeminiProvider(VisionProvider):
    """Uses google-generativeai SDK with gemini-2.0-flash."""

    MODEL = "gemini-2.0-flash"

    def __init__(self) -> None:
        api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise EnvironmentError(
                "VISION_PROVIDER=gemini requires GOOGLE_API_KEY (or GEMINI_API_KEY) to be set."
            )
        try:
            import google.generativeai as genai  # type: ignore
        except ImportError as exc:
            raise ImportError(
                "google-generativeai is not installed. Run: pip install google-generativeai"
            ) from exc

        genai.configure(api_key=api_key)
        self._model = genai.GenerativeModel(self.MODEL)

    def extract_claim_fields(self, image_bytes: bytes, mime_type: str) -> dict:
        import google.generativeai as genai  # type: ignore

        image_part = {"mime_type": mime_type, "data": image_bytes}
        response = self._model.generate_content([EXTRACTION_PROMPT, image_part])
        return _parse_llm_response(response.text)


# ---------------------------------------------------------------------------
# Siliconflow provider
# ---------------------------------------------------------------------------

class SiliconflowProvider(VisionProvider):
    """Uses Siliconflow's OpenAI-compatible API with Qwen2-VL-72B-Instruct."""

    BASE_URL = "https://api.siliconflow.com/v1/chat/completions"
    MODEL = "Qwen/Qwen3-VL-32B-Instruct"

    def __init__(self) -> None:
        self._api_key = os.environ.get("SILICONFLOW_API_KEY")
        if not self._api_key:
            raise EnvironmentError(
                "VISION_PROVIDER=siliconflow requires SILICONFLOW_API_KEY to be set."
            )
        try:
            import httpx  # noqa: F401
        except ImportError as exc:
            raise ImportError(
                "httpx is not installed. Run: pip install httpx"
            ) from exc

    def extract_claim_fields(self, image_bytes: bytes, mime_type: str) -> dict:
        import httpx

        # Encode image as base64 data URL
        b64 = base64.b64encode(image_bytes).decode("utf-8")
        data_url = f"data:{mime_type};base64,{b64}"

        payload = {
            "model": self.MODEL,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": data_url}},
                        {"type": "text", "text": EXTRACTION_PROMPT},
                    ],
                }
            ],
            "max_tokens": 1024,
            "temperature": 0.0,
        }

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        with httpx.Client(timeout=60.0) as client:
            resp = client.post(self.BASE_URL, json=payload, headers=headers)
            if resp.status_code >= 400:
                raise RuntimeError(
                    f"Siliconflow API {resp.status_code} for model {self.MODEL!r}: {resp.text}"
                )

        text = resp.json()["choices"][0]["message"]["content"]
        return _parse_llm_response(text)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

_PROVIDERS: dict[str, type[VisionProvider]] = {
    "gemini": GeminiProvider,
    "siliconflow": SiliconflowProvider,
}


def get_provider() -> VisionProvider:
    """Instantiate and return the configured vision provider.

    Reads VISION_PROVIDER env var (default: "gemini").
    """
    name = os.environ.get("VISION_PROVIDER", "gemini").strip().lower()
    cls = _PROVIDERS.get(name)
    if cls is None:
        raise ValueError(
            f"Unknown VISION_PROVIDER={name!r}. Valid options: {list(_PROVIDERS)}"
        )
    return cls()
