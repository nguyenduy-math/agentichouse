"""Admin router: document ingestion and indexing control."""
from __future__ import annotations

import logging
from pathlib import Path

import aiofiles
from fastapi import APIRouter, File, HTTPException, Request, UploadFile

from app.schemas import IndexRequest, IndexResponse, IndexStatusResponse, IngestResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/admin")

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".doc", ".txt"}


@router.post("/ingest", response_model=IngestResponse)
async def ingest_document(
    request: Request,
    file: UploadFile = File(...),
) -> IngestResponse:
    """
    Upload a document and prepare it for GraphRAG indexing.

    Accepts: PDF, DOCX, TXT
    Saves to graphrag_workspace/input/ as pre-split article .txt files.
    """
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{suffix}'. Allowed: {ALLOWED_EXTENSIONS}",
        )

    indexing_svc = request.app.state.indexing_service
    documents_dir = Path(request.app.state.documents_dir)
    documents_dir.mkdir(parents=True, exist_ok=True)

    # Save uploaded file
    upload_path = documents_dir / file.filename
    try:
        async with aiofiles.open(upload_path, "wb") as f:
            content = await file.read()
            await f.write(content)
    except Exception as exc:
        logger.error("Failed to save uploaded file: %s", exc)
        raise HTTPException(status_code=500, detail=f"Failed to save file: {exc}")

    # Pre-process: parse + split into article chunks → graphrag_workspace/input/
    try:
        output_paths = await asyncio.to_thread(
            indexing_svc.prepare_for_graphrag, upload_path
        )
        message = f"Prepared {len(output_paths)} chunks from '{file.filename}'"
    except Exception as exc:
        logger.error("Document preparation failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"Document preparation failed: {exc}")

    return IngestResponse(
        filename=file.filename,
        status="uploaded",
        message=message,
    )


@router.post("/index", response_model=IndexResponse)
async def trigger_indexing(
    body: IndexRequest,
    request: Request,
) -> IndexResponse:
    """
    Start the GraphRAG indexing pipeline.

    Steps (async, background):
      1. graphrag index (entity extraction, community detection)
      2. import_to_neo4j.py (Parquet → Neo4j bulk import)
      3. Reload GraphRAG search engines

    Returns immediately; poll /admin/status to check progress.
    """
    indexing_svc = request.app.state.indexing_service
    started = await indexing_svc.start_indexing(reimport=body.reimport)

    if not started:
        return IndexResponse(
            status="already_running",
            message="Indexing pipeline is already running.",
        )

    return IndexResponse(
        status="started",
        message="Indexing pipeline started. Poll /admin/status for progress.",
    )


@router.get("/status", response_model=IndexStatusResponse)
async def indexing_status(request: Request) -> IndexStatusResponse:
    """Poll the current indexing pipeline status."""
    indexing_svc = request.app.state.indexing_service
    return IndexStatusResponse(
        status=indexing_svc.status,
        message=indexing_svc.message,
        last_completed_at=indexing_svc.last_completed_at,
    )


# asyncio imported here to avoid top-level import issues with aiofiles
import asyncio  # noqa: E402
