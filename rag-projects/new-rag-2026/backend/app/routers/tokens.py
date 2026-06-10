"""Token usage endpoints."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

router = APIRouter(prefix="/api/v1")


# ── Response schemas ──────────────────────────────────────────────────────────

class CallTypeBreakdown(BaseModel):
    call_type: str
    total_tokens: int
    cost_usd: float
    calls: int


class ModelBreakdown(BaseModel):
    provider: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_usd: float


class TurnBreakdown(BaseModel):
    turn_id: str
    turn_number: int | None
    total_tokens: int
    cost_usd: float
    calls: int


class SessionTokenSummary(BaseModel):
    session_id: str
    total_prompt_tokens: int
    total_completion_tokens: int
    total_tokens: int
    total_cost_usd: float
    total_calls: int
    by_call_type: list[CallTypeBreakdown]
    by_model: list[ModelBreakdown]
    turn_breakdown: list[TurnBreakdown]


class AdminTokenRow(BaseModel):
    session_id: str
    total_tokens: int
    total_cost_usd: float
    total_calls: int
    first_call: str
    last_call: str


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/sessions/{session_id}/tokens", response_model=SessionTokenSummary)
async def get_session_tokens(session_id: str, request: Request) -> SessionTokenSummary:
    history_store = getattr(request.app.state, "history_store", None)
    if history_store is None:
        raise HTTPException(status_code=503, detail="History store not available.")
    summary = await history_store.get_session_token_summary(session_id)
    return SessionTokenSummary(**summary)


@router.get("/admin/tokens/summary", response_model=list[AdminTokenRow])
async def get_admin_token_summary(
    request: Request, limit: int = 100
) -> list[AdminTokenRow]:
    history_store = getattr(request.app.state, "history_store", None)
    if history_store is None:
        raise HTTPException(status_code=503, detail="History store not available.")
    rows = await history_store.get_all_sessions_token_summary(limit=limit)
    return [AdminTokenRow(**r) for r in rows]
