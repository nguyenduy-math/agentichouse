"""Application configuration, loaded from backend/.env.

LightRAG's Neo4JStorage reads NEO4J_* directly from os.environ, and
pydantic-settings does NOT populate os.environ on its own — so we call
load_dotenv() here at import time, before LightRAG is ever constructed.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv()

# Accept either GEMINI_API_KEY or GOOGLE_API_KEY (common alternative name).
if not os.environ.get("GEMINI_API_KEY") and os.environ.get("GOOGLE_API_KEY"):
    os.environ["GEMINI_API_KEY"] = os.environ["GOOGLE_API_KEY"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Google Gemini ---
    gemini_api_key: str
    gemini_llm_model: str = "gemini-2.5-flash"
    gemini_embedding_model: str = "gemini-embedding-001"
    embedding_dim: int = 1536
    embedding_max_token_size: int = 2048

    # --- Neo4j ---
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_username: str = "neo4j"
    neo4j_password: str = "please-change-me"
    neo4j_database: str = "neo4j"

    # --- Storage paths ---
    document_folder: str = "./data/documents"
    lightrag_base_dir: str = "./rag_storage/lightrag"
    pageindex_base_dir: str = "./rag_storage/pageindex"

    # --- Domain / query ---
    default_history_turns: int = 3
    response_language: str = "Vietnamese"

    # --- Server ---
    host: str = "127.0.0.1"
    port: int = 8000
    # Comma-separated string so pydantic-settings v2 doesn't try json.loads() on it.
    # Parsed into a list in main.py via settings.get_cors_origins().
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    def get_cors_origins(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
