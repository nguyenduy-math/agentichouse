"""Hỏi đáp — tìm trên cây JSON và sinh câu trả lời tiếng Việt có dẫn chứng."""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.config import settings
from app.schemas import ChatCitation, ChatRequest, ChatResponse

router = APIRouter(tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
async def chat(request: Request, payload: ChatRequest) -> ChatResponse:
    search = request.app.state.search

    history = None
    if payload.history:
        turns = payload.history_turns or settings.default_history_turns
        history = [{"role": m.role, "content": m.content} for m in payload.history]
        history = history[-turns * 2:]

    result = await search.query(payload.message, history=history)

    return ChatResponse(
        answer=result.answer,
        citations=[ChatCitation(**c) for c in result.citations],
        documents_consulted=result.documents,
    )
