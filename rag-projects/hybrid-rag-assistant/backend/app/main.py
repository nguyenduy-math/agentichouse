from contextlib import asynccontextmanager
from pathlib import Path

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.dependencies import _agent_registry, _embedding, _llm, _orchestrator, _rag, _reranker, _session
from app.routers import admin, chat, session

log = structlog.get_logger()

DIST_DIR = Path(__file__).parent.parent.parent / "frontend" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("startup.begin")
    # Eagerly initialize singletons — reranker downloads model, agents load BM25 indexes
    _embedding()
    _reranker()
    _llm()
    _session()
    _agent_registry()
    _orchestrator()
    _rag()
    log.info("startup.done")
    yield
    log.info("shutdown")


def create_app() -> FastAPI:
    app = FastAPI(title="Hybrid RAG Assistant", version="1.0.0", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register routes under /api and also bare (for SPA)
    for prefix in ("/api", ""):
        app.include_router(session.router, prefix=prefix)
        app.include_router(chat.router, prefix=prefix)
        app.include_router(admin.router, prefix=prefix)

    # Serve compiled frontend if dist/ exists
    if DIST_DIR.exists():
        app.mount("/", StaticFiles(directory=str(DIST_DIR), html=True), name="static")

    return app


app = create_app()
