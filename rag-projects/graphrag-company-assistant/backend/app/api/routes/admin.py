from __future__ import annotations

import asyncio
import os
import shutil
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Request
from pydantic import BaseModel

from app.dependencies import get_indexing_service, get_neo4j_store, get_token_log_service
from app.services.indexing_service import IndexingService
from app.services.neo4j_store import Neo4jStore
from app.services.token_log_service import TokenLogService

router = APIRouter()

VALID_DOC_TYPES = {"handbooks", "hr_policies", "conduct", "benefits", "procedures"}


class IndexStartResponse(BaseModel):
    status: str


class IndexStatusResponse(BaseModel):
    status: str
    progress: int = 0
    total: int = 0
    stage: str = ""
    last_error: str | None = None
    stats: dict[str, Any] = {}


class IngestResponse(BaseModel):
    status: str
    path: str
    doc_type: str


@router.post("/index", response_model=IndexStartResponse, summary="Kích hoạt pipeline lập chỉ mục đầy đủ")
async def trigger_index(
    request: Request,
    indexing_service: IndexingService = Depends(get_indexing_service),
) -> IndexStartResponse:
    status = request.app.state.indexing_status
    if status.get("status") == "running":
        raise HTTPException(status_code=409, detail="Indexing already in progress")

    async def run() -> None:
        status["status"] = "running"
        status["progress"] = 0
        status["last_error"] = None

        def cb(stage: str, done: int, total: int) -> None:
            status["progress"] = done
            status["total"] = total
            status["stage"] = stage

        try:
            result = await indexing_service.run_full_pipeline(
                raw_dir="./data/raw",
                progress_callback=cb,
            )
            status["status"] = "completed"
            status["stats"] = result.model_dump()
        except Exception as e:
            status["status"] = "failed"
            status["last_error"] = str(e)

    asyncio.create_task(run())
    return IndexStartResponse(status="started")


@router.get("/index/status", response_model=IndexStatusResponse, summary="Trạng thái pipeline lập chỉ mục")
async def index_status(request: Request) -> IndexStatusResponse:
    return IndexStatusResponse(**request.app.state.indexing_status)


@router.post("/ingest", response_model=IngestResponse, summary="Upload tài liệu chính sách")
async def ingest_document(
    file: UploadFile = File(...),
    doc_type: str = Form(
        ...,
        description="Loại tài liệu: handbooks | hr_policies | conduct | benefits | procedures",
    ),
) -> IngestResponse:
    if doc_type not in VALID_DOC_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"doc_type phải là một trong: {sorted(VALID_DOC_TYPES)}",
        )

    dest_dir = os.path.join("./data/raw", doc_type)
    os.makedirs(dest_dir, exist_ok=True)
    dest_path = os.path.join(dest_dir, file.filename or "document")

    with open(dest_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    return IngestResponse(status="uploaded", path=dest_path, doc_type=doc_type)


@router.get("/stats", summary="Thống kê Neo4j (nodes, edges, chunks, communities)")
async def get_stats(
    neo4j_store: Neo4jStore = Depends(get_neo4j_store),
) -> dict[str, Any]:
    return await neo4j_store.get_stats()


@router.get("/token-usage", summary="Lịch sử token gần đây")
async def token_usage(
    limit: int = 100,
    token_log: TokenLogService = Depends(get_token_log_service),
) -> list[dict[str, Any]]:
    return await token_log.get_recent(limit=limit)


@router.get("/token-usage/summary", summary="Thống kê token theo loại gọi")
async def token_usage_summary(
    token_log: TokenLogService = Depends(get_token_log_service),
) -> dict[str, Any]:
    return await token_log.get_summary()
