import structlog
from sentence_transformers import CrossEncoder

from app.config import settings

log = structlog.get_logger()


class RerankService:
    def __init__(self) -> None:
        log.info("reranker.loading", model=settings.reranker_model)
        self._model = CrossEncoder(settings.reranker_model)
        log.info("reranker.ready")

    def rerank(
        self,
        query: str,
        candidates: list[dict],  # each has "chunk_id", "text", "metadata"
        top_n: int | None = None,
    ) -> list[dict]:
        top_n = top_n or settings.reranker_top_n
        if not candidates:
            return []
        pairs = [(query, c["text"]) for c in candidates]
        scores = self._model.predict(pairs)
        ranked = sorted(
            zip(candidates, scores), key=lambda x: x[1], reverse=True
        )
        result = []
        for candidate, score in ranked[:top_n]:
            result.append({**candidate, "rerank_score": float(score)})
        return result
