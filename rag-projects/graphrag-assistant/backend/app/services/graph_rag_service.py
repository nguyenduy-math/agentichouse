from __future__ import annotations

import structlog

from app.config import settings
from app.models.chat import ChatResponse, VerificationResult
from app.prompts.verification_prompts import FALLBACK_ANSWER
from app.models.graph import PolicySource, GraphData, GraphNode, GraphEdge
from app.services.embedding_service import EmbeddingService
from app.services.llm_service import LLMService
from app.services.neo4j_store import Neo4jStore
from app.services.session_service import SessionService

logger = structlog.get_logger()


class GraphRAGService:
    def __init__(
        self,
        llm_service: LLMService,
        embedding_service: EmbeddingService,
        neo4j_store: Neo4jStore,
        session_service: SessionService,
    ) -> None:
        self._llm = llm_service
        self._emb = embedding_service
        self._store = neo4j_store
        self._sessions = session_service

    async def process_message(self, session_id: str, message: str) -> ChatResponse:
        session = self._sessions.get_session(session_id)
        history = [
            {"role": m.role, "content": m.content}
            for m in (session.messages if session else [])
        ]

        query_type = await self._llm.classify_query(message)
        logger.info("query_classified", query_type=query_type, message=message[:80])

        embedding = await self._emb.embed_query(message)

        if query_type == "GLOBAL":
            context, sources, graph_data = await self._global_search(embedding)
        else:
            context, sources, graph_data = await self._local_search(embedding)

        reply = await self._llm.generate(
            system_prompt=self._build_system_prompt(context),
            history=history,
            user_message=message,
        )

        verification: VerificationResult | None = None
        if settings.enable_answer_verification:
            verification = await self._llm.verify_answer(message, context, reply)
            if not verification.is_grounded or verification.confidence < 3:
                reply = FALLBACK_ANSWER

        self._sessions.append_message(session_id, "user", message)
        self._sessions.append_message(session_id, "assistant", reply)

        return ChatResponse(
            session_id=session_id,
            reply=reply,
            sources=sources,
            query_type=query_type,
            graph_data=graph_data,
            verification=verification,
        )

    # ── LOCAL search ─────────────────────────────────────────────────────────

    async def _local_search(
        self, embedding: list[float]
    ) -> tuple[str, list[PolicySource], GraphData | None]:
        chunks = await self._store.vector_search_chunks(
            embedding, settings.max_local_chunks
        )

        seed_names: list[str] = []
        for c in chunks:
            seed_names.extend(c.get("entity_names") or [])
        seed_names = list(dict.fromkeys(seed_names))[:20]

        neighborhood = await self._store.get_entity_neighborhood(
            seed_names, depth=settings.graph_hop_depth
        )

        context = self._build_local_context(chunks, neighborhood)
        sources = self._build_sources(chunks)
        graph_data = self._build_graph_data(neighborhood, set(seed_names))
        return context, sources, graph_data

    def _build_local_context(self, chunks: list[dict], neighborhood: dict) -> str:
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
        grounding_chunks = await self._store.vector_search_chunks(embedding, 3)

        context = self._build_global_context(communities, grounding_chunks)
        sources = self._build_sources(grounding_chunks)
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
                    excerpt=c["text"][:300],
                    relevance_score=round(float(c.get("score", 0.0)), 4),
                    entities=", ".join((c.get("entity_names") or [])[:5]),
                )
            )
        return sources

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
