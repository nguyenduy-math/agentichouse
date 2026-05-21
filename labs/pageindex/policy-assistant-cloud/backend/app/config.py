"""Application configuration, loaded from backend/.env.

Two external services are configured here:
  * PageIndex Cloud — builds the knowledge tree for each uploaded document
    (https://dash.pageindex.ai/api-keys).
  * Google Gemini — navigates the downloaded tree and writes the Vietnamese answer.

We call load_dotenv() at import time so the keys are present before any client
is constructed, and accept GOOGLE_API_KEY as an alias for GEMINI_API_KEY.
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

    # --- PageIndex Cloud ---
    pageindex_api_key: str

    # --- Google Gemini ---
    gemini_api_key: str
    gemini_llm_model: str = "gemini-2.5-flash"

    # --- Storage paths ---
    document_folder: str = "./data/documents"   # transient PDF upload landing
    tree_storage_dir: str = "./tree_storage"     # downloaded {doc_id}.json trees + registry

    # --- Query behaviour ---
    response_language: str = "Vietnamese"
    default_history_turns: int = 3

    # --- Cloud processing poll ---
    poll_interval_seconds: int = 3
    poll_timeout_seconds: int = 300

    # --- Context-window budgets (token estimates, not characters) ---
    # Truncation happens on token boundaries via app.context_budget.
    tree_nav_budget_tokens: int = 4000          # compacted tree → navigation prompt
    answer_content_budget_tokens: int = 4500    # node text + trích PDF → answer prompt
    synthesis_input_budget_tokens: int = 4000   # merged per-doc answers → synthesis prompt
    max_docs_per_synthesis: int = 5             # cap trees we fan out to per query
    max_sections_per_doc: int = 3               # cap nodes read per document
    tree_max_depth: int = 3                     # how deep to walk the tree in the nav prompt
    tree_summary_char_cap: int = 200            # per-node summary trim in the nav prompt

    # --- Server ---
    host: str = "127.0.0.1"
    port: int = 8000
    # Comma-separated string so pydantic-settings v2 doesn't try json.loads() on it.
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    def get_cors_origins(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
