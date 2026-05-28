from __future__ import annotations

import structlog
import cohere

logger = structlog.get_logger()


class RerankService:
    def __init__(self, api_key: str, model: str, top_n: int) -> None:
        self._model = model
        self._top_n = top_n
        self._client = cohere.AsyncClientV2(api_key=api_key)

    async def rerank(
        self,
        query: str,
        documents: list[dict],
        text_key: str = "text",
    ) -> list[dict]:
        if not documents:
            return documents

        texts = [d.get(text_key, "") for d in documents]
        top_n = min(self._top_n, len(documents))

        try:
            result = await self._client.rerank(
                model=self._model,
                query=query,
                documents=texts,
                top_n=top_n,
            )
        except Exception as exc:
            logger.warning("rerank_failed", error=str(exc), model=self._model)
            return documents

        reordered: list[dict] = []
        for r in result.results:
            doc = dict(documents[r.index])
            doc["rerank_score"] = float(r.relevance_score)
            reordered.append(doc)

        logger.info(
            "rerank_complete",
            input_count=len(documents),
            output_count=len(reordered),
            top_score=reordered[0]["rerank_score"] if reordered else None,
        )
        return reordered
