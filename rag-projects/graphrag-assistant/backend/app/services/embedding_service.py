from __future__ import annotations

import structlog
from google import genai
from google.genai import types

from app.config import settings

logger = structlog.get_logger()


class EmbeddingService:
    def __init__(self) -> None:
        self._client: genai.Client | None = None

    async def initialize(self) -> None:
        self._client = genai.Client(
            api_key=settings.google_api_key,
            http_options={"api_version": "v1beta"},
        )
        logger.info("embedding_service_initialized", model=settings.gemini_embedding_model)

    async def embed_query(self, text: str) -> list[float]:
        result = self._client.models.embed_content(
            model=settings.gemini_embedding_model,
            contents=text,
            config=types.EmbedContentConfig(task_type="RETRIEVAL_QUERY"),
        )
        return list(result.embeddings[0].values)

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        embeddings: list[list[float]] = []
        for text in texts:
            result = self._client.models.embed_content(
                model=settings.gemini_embedding_model,
                contents=text,
                config=types.EmbedContentConfig(task_type="RETRIEVAL_DOCUMENT"),
            )
            embeddings.append(list(result.embeddings[0].values))
        return embeddings
