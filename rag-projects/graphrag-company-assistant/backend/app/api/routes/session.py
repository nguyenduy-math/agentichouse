from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.dependencies import get_session_service
from app.services.session_service import SessionService

router = APIRouter()


class SessionResponse(BaseModel):
    session_id: str


@router.post("", response_model=SessionResponse, summary="Tạo phiên trò chuyện mới")
async def create_session(
    session_service: SessionService = Depends(get_session_service),
) -> SessionResponse:
    session = session_service.create_session()
    return SessionResponse(session_id=session.session_id)


@router.delete("/{session_id}", summary="Xóa phiên trò chuyện")
async def delete_session(
    session_id: str,
    session_service: SessionService = Depends(get_session_service),
) -> dict:
    deleted = session_service.delete_session(session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"status": "deleted"}
