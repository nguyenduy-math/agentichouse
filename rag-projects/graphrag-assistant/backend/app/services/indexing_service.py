from __future__ import annotations

import asyncio
import os
from typing import Callable

import community as community_louvain
import networkx as nx
import structlog

from app.config import settings
from app.models.documents import ChunkWithMeta, NodeData
from app.models.graph import IndexingResult
from app.services.embedding_service import EmbeddingService
from app.services.llm_service import LLMService
from app.services.neo4j_store import Neo4jStore
from app.utils.document_parser import parse_document
from app.utils.text_splitter import split_by_article, split_text

logger = structlog.get_logger()

ProgressCallback = Callable[[str, int, int], None]

DOC_TYPES = ["handbooks", "hr_policies", "conduct", "benefits", "procedures"]


class IndexingService:
    def __init__(
        self,
        llm_service: LLMService,
        embedding_service: EmbeddingService,
        neo4j_store: Neo4jStore,
    ) -> None:
        self._llm = llm_service
        self._emb = embedding_service
        self._store = neo4j_store

    async def run_full_pipeline(
        self,
        raw_dir: str,
        progress_callback: ProgressCallback | None = None,
    ) -> IndexingResult:
        def cb(stage: str, done: int, total: int) -> None:
            if progress_callback:
                progress_callback(stage, done, total)

        await self._store.clear()

        # Stage 1: Parse & chunk
        chunks = self._parse_all(raw_dir)
        cb("parsing", len(chunks), len(chunks))
        logger.info("parsed_chunks", count=len(chunks))

        # Stage 2: Extract entities + relations, store in Neo4j
        all_entity_names_per_chunk: dict[str, list[str]] = {}
        batch = settings.entity_extraction_batch
        for i in range(0, len(chunks), batch):
            batch_chunks = chunks[i : i + batch]
            for j, chunk in enumerate(batch_chunks):
                result = await self._llm.extract_entities_and_relations(chunk.text)
                entity_names = await self._store_entities_and_relations(chunk, result)
                all_entity_names_per_chunk[chunk.id] = entity_names
                cb("extracting", i + j + 1, len(chunks))
            if i + batch < len(chunks):
                await asyncio.sleep(1.0)

        logger.info("extraction_complete")

        # Stage 3: Embed chunks and store in Neo4j
        for idx, chunk in enumerate(chunks):
            entity_names = all_entity_names_per_chunk.get(chunk.id, [])
            embedding = await self._emb.embed_documents([chunk.text])
            await self._store.upsert_chunk(chunk, embedding[0], entity_names)
            for name in entity_names:
                await self._store.link_chunk_to_entity(chunk.id, name)
            cb("embedding_chunks", idx + 1, len(chunks))

        # Stage 4: Community detection via python-louvain
        nodes, edges = await self._store.get_all_entities_and_edges()
        G = nx.Graph()
        for n in nodes:
            G.add_node(n["name"])
        for src, tgt, data in edges:
            G.add_edge(src, tgt)

        communities: dict[int, list[str]] = {}
        if G.number_of_nodes() > 0:
            partition = community_louvain.best_partition(G)
            for node_name, comm_id in partition.items():
                await self._store.set_entity_community(node_name, comm_id)
                communities.setdefault(comm_id, []).append(node_name)

        cb("community_detection", 1, 1)
        logger.info("communities_detected", count=len(communities))

        # Stage 5: Generate + embed community summaries
        eligible = {cid: names for cid, names in communities.items() if len(names) >= 3}
        for idx, (comm_id, node_names) in enumerate(eligible.items()):
            nodes_data = [n for n in nodes if n["name"] in node_names]
            edges_data = [
                (src, tgt, data)
                for src, tgt, data in edges
                if src in node_names or tgt in node_names
            ]
            summary = await self._llm.generate_community_summary(nodes_data, edges_data)
            emb = await self._emb.embed_documents([summary])
            await self._store.upsert_community(comm_id, summary, emb[0], node_names)
            cb("summarizing", idx + 1, len(eligible))

        stats = await self._store.get_stats()
        return IndexingResult(
            chunks_count=stats.get("chunks", len(chunks)),
            nodes_count=stats.get("entities", 0),
            edges_count=stats.get("edges", 0),
            communities_count=stats.get("communities", 0),
            summaries_count=len(eligible),
        )

    def _parse_all(self, raw_dir: str) -> list[ChunkWithMeta]:
        chunks: list[ChunkWithMeta] = []
        for doc_type in DOC_TYPES:
            folder = os.path.join(raw_dir, doc_type)
            if not os.path.isdir(folder):
                continue
            for fname in sorted(os.listdir(folder)):
                fpath = os.path.join(folder, fname)
                if not os.path.isfile(fpath):
                    continue
                pages = parse_document(fpath)
                for page in pages:
                    for idx, chunk_text in enumerate(
                        split_by_article(page["text"], settings.chunk_size)
                    ):
                        chunks.append(
                            ChunkWithMeta(
                                text=chunk_text,
                                source_file=fname,
                                doc_type=doc_type,
                                page_number=page["page"],
                                chunk_index=idx,
                            )
                        )
        return chunks

    async def _store_entities_and_relations(
        self, chunk: ChunkWithMeta, extraction: dict
    ) -> list[str]:
        entity_names: list[str] = []
        for e in extraction.get("entities", []):
            name = e.get("name", "").strip()
            if not name:
                continue
            node = NodeData(
                name=name,
                type=e.get("type", "CHINH_SACH"),
                description=e.get("description", ""),
                source_chunk_ids=[chunk.id],
            )
            await self._store.upsert_entity(node)
            entity_names.append(name)

        for rel in extraction.get("relations", []):
            src = rel.get("source", "").strip()
            tgt = rel.get("target", "").strip()
            relation = rel.get("relation", "THAM_CHIEU").strip()
            if src and tgt and src != tgt:
                await self._store.upsert_relationship(src, relation, tgt)

        return entity_names
