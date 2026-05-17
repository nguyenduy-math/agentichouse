"""Offline CLI: python -m scripts.build_graph_index"""
from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.embedding_service import EmbeddingService
from app.services.indexing_service import IndexingService
from app.services.llm_service import LLMService
from app.services.neo4j_store import Neo4jStore


def progress_cb(stage: str, done: int, total: int) -> None:
    bar = f"[{done}/{total}]" if total else ""
    print(f"  {stage} {bar}", flush=True)


async def main() -> None:
    print("Khởi tạo dịch vụ...")
    embedding_service = EmbeddingService()
    await embedding_service.initialize()

    neo4j_store = Neo4jStore()
    await neo4j_store.initialize()

    llm_service = LLMService()

    indexing_service = IndexingService(
        llm_service=llm_service,
        embedding_service=embedding_service,
        neo4j_store=neo4j_store,
    )

    print("Bắt đầu pipeline lập chỉ mục...")
    result = await indexing_service.run_full_pipeline(
        raw_dir="./data/raw",
        progress_callback=progress_cb,
    )

    print("\n=== Lập chỉ mục hoàn tất ===")
    print(f"  Chunks:      {result.chunks_count}")
    print(f"  Thực thể:   {result.nodes_count}")
    print(f"  Quan hệ:    {result.edges_count}")
    print(f"  Communities: {result.communities_count}")
    print(f"  Tóm tắt:    {result.summaries_count}")

    await neo4j_store.close()


if __name__ == "__main__":
    asyncio.run(main())
