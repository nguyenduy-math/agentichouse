"""Nạp tài liệu — tải PDF lên PageIndex Cloud, tải cây JSON về kho cục bộ."""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Request, UploadFile

from app.config import settings
from app.schemas import DocInfo, IngestResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ingest", tags=["ingest"])


@router.post("/upload", response_model=IngestResponse)
async def upload(request: Request, file: UploadFile = File(...)) -> IngestResponse:
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Chỉ hỗ trợ tệp PDF.")

    doc_folder = Path(settings.document_folder)
    doc_folder.mkdir(parents=True, exist_ok=True)
    dest = doc_folder / file.filename
    dest.write_bytes(await file.read())

    cloud = request.app.state.cloud
    try:
        result = await cloud.ingest(dest)
    except Exception as exc:
        logger.exception("Nạp tài liệu thất bại")
        raise HTTPException(status_code=502, detail=f"Lỗi xử lý trên PageIndex Cloud: {exc}")

    return IngestResponse(
        doc_id=result["doc_id"],
        filename=result["filename"],
        status=result.get("status", "completed"),
        tree_path=result["tree_path"],
        node_count=result.get("node_count", 0),
    )


@router.get("/list", response_model=list[DocInfo])
async def list_docs(request: Request) -> list[DocInfo]:
    cloud = request.app.state.cloud
    return [DocInfo(**d) for d in cloud.list_docs()]


@router.delete("/{doc_id}")
async def delete_doc(request: Request, doc_id: str) -> dict:
    cloud = request.app.state.cloud
    ok = await cloud.delete(doc_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Không tìm thấy tài liệu.")
    return {"deleted": doc_id}
