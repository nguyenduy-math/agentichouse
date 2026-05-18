"""FastAPI application entry point.

Run from the backend/ directory:

    uvicorn app.main:app --host 127.0.0.1 --port 8000
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.agents.benefits_agent import BenefitsAgent
from app.agents.compliance_agent import ComplianceAgent
from app.agents.conduct_agent import ConductAgent
from app.agents.finance_agent import FinanceAgent
from app.agents.handbook_agent import HandbookAgent
from app.agents.hr_policy_agent import HRPolicyAgent
from app.agents.it_security_agent import ITSecurityAgent
from app.agents.medical_agent import MedicalAgent
from app.agents.orchestrator import OrchestratorAgent
from app.agents.procedures_agent import ProceduresAgent
from app.agents.training_agent import TrainingAgent
from app.config import settings
from app.routers import admin, chat, health, ingest

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    logger.info("Startup: initializing domain specialist agents…")

    agents = {
        # Chính sách nội bộ công ty
        "HR_POLICY":   HRPolicyAgent(),
        "BENEFITS":    BenefitsAgent(),
        "CONDUCT":     ConductAgent(),
        "PROCEDURES":  ProceduresAgent(),
        "HANDBOOK":    HandbookAgent(),
        # Lĩnh vực mở rộng
        "MEDICAL":     MedicalAgent(),
        "IT_SECURITY": ITSecurityAgent(),
        "COMPLIANCE":  ComplianceAgent(),
        "FINANCE":     FinanceAgent(),
        "TRAINING":    TrainingAgent(),
    }

    # LightRAG agents need async initialization (Neo4j + storage setup)
    await asyncio.gather(*[
        agent.initialize()
        for agent in agents.values()
        if agent.engine_type == "lightrag"
    ])
    # PageIndex agents initialize synchronously in __init__ — no async needed
    for agent in agents.values():
        if agent.engine_type == "pageindex":
            await agent.initialize()

    orchestrator = OrchestratorAgent(agents=agents)
    _app.state.orchestrator = orchestrator

    logger.info(
        "Startup complete. Agents: %s",
        {d: a.engine_type for d, a in agents.items()},
    )

    yield

    logger.info("Shutdown: finalizing agents…")
    await asyncio.gather(*[
        agent.shutdown()
        for agent in agents.values()
        if agent.engine_type == "lightrag"
    ])


app = FastAPI(
    title="Trợ lý Chính sách Doanh nghiệp",
    description=(
        "Hệ thống đa tác nhân RAG: 10 chuyên gia tư vấn theo lĩnh vực (LightRAG + PageIndex) "
        "được điều phối bởi OrchestratorAgent."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.get_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers at root + /api prefix (Vite proxy uses /api in dev)
for api_router in (health.router, ingest.router, chat.router, admin.router):
    app.include_router(api_router)
    app.include_router(api_router, prefix="/api")

# Serve built React SPA in production
_frontend_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if _frontend_dist.is_dir():
    app.mount("/", StaticFiles(directory=str(_frontend_dist), html=True), name="frontend")
    logger.info("Serving built frontend from %s", _frontend_dist)
