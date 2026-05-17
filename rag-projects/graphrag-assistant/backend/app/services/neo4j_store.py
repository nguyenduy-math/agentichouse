from __future__ import annotations

import structlog
from neo4j import AsyncGraphDatabase, AsyncDriver

from app.config import settings
from app.models.documents import NodeData, ChunkWithMeta

logger = structlog.get_logger()

_CHUNK_INDEX = "policy_chunks"
_COMMUNITY_INDEX = "community_summaries"


class Neo4jStore:
    def __init__(self) -> None:
        self._driver: AsyncDriver | None = None

    async def initialize(self) -> None:
        self._driver = AsyncGraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
        )
        await self._driver.verify_connectivity()
        await self._create_schema()
        logger.info("neo4j_store_initialized", uri=settings.neo4j_uri)

    async def close(self) -> None:
        if self._driver:
            await self._driver.close()

    # ── Schema ──────────────────────────────────────────────────────────────

    async def _create_schema(self) -> None:
        async with self._driver.session() as s:
            await s.run(
                "CREATE CONSTRAINT entity_name IF NOT EXISTS "
                "FOR (e:Entity) REQUIRE e.name IS UNIQUE"
            )
            await s.run(
                "CREATE CONSTRAINT chunk_id IF NOT EXISTS "
                "FOR (c:PolicyChunk) REQUIRE c.id IS UNIQUE"
            )
            await s.run(
                "CREATE CONSTRAINT community_id IF NOT EXISTS "
                "FOR (c:Community) REQUIRE c.community_id IS UNIQUE"
            )
            dim = settings.embedding_dim
            await s.run(
                f"CREATE VECTOR INDEX {_CHUNK_INDEX} IF NOT EXISTS "
                f"FOR (c:PolicyChunk) ON (c.embedding) "
                f"OPTIONS {{indexConfig: {{"
                f"`vector.dimensions`: {dim}, "
                f"`vector.similarity_function`: 'cosine'"
                f"}}}}"
            )
            await s.run(
                f"CREATE VECTOR INDEX {_COMMUNITY_INDEX} IF NOT EXISTS "
                f"FOR (c:Community) ON (c.embedding) "
                f"OPTIONS {{indexConfig: {{"
                f"`vector.dimensions`: {dim}, "
                f"`vector.similarity_function`: 'cosine'"
                f"}}}}"
            )

    # ── Upsert operations ────────────────────────────────────────────────────

    async def upsert_chunk(
        self,
        chunk: ChunkWithMeta,
        embedding: list[float],
        entity_names: list[str],
    ) -> None:
        async with self._driver.session() as s:
            await s.run(
                """
                MERGE (c:PolicyChunk {id: $id})
                SET c.text = $text,
                    c.source_file = $source_file,
                    c.doc_type = $doc_type,
                    c.page_number = $page_number,
                    c.chunk_index = $chunk_index,
                    c.embedding = $embedding,
                    c.entity_names = $entity_names
                """,
                id=chunk.id,
                text=chunk.text,
                source_file=chunk.source_file,
                doc_type=chunk.doc_type,
                page_number=chunk.page_number,
                chunk_index=chunk.chunk_index,
                embedding=embedding,
                entity_names=entity_names,
            )

    async def upsert_entity(self, entity: NodeData) -> None:
        async with self._driver.session() as s:
            await s.run(
                """
                MERGE (e:Entity {name: $name})
                SET e.type = $type,
                    e.description = $description,
                    e.community_id = $community_id
                """,
                name=entity.name,
                type=entity.type,
                description=entity.description,
                community_id=entity.community_id,
            )

    async def upsert_relationship(
        self, source_name: str, rel_type: str, target_name: str
    ) -> None:
        safe_rel = rel_type.upper().replace(" ", "_")
        query = (
            "MATCH (s:Entity {name: $src}), (t:Entity {name: $tgt}) "
            f"MERGE (s)-[:{safe_rel}]->(t)"
        )
        async with self._driver.session() as s:
            await s.run(query, src=source_name, tgt=target_name)

    async def link_chunk_to_entity(self, chunk_id: str, entity_name: str) -> None:
        async with self._driver.session() as s:
            await s.run(
                """
                MATCH (c:PolicyChunk {id: $cid}), (e:Entity {name: $name})
                MERGE (c)-[:MENTIONS]->(e)
                """,
                cid=chunk_id,
                name=entity_name,
            )

    async def upsert_community(
        self,
        community_id: int,
        summary: str,
        embedding: list[float],
        node_names: list[str],
    ) -> None:
        async with self._driver.session() as s:
            await s.run(
                """
                MERGE (c:Community {community_id: $cid})
                SET c.summary = $summary,
                    c.embedding = $embedding,
                    c.node_count = $count
                """,
                cid=community_id,
                summary=summary,
                embedding=embedding,
                count=len(node_names),
            )
            for name in node_names:
                await s.run(
                    """
                    MATCH (e:Entity {name: $name}), (c:Community {community_id: $cid})
                    MERGE (e)-[:THUOC_CONG_DONG]->(c)
                    """,
                    name=name,
                    cid=community_id,
                )

    async def set_entity_community(self, entity_name: str, community_id: int) -> None:
        async with self._driver.session() as s:
            await s.run(
                "MATCH (e:Entity {name: $name}) SET e.community_id = $cid",
                name=entity_name,
                cid=community_id,
            )

    # ── Vector search ────────────────────────────────────────────────────────

    async def vector_search_chunks(
        self, embedding: list[float], k: int
    ) -> list[dict]:
        async with self._driver.session() as s:
            result = await s.run(
                f"""
                CALL db.index.vector.queryNodes('{_CHUNK_INDEX}', $k, $emb)
                YIELD node, score
                RETURN node.id AS id,
                       node.text AS text,
                       node.source_file AS source_file,
                       node.doc_type AS doc_type,
                       node.page_number AS page_number,
                       node.chunk_index AS chunk_index,
                       node.entity_names AS entity_names,
                       score
                """,
                k=k,
                emb=embedding,
            )
            return [dict(r) for r in await result.data()]

    async def vector_search_communities(
        self, embedding: list[float], k: int
    ) -> list[dict]:
        async with self._driver.session() as s:
            result = await s.run(
                f"""
                CALL db.index.vector.queryNodes('{_COMMUNITY_INDEX}', $k, $emb)
                YIELD node, score
                RETURN node.community_id AS community_id,
                       node.summary AS summary,
                       node.node_count AS node_count,
                       score
                """,
                k=k,
                emb=embedding,
            )
            return [dict(r) for r in await result.data()]

    # ── Graph traversal ──────────────────────────────────────────────────────

    async def get_entity_neighborhood(
        self, entity_names: list[str], depth: int = 2
    ) -> dict:
        if not entity_names:
            return {"entities": [], "triples": []}
        async with self._driver.session() as s:
            # Step 1: collect all entities reachable within `depth` hops.
            # Neo4j does not support parameters in variable-length path bounds,
            # so depth is interpolated directly into the query string.
            entities_result = await s.run(
                f"""
                UNWIND $names AS name
                MATCH (e:Entity {{name: name}})
                WITH COLLECT(DISTINCT e) AS seeds
                UNWIND seeds AS seed
                OPTIONAL MATCH (seed)-[*1..{depth}]-(neighbor:Entity)
                WITH seeds, COLLECT(DISTINCT neighbor) AS neighbors
                WITH seeds + neighbors AS all_nodes
                UNWIND all_nodes AS node
                RETURN DISTINCT node.name AS name,
                               node.type AS type,
                               node.description AS description
                """,
                names=entity_names,
            )
            entities = [dict(r) for r in await entities_result.data()]

            if not entities:
                return {"entities": [], "triples": []}

            all_names = [e["name"] for e in entities if e.get("name")]

            # Step 2: get all relationships among the discovered entities.
            triples_result = await s.run(
                """
                MATCH (a:Entity)-[r]->(b:Entity)
                WHERE a.name IN $names AND b.name IN $names
                RETURN DISTINCT a.name AS source,
                               type(r) AS relation,
                               b.name AS target
                """,
                names=all_names,
            )
            triples = [dict(r) for r in await triples_result.data()]

        return {"entities": entities, "triples": triples}

    # ── Community detection helpers ──────────────────────────────────────────

    async def get_all_entities_and_edges(self) -> tuple[list[dict], list[tuple]]:
        async with self._driver.session() as s:
            nodes_result = await s.run(
                "MATCH (e:Entity) RETURN e.name AS name, e.type AS type, e.description AS description"
            )
            nodes = [dict(r) for r in await nodes_result.data()]

            edges_result = await s.run(
                "MATCH (a:Entity)-[r]->(b:Entity) RETURN a.name AS src, type(r) AS rel, b.name AS tgt"
            )
            edges_raw = await edges_result.data()
            edges = [(r["src"], r["tgt"], {"relation": r["rel"]}) for r in edges_raw]

        return nodes, edges

    # ── Stats & maintenance ──────────────────────────────────────────────────

    async def get_stats(self) -> dict:
        async with self._driver.session() as s:
            r = await s.run(
                """
                CALL { MATCH (c:PolicyChunk) RETURN COUNT(c) AS chunks }
                CALL { MATCH (e:Entity) RETURN COUNT(e) AS entities }
                CALL { MATCH (a:Entity)-[r]->(b:Entity) RETURN COUNT(r) AS edges }
                CALL { MATCH (c:Community) RETURN COUNT(c) AS communities }
                RETURN chunks, entities, edges, communities
                """
            )
            data = await r.data()
            return data[0] if data else {}

    async def clear(self) -> None:
        async with self._driver.session() as s:
            await s.run("MATCH (n) DETACH DELETE n")
        logger.info("neo4j_store_cleared")
