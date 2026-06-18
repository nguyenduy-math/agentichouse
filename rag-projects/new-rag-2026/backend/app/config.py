"""
Pydantic settings for new-rag-2026.
All values can be overridden via environment variables or .env file.
"""
from __future__ import annotations

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ── Agent-layer LLM ───────────────────────────────────────────────────────
    LLM_PROVIDER: str = "gemini"  # gemini | openai | siliconflow

    # ── Gemini ────────────────────────────────────────────────────────────────
    GEMINI_API_KEY: str = ""
    GEMINI_CHAT_MODEL: str = "gemini-2.0-flash"
    GEMINI_EMBED_MODEL: str = "gemini-embedding-001"

    # ── OpenAI ────────────────────────────────────────────────────────────────
    OPENAI_API_KEY: str = ""
    OPENAI_CHAT_MODEL: str = "gpt-4o"
    OPENAI_EMBED_MODEL: str = "text-embedding-3-small"

    # ── Siliconflow ───────────────────────────────────────────────────────────
    SILICONFLOW_API_KEY: str = ""
    SILICONFLOW_MODEL: str = "deepseek-ai/DeepSeek-V3"
    SILICONFLOW_EMBED_MODEL: str = "BAAI/bge-large-zh-v1.5"

    # ── GraphRAG ──────────────────────────────────────────────────────────────
    GRAPHRAG_ROOT: str = "./graphrag_workspace"
    GRAPHRAG_QUERY_MODEL: str = "gemini-2.0-flash"
    EMBEDDING_MODEL: str = "gemini-embedding-001"

    # ── Neo4j ─────────────────────────────────────────────────────────────────
    NEO4J_URI: str = "bolt://localhost:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str = ""

    # ── Embedding ─────────────────────────────────────────────────────────────
    # 3072 for gemini-embedding-001, 768 for text-embedding-004,
    # 1536 for text-embedding-3-small, 1024 for BAAI/bge-large-zh-v1.5
    EMBEDDING_DIM: int = 3072

    # ── Retrieval quality ─────────────────────────────────────────────────────
    RERANK_CANDIDATE_POOL: int = 25   # overfetch size for reranking
    MAX_LOCAL_CHUNKS: int = 8         # final context size after rerank
    ENABLE_RERANK: bool = True
    COHERE_API_KEY: str = ""
    COHERE_RERANK_MODEL: str = "rerank-multilingual-v3.0"

    # Graph traversal
    GRAPH_HOP_DEPTH: int = 2

    # Answer verification
    ENABLE_ANSWER_VERIFICATION: bool = True
    VERIFICATION_CONFIDENCE_THRESHOLD: int = 3

    # ── Session ───────────────────────────────────────────────────────────────
    SESSION_TTL_MINUTES: int = 60

    # ── CORS ──────────────────────────────────────────────────────────────────
    CORS_ORIGINS: list[str] = ["http://localhost:5173"]

    # ── App ───────────────────────────────────────────────────────────────────
    LOG_LEVEL: str = "INFO"

    # ── LangSmith ─────────────────────────────────────────────────────────────
    LANGCHAIN_TRACING_V2: str = "false"
    LANGCHAIN_API_KEY: str = ""
    LANGCHAIN_PROJECT: str = "new-rag-2026"
    LANGCHAIN_ENDPOINT: str = "https://api.smith.langchain.com"

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


settings = Settings()
