from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.dependencies import get_graph_rag_service, get_session_service
from app.models.chat import ChatRequest, ChatResponse, ChatHistoryResponse, Message
from app.services.graph_rag_service import GraphRAGService
from app.services.session_service import SessionService

router = APIRouter()


@router.post("", response_model=ChatResponse, summary="Gửi câu hỏi và nhận câu trả lời")
async def send_message(
    request: ChatRequest,
    rag_service: GraphRAGService = Depends(get_graph_rag_service),
    session_service: SessionService = Depends(get_session_service),
) -> ChatResponse:
    session = session_service.get_session(request.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    try:
        return await rag_service.process_message(request.session_id, request.message)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{session_id}/history", response_model=ChatHistoryResponse, summary="Lấy lịch sử trò chuyện")
async def get_history(
    session_id: str,
    session_service: SessionService = Depends(get_session_service),
) -> ChatHistoryResponse:
    session = session_service.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    messages = [
        Message(role=m.role, content=m.content, timestamp=m.timestamp)
        for m in session.messages
    ]
    return ChatHistoryResponse(session_id=session_id, messages=messages)
