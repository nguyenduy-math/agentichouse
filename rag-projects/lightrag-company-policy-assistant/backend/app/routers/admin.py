"""Admin endpoints — stats, agent listing, reindex trigger."""

from __future__ import annotations

import asyncio
import logging
import shutil
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Request

from app.config import settings
from app.domains import DOMAIN_BY_KEY
from app.ingestion import collect_documents
from app.schemas import AdminAgentsResponse, AdminStatsResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/stats", response_model=AdminStatsResponse)
async def stats(request: Request) -> AdminStatsResponse:
    orchestrator = request.app.state.orchestrator
    agent_health = orchestrator.agent_health_map()
    total = sum(h.indexed_docs for h in agent_health.values())
    return AdminStatsResponse(agents=agent_health, total_indexed_docs=total)


@router.get("/agents", response_model=AdminAgentsResponse)
async def list_agents(request: Request) -> AdminAgentsResponse:
    orchestrator = request.app.state.orchestrator
    result = []
    for domain, agent in orchestrator.agent_items():
        result.append({
            "domain": domain,
            "engine_type": agent.engine_type,
            "ready": agent.is_ready(),
            "indexed_docs": agent.indexed_count(),
        })
    return AdminAgentsResponse(agents=result)


async def _reindex_all(orchestrator) -> None:
    """Background task: walk data/documents/ and re-index every file."""
    agent_map = dict(orchestrator.agent_items())
    base = Path(settings.document_folder)
    for domain, agent in agent_map.items():
        info = DOMAIN_BY_KEY.get(domain)
        if info is None:
            continue
        sub = base / info.doc_type
        if not sub.exists():
            continue
        try:
            texts, sources, _ = collect_documents(sub)
            for source in sources:
                try:
                    await agent.index_document(Path(source))
                except Exception as exc:
                    logger.warning("Reindex failed for %s: %s", source, exc)
        except Exception as exc:
            logger.warning("Reindex failed for %s: %s", domain, exc)
    logger.info("Reindex complete.")


async def _reset_all(orchestrator) -> dict:
    """Wipe Neo4j graph + local LightRAG storage, then return a summary."""
    from neo4j import AsyncGraphDatabase

    # 1. Shut down all LightRAG instances so file handles are released.
    for _domain, agent in orchestrator.agent_items():
        try:
            await agent.shutdown()
        except Exception as exc:
            logger.warning("Shutdown error during reset: %s", exc)

    # 2. Clear Neo4j — delete all nodes and relationships.
    neo4j_cleared = False
    driver = None
    try:
        driver = AsyncGraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_username, settings.neo4j_password),
        )
        async with driver.session(database=settings.neo4j_database) as session:
            await session.run("MATCH (n) DETACH DELETE n")
        neo4j_cleared = True
        logger.info("Neo4j graph cleared.")
    except Exception as exc:
        logger.error("Failed to clear Neo4j: %s", exc)
    finally:
        if driver:
            await driver.close()

    # 3. Delete local LightRAG storage dirs (KV + vector stores).
    storage_dir = Path(settings.lightrag_base_dir)
    if storage_dir.exists():
        shutil.rmtree(storage_dir)
        logger.info("Deleted LightRAG storage: %s", storage_dir)

    # 4. Re-initialize all agents with fresh (empty) storage.
    for _domain, agent in orchestrator.agent_items():
        try:
            await agent.initialize()
            agent.reset_doc_count()
        except Exception as exc:
            logger.error("Re-init error after reset: %s", exc)

    return {"neo4j_cleared": neo4j_cleared, "storage_deleted": str(storage_dir)}


@router.post("/reset")
async def reset(request: Request) -> dict:
    """Wipe all Neo4j nodes and local LightRAG storage, then re-initialize.

    Call POST /admin/reindex afterwards to re-insert documents in Vietnamese.
    """
    orchestrator = request.app.state.orchestrator
    result = await _reset_all(orchestrator)
    return {
        "message": "Reset complete. Call POST /admin/reindex to re-insert documents.",
        **result,
    }


@router.post("/reindex")
async def reindex(request: Request, background_tasks: BackgroundTasks) -> dict:
    orchestrator = request.app.state.orchestrator
    background_tasks.add_task(_reindex_all, orchestrator)
    return {"message": "Reindex started in background. Check /admin/stats for progress."}
