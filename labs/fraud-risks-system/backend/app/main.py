from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.database import init_db
from app.batch_pipeline import start_scheduler, stop_scheduler
from app.routers import claims, review, batch, health

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    logger.info("Startup: initializing database...")
    await init_db()
    logger.info("Startup: starting batch scheduler...")
    start_scheduler()
    logger.info("Startup complete.")
    yield
    logger.info("Shutdown: stopping batch scheduler...")
    stop_scheduler()


app = FastAPI(
    title="Healthcare Claim Fraud Detection",
    description="LLM-powered fraud detection with human-in-the-loop review.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for router in (health.router, claims.router, review.router, batch.router):
    app.include_router(router)
    app.include_router(router, prefix="/api")

_frontend_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if _frontend_dist.is_dir():
    app.mount("/", StaticFiles(directory=str(_frontend_dist), html=True), name="frontend")
    logger.info("Serving built frontend from %s", _frontend_dist)
