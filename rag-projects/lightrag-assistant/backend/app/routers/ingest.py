"""POST /ingest and POST /ingest/upload — load documents into the knowledge graph."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.config import settings
from app.ingestion import SUPPORTED_EXTENSIONS, collect_documents, extract_text
from app.rag_engine import get_rag
from app.schemas import IngestFolderRequest, IngestResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ingest", tags=["ingest"])


@router.post("", response_model=IngestResponse)
async def ingest_folder(request: IngestFolderRequest) -> IngestResponse:
    """Ingest every supported file in a server-side folder.

    LightRAG extracts insurance entities/relationships into Neo4j during this call,
    so it runs synchronously and may take a while for large folders.
    """
    rag = get_rag()
    folder = request.folder or settings.document_folder

    try:
        texts, sources, skipped = collect_documents(folder)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    if not texts:
        return IngestResponse(
            ingested_files=[],
            skipped_files=skipped,
            count=0,
            message=f"Không tìm thấy tài liệu hợp lệ trong: {folder}",
        )

    await rag.ainsert(texts, file_paths=sources)
    logger.info("Ingested %d document(s) from %s", len(sources), folder)
    return IngestResponse(
        ingested_files=sources,
        skipped_files=skipped,
        count=len(sources),
        message=f"Đã nạp {len(sources)} tài liệu vào tri thức.",
    )


@router.post("/upload", response_model=IngestResponse)
async def ingest_upload(files: list[UploadFile] = File(...)) -> IngestResponse:
    """Upload documents via multipart and ingest them immediately.

    Uploaded files are saved into the configured DOCUMENT_FOLDER so they persist
    and can be re-ingested later.
    """
    rag = get_rag()
    dest_dir = Path(settings.document_folder)
    dest_dir.mkdir(parents=True, exist_ok=True)

    texts: list[str] = []
    sources: list[str] = []
    skipped: list[str] = []

    for upload in files:
        filename = Path(upload.filename or "").name
        if not filename or Path(filename).suffix.lower() not in SUPPORTED_EXTENSIONS:
            skipped.append(upload.filename or "<unnamed>")
            await upload.close()
            continue

        dest = dest_dir / filename
        with dest.open("wb") as out_file:
            shutil.copyfileobj(upload.file, out_file)
        await upload.close()

        try:
            text = extract_text(dest).strip()
        except Exception as exc:  # noqa: BLE001 - skip unreadable uploads
            logger.warning("Failed to extract uploaded file %s: %s", dest, exc)
            skipped.append(filename)
            continue
        if not text:
            skipped.append(filename)
            continue

        texts.append(text)
        sources.append(str(dest))

    if not texts:
        return IngestResponse(
            ingested_files=[],
            skipped_files=skipped,
            count=0,
            message="Không có tài liệu hợp lệ trong tệp tải lên.",
        )

    await rag.ainsert(texts, file_paths=sources)
    logger.info("Uploaded and ingested %d document(s)", len(sources))
    return IngestResponse(
        ingested_files=sources,
        skipped_files=skipped,
        count=len(sources),
        message=f"Đã tải lên và nạp {len(sources)} tài liệu.",
    )
