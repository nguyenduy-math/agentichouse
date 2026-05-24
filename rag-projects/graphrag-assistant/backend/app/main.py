from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.services.session_service import SessionService
from app.services.embedding_service import create_embedding_service
from app.services.neo4j_store import Neo4jStore
from app.services.llm_service import create_llm_service
from app.services.indexing_service import IndexingService
from app.services.graph_rag_service import GraphRAGService

logger = structlog.get_logger()

_DESCRIPTION = """
GraphRAG-powered trợ lý nội quy công ty Agentic House (tiếng Việt).

### Bắt đầu nhanh
1. **Tạo phiên** — `POST /api/v1/session`
2. **Gửi câu hỏi** — `POST /api/v1/chat`
3. **Xem đồ thị tri thức** — `GET /api/v1/graph/nodes`

### Loại tài liệu được chấp nhận bởi `/admin/ingest`
| Giá trị | Mô tả |
|---------|-------|
| `handbooks` | Sổ tay nhân viên |
| `hr_policies` | Chính sách nhân sự |
| `conduct` | Quy tắc ứng xử |
| `benefits` | Phúc lợi |
| `procedures` | Quy trình |
"""

_TAGS = [
    {"name": "session", "description": "Tạo và xóa phiên trò chuyện."},
    {"name": "chat", "description": "Gửi câu hỏi và xem lịch sử trò chuyện."},
    {"name": "graph", "description": "Đồ thị tri thức: nodes, edges, community summaries."},
    {"name": "admin", "description": "Upload tài liệu, kích hoạt pipeline lập chỉ mục, thống kê hệ thống."},
]


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    logger.info("starting_up", llm_provider=settings.llm_provider)

    for doc_type in ["handbooks", "hr_policies", "conduct", "benefits", "procedures"]:
        os.makedirs(f"./data/raw/{doc_type}", exist_ok=True)

    session_service = SessionService(ttl_seconds=settings.session_ttl_seconds)
    session_service.start_cleanup()

    embedding_service = create_embedding_service()
    await embedding_service.initialize()

    neo4j_store = Neo4jStore()
    await neo4j_store.initialize()

    llm_service = create_llm_service()

    indexing_service = IndexingService(
        llm_service=llm_service,
        embedding_service=embedding_service,
        neo4j_store=neo4j_store,
    )

    graph_rag_service = GraphRAGService(
        llm_service=llm_service,
        embedding_service=embedding_service,
        neo4j_store=neo4j_store,
        session_service=session_service,
    )

    app.state.session_service = session_service
    app.state.embedding_service = embedding_service
    app.state.neo4j_store = neo4j_store
    app.state.llm_service = llm_service
    app.state.indexing_service = indexing_service
    app.state.graph_rag_service = graph_rag_service
    app.state.indexing_status = {
        "status": "idle",
        "progress": 0,
        "total": 0,
        "stage": "",
        "last_error": None,
        "stats": {},
    }

    logger.info("startup_complete")
    yield

    session_service.stop_cleanup()
    await neo4j_store.close()
    logger.info("shutdown_complete")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Agentic House Policy Assistant",
        version="1.0.0",
        description=_DESCRIPTION,
        openapi_tags=_TAGS,
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    from app.api.routes import session, chat, admin, graph

    app.include_router(session.router, prefix="/api/v1/session", tags=["session"])
    app.include_router(chat.router, prefix="/api/v1/chat", tags=["chat"])
    app.include_router(admin.router, prefix="/api/v1/admin", tags=["admin"])
    app.include_router(graph.router, prefix="/api/v1/graph", tags=["graph"])

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok", "max_chat_retries": settings.max_chat_retries}

    return app


app = create_app()
