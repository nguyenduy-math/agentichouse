from __future__ import annotations

import json
from abc import ABC, abstractmethod

import structlog
from google import genai
from google.genai import types
from openai import AsyncOpenAI

from app.config import settings
from app.models.chat import TokenUsage, VerificationResult
from app.prompts.extraction_prompts import (
    ENTITY_EXTRACTION_PROMPT,
    COMMUNITY_SUMMARY_PROMPT,
    QUERY_CLASSIFICATION_PROMPT,
)
from app.prompts.rag_prompts import ANSWER_GENERATION_PROMPT
from app.prompts.verification_prompts import ANSWER_VERIFICATION_PROMPT

logger = structlog.get_logger()


class LLMService(ABC):
    @abstractmethod
    async def generate(
        self,
        system_prompt: str,
        history: list[dict],
        user_message: str,
        temperature: float = 0.3,
    ) -> tuple[str, TokenUsage]: ...

    @abstractmethod
    async def generate_answer(self, question: str, context: str) -> str: ...

    @abstractmethod
    async def extract_entities_and_relations(self, chunk_text: str) -> dict: ...

    @abstractmethod
    async def generate_community_summary(
        self,
        nodes_data: list[dict],
        edges_data: list[tuple],
    ) -> str: ...

    @abstractmethod
    async def classify_query(self, question: str) -> str: ...

    @abstractmethod
    async def verify_answer(self, question: str, context: str, answer: str) -> VerificationResult: ...


_GEMINI_JSON_CONFIG = types.GenerateContentConfig(
    response_mime_type="application/json",
    temperature=0.0,
)


class GeminiLLMService(LLMService):
    def __init__(self) -> None:
        self._client = genai.Client(
            api_key=settings.google_api_key,
            http_options={"api_version": "v1beta"},
        )
        self._model = settings.gemini_model

    async def generate(
        self,
        system_prompt: str,
        history: list[dict],
        user_message: str,
        temperature: float = 0.3,
    ) -> tuple[str, TokenUsage]:
        gemini_history = [
            types.Content(
                role="user" if msg["role"] == "user" else "model",
                parts=[types.Part(text=msg["content"])],
            )
            for msg in history
        ]
        chat = self._client.chats.create(model=self._model, history=gemini_history)
        full_message = (
            f"{system_prompt}\n\n{user_message}" if not gemini_history else user_message
        )
        response = chat.send_message(
            full_message,
            config=types.GenerateContentConfig(temperature=temperature, max_output_tokens=2048),
        )
        try:
            meta = response.usage_metadata
            usage = TokenUsage(
                prompt_tokens=meta.prompt_token_count or 0,
                completion_tokens=meta.candidates_token_count or 0,
                total_tokens=meta.total_token_count or 0,
                model=self._model,
                llm_provider="gemini",
            )
        except Exception:
            usage = TokenUsage(model=self._model, llm_provider="gemini")
        return response.text, usage

    async def generate_answer(self, question: str, context: str) -> str:
        prompt = ANSWER_GENERATION_PROMPT.format(question=question, context=context)
        response = self._client.models.generate_content(
            model=self._model,
            contents=prompt,
            config=types.GenerateContentConfig(temperature=0.3, max_output_tokens=2048),
        )
        return response.text

    async def extract_entities_and_relations(self, chunk_text: str) -> dict:
        prompt = ENTITY_EXTRACTION_PROMPT.format(chunk_text=chunk_text)
        try:
            response = self._client.models.generate_content(
                model=self._model,
                contents=prompt,
                config=_GEMINI_JSON_CONFIG,
            )
            return json.loads(response.text)
        except Exception as e:
            logger.warning("entity_extraction_failed", error=str(e))
            return {"entities": [], "relations": []}

    async def generate_community_summary(
        self,
        nodes_data: list[dict],
        edges_data: list[tuple],
    ) -> str:
        nodes_text = "\n".join(
            f"- {n.get('name', '')} ({n.get('type', '')}): {n.get('description', '')}"
            for n in nodes_data[:30]
        )
        edges_text = "\n".join(
            f"- {u} --[{data.get('relation', '')}]--> {v}"
            for u, v, data in edges_data[:30]
        )
        prompt = COMMUNITY_SUMMARY_PROMPT.format(nodes_text=nodes_text, edges_text=edges_text)
        response = self._client.models.generate_content(
            model=self._model,
            contents=prompt,
            config=types.GenerateContentConfig(temperature=0.3, max_output_tokens=512),
        )
        return response.text

    async def classify_query(self, question: str) -> str:
        prompt = QUERY_CLASSIFICATION_PROMPT.format(question=question)
        try:
            response = self._client.models.generate_content(
                model=self._model,
                contents=prompt,
                config=_GEMINI_JSON_CONFIG,
            )
            data = json.loads(response.text)
            return data.get("query_type", "LOCAL")
        except Exception:
            return "LOCAL"

    async def verify_answer(self, question: str, context: str, answer: str) -> VerificationResult:
        prompt = ANSWER_VERIFICATION_PROMPT.format(
            question=question,
            context=context[:4000],
            answer=answer,
        )
        try:
            response = self._client.models.generate_content(
                model=self._model,
                contents=prompt,
                config=_GEMINI_JSON_CONFIG,
            )
            data = json.loads(response.text)
            confidence = max(1, min(5, int(data.get("confidence", 3))))
            return VerificationResult(
                is_grounded=bool(data.get("is_grounded", True)),
                confidence=confidence,
                issues=data.get("issues", []),
            )
        except Exception as e:
            logger.warning("answer_verification_failed", error=str(e))
            return VerificationResult(is_grounded=True, confidence=5, issues=[])


