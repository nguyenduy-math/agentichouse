"""Application configuration, loaded from backend/.env.

LightRAG's Neo4JStorage reads NEO4J_* directly from os.environ, and
pydantic-settings does NOT populate os.environ on its own — so we call
load_dotenv() here at import time, before LightRAG is ever constructed.
"""

from __future__ import annotations

from dotenv import load_dotenv
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Populate os.environ from backend/.env so LightRAG's Neo4j backend can read it.
load_dotenv()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Google Gemini ---
    gemini_api_key: str  # no default — the app fails fast at startup if missing
    gemini_llm_model: str = "gemini-2.5-flash"
    gemini_embedding_model: str = "gemini-embedding-001"
    embedding_dim: int = 1536
    embedding_max_token_size: int = 2048

    # --- Neo4j (graph storage backend) ---
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_username: str = "neo4j"
    neo4j_password: str = "please-change-me"
    neo4j_database: str = "neo4j"

    # --- LightRAG / domain ---
    working_dir: str = "./rag_storage"
    document_folder: str = "./data/documents"
    default_query_mode: str = "hybrid"
    default_history_turns: int = 3
    response_language: str = "Vietnamese"

    # --- Server ---
    host: str = "127.0.0.1"
    port: int = 8000
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_cors_origins(cls, value: object) -> object:
        """Accept a comma-separated string from the .env file."""
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value


settings = Settings()
