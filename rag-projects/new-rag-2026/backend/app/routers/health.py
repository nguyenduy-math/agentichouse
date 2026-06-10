"""Health check router."""
from __future__ import annotations

from fastapi import APIRouter, Request

from app.config import settings
from app.schemas import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health(request: Request) -> HealthResponse:
    """Liveness check — also reports Neo4j connectivity and GraphRAG readiness."""
    neo4j_ok = False
    graphrag_ok = False

    neo4j_store = getattr(request.app.state, "neo4j_store", None)
    graphrag_svc = getattr(request.app.state, "graphrag_service", None)

    if neo4j_store is not None:
        neo4j_ok = neo4j_store.is_connected

    if graphrag_svc is not None:
        graphrag_ok = graphrag_svc.is_ready

    return HealthResponse(
        status="ok",
        neo4j_connected=neo4j_ok,
        graphrag_ready=graphrag_ok,
        llm_provider=settings.LLM_PROVIDER,
        version="2.0.0",
    )
