"""
Cohere multilingual cross-encoder reranking service.

Uses cohere rerank-multilingual-v3.0 to rerank retrieved chunks.
Cross-encoder processes query+chunk together for direct relevance scoring,
catching cases that cosine similarity misranks.

Decorated with @traceable for LangSmith observability (Layer 4 of pipeline).
Carried over from graphrag-assistant with @traceable added.
"""
from __future__ import annotations

import logging
import os

from langsmith import traceable

logger = logging.getLogger(__name__)


class RerankService:
    """
    Cohere cross-encoder reranker.

    Falls back gracefully if COHERE_API_KEY is not set or on API errors
    (returns documents sorted by original cosine score).
    """

    def __init__(self) -> None:
        self._api_key = os.environ.get("COHERE_API_KEY", "")
        self._model = os.environ.get(
            "COHERE_RERANK_MODEL", "rerank-multilingual-v3.0"
        )
        self._top_n = int(os.environ.get("MAX_LOCAL_CHUNKS", "8"))
        self._client = None

        if self._api_key:
            try:
                from cohere import AsyncClientV2
                self._client = AsyncClientV2(api_key=self._api_key)
            except ImportError:
                logger.warning("cohere package not installed; reranking disabled.")

    @property
    def is_available(self) -> bool:
        return self._client is not None and bool(self._api_key)

    @traceable(
        name="cohere_rerank",
        run_type="retriever",
        metadata={"model": "rerank-multilingual-v3.0"},
    )
    async def rerank(
        self,
        query: str,
        documents: list[dict],
        text_key: str = "text",
    ) -> list[dict]:
        """
        Rerank documents using Cohere cross-encoder.

        Args:
            query: The search query
            documents: List of document dicts containing text_key
            text_key: Key in each document dict containing the text to rerank

        Returns:
            Reranked documents (top self._top_n) with rerank_score added.
            If reranking is unavailable, returns documents[:self._top_n] unchanged.

        @traceable logs: input count, output count, top rerank score.
        """
        if not documents:
            return documents

        if not self.is_available:
            logger.debug("Reranking skipped (no Cohere API key or client).")
            return documents[: self._top_n]

        texts = [d.get(text_key, "") or "" for d in documents]
        top_n = min(self._top_n, len(documents))

        try:
            result = await self._client.rerank(
                model=self._model,
                query=query,
                documents=texts,
                top_n=top_n,
            )
        except Exception as exc:
            logger.warning("Cohere rerank failed: %s. Falling back to top-k by score.", exc)
            return documents[:top_n]

        reordered: list[dict] = []
        for r in result.results:
            doc = dict(documents[r.index])
            doc["rerank_score"] = float(r.relevance_score)
            reordered.append(doc)

        return reordered
