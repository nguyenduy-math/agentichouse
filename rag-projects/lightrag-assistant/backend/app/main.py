"""FastAPI application entry point.

Run from the ``backend/`` directory:

    uvicorn app.main:app --host 127.0.0.1 --port 8000
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.rag_engine import init_rag, shutdown_rag
from app.routers import chat, health, ingest, query

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # LightRAG's async init must run inside the event loop — this is the place.
    logger.info("Startup: initializing LightRAG engine...")
    await init_rag()
    logger.info("Startup complete.")
    yield
    logger.info("Shutdown: finalizing LightRAG engine...")
    await shutdown_rag()


app = FastAPI(
    title="Vietnam Insurance Assistant",
    description=(
        "LightRAG + Neo4j + Gemini — retrieval-augmented Q&A and chat over "
        "Vietnamese insurance documents."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register each router twice: at the root (handy for curl / PowerShell testing)
# and under /api (what the frontend's Vite dev proxy forwards to).
for api_router in (health.router, ingest.router, query.router, chat.router):
    app.include_router(api_router)
    app.include_router(api_router, prefix="/api")

# In production, serve the built React SPA from this same process.
# (During dev the SPA runs on the Vite server; frontend/dist won't exist yet.)
_frontend_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if _frontend_dist.is_dir():
    app.mount("/", StaticFiles(directory=str(_frontend_dist), html=True), name="frontend")
    logger.info("Serving built frontend from %s", _frontend_dist)
