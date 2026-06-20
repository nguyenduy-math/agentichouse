"""
Pydantic request/response schemas for all API endpoints.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


# ── Session ───────────────────────────────────────────────────────────────────

class SessionCreateResponse(BaseModel):
    session_id: str
    created_at: str


class SessionDeleteResponse(BaseModel):
    session_id: str
    status: str = "deleted"


# ── Chat ──────────────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    session_id: str = Field(..., description="UUID session identifier")
    message: str = Field(..., description="User message in Vietnamese")
    mode: Literal["auto", "local", "global"] = Field(
        "auto",
        description="Search mode: auto lets the orchestrator decide",
    )


class SourceItem(BaseModel):
    type: str  # "text_unit" | "community_report"
    id: str | None = None
    text: str | None = None
    title: str | None = None
    summary: str | None = None
    document: str | None = None
    rerank_score: float | None = None
    entity_hit_count: int | None = None


class ChatResponse(BaseModel):
    reply: str
    sources: list[SourceItem] = []
    query_type: str  # "local" | "global"
    session_id: str
    domain_keys: list[str] = []
    agent_count: int = 1
    rewritten_query: str | None = None
    verification: dict[str, Any] | None = None


# ── Agent trace ───────────────────────────────────────────────────────────────

class AgentResultItem(BaseModel):
    domain_key: str
    domain_name_vi: str
    answer: str
    sources_count: int
    search_mode: str


class AgentTraceResponse(BaseModel):
    session_id: str
    last_question: str | None = None
    domain_keys: list[str] = []
    search_mode: str | None = None
    agent_results: list[AgentResultItem] = []


# ── Admin ─────────────────────────────────────────────────────────────────────

class IngestResponse(BaseModel):
    filename: str
    status: str = "uploaded"
    message: str | None = None
    domain: str | None = None


class IndexRequest(BaseModel):
    domain: str = Field(
        ...,
        description="Domain key to index (hr, benefits, it, finance, compliance, procedures, general)",
    )
    reimport: bool = Field(
        False,
        description="If True, re-run import_to_neo4j.py even if artifacts exist",
    )


class IndexResponse(BaseModel):
    status: str  # "started" | "already_running"
    message: str | None = None


class IndexStatusResponse(BaseModel):
    status: str  # "idle" | "indexing" | "importing" | "ready" | "error"
    message: str | None = None
    last_completed_at: str | None = None


# ── Health ────────────────────────────────────────────────────────────────────

class HealthResponse(BaseModel):
    status: str = "ok"
    neo4j_connected: bool = False
    graphrag_ready: bool = False
    llm_provider: str = "gemini"
    version: str = "2.0.0"
