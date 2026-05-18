"""GET /health — per-agent readiness probe."""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.schemas import HealthResponse
from app.config import settings

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health(request: Request) -> HealthResponse:
    orchestrator = request.app.state.orchestrator
    agent_health = orchestrator.agent_health_map()
    neo4j_ok = await orchestrator.check_neo4j()
    all_ready = all(h.ready for h in agent_health.values())
    return HealthResponse(
        status="ok" if (all_ready and neo4j_ok) else "degraded",
        agents=agent_health,
        neo4j_connected=neo4j_ok,
        llm_model=settings.gemini_llm_model,
        embedding_model=settings.gemini_embedding_model,
    )
