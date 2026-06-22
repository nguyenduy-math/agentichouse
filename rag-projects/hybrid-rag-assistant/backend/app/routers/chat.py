from fastapi import APIRouter, Depends

from app.dependencies import get_rag_service, get_session_service
from app.schemas import ChatRequest, ChatResponse, HistoryMessage
from app.services.rag_service import RAGService
from app.services.session_service import SessionService

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
async def chat(
    req: ChatRequest,
    rag: RAGService = Depends(get_rag_service),
) -> ChatResponse:
    return await rag.query(req.session_id, req.message)


@router.get("/{session_id}/history", response_model=list[HistoryMessage])
def get_history(
    session_id: str, session: SessionService = Depends(get_session_service)
) -> list[HistoryMessage]:
    messages = session.get_full_history(session_id)
    return [HistoryMessage(role=m["role"], content=m["content"]) for m in messages]
