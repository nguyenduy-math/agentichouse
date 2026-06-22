from collections import defaultdict

from app.config import settings


def rrf_merge(
    bm25_results: list[tuple[str, float]],
    vector_results: list[tuple[str, float, dict, str]],
    k: int | None = None,
) -> list[str]:
    """Reciprocal Rank Fusion over BM25 and vector result lists.

    Returns a deduplicated list of chunk_ids sorted by fused score descending.
    """
    k = k or settings.rrf_k
    scores: dict[str, float] = defaultdict(float)

    for rank, (chunk_id, _) in enumerate(bm25_results):
        scores[chunk_id] += 1.0 / (k + rank + 1)

    for rank, (chunk_id, _, _meta, _text) in enumerate(vector_results):
        scores[chunk_id] += 1.0 / (k + rank + 1)

    return sorted(scores.keys(), key=lambda cid: scores[cid], reverse=True)
