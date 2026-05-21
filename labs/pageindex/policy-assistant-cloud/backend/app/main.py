"""FastAPI app — trợ lý chính sách dùng PageIndex Cloud + Gemini (tiếng Việt).

PageIndex Cloud dựng cây tri thức cho từng tài liệu rồi tải về dưới dạng JSON;
Gemini điều hướng cây JSON đó và sinh câu trả lời tiếng Việt có dẫn chứng.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import chat, health, ingest
from app.services.pageindex_cloud import PageIndexCloudService
from app.services.search_service import SearchService

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    cloud = PageIndexCloudService(
        api_key=settings.pageindex_api_key,
        tree_dir=Path(settings.tree_storage_dir),
        poll_interval=settings.poll_interval_seconds,
        poll_timeout=settings.poll_timeout_seconds,
    )
    app.state.cloud = cloud
    app.state.search = SearchService(tree_source=cloud)
    logging.getLogger(__name__).info(
        "Khởi động: %d tài liệu đã nạp trong %s",
        cloud.indexed_count(), settings.tree_storage_dir,
    )
    yield


app = FastAPI(title="Trợ lý chính sách — PageIndex Cloud", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.get_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(ingest.router)
app.include_router(chat.router)
