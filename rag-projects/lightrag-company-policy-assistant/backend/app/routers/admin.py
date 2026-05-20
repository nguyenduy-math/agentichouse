"""Admin endpoints — stats, agent listing, reindex trigger."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Request

from app.config import settings
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
    for domain, agent in orchestrator._agents.items():
        result.append({
            "domain": domain,
            "engine_type": agent.engine_type,
            "ready": agent.is_ready(),
            "indexed_docs": agent.indexed_count(),
        })
    return AdminAgentsResponse(agents=result)


async def _reindex_all(orchestrator) -> None:
    """Background task: walk data/documents/ and re-index every file."""
    from app.domains import DOC_TYPE_TO_DOMAIN

    base = Path(settings.document_folder)
    for doc_type, domain in DOC_TYPE_TO_DOMAIN.items():
        sub = base / doc_type
        if not sub.exists():
            continue
        agent = orchestrator._agents.get(domain)
        if agent is None:
            continue
        try:
            texts, sources, _ = collect_documents(sub)
            for source in sources:
                try:
                    await agent.index_document(Path(source))
                except Exception as exc:
                    logger.warning("Reindex failed for %s: %s", source, exc)
        except Exception as exc:
            logger.warning("Reindex failed for %s: %s", doc_type, exc)
    logger.info("Reindex complete.")


@router.post("/reindex")
async def reindex(request: Request, background_tasks: BackgroundTasks) -> dict:
    orchestrator = request.app.state.orchestrator
    background_tasks.add_task(_reindex_all, orchestrator)
    return {"message": "Reindex started in background. Check /admin/stats for progress."}
