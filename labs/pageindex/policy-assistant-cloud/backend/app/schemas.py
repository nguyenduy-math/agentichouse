"""Pydantic models — Gemini structured outputs and the public API contract."""

from __future__ import annotations

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Gemini structured-output schemas (response_schema)
# ---------------------------------------------------------------------------

class RelevantNode(BaseModel):
    """One tree node the navigator judged relevant to the question."""

    node_id: str
    title: str = ""
    reason: str = ""


class TreeNavigation(BaseModel):
    """Result of navigating one document tree: which nodes to read."""

    relevant_nodes: list[RelevantNode] = Field(default_factory=list)


class Citation(BaseModel):
    page: int = 0
    section: str = ""


class GroundedAnswer(BaseModel):
    answer: str = ""
    citations: list[Citation] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Public API models
# ---------------------------------------------------------------------------

class ChatMessage(BaseModel):
    role: str  # "user" | "assistant"
    content: str


class ChatRequest(BaseModel):
    message: str
    history: list[ChatMessage] | None = None
    history_turns: int | None = None


class ChatCitation(BaseModel):
    document: str
    page: int
    section: str


class ChatResponse(BaseModel):
    answer: str
    citations: list[ChatCitation] = Field(default_factory=list)
    documents_consulted: list[str] = Field(default_factory=list)


class IngestResponse(BaseModel):
    doc_id: str
    filename: str
    status: str
    tree_path: str
    node_count: int = 0


class DocInfo(BaseModel):
    doc_id: str
    filename: str
    node_count: int = 0


class HealthResponse(BaseModel):
    status: str = "ok"
    indexed_count: int = 0
    pageindex_key_present: bool = False
    gemini_key_present: bool = False
