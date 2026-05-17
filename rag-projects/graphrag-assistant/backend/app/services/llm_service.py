from __future__ import annotations

import json

import structlog
from google import genai
from google.genai import types

from app.config import settings
from app.prompts.extraction_prompts import (
    ENTITY_EXTRACTION_PROMPT,
    COMMUNITY_SUMMARY_PROMPT,
    QUERY_CLASSIFICATION_PROMPT,
)
from app.prompts.rag_prompts import ANSWER_GENERATION_PROMPT
from app.prompts.system_prompt import POLICY_SYSTEM_PROMPT

logger = structlog.get_logger()

_JSON_CONFIG = types.GenerateContentConfig(
    response_mime_type="application/json",
    temperature=0.0,
)


class LLMService:
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
    ) -> str:
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
        return response.text

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
                config=_JSON_CONFIG,
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
                config=_JSON_CONFIG,
            )
            data = json.loads(response.text)
            return data.get("query_type", "LOCAL")
        except Exception:
            return "LOCAL"
