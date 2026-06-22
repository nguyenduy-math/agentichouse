import json
from pathlib import Path

import structlog
from rank_bm25 import BM25Okapi

from app.config import settings

log = structlog.get_logger()


def _tokenize(text: str) -> list[str]:
    return text.lower().split()


class BM25Service:
    def __init__(self, name: str = "default") -> None:
        self._name = name
        self._index: BM25Okapi | None = None
        self._corpus_ids: list[str] = []
        self._corpus_texts: list[str] = []
        base = Path(settings.bm25_index_path)
        self._index_path = base.parent / f"bm25_{name}.json"

    def load(self) -> None:
        if self._index_path.exists():
            with self._index_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            self._corpus_ids = [item["id"] for item in data]
            self._corpus_texts = [item["text"] for item in data]
            self._index = BM25Okapi([_tokenize(t) for t in self._corpus_texts])
            log.info("bm25.loaded", name=self._name, size=len(self._corpus_ids))
        else:
            log.info("bm25.no_index_found", name=self._name)

    def rebuild(self, chunk_ids: list[str], chunk_texts: list[str]) -> None:
        self._corpus_ids = chunk_ids
        self._corpus_texts = chunk_texts
        self._index = BM25Okapi([_tokenize(t) for t in chunk_texts])
        self._index_path.parent.mkdir(parents=True, exist_ok=True)
        data = [{"id": id_, "text": text} for id_, text in zip(chunk_ids, chunk_texts)]
        with self._index_path.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        log.info("bm25.rebuilt", name=self._name, size=len(chunk_ids))

    def search(self, query: str, k: int | None = None) -> list[tuple[str, float]]:
        if self._index is None or not self._corpus_ids:
            return []
        k = k or settings.bm25_top_k
        scores = self._index.get_scores(_tokenize(query))
        top_k = min(k, len(self._corpus_ids))
        indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]
        return [(self._corpus_ids[i], float(scores[i])) for i in indices]

    @property
    def corpus_size(self) -> int:
        return len(self._corpus_ids)
