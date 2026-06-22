from google import genai
from google.genai import types

from app.config import settings


class EmbeddingService:
    def __init__(self) -> None:
        self._client = genai.Client(api_key=settings.gemini_api_key)
        self._model = settings.gemini_embedding_model

    async def embed(self, text: str) -> list[float]:
        resp = await self._client.aio.models.embed_content(
            model=self._model,
            contents=text,
            config=types.EmbedContentConfig(task_type="RETRIEVAL_QUERY"),
        )
        return resp.embeddings[0].values

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        resp = await self._client.aio.models.embed_content(
            model=self._model,
            contents=texts,
            config=types.EmbedContentConfig(task_type="RETRIEVAL_DOCUMENT"),
        )
        return [e.values for e in resp.embeddings]
