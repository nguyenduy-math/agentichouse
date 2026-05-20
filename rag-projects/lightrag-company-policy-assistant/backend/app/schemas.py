"""Pydantic request/response models for the multi-agent policy assistant API."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# Keep this Literal in sync with app.domains.DOMAINS — domains._assert_schema_in_sync()
# verifies the two match at startup and fails fast otherwise (audit ref: B1).
DomainKey = Literal[
    "HR_POLICY", "BENEFITS", "CONDUCT", "PROCEDURES", "HANDBOOK",
    "MEDICAL", "IT_SECURITY", "COMPLIANCE", "FINANCE", "TRAINING",
]
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
# LLM structured-output schemas (passed to Gemini as response_schema)
# ---------------------------------------------------------------------------
# Using these as Gemini response_schema guarantees the model can only emit valid
# shapes/values — no manual validate-and-default dance (audit refs: B2, B4).

class DomainClassification(BaseModel):
    """Classifier output — Gemini may only return keys from the DomainKey enum."""

    domains: list[DomainKey] = Field(
        default_factory=list,
        description="1-3 relevant policy domains, most relevant first. Empty if none apply.",
    )


class RelevantNode(BaseModel):
    """One section a PageIndex tree-navigation step decided is worth reading."""

    node_id: str = ""
    start_page: int
    end_page: int
    reason: str = ""


class TreeNavigation(BaseModel):
    relevant_nodes: list[RelevantNode] = Field(default_factory=list)


class PageCitation(BaseModel):
    """A citation produced by the answer step, tied to the text it actually used."""

    page: int
    section: str = ""


class GroundedAnswer(BaseModel):
    """PageIndex answer-step output: answer text + the citations it relied on."""

    answer: str
    citations: list[PageCitation] = Field(default_factory=list)


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
