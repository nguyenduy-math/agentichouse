import structlog
import chromadb
from chromadb.config import Settings as ChromaSettings

from app.config import settings

log = structlog.get_logger()

class VectorService:
    def __init__(self, collection_name: str = "chunks") -> None:
        self._client = chromadb.PersistentClient(
            path=settings.chroma_persist_dir,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        self._col = self._client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        log.info("chroma.ready", collection=collection_name, count=self._col.count())

    def add(
        self,
        chunk_ids: list[str],
        embeddings: list[list[float]],
        texts: list[str],
        metadatas: list[dict],
    ) -> None:
        self._col.upsert(
            ids=chunk_ids,
            embeddings=embeddings,
            documents=texts,
            metadatas=metadatas,
        )
        log.info("chroma.upserted", count=len(chunk_ids))

    def search(
        self, embedding: list[float], k: int | None = None
    ) -> list[tuple[str, float, dict, str]]:
        k = k or settings.vector_top_k
        k = min(k, self._col.count() or 1)
        results = self._col.query(
            query_embeddings=[embedding],
            n_results=k,
            include=["distances", "metadatas", "documents"],
        )
        ids = results["ids"][0]
        distances = results["distances"][0]
        metadatas = results["metadatas"][0]
        documents = results["documents"][0]
        # distance in cosine space is 1 - similarity; convert to similarity score
        return [
            (ids[i], 1.0 - distances[i], metadatas[i], documents[i])
            for i in range(len(ids))
        ]

    def get_by_ids(self, chunk_ids: list[str]) -> list[dict]:
        if not chunk_ids:
            return []
        results = self._col.get(
            ids=chunk_ids,
            include=["metadatas", "documents"],
        )
        out = []
        for i, cid in enumerate(results["ids"]):
            out.append(
                {
                    "chunk_id": cid,
                    "metadata": results["metadatas"][i],
                    "text": results["documents"][i],
                }
            )
        return out

    @property
    def total_chunks(self) -> int:
        return self._col.count()
