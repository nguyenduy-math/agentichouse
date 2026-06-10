"""
Async Neo4j driver wrapper with vector search and graph traversal helpers.

Implements:
  - entity_vector_search: cosine similarity on Entity.embedding
  - community_vector_search: cosine similarity on Community.embedding
  - get_chunks_by_entity_names: type-aware entity seeding (Layer 3)
  - get_entity_neighborhood: 2-hop graph traversal (Layer 6)
  - get_specific_entity_names: type filter for entity seeding
  - get_entity_text_units: text units mentioning an entity
  - as_entity_vector_store: adapter for GraphRAG LocalSearchMixedContext

All retrieval methods decorated with @traceable for LangSmith observability.
"""
from __future__ import annotations

import asyncio
import os
from typing import Any

from langsmith import traceable
from neo4j import AsyncGraphDatabase, AsyncDriver


# ── Entity type classification ─────────────────────────────────────────────────
# Used by Layer 3 type-aware entity seeding.
# Specific types: narrow scope → min_entity_hits=1 is safe (low noise risk)
# Generic types: appear everywhere → require min_entity_hits=2 to prevent flooding

SPECIFIC_ENTITY_TYPES: frozenset[str] = frozenset({
    "chính sách",   # policy
    "quy trình",    # process
    "quy tắc",      # rule
    "quyền lợi",    # benefit/entitlement
    "ngoại lệ",     # exception
    "khái niệm",    # concept
    "sự kiện",      # event
})

GENERIC_ENTITY_TYPES: frozenset[str] = frozenset({
    "người",        # person / role
    "tổ chức",      # organization / department
    "địa điểm",     # location
})


