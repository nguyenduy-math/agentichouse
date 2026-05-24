from __future__ import annotations

import json

import structlog
from openai import AsyncOpenAI

from app.config import settings
from app.prompts.extraction_prompts import (
    ENTITY_EXTRACTION_PROMPT,
    COMMUNITY_SUMMARY_PROMPT,
    QUERY_CLASSIFICATION_PROMPT,
)
from app.prompts.rag_prompts import ANSWER_GENERATION_PROMPT
from app.prompts.system_prompt import POLICY_SYSTEM_PROMPT  # noqa: F401 (kept for interface parity)

logger = structlog.get_logger()


class OpenAILLMService:
    def __init__(self) -> None:
        self._client = AsyncOpenAI(api_key=settings.openai_api_key)
        self._model = settings.openai_model

    async def generate(
        self,
        system_prompt: str,
        history: list[dict],
        user_message: str,
        temperature: float = 0.3,
    ) -> str:
        messages: list[dict] = [{"role": "system", "content": system_prompt}]
        for msg in history:
            role = "assistant" if msg["role"] in ("assistant", "model") else "user"
            messages.append({"role": role, "content": msg["content"]})
        messages.append({"role": "user", "content": user_message})
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            temperature=temperature,
            max_tokens=2048,
        )
        return response.choices[0].message.content

    async def generate_answer(self, question: str, context: str) -> str:
        prompt = ANSWER_GENERATION_PROMPT.format(question=question, context=context)
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=2048,
        )
        return response.choices[0].message.content

    async def extract_entities_and_relations(self, chunk_text: str) -> dict:
        prompt = ENTITY_EXTRACTION_PROMPT.format(chunk_text=chunk_text)
        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0.0,
            )
            return json.loads(response.choices[0].message.content)
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
        return response.choices[0].message.content

    async def classify_query(self, question: str) -> str:
        prompt = QUERY_CLASSIFICATION_PROMPT.format(question=question)
        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0.0,
            )
            data = json.loads(response.choices[0].message.content)
            return data.get("query_type", "LOCAL")
        except Exception:
            return "LOCAL"
