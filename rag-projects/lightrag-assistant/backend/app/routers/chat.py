"""POST /chat — multi-turn RAG chat with conversation history.

The server is stateless: the client sends the prior ``history`` with each
request, and the response returns the history with this turn appended so the
client can echo it back next time.
"""

from __future__ import annotations

from fastapi import APIRouter
from lightrag import QueryParam

from app.config import settings
from app.domain import DOMAIN_USER_PROMPT
from app.rag_engine import get_rag
from app.schemas import ChatRequest, ChatResponse, ChatTurn

router = APIRouter(tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    rag = get_rag()

    history = [{"role": turn.role, "content": turn.content} for turn in request.history]
    history_turns = (
        request.history_turns
        if request.history_turns is not None
        else settings.default_history_turns
    )

    param = QueryParam(
        mode=request.mode,
        conversation_history=history,
        history_turns=history_turns,
        user_prompt=DOMAIN_USER_PROMPT,
    )
    answer = str(await rag.aquery(request.message, param=param))

    updated_history = [
        *request.history,
        ChatTurn(role="user", content=request.message),
        ChatTurn(role="assistant", content=answer),
    ]
    return ChatResponse(answer=answer, history=updated_history, mode=request.mode)
