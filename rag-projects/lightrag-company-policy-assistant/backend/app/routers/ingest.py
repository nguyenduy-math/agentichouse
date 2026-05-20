"""POST /ingest and POST /ingest/upload — index documents into domain agents."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile

from app.config import settings
from app.domains import DOC_TYPE_TO_DOMAIN, VALID_DOC_TYPES
from app.ingestion import SUPPORTED_EXTENSIONS, collect_documents
from app.schemas import IngestFolderRequest, IngestResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ingest", tags=["ingest"])

# DOC_TYPE_TO_DOMAIN / VALID_DOC_TYPES now live in app.domains (single source of
# truth) and are re-exported here for backwards-compatible imports.


def _infer_domain(path: Path, base: Path) -> str | None:
    """Infer the domain key from a file's position in the documents tree."""
    try:
        rel = path.relative_to(base)
        first_part = rel.parts[0] if rel.parts else None
        return DOC_TYPE_TO_DOMAIN.get(first_part or "")
    except ValueError:
        return None


@router.post("", response_model=IngestResponse)
async def ingest_folder(request: Request, body: IngestFolderRequest) -> IngestResponse:
    """Ingest every supported file in the documents folder into the correct domain agent."""
    orchestrator = request.app.state.orchestrator
    base = Path(body.folder or settings.document_folder)

    try:
        texts, sources, skipped = collect_documents(base)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    if not texts:
        return IngestResponse(
            ingested_files=[],
            skipped_files=skipped,
            count=0,
            message=f"No valid documents found in: {base}",
        )

    ingested: list[str] = []
    for text, source in zip(texts, sources):
        source_path = Path(source)
        domain = _infer_domain(source_path, base)
        if domain and domain in orchestrator._agents:
            try:
                await orchestrator._agents[domain].index_document(source_path)
                ingested.append(source)
            except Exception as exc:
                logger.warning("Failed to index %s into %s: %s", source, domain, exc)
                skipped.append(source)
        else:
            logger.warning("No domain agent for %s (doc_type unknown)", source)
            skipped.append(source)

    return IngestResponse(
        ingested_files=ingested,
        skipped_files=skipped,
        count=len(ingested),
        message=f"Indexed {len(ingested)} document(s) into domain agents.",
    )


@router.post("/upload", response_model=IngestResponse)
async def ingest_upload(
    request: Request,
    files: list[UploadFile] = File(...),
    doc_type: str = Form(...),
) -> IngestResponse:
    """Upload documents and index them into the specified domain agent."""
    if doc_type not in VALID_DOC_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid doc_type '{doc_type}'. Valid values: {sorted(VALID_DOC_TYPES)}",
        )

    domain = DOC_TYPE_TO_DOMAIN[doc_type]
    orchestrator = request.app.state.orchestrator
    agent = orchestrator._agents.get(domain)
    if agent is None:
        raise HTTPException(status_code=500, detail=f"No agent registered for domain {domain}")

    dest_dir = Path(settings.document_folder) / doc_type
    dest_dir.mkdir(parents=True, exist_ok=True)

    ingested: list[str] = []
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
            await agent.index_document(dest)
            ingested.append(str(dest))
        except Exception as exc:
            logger.warning("Failed to index %s: %s", dest, exc)
            skipped.append(filename)

    return IngestResponse(
        ingested_files=ingested,
        skipped_files=skipped,
        count=len(ingested),
        message=f"Indexed {len(ingested)} document(s) into {domain} agent.",
    )
