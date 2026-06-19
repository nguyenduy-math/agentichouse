from __future__ import annotations

from abc import ABC, abstractmethod

import structlog
from google import genai
from google.genai import types
from openai import AsyncOpenAI

from app.config import settings

logger = structlog.get_logger()


class EmbeddingService(ABC):
    @abstractmethod
    async def initialize(self) -> None: ...

    @abstractmethod
    async def embed_query(self, text: str) -> list[float]: ...

    @abstractmethod
    async def embed_documents(self, texts: list[str]) -> list[list[float]]: ...


class GeminiEmbeddingService(EmbeddingService):
    def __init__(self) -> None:
        self._client: genai.Client | None = None

    async def initialize(self) -> None:
        self._client = genai.Client(
            api_key=settings.google_api_key,
            http_options={"api_version": "v1beta"},
        )
        logger.info("embedding_service_initialized", provider="gemini", model=settings.gemini_embedding_model)

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


class OpenAIEmbeddingService(EmbeddingService):
    def __init__(self) -> None:
        self._client: AsyncOpenAI | None = None

    async def initialize(self) -> None:
        self._client = AsyncOpenAI(api_key=settings.openai_api_key)
        logger.info("embedding_service_initialized", provider="openai", model=settings.openai_embedding_model)

    async def embed_query(self, text: str) -> list[float]:
        result = await self._client.embeddings.create(
            model=settings.openai_embedding_model,
            input=text,
            dimensions=settings.embedding_dim,
        )
        return list(result.data[0].embedding)

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        result = await self._client.embeddings.create(
            model=settings.openai_embedding_model,
            input=texts,
            dimensions=settings.embedding_dim,
        )
        return [list(d.embedding) for d in result.data]


def create_embedding_service() -> EmbeddingService:
    provider = settings.llm_provider.lower()
    if provider == "openai":
        return OpenAIEmbeddingService()
    if provider == "gemini":
        return GeminiEmbeddingService()
    raise ValueError(f"Unknown LLM_PROVIDER: {settings.llm_provider!r} (expected 'gemini' or 'openai')")
