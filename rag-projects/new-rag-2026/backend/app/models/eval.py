"""
Pydantic models for the Ragas Evaluation Report feature.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


# ── Turn (from SQLite) ────────────────────────────────────────────────────────

class EvalTurn(BaseModel):
    turn_id: str
    session_id: str
    turn_number: int
    question: str
    answer: str
    sources: list[dict[str, Any]] = []
    domain_keys: list[str] = []
    query_type: str = ""
    is_fallback: bool = False
    timestamp: str


# ── Session summary ───────────────────────────────────────────────────────────

class SessionSummary(BaseModel):
    session_id: str
    turn_count: int
    last_active: str
    created_at: str


class SessionListResponse(BaseModel):
    sessions: list[SessionSummary]
    total: int


class SessionTurnsResponse(BaseModel):
    session_id: str
    turns: list[EvalTurn]


# ── Eval run request ──────────────────────────────────────────────────────────

class EvalRunRequest(BaseModel):
    turn_ids: list[str] = Field(..., min_length=1)
    judge_provider: str = Field("openai", description="openai | gemini | siliconflow")
    judge_model: str = Field("gpt-4o-mini")
    reference_answers: dict[str, str] = Field(
        default_factory=dict,
        description="Optional {turn_id: reference_text} for context_recall / answer_correctness",
    )


class EvalRunStartResponse(BaseModel):
    run_id: str
    status: str = "pending"
    turn_count: int


# ── Per-turn score ────────────────────────────────────────────────────────────

class EvalTurnScore(BaseModel):
    turn_id: str
    question: str
    answer: str
    domain_keys: list[str] = []
    query_type: str = ""
    faithfulness: float | None = None
    answer_relevancy: float | None = None
    context_precision: float | None = None
    context_recall: float | None = None
    answer_correctness: float | None = None
    reference_answer: str = ""


# ── Run result ────────────────────────────────────────────────────────────────

class EvalRunResult(BaseModel):
    run_id: str
    status: str
    judge_provider: str
    judge_model: str
    created_at: str
    turn_count: int
    error: str | None = None
    scores: list[EvalTurnScore] = []
    averages: dict[str, float | None] = {}


class EvalRunSummary(BaseModel):
    run_id: str
    created_at: str
    turn_count: int
    judge_provider: str
    judge_model: str
    status: str
    error: str | None = None


class EvalRunListResponse(BaseModel):
    runs: list[EvalRunSummary]
