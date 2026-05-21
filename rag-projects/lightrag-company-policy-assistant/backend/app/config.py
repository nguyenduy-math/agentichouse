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
    # Turns of history fed to the classifier so elliptical follow-ups route
    # correctly ("what about for contractors?"). Audit ref: D2.
    classify_history_turns: int = 2

    # --- Context-window budgets (token estimates, not characters) ---
    # Truncation happens on token boundaries via app.context_budget; these caps
    # replace the old scattered character slices ([:8000], [:6000], …).
    # Audit refs: C1, C3, C4.
    synthesis_input_budget_tokens: int = 4000   # merged specialist answers → synthesis prompt
    tree_nav_budget_tokens: int = 4000          # compacted PageIndex tree → navigation prompt
    answer_content_budget_tokens: int = 3000    # extracted page text → answer prompt
    # Cap on specialist answers fed into synthesis. The classifier prompt instructs
    # the model to return 1–3 domains, so in practice this rarely exceeds 3; the
    # cap here is a safety net for callers that bypass the prompt constraint (C3).
    max_docs_per_synthesis: int = 5
    max_sections_per_doc: int = 3               # cap sections read per document
    tree_max_depth: int = 3                     # how deep to walk the PageIndex tree (C4)
    tree_summary_char_cap: int = 200            # per-node summary trim in the nav prompt (C4)

    # --- Server ---
    host: str = "127.0.0.1"
    port: int = 8000
    # Comma-separated string so pydantic-settings v2 doesn't try json.loads() on it.
    # Parsed into a list in main.py via settings.get_cors_origins().
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    def get_cors_origins(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
