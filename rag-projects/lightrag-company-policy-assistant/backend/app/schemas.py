"""Pydantic request/response models for the multi-agent policy assistant API."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

DomainKey = Literal["HR_POLICY", "BENEFITS", "CONDUCT", "PROCEDURES", "HANDBOOK"]
EngineType = Literal["lightrag", "pageindex"]


# ---------------------------------------------------------------------------
# Shared primitives
# ---------------------------------------------------------------------------

class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class Citation(BaseModel):
    document: str
    page: int
    section: str = ""
    domain: str


class AgentHealth(BaseModel):
    ready: bool
    engine_type: EngineType
    indexed_docs: int = 0


# ---------------------------------------------------------------------------
# Ingest
# ---------------------------------------------------------------------------

class IngestFolderRequest(BaseModel):
    folder: str | None = Field(
        default=None,
        description="Root folder to ingest. Defaults to DOCUMENT_FOLDER.",
    )


class IngestResponse(BaseModel):
    ingested_files: list[str]
    skipped_files: list[str]
    count: int
    message: str


# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    history: list[ChatTurn] = Field(default_factory=list)
    history_turns: int | None = Field(default=None, ge=0)


class ChatResponse(BaseModel):
    answer: str
    domains_consulted: list[str]
    citations: list[Citation] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)
    history: list[ChatTurn]


# ---------------------------------------------------------------------------
# Health / Admin
# ---------------------------------------------------------------------------

class HealthResponse(BaseModel):
    status: str
    agents: dict[str, AgentHealth]
    neo4j_connected: bool
    llm_model: str
    embedding_model: str


class AdminStatsResponse(BaseModel):
    agents: dict[str, AgentHealth]
    total_indexed_docs: int


class AdminAgentsResponse(BaseModel):
    agents: list[dict]
