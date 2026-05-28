from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Provider selection: "gemini" | "openai"
    llm_provider: str = "gemini"

    # Google Gemini
    google_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    gemini_embedding_model: str = "models/gemini-embedding-exp-03-07"
    embedding_dim: int = 3072

    # OpenAI
    openai_api_key: str = ""
    openai_model: str = "gpt-4.1"
    openai_embedding_model: str = "text-embedding-3-large"

    # Neo4j
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "techviet2024"

    # Chunking
    chunk_size: int = 2800
    chunk_overlap: int = 400

    # Retrieval tuning
    max_local_chunks: int = 12
    max_community_summaries: int = 5
    graph_hop_depth: int = 2
    entity_extraction_batch: int = 5

    # Reranking (Cohere)
    enable_rerank: bool = True
    cohere_api_key: str = ""
    cohere_rerank_model: str = "rerank-multilingual-v3.0"
    rerank_candidate_pool: int = 25
    rerank_top_n: int = 8

    # Answer verification
    enable_answer_verification: bool = True
    max_chat_retries: int = 3

    # Session
    session_ttl_seconds: int = 3600

    # Token logging
    token_db_path: str = "./data/token_logs.db"

    # CORS
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]


settings = Settings()
