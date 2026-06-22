from functools import lru_cache

from google import genai

from app.agents.domain_agent import DomainAgent
from app.agents.orchestrator_agent import OrchestratorAgent
from app.config import settings
from app.domains import DOMAINS
from app.services.bm25_service import BM25Service
from app.services.embedding_service import EmbeddingService
from app.services.llm_service import LLMService
from app.services.rag_service import RAGService
from app.services.rerank_service import RerankService
from app.services.session_service import SessionService
from app.services.vector_service import VectorService


# Shared singletons
@lru_cache(maxsize=1)
def _embedding() -> EmbeddingService:
    return EmbeddingService()


@lru_cache(maxsize=1)
def _reranker() -> RerankService:
    return RerankService()


@lru_cache(maxsize=1)
def _llm() -> LLMService:
    return LLMService()


@lru_cache(maxsize=1)
def _session() -> SessionService:
    return SessionService()


@lru_cache(maxsize=1)
def _gemini_client() -> genai.Client:
    return genai.Client(api_key=settings.gemini_api_key)


# Per-domain agent registry
@lru_cache(maxsize=1)
def _agent_registry() -> dict[str, DomainAgent]:
    registry: dict[str, DomainAgent] = {}
    for domain_key, domain_label in DOMAINS.items():
        bm25 = BM25Service(name=domain_key)
        bm25.load()
        vector = VectorService(collection_name=f"chunks_{domain_key}")
        registry[domain_key] = DomainAgent(
            domain_key=domain_key,
            domain_label=domain_label,
            bm25=bm25,
            vector=vector,
            embedding=_embedding(),
            reranker=_reranker(),
        )
    return registry


@lru_cache(maxsize=1)
def _orchestrator() -> OrchestratorAgent:
    return OrchestratorAgent(
        agents=_agent_registry(),
        llm_client=_gemini_client(),
    )


@lru_cache(maxsize=1)
def _rag() -> RAGService:
    return RAGService(
        orchestrator=_orchestrator(),
        llm=_llm(),
        session=_session(),
    )


# FastAPI dependency callables
def get_agent_registry() -> dict[str, DomainAgent]:
    return _agent_registry()


def get_session_service() -> SessionService:
    return _session()


def get_rag_service() -> RAGService:
    return _rag()


def get_bm25_service(domain: str = "general") -> BM25Service:
    return _agent_registry()[domain]._bm25


def get_vector_service(domain: str = "general") -> VectorService:
    return _agent_registry()[domain]._vector
