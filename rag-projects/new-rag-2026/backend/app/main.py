"""
FastAPI application entry point.

Lifespan:
  - Connects Neo4j
  - Loads GraphRAG search engines if artifacts exist
  - Starts session TTL cleanup loop
  - Initializes OrchestratorAgent with all dependencies

Shutdown:
  - Closes Neo4j connection
  - Stops cleanup loop
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import admin, chat, eval, health, session, tokens

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def _build_orchestrator(app: FastAPI) -> None:
    from app.agents.benefits_agent import BenefitsAgent
    from app.agents.compliance_agent import ComplianceAgent
    from app.agents.finance_agent import FinanceAgent
    from app.agents.general_agent import GeneralAgent
    from app.agents.hr_agent import HRAgent
    from app.agents.it_agent import ITAgent
    from app.agents.orchestrator import OrchestratorAgent
    from app.agents.procedures_agent import ProceduresAgent
    from app.services.llm_service import create_chat_model
    from app.services.rerank_service import RerankService
    from app.services.verification_service import VerificationService

    llm = create_chat_model(settings.LLM_PROVIDER)

    agents = {
        "hr": HRAgent(llm),
        "benefits": BenefitsAgent(llm),
        "it": ITAgent(llm),
        "finance": FinanceAgent(llm),
        "compliance": ComplianceAgent(llm),
        "procedures": ProceduresAgent(llm),
        "general": GeneralAgent(llm),
    }

    rerank_svc = RerankService()
    verify_svc = VerificationService(llm)

    app.state.orchestrator = OrchestratorAgent(
        llm=llm,
        graphrag_registry=app.state.graphrag_registry,
        neo4j_store=app.state.neo4j_store,
        agents=agents,
        rerank_service=rerank_svc,
        verification_service=verify_svc,
        graph_hop_depth=settings.GRAPH_HOP_DEPTH,
        enable_rerank=settings.ENABLE_RERANK,
        rerank_pool_size=settings.RERANK_CANDIDATE_POOL,
        max_chunks=settings.MAX_LOCAL_CHUNKS,
    )
    logger.info("OrchestratorAgent initialized with provider: %s", settings.LLM_PROVIDER)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting new-rag-2026 backend...")

    from app.services.neo4j_store import Neo4jStore
    neo4j_store = Neo4jStore()
    app.state.neo4j_store = neo4j_store
    try:
        await neo4j_store.connect()
        logger.info("Neo4j connected: %s", settings.NEO4J_URI)
    except Exception as exc:
        logger.warning("Neo4j connection failed (continuing without graph): %s", exc)

    from app.domains import DOMAINS
    from app.services.graphrag_service import GraphRAGService

    graphrag_root = Path(settings.GRAPHRAG_ROOT)

    # Build per-domain registry.  Each domain gets its own GraphRAGService pointing
    # at graphrag_workspace/{domain_key}/.  A "legacy" service keeps backward
    # compatibility with existing documents indexed before per-domain support.
    graphrag_registry: dict[str, GraphRAGService] = {}

    # Legacy whole-corpus service (documents uploaded before per-domain support)
    legacy_svc = GraphRAGService(workspace_root=str(graphrag_root), neo4j_store=neo4j_store)
    if (graphrag_root / "output" / "entities.parquet").exists():
        logger.info("Loading legacy (whole-corpus) GraphRAG artifacts...")
        await legacy_svc.reload()
    graphrag_registry["legacy"] = legacy_svc

    # Per-domain services — load artifacts if already indexed
    for domain in DOMAINS:
        workspace = graphrag_root / domain.key
        svc = GraphRAGService(workspace_root=str(workspace), neo4j_store=neo4j_store)
        if (workspace / "output" / "entities.parquet").exists():
            logger.info("Loading GraphRAG artifacts for domain '%s'...", domain.key)
            await svc.reload()
        graphrag_registry[domain.key] = svc

    app.state.graphrag_registry = graphrag_registry

    from app.services.indexing_service import IndexingService
    indexing_svc = IndexingService(
        graphrag_root=settings.GRAPHRAG_ROOT,
        neo4j_uri=settings.NEO4J_URI,
        neo4j_user=settings.NEO4J_USER,
        neo4j_password=settings.NEO4J_PASSWORD,
    )
    indexing_svc.set_graphrag_registry(graphrag_registry)
    app.state.indexing_service = indexing_svc
    app.state.documents_dir = "./data/documents"

    from app.services.session_service import SessionService
    session_svc = SessionService(ttl_minutes=settings.SESSION_TTL_MINUTES)
    session_svc.start_cleanup_loop()
    app.state.session_service = session_svc

    # Per-turn progress trackers: session_id → ProgressTracker
    # Created by POST /chat and consumed by GET /chat/{id}/progress (SSE).
    app.state.progress_store: dict = {}

    from app.services.history_store import HistoryStore
    history_store = HistoryStore()
    await history_store.initialize()
    app.state.history_store = history_store

    retention_days = int(os.environ.get("HISTORY_RETENTION_DAYS", "90"))
    deleted = await history_store.delete_old_turns(retention_days)
    if deleted:
        logger.info("Purged %d old turns (retention=%d days)", deleted, retention_days)

    from app.services.eval_service import EvalService
    app.state.eval_service = EvalService(history_store)

    _build_orchestrator(app)
    logger.info("Startup complete.")
    yield

    logger.info("Shutting down...")
    session_svc.stop_cleanup_loop()
    await neo4j_store.close()
    logger.info("Shutdown complete.")


def create_app() -> FastAPI:
    app = FastAPI(
        title="new-rag-2026 Multi-Agent GraphRAG Assistant",
        description="Vietnamese multi-agent assistant powered by Microsoft GraphRAG and Neo4j",
        version="2.0.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router)
    app.include_router(session.router)
    app.include_router(admin.router)
    app.include_router(chat.router)
    app.include_router(eval.router)
    app.include_router(tokens.router, tags=["tokens"])

    return app


app = create_app()
