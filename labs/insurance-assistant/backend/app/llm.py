"""Provider-agnostic LLM layer.

Both agents talk to the LLM exclusively through this module so the backend can
switch between Google Gemini and SiliconFlow (OpenAI-compatible) via the
``LLM_PROVIDER`` setting, without changing any agent logic.

Canonical message format used across the codebase::

    [{"role": "user" | "model", "content": "..."}, ...]

This matches ``session.history`` and Gemini's role convention; the SiliconFlow
provider maps ``"model"`` -> ``"assistant"`` internally.
"""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod

from pydantic import BaseModel

from app.config import settings

logger = logging.getLogger(__name__)

Message = dict[str, str]


# ---------------------------------------------------------------------------
# Interface
# ---------------------------------------------------------------------------

class LLMProvider(ABC):
    @abstractmethod
    async def generate_text(
        self, *, messages: list[Message], system: str, temperature: float
    ) -> str:
        ...

    @abstractmethod
    async def generate_structured(
        self,
        *,
        messages: list[Message],
        system: str,
        temperature: float,
        schema: type[BaseModel],
    ) -> dict:
        ...


# ---------------------------------------------------------------------------
# Gemini (google-genai)
# ---------------------------------------------------------------------------

class GeminiProvider(LLMProvider):
    def __init__(self) -> None:
        from google import genai

        self._client = genai.Client(api_key=settings.gemini_api_key)
        self._model = settings.gemini_llm_model

    def _contents(self, messages: list[Message]):
        from google.genai import types

        return [
            types.Content(role=m["role"], parts=[types.Part(text=m["content"])])
            for m in messages
        ]

    async def generate_text(
        self, *, messages: list[Message], system: str, temperature: float
    ) -> str:
        from google.genai import types

        response = await self._client.aio.models.generate_content(
            model=self._model,
            contents=self._contents(messages),
            config=types.GenerateContentConfig(
                system_instruction=system,
                temperature=temperature,
            ),
        )
        return response.text.strip()

    async def generate_structured(
        self,
        *,
        messages: list[Message],
        system: str,
        temperature: float,
        schema: type[BaseModel],
    ) -> dict:
        from google.genai import types

        response = await self._client.aio.models.generate_content(
            model=self._model,
            contents=self._contents(messages),
            config=types.GenerateContentConfig(
                system_instruction=system,
                temperature=temperature,
                response_mime_type="application/json",
                response_schema=schema,
            ),
        )
        return json.loads(response.text)


# ---------------------------------------------------------------------------
# SiliconFlow (OpenAI-compatible)
# ---------------------------------------------------------------------------

class SiliconFlowProvider(LLMProvider):
    def __init__(self) -> None:
        from openai import AsyncOpenAI

        self._client = AsyncOpenAI(
            api_key=settings.siliconflow_api_key,
            base_url=settings.siliconflow_base_url,
        )
        self._model = settings.siliconflow_llm_model

    @staticmethod
    def _messages(messages: list[Message], system: str) -> list[Message]:
        out: list[Message] = [{"role": "system", "content": system}]
        for m in messages:
            role = "assistant" if m["role"] == "model" else m["role"]
            out.append({"role": role, "content": m["content"]})
        return out

    async def generate_text(
        self, *, messages: list[Message], system: str, temperature: float
    ) -> str:
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=self._messages(messages, system),
            temperature=temperature,
        )
        return (response.choices[0].message.content or "").strip()

    async def generate_structured(
        self,
        *,
        messages: list[Message],
        system: str,
        temperature: float,
        schema: type[BaseModel],
    ) -> dict:
        schema_json = json.dumps(schema.model_json_schema(), ensure_ascii=False)
        system_with_schema = (
            f"{system}\n\n"
            "Trả về DUY NHẤT một đối tượng JSON hợp lệ theo JSON schema sau, "
            "không kèm văn bản giải thích, không dùng markdown:\n"
            f"{schema_json}"
        )
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=self._messages(messages, system_with_schema),
            temperature=temperature,
            response_format={"type": "json_object"},
        )
        text = (response.choices[0].message.content or "").strip()
        return json.loads(_strip_json_fences(text))


def _strip_json_fences(text: str) -> str:
    """Tolerate models that wrap JSON in ```json ... ``` fences."""
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[-1] if "\n" in t else t[3:]
        if t.rstrip().endswith("```"):
            t = t.rstrip()[:-3]
    return t.strip()


# ---------------------------------------------------------------------------
# Selection
# ---------------------------------------------------------------------------

_provider: LLMProvider | None = None


def get_provider() -> LLMProvider:
    global _provider
    if _provider is not None:
        return _provider

    name = (settings.llm_provider or "gemini").lower()
    if name == "gemini":
        if not settings.gemini_api_key:
            raise RuntimeError("LLM_PROVIDER=gemini nhưng GEMINI_API_KEY chưa được cấu hình.")
        _provider = GeminiProvider()
    elif name == "siliconflow":
        if not settings.siliconflow_api_key:
            raise RuntimeError(
                "LLM_PROVIDER=siliconflow nhưng SILICONFLOW_API_KEY chưa được cấu hình."
            )
        _provider = SiliconFlowProvider()
    else:
        raise RuntimeError(
            f"LLM_PROVIDER không hợp lệ: '{settings.llm_provider}'. "
            "Chỉ hỗ trợ 'gemini' hoặc 'siliconflow'."
        )

    logger.info("LLM provider initialized: %s", name)
    return _provider
