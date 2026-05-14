"""GET /health — readiness probe for the RAG engine and Neo4j."""

from __future__ import annotations

from fastapi import APIRouter

from app.config import settings
from app.rag_engine import check_neo4j, is_initialized
from app.schemas import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    rag_ok = is_initialized()
    neo4j_ok = await check_neo4j()
    return HealthResponse(
        status="ok" if (rag_ok and neo4j_ok) else "degraded",
        rag_initialized=rag_ok,
        neo4j_connected=neo4j_ok,
        llm_model=settings.gemini_llm_model,
        embedding_model=settings.gemini_embedding_model,
        working_dir=settings.working_dir,
    )
