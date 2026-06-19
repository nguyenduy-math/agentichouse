from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from app.dependencies import get_neo4j_store
from app.services.neo4j_store import Neo4jStore

router = APIRouter()


@router.get("/nodes", summary="Lấy danh sách tất cả thực thể trong đồ thị")
async def get_nodes(
    neo4j_store: Neo4jStore = Depends(get_neo4j_store),
) -> dict[str, Any]:
    nodes, edges = await neo4j_store.get_all_entities_and_edges()
    return {
        "nodes": nodes,
        "edges": [
            {"source": src, "relation": data.get("relation", ""), "target": tgt}
            for src, tgt, data in edges
        ],
    }


@router.get("/community/{community_id}", summary="Lấy tóm tắt và thực thể của một community")
async def get_community(
    community_id: int,
    neo4j_store: Neo4jStore = Depends(get_neo4j_store),
) -> dict[str, Any]:
    async with neo4j_store._driver.session() as s:
        result = await s.run(
            """
            MATCH (c:Community {community_id: $cid})
            OPTIONAL MATCH (e:Entity)-[:THUOC_CONG_DONG]->(c)
            RETURN c.summary AS summary, c.node_count AS node_count,
                   COLLECT(DISTINCT {name: e.name, type: e.type}) AS entities
            """,
            cid=community_id,
        )
        data = await result.data()
    if not data:
        return {"community_id": community_id, "summary": "", "entities": []}
    row = data[0]
    return {
        "community_id": community_id,
        "summary": row["summary"],
        "node_count": row["node_count"],
        "entities": row["entities"],
    }
