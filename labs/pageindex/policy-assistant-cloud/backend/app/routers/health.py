"""Health check — báo trạng thái dịch vụ và sự hiện diện của API key."""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.config import settings
from app.schemas import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health(request: Request) -> HealthResponse:
    cloud = request.app.state.cloud
    return HealthResponse(
        status="ok",
        indexed_count=cloud.indexed_count(),
        pageindex_key_present=bool(settings.pageindex_api_key),
        gemini_key_present=bool(settings.gemini_api_key),
    )
