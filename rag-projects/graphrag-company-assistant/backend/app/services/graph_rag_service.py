from __future__ import annotations

import structlog

from app.config import settings
from app.models.chat import ChatResponse, VerificationResult
from app.prompts.verification_prompts import FALLBACK_ANSWER
from app.models.graph import PolicySource, GraphData, GraphNode, GraphEdge
from app.services.embedding_service import EmbeddingService
from app.services.llm_service import LLMService
from app.services.neo4j_store import Neo4jStore
from app.services.rerank_service import RerankService
from app.services.session_service import SessionService

logger = structlog.get_logger()


class GraphRAGService:
    def __init__(
        self,
        llm_service: LLMService,
        embedding_service: EmbeddingService,
        neo4j_store: Neo4jStore,
        session_service: SessionService,
        rerank_service: RerankService | None = None,
    ) -> None:
        self._llm = llm_service
        self._emb = embedding_service
        self._store = neo4j_store
        self._sessions = session_service
        self._rerank = rerank_service

    async def process_message(self, session_id: str, message: str) -> ChatResponse:
        session = self._sessions.get_session(session_id)
        history = [
            {"role": m.role, "content": m.content}
            for m in (session.messages[-10:] if session else [])
        ]

        query_type = await self._llm.classify_query(message)
        logger.info("query_classified", query_type=query_type, message=message[:80])

        retrieval_query = await self._llm.rewrite_query(history, message)
        logger.info("retrieval_query_rewritten", rewritten=retrieval_query[:120])
        embedding = await self._emb.embed_query(retrieval_query)

        if query_type == "GLOBAL":
            context, sources, graph_data = await self._global_search(embedding)
        else:
            context, sources, graph_data = await self._local_search(embedding, retrieval_query)

        reply = await self._llm.generate(
            system_prompt=self._build_system_prompt(context),
            history=history,
            user_message=message,
        )

        verification: VerificationResult | None = None
        is_fallback = False
        if settings.enable_answer_verification:
            verification = await self._llm.verify_answer(message, context, reply)
            if not verification.is_grounded or verification.confidence < 3:
                reply = FALLBACK_ANSWER
                is_fallback = True

        self._sessions.append_message(session_id, "user", message)
        self._sessions.append_message(session_id, "assistant", reply)

        return ChatResponse(
            session_id=session_id,
            reply=reply,
            sources=sources,
            query_type=query_type,
            graph_data=graph_data,
            verification=verification,
            is_fallback=is_fallback,
        )

    # ── LOCAL search ─────────────────────────────────────────────────────────

    async def _local_search(
        self, embedding: list[float], retrieval_query: str
    ) -> tuple[str, list[PolicySource], GraphData | None]:
        # Overfetch from vector search to give the reranker headroom.
        pool_size = (
            settings.rerank_candidate_pool
            if (settings.enable_rerank and self._rerank is not None)
            else settings.max_local_chunks
        )
        chunks = await self._store.vector_search_chunks(embedding, pool_size)

        # Entity-augmentation seeds come from the raw vector pool (broad recall).
        seed_pool: list[str] = []
        for c in chunks:
            seed_pool.extend(c.get("entity_names") or [])
        seed_pool = list(dict.fromkeys(seed_pool))[:20]

        # Augment with entity-linked chunks using type-aware thresholds:
        # - Specific-type entities (QUY_TAC, CHINH_SACH, etc.) are scoped to a single
        #   policy area → min_hits=1 is safe and recovers cross-aspect recall.
        # - Generic entities (VAI_TRO, PHONG_BAN) appear everywhere → require 2+
        #   co-occurrences to avoid flooding the context with off-topic chunks.
        specific_seeds = await self._store.get_specific_entity_names(seed_pool)
        if specific_seeds:
            entity_chunks = await self._store.get_chunks_by_entity_names(
                specific_seeds, k=3, min_entity_hits=1
            )
        else:
            entity_chunks = await self._store.get_chunks_by_entity_names(
                seed_pool, k=3, min_entity_hits=2
            )
        seen_ids = {c["id"] for c in chunks}
        for ec in entity_chunks:
            if ec["id"] not in seen_ids:
                chunks.append(ec)
                seen_ids.add(ec["id"])

        # Two-stage funnel: vector + entity recall → cross-encoder precision.
        if settings.enable_rerank and self._rerank is not None:
            chunks = await self._rerank.rerank(retrieval_query, chunks)
        else:
            chunks = chunks[: settings.max_local_chunks]

        # Anchor the graph neighborhood on the *winning* entities post-rerank.
        seed_names: list[str] = []
        for c in chunks:
            seed_names.extend(c.get("entity_names") or [])
        seed_names = list(dict.fromkeys(seed_names))[:20]

        neighborhood = await self._store.get_entity_neighborhood(
            seed_names, depth=settings.graph_hop_depth
        )

        context = self._build_local_context(chunks, neighborhood, seed_names=set(seed_names))
        sources = self._build_sources(chunks)
        graph_source = self._build_graph_source(neighborhood)
        if graph_source:
            sources.append(graph_source)
        graph_data = self._build_graph_data(neighborhood, set(seed_names))
        return context, sources, graph_data

    def _build_local_context(
        self, chunks: list[dict], neighborhood: dict, seed_names: set[str] | None = None
    ) -> str:
        parts: list[str] = ["## Đoạn văn bản liên quan:"]
        for c in chunks:
            parts.append(
                f"[{c['source_file']} | {c['doc_type']} | trang {c['page_number']}]\n{c['text']}"
            )

        entities = neighborhood.get("entities", [])
        if entities:
            parts.append("\n## Các thực thể liên quan:")
            for e in entities[:20]:
                parts.append(f"- {e['name']} ({e['type']}): {e['description']}")

        triples = neighborhood.get("triples", [])
        if triples:
            # Only include triples where both endpoints are seed entities (directly from
            # matched chunks). 2-hop neighbors produce unrelated triples that cause the
            # LLM to hallucinate rules not present in the retrieved text.
            if seed_names:
                triples = [
                    t for t in triples
                    if t.get("source") in seed_names and t.get("target") in seed_names
                ]
            parts.append("\n## Quan hệ trong đồ thị tri thức:")
            for t in triples[:30]:
                parts.append(f"- {t['source']} --[{t['relation']}]--> {t['target']}")

        return "\n".join(parts)

    # ── GLOBAL search ─────────────────────────────────────────────────────────

    async def _global_search(
        self, embedding: list[float]
    ) -> tuple[str, list[PolicySource], GraphData | None]:
        communities = await self._store.vector_search_communities(
            embedding, settings.max_community_summaries
        )
        grounding_chunks = await self._store.vector_search_chunks(embedding, 6)

        context = self._build_global_context(communities, grounding_chunks)
        sources = self._build_community_sources(communities) + self._build_sources(grounding_chunks)
        return context, sources, None

    def _build_global_context(
        self, communities: list[dict], chunks: list[dict]
    ) -> str:
        parts: list[str] = ["## Tóm tắt các chủ đề chính sách liên quan:"]
        for idx, c in enumerate(communities, 1):
            parts.append(f"\n### Nhóm chủ đề {idx} ({c.get('node_count', 0)} thực thể):")
            parts.append(c.get("summary", ""))

        if chunks:
            parts.append("\n## Ví dụ minh họa từ tài liệu:")
            for c in chunks:
                parts.append(
                    f"[{c['source_file']} | trang {c['page_number']}]\n{c['text'][:500]}..."
                )

        return "\n".join(parts)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _build_sources(self, chunks: list[dict]) -> list[PolicySource]:
        sources: list[PolicySource] = []
        seen: set[str] = set()
        for c in chunks:
            key = f"{c['source_file']}:{c['page_number']}"
            if key in seen:
                continue
            seen.add(key)
            sources.append(
                PolicySource(
                    source_file=c["source_file"],
                    doc_type=c.get("doc_type", ""),
                    page_number=c.get("page_number", 0),
                    excerpt=c["text"],
                    relevance_score=round(float(c.get("rerank_score", c.get("score", 0.0))), 4),
                    entities=", ".join((c.get("entity_names") or [])[:5]),
                )
            )
        return sources

    def _build_community_sources(self, communities: list[dict]) -> list[PolicySource]:
        sources: list[PolicySource] = []
        for idx, c in enumerate(communities, 1):
            summary = c.get("summary") or ""
            if not summary:
                continue
            community_id = c.get("community_id", idx)
            sources.append(
                PolicySource(
                    source_file=f"community_{community_id}",
                    doc_type="community_summary",
                    page_number=0,
                    excerpt=summary,
                    relevance_score=round(float(c.get("score", 0.0)), 4),
                    entities="",
                )
            )
        return sources

    def _build_graph_source(self, neighborhood: dict) -> PolicySource | None:
        entities = neighborhood.get("entities", [])
        triples = neighborhood.get("triples", [])
        if not entities and not triples:
            return None

        parts: list[str] = []
        if entities:
            parts.append("Các thực thể liên quan:")
            for e in entities[:20]:
                desc = e.get("description") or ""
                parts.append(f"- {e['name']} ({e.get('type', '')}): {desc}")
        if triples:
            if parts:
                parts.append("")
            parts.append("Quan hệ trong đồ thị tri thức:")
            for t in triples[:30]:
                parts.append(f"- {t['source']} --[{t['relation']}]--> {t['target']}")

        entity_names = [e["name"] for e in entities[:5] if e.get("name")]
        return PolicySource(
            source_file="knowledge_graph",
            doc_type="graph_relations",
            page_number=0,
            excerpt="\n".join(parts),
            relevance_score=0.0,
            entities=", ".join(entity_names),
        )

    def _build_graph_data(self, neighborhood: dict, seed_names: set[str]) -> GraphData | None:
        all_entities = neighborhood.get("entities", [])
        all_triples = neighborhood.get("triples", [])

        entities = [e for e in all_entities if e.get("name") in seed_names]
        if not entities:
            return None

        kept = {e["name"] for e in entities}
        nodes = [
            GraphNode(
                id=e["name"],
                label=e["name"],
                type=e.get("type") or "",
                description=e.get("description") or "",
            )
            for e in entities
        ]
        edges = [
            GraphEdge(source=t["source"], relation=t["relation"], target=t["target"])
            for t in all_triples
            if t.get("source") in kept and t.get("target") in kept
        ]
        return GraphData(nodes=nodes, edges=edges)

    def _build_system_prompt(self, context: str) -> str:
        from app.prompts.system_prompt import POLICY_SYSTEM_PROMPT
        return POLICY_SYSTEM_PROMPT.format(context=context)
