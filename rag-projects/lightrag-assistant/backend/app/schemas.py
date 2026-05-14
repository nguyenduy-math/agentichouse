"""Pydantic request/response models for the API."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

QueryMode = Literal["naive", "local", "global", "hybrid", "mix"]


class IngestFolderRequest(BaseModel):
    folder: str | None = Field(
        default=None,
        description="Folder to ingest. Defaults to the configured DOCUMENT_FOLDER.",
    )


class IngestResponse(BaseModel):
    ingested_files: list[str]
    skipped_files: list[str]
    count: int
    message: str


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=1)
    mode: QueryMode = "hybrid"
    top_k: int | None = Field(default=None, ge=1)
    only_need_context: bool = False


class QueryResponse(BaseModel):
    answer: str
    mode: QueryMode


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    history: list[ChatTurn] = Field(default_factory=list)
    mode: QueryMode = "hybrid"
    history_turns: int | None = Field(default=None, ge=0)


class ChatResponse(BaseModel):
    answer: str
    history: list[ChatTurn]
    mode: QueryMode


class HealthResponse(BaseModel):
    status: str
    rag_initialized: bool
    neo4j_connected: bool
    llm_model: str
    embedding_model: str
    working_dir: str
