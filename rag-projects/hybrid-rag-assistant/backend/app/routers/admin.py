import asyncio

import structlog
from fastapi import APIRouter, Depends, HTTPException, UploadFile, Query

from app.agents.domain_agent import DomainAgent
from app.dependencies import get_agent_registry
from app.domains import DOMAIN_KEYS, DOMAINS
from app.schemas import IndexStatusResponse, StatsResponse

log = structlog.get_logger()
router = APIRouter(prefix="/admin", tags=["admin"])

_index_status: dict = {"status": "idle", "message": "", "chunks_indexed": 0}


@router.post("/ingest")
async def ingest_document(
    file: UploadFile,
    domain: str = Query(default="general", description="Domain key to ingest into"),
    registry: dict[str, DomainAgent] = Depends(get_agent_registry),
) -> dict:
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")
    if domain not in DOMAIN_KEYS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown domain '{domain}'. Valid: {DOMAIN_KEYS}",
        )
    content = await file.read()
    agent = registry[domain]
    chunks = await agent.ingest(content, file.filename)
    return {"filename": file.filename, "domain": domain, "chunks_created": len(chunks)}


@router.post("/index", response_model=IndexStatusResponse)
async def trigger_index(
    domain: str = Query(default="general"),
    registry: dict[str, DomainAgent] = Depends(get_agent_registry),
) -> IndexStatusResponse:
    global _index_status
    if domain not in DOMAIN_KEYS:
        raise HTTPException(status_code=400, detail=f"Unknown domain '{domain}'")
    _index_status = {"status": "running", "message": f"Rebuilding BM25 for '{domain}'", "chunks_indexed": 0}

    async def _run() -> None:
        global _index_status
        try:
            agent = registry[domain]
            await agent._rebuild_bm25()
            _index_status = {
                "status": "done",
                "message": f"BM25 rebuilt for '{domain}'",
                "chunks_indexed": agent.chunk_count,
            }
        except Exception as exc:
            log.error("index.failed", error=str(exc))
            _index_status = {"status": "error", "message": str(exc), "chunks_indexed": 0}

    asyncio.create_task(_run())
    return IndexStatusResponse(**_index_status)


@router.get("/index/status", response_model=IndexStatusResponse)
def index_status() -> IndexStatusResponse:
    return IndexStatusResponse(**_index_status)


@router.get("/stats", response_model=StatsResponse)
def stats(registry: dict[str, DomainAgent] = Depends(get_agent_registry)) -> StatsResponse:
    total = sum(a.chunk_count for a in registry.values())
    bm25_total = sum(a._bm25.corpus_size for a in registry.values())
    return StatsResponse(total_chunks=total, bm25_corpus_size=bm25_total)


@router.get("/domains")
def list_domains() -> dict:
    return DOMAINS