class Neo4jStore:
    """
    Async Neo4j driver wrapper.
    Provides vector search (entity, community) and graph traversal helpers.
    """

    def __init__(self) -> None:
        self._driver: AsyncDriver | None = None

    async def connect(self) -> None:
        """Connect to Neo4j and verify connectivity."""
        self._driver = AsyncGraphDatabase.driver(
            os.environ.get("NEO4J_URI", "bolt://localhost:7687"),
            auth=(
                os.environ.get("NEO4J_USER", "neo4j"),
                os.environ.get("NEO4J_PASSWORD", ""),
            ),
        )
        await self._driver.verify_connectivity()

    async def close(self) -> None:
        """Close the Neo4j driver connection."""
        if self._driver:
            await self._driver.close()
            self._driver = None

    @property
    def is_connected(self) -> bool:
        return self._driver is not None

    # ── Vector search ──────────────────────────────────────────────────────────

    async def entity_vector_search(
        self,
        query_embedding: list[float],
        top_k: int = 10,
    ) -> list[dict[str, Any]]:
        """Return top-k entities by cosine similarity to query_embedding."""
        async with self._driver.session() as session:
            result = await session.run(
                """
                CALL db.index.vector.queryNodes(
                    'entity_embedding', $k, $embedding
                ) YIELD node, score
                RETURN node.id AS id,
                       node.name AS name,
                       node.type AS type,
                       node.description AS description,
                       score
                ORDER BY score DESC
                """,
                k=top_k,
                embedding=query_embedding,
            )
            return [dict(r) async for r in result]

    async def community_vector_search(
        self,
        query_embedding: list[float],
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        """Return top-k community summaries by cosine similarity."""
        async with self._driver.session() as session:
            result = await session.run(
                """
                CALL db.index.vector.queryNodes(
                    'community_embedding', $k, $embedding
                ) YIELD node, score
                RETURN node.id AS id,
                       node.title AS title,
                       node.summary AS summary,
                       node.level AS level,
                       score
                ORDER BY score DESC
                """,
                k=top_k,
                embedding=query_embedding,
            )
            return [dict(r) async for r in result]

    # ── Layer 3: Type-aware entity seeding ────────────────────────────────────

    @traceable(
        name="neo4j_entity_seeding",
        run_type="retriever",
        metadata={"store": "neo4j"},
    )
    async def get_chunks_by_entity_names(
        self,
        entity_names: list[str],
        k: int = 5,
        min_entity_hits: int = 2,
    ) -> list[dict[str, Any]]:
        """
        Return TextUnit nodes that co-mention at least min_entity_hits of the given entities.

        Requiring co-occurrence ensures topical focus — a chunk mentioning 3 seed entities
        is almost certainly on-topic; one mentioning only 'Nhân viên' may not be.

        @traceable logs: entity_names, min_hits, result count.
        """
        async with self._driver.session() as session:
            result = await session.run(
                """
                MATCH (t:TextUnit)-[:MENTIONS]->(e:Entity)
                WHERE e.name IN $names
                WITH t, COUNT(DISTINCT e) AS hits
                WHERE hits >= $min_hits
                RETURN t.id AS id,
                       t.text AS text,
                       t.document_id AS document_id,
                       hits AS entity_hit_count,
                       0.5 AS score
                ORDER BY hits DESC
                LIMIT $k
                """,
                names=entity_names,
                min_hits=min_entity_hits,
                k=k,
            )
            return [dict(r) async for r in result]

    @traceable(
        name="neo4j_specific_entity_filter",
        run_type="retriever",
    )
    async def get_specific_entity_names(
        self, entity_names: list[str]
    ) -> list[str]:
        """
        Filter entity names to only those with specific (non-generic) types.
        Used to decide whether min_entity_hits=1 or 2 is appropriate.

        @traceable logs: input count vs output count.
        """
        async with self._driver.session() as session:
            result = await session.run(
                """
                MATCH (e:Entity)
                WHERE e.name IN $names AND e.type IN $types
                RETURN e.name AS name
                """,
                names=entity_names,
                types=list(SPECIFIC_ENTITY_TYPES),
            )
            return [r["name"] async for r in result]

    # ── Layer 6: Graph neighborhood traversal ─────────────────────────────────

    @traceable(
        name="neo4j_graph_traversal",
        run_type="retriever",
        metadata={"store": "neo4j"},
    )
    async def get_entity_neighborhood(
        self,
        entity_names: list[str],
        depth: int = 2,
    ) -> dict[str, Any]:
        """
        2-hop (configurable) graph traversal from seed entities.

        Step 1: collect all entities reachable within `depth` hops from seeds.
        Step 2: fetch all RELATED_TO relationships among discovered entities.

        @traceable logs: entity_names, depth, entities+triples counts.

        Note: depth is interpolated into the query string (not parameterized)
        because Neo4j does not support parameterized hop bounds.
        """
        async with self._driver.session() as session:
            entities_result = await session.run(
                f"""
                UNWIND $names AS name
                MATCH (e:Entity {{name: name}})
                WITH COLLECT(DISTINCT e) AS seeds
                UNWIND seeds AS seed
                OPTIONAL MATCH (seed)-[*1..{depth}]-(neighbor:Entity)
                WITH seeds + COLLECT(DISTINCT neighbor) AS all_nodes
                UNWIND all_nodes AS node
                RETURN DISTINCT node.name AS name,
                                node.type AS type,
                                node.description AS description
                """,
                names=entity_names,
            )
            entities = [dict(r) async for r in entities_result]

            if not entities:
                return {"entities": [], "triples": []}

            all_names = [e["name"] for e in entities if e.get("name")]

            triples_result = await session.run(
                """
                MATCH (a:Entity)-[r:RELATED_TO]->(b:Entity)
                WHERE a.name IN $names AND b.name IN $names
                RETURN DISTINCT a.name AS source,
                                type(r) AS relation,
                                b.name AS target
                """,
                names=all_names,
            )
            triples = [dict(r) async for r in triples_result]

        return {"entities": entities, "triples": triples}

    # ── Utility queries ────────────────────────────────────────────────────────

    async def get_entity_text_units(
        self, entity_id: str
    ) -> list[dict[str, Any]]:
        """Return text units that mention an entity (by entity ID)."""
        async with self._driver.session() as session:
            result = await session.run(
                """
                MATCH (t:TextUnit)-[:MENTIONS]->(e:Entity {id: $id})
                RETURN t.id AS id, t.text AS text, t.document_id AS document_id
                LIMIT 20
                """,
                id=entity_id,
            )
            return [dict(r) async for r in result]

    async def get_entity_neighbors(
        self,
        entity_id: str,
        max_depth: int = 2,
    ) -> list[dict[str, Any]]:
        """Traverse the graph from an entity and return neighboring entities."""
        async with self._driver.session() as session:
            result = await session.run(
                f"""
                MATCH (e:Entity {{id: $id}})-[r:RELATED_TO*1..{max_depth}]-(neighbor:Entity)
                RETURN DISTINCT neighbor.id AS id,
                               neighbor.name AS name,
                               neighbor.type AS type,
                               neighbor.description AS description
                LIMIT 50
                """,
                id=entity_id,
            )
            return [dict(r) async for r in result]

    async def get_graph_stats(self) -> dict[str, int]:
        """Return node counts for health/status reporting."""
        async with self._driver.session() as session:
            result = await session.run(
                """
                MATCH (n)
                RETURN labels(n)[0] AS label, COUNT(n) AS count
                ORDER BY count DESC
                """
            )
            return {r["label"]: r["count"] async for r in result}

    # ── GraphRAG adapter ───────────────────────────────────────────────────────

    def as_entity_vector_store(self) -> "_Neo4jEntityVectorStoreAdapter":
        """
        Returns a thin adapter implementing the VectorStore interface
        expected by GraphRAG's LocalSearchMixedContext.
        """
        return _Neo4jEntityVectorStoreAdapter(self)


class _Neo4jEntityVectorStoreAdapter:
    """
    Minimal adapter implementing the subset of GraphRAG's VectorStore API
    needed by LocalSearchMixedContext.entity_text_embeddings.

    GraphRAG expects:
        store.search(query_embedding, k) -> list of (id, score) tuples
    """

    def __init__(self, neo4j: Neo4jStore) -> None:
        self._neo4j = neo4j

    def search(
        self,
        query_embedding: list[float],
        k: int = 10,
    ) -> list[tuple[str, float]]:
        """
        Synchronous wrapper — GraphRAG's LocalSearch calls this synchronously
        in some code paths.

        If this causes event loop conflicts in newer GraphRAG versions,
        consider using nest_asyncio or restructuring to async.
        """
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # If already inside an async context, create a concurrent future
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(
                        asyncio.run,
                        self._neo4j.entity_vector_search(query_embedding, top_k=k),
                    )
                    results = future.result()
            else:
                results = loop.run_until_complete(
                    self._neo4j.entity_vector_search(query_embedding, top_k=k)
                )
        except Exception:
            return []
        return [(r["id"], r["score"]) for r in results]
