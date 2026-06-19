from __future__ import annotations

from fastapi import Request

from app.services.session_service import SessionService
from app.services.embedding_service import EmbeddingService
from app.services.neo4j_store import Neo4jStore
from app.services.llm_service import LLMService
from app.services.indexing_service import IndexingService
from app.services.graph_rag_service import GraphRAGService
from app.services.token_log_service import TokenLogService


def get_session_service(request: Request) -> SessionService:
    return request.app.state.session_service


def get_embedding_service(request: Request) -> EmbeddingService:
    return request.app.state.embedding_service


def get_neo4j_store(request: Request) -> Neo4jStore:
    return request.app.state.neo4j_store


def get_llm_service(request: Request) -> LLMService:
    return request.app.state.llm_service


def get_indexing_service(request: Request) -> IndexingService:
    return request.app.state.indexing_service


def get_graph_rag_service(request: Request) -> GraphRAGService:
    return request.app.state.graph_rag_service


def get_token_log_service(request: Request) -> TokenLogService:
    return request.app.state.token_log_service
