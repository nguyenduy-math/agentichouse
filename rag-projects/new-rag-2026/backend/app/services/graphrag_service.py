"""
GraphRAG query service wrapping Microsoft GraphRAG LocalSearch and GlobalSearch.

Uses Neo4j for vector similarity search (entity and community embeddings).
Reads graph structure from Parquet artifacts (Option B — safe hybrid default).

Option A (native Neo4j storage) is available when graphrag 2.x stabilizes
the storage.type: neo4j backend — swap the storage block in settings.yaml.
"""
from __future__ import annotations

import asyncio
import logging
import os
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class SearchMode(str, Enum):
    LOCAL = "local"
    GLOBAL = "global"


class GraphRAGService:
    """
    Wraps Microsoft GraphRAG LocalSearch and GlobalSearch.

    Uses Neo4j for vector similarity search via _Neo4jEntityVectorStoreAdapter.
    Reads graph structure from Parquet artifacts at startup (Option B).

    Thread safety: asyncio.Lock() guards the search engine reload path.
    """

    def __init__(self, workspace_root: str, neo4j_store: Any) -> None:
        self._root = Path(workspace_root)
        self._artifacts = self._root / "output" / "artifacts"
        self._neo4j = neo4j_store
        self._local_search: Any | None = None
        self._global_search: Any | None = None
        self._lock = asyncio.Lock()

    @property
    def is_ready(self) -> bool:
        return self._local_search is not None and self._global_search is not None

    async def search(self, question: str, mode: SearchMode) -> dict[str, Any]:
        """
        Execute a GraphRAG search query.

        Args:
            question: The user's question (Vietnamese)
            mode: LOCAL for single-domain, GLOBAL for cross-domain

        Returns:
            dict with keys: reply (str), sources (list[dict])
        """
        engine = self._local_search if mode == SearchMode.LOCAL else self._global_search

        if engine is None:
            logger.warning("GraphRAG not ready — no artifacts found or not loaded.")
            return {"reply": "", "sources": []}

        try:
            result = await engine.asearch(question)
            return {
                "reply": result.response,
                "sources": self._extract_sources(result.context_data),
            }
        except Exception as exc:
            logger.error("GraphRAG search error: %s", exc)
            return {"reply": "", "sources": []}

    async def reload(self) -> None:
        """
        (Re)load search engines from Parquet artifacts.
        Called after indexing + Neo4j import completes.
        Thread-safe via asyncio.Lock().
        """
        async with self._lock:
            try:
                self._local_search = await asyncio.to_thread(self._build_local_search)
                self._global_search = await asyncio.to_thread(self._build_global_search)
                logger.info("GraphRAG search engines loaded successfully.")
            except Exception as exc:
                logger.error("Failed to load GraphRAG search engines: %s", exc)
                self._local_search = None
                self._global_search = None

    def _get_llm(self) -> Any:
        """
        GraphRAG's own LLM client for query-time summarization.
        Uses Gemini via OpenAI-compatible endpoint.
        Separate from the agent-layer LLM.
        """
        from graphrag.query.llm.oai.chat_openai import ChatOpenAI
        from graphrag.query.llm.oai.typing import OpenaiApiType

        return ChatOpenAI(
            api_key=os.environ.get("GEMINI_API_KEY", ""),
            model=os.environ.get("GRAPHRAG_QUERY_MODEL", "gemini-2.0-flash"),
            api_base="https://generativelanguage.googleapis.com/v1beta/openai/",
            api_type=OpenaiApiType.OpenAI,
            max_retries=10,
        )

    def _get_embedder(self) -> Any:
        """GraphRAG embedding client for query-time entity matching."""
        from graphrag.query.llm.oai.embedding import OpenAIEmbedding
        from graphrag.query.llm.oai.typing import OpenaiApiType

        return OpenAIEmbedding(
            api_key=os.environ.get("GEMINI_API_KEY", ""),
            model=os.environ.get("EMBEDDING_MODEL", "text-embedding-004"),
            api_base="https://generativelanguage.googleapis.com/v1beta/openai/",
            api_type=OpenaiApiType.OpenAI,
            max_retries=10,
        )

    def _build_local_search(self) -> Any:
        """
        Build GraphRAG LocalSearch from Parquet artifacts + Neo4j vector store.
        Runs in a thread (CPU-bound Parquet reads).
        """
        import pandas as pd
        from graphrag.query.context_builder.entity_extraction import EntityVectorStoreKey
        from graphrag.query.indexer_adapters import (
            read_indexer_communities,
            read_indexer_entities,
            read_indexer_relationships,
            read_indexer_reports,
            read_indexer_text_units,
        )
        from graphrag.query.structured_search.local_search.mixed_context import (
            LocalSearchMixedContext,
        )
        from graphrag.query.structured_search.local_search.search import LocalSearch

        a = self._artifacts
        entity_df = pd.read_parquet(a / "create_final_entities.parquet")
        rel_df = pd.read_parquet(a / "create_final_relationships.parquet")
        report_df = pd.read_parquet(a / "create_final_community_reports.parquet")
        text_unit_df = pd.read_parquet(a / "create_final_text_units.parquet")
        node_df = pd.read_parquet(a / "create_final_nodes.parquet")

        entities = read_indexer_entities(entity_df, node_df, community_level=2)
        relationships = read_indexer_relationships(rel_df)
        reports = read_indexer_reports(report_df, node_df, community_level=2)
        text_units = read_indexer_text_units(text_unit_df)

        # Neo4j vector store adapter instead of LanceDB
        entity_store = self._neo4j.as_entity_vector_store()

        context_builder = LocalSearchMixedContext(
            community_reports=reports,
            text_units=text_units,
            entities=entities,
            relationships=relationships,
            entity_text_embeddings=entity_store,
            embedding_vectorstore_key=EntityVectorStoreKey.ID,
            text_embedder=self._get_embedder(),
        )

        return LocalSearch(
            llm=self._get_llm(),
            context_builder=context_builder,
            token_encoder=None,
            llm_params={"max_tokens": 2000, "temperature": 0},
            context_builder_params={
                "text_unit_prop": 0.5,
                "community_prop": 0.1,
                "conversation_history_max_turns": 5,
                "top_k_mapped_entities": 10,
                "top_k_relationships": 10,
                "max_tokens": 12000,
            },
        )

    def _build_global_search(self) -> Any:
        """
        Build GraphRAG GlobalSearch from Parquet artifacts.
        Runs in a thread (CPU-bound Parquet reads).
        """
        import pandas as pd
        from graphrag.query.indexer_adapters import (
            read_indexer_entities,
            read_indexer_reports,
        )
        from graphrag.query.structured_search.global_search.community_context import (
            GlobalCommunityContext,
        )
        from graphrag.query.structured_search.global_search.search import GlobalSearch

        a = self._artifacts
        report_df = pd.read_parquet(a / "create_final_community_reports.parquet")
        node_df = pd.read_parquet(a / "create_final_nodes.parquet")
        entity_df = pd.read_parquet(a / "create_final_entities.parquet")

        reports = read_indexer_reports(report_df, node_df, community_level=2)
        entities = read_indexer_entities(entity_df, node_df, community_level=2)

        context_builder = GlobalCommunityContext(
            community_reports=reports,
            entities=entities,
            token_encoder=None,
        )

        return GlobalSearch(
            llm=self._get_llm(),
            context_builder=context_builder,
            token_encoder=None,
            max_data_tokens=12000,
            map_llm_params={"max_tokens": 1000, "temperature": 0},
            reduce_llm_params={"max_tokens": 2000, "temperature": 0},
            concurrent_coroutines=32,
            response_type="multiple paragraphs",
        )

    def _extract_sources(self, context_data: Any) -> list[dict]:
        """Extract source references from GraphRAG context_data."""
        sources: list[dict] = []

        if not context_data:
            return sources

        # Handle both dict and object-style context_data
        if isinstance(context_data, dict):
            text_units = context_data.get("text_units", [])
            reports = context_data.get("reports", [])
        else:
            text_units = getattr(context_data, "text_units", []) or []
            reports = getattr(context_data, "reports", []) or []

        for unit in text_units:
            if isinstance(unit, dict):
                sources.append({
                    "type": "text_unit",
                    "id": unit.get("id"),
                    "text": (unit.get("text", "") or "")[:400],
                    "document": unit.get("document_id"),
                })
            else:
                sources.append({
                    "type": "text_unit",
                    "id": getattr(unit, "id", None),
                    "text": (getattr(unit, "text", "") or "")[:400],
                    "document": getattr(unit, "document_id", None),
                })

        for report in reports:
            if isinstance(report, dict):
                sources.append({
                    "type": "community_report",
                    "id": report.get("id"),
                    "title": report.get("title"),
                    "summary": (report.get("summary", "") or "")[:400],
                })
            else:
                sources.append({
                    "type": "community_report",
                    "id": getattr(report, "id", None),
                    "title": getattr(report, "title", None),
                    "summary": (getattr(report, "summary", "") or "")[:400],
                })

        return sources
