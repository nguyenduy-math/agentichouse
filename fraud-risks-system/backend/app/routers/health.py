from __future__ import annotations

from fastapi import APIRouter

from app.config import settings
from app.database import engine
from app.fraud_analyzer import check_llm_connectivity
from app.schemas import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health():
    db_ok = False
    try:
        async with engine.connect() as conn:
            await conn.execute(__import__("sqlalchemy").text("SELECT 1"))
        db_ok = True
    except Exception:
        pass

    return HealthResponse(
        status="ok" if db_ok else "degraded",
        db_connected=db_ok,
        llm_model=settings.llm_model,
    )
