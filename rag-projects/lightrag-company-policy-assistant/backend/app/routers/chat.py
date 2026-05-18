"""POST /chat — main conversation endpoint via the OrchestratorAgent."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request

from app.config import settings
from app.schemas import ChatRequest, ChatResponse, ChatTurn

logger = logging.getLogger(__name__)
router = APIRouter(tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
async def chat(request: Request, body: ChatRequest) -> ChatResponse:
    orchestrator = request.app.state.orchestrator
    history_turns = body.history_turns if body.history_turns is not None else settings.default_history_turns
    history = [{"role": t.role, "content": t.content} for t in body.history]

    result = await orchestrator.process_message(
        message=body.message,
        history=history,
        history_turns=history_turns,
    )

    # Append this turn to the history returned to the client
    updated_history = list(body.history) + [
        ChatTurn(role="user", content=body.message),
        ChatTurn(role="assistant", content=result.answer),
    ]

    return ChatResponse(
        answer=result.answer,
        domains_consulted=result.domains_consulted,
        citations=result.citations,
        entities=result.entities,
        history=updated_history,
    )