class OpenAILLMService(LLMService):
    def __init__(self) -> None:
        self._client = AsyncOpenAI(api_key=settings.openai_api_key)
        self._model = settings.openai_model

    async def generate(
        self,
        system_prompt: str,
        history: list[dict],
        user_message: str,
        temperature: float = 0.3,
    ) -> tuple[str, TokenUsage]:
        messages: list[dict] = [{"role": "system", "content": system_prompt}]
        for msg in history:
            role = "assistant" if msg["role"] == "assistant" else "user"
            messages.append({"role": role, "content": msg["content"]})
        messages.append({"role": "user", "content": user_message})

        response = await self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            temperature=temperature,
            max_tokens=2048,
        )
        content = response.choices[0].message.content or ""
        try:
            u = response.usage
            usage = TokenUsage(
                prompt_tokens=u.prompt_tokens,
                completion_tokens=u.completion_tokens,
                total_tokens=u.total_tokens,
                model=self._model,
                llm_provider="openai",
            )
        except Exception:
            usage = TokenUsage(model=self._model, llm_provider="openai")
        return content, usage

    async def generate_answer(self, question: str, context: str) -> str:
        prompt = ANSWER_GENERATION_PROMPT.format(question=question, context=context)
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=2048,
        )
        return response.choices[0].message.content or ""

    async def extract_entities_and_relations(self, chunk_text: str) -> dict:
        prompt = ENTITY_EXTRACTION_PROMPT.format(chunk_text=chunk_text)
        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
                response_format={"type": "json_object"},
            )
            return json.loads(response.choices[0].message.content or "{}")
        except Exception as e:
            logger.warning("entity_extraction_failed", error=str(e))
            return {"entities": [], "relations": []}

    async def generate_community_summary(
        self,
        nodes_data: list[dict],
        edges_data: list[tuple],
    ) -> str:
        nodes_text = "\n".join(
            f"- {n.get('name', '')} ({n.get('type', '')}): {n.get('description', '')}"
            for n in nodes_data[:30]
        )
        edges_text = "\n".join(
            f"- {u} --[{data.get('relation', '')}]--> {v}"
            for u, v, data in edges_data[:30]
        )
        prompt = COMMUNITY_SUMMARY_PROMPT.format(nodes_text=nodes_text, edges_text=edges_text)
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=512,
        )
        return response.choices[0].message.content or ""

    async def classify_query(self, question: str) -> str:
        prompt = QUERY_CLASSIFICATION_PROMPT.format(question=question)
        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
                response_format={"type": "json_object"},
            )
            data = json.loads(response.choices[0].message.content or "{}")
            return data.get("query_type", "LOCAL")
        except Exception:
            return "LOCAL"

    async def verify_answer(self, question: str, context: str, answer: str) -> VerificationResult:
        prompt = ANSWER_VERIFICATION_PROMPT.format(
            question=question,
            context=context[:4000],
            answer=answer,
        )
        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
                response_format={"type": "json_object"},
            )
            data = json.loads(response.choices[0].message.content or "{}")
            confidence = max(1, min(5, int(data.get("confidence", 3))))
            return VerificationResult(
                is_grounded=bool(data.get("is_grounded", True)),
                confidence=confidence,
                issues=data.get("issues", []),
            )
        except Exception as e:
            logger.warning("answer_verification_failed", error=str(e))
            return VerificationResult(is_grounded=True, confidence=5, issues=[])


def create_llm_service() -> LLMService:
    provider = settings.llm_provider.lower()
    if provider == "openai":
        return OpenAILLMService()
    if provider == "gemini":
        return GeminiLLMService()
    raise ValueError(f"Unknown LLM_PROVIDER: {settings.llm_provider!r} (expected 'gemini' or 'openai')")
