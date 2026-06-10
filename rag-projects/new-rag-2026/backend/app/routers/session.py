"""Session management router."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.schemas import SessionCreateResponse, SessionDeleteResponse

router = APIRouter(prefix="/api/v1")


@router.post("/session", response_model=SessionCreateResponse)
async def create_session(request: Request) -> SessionCreateResponse:
    """Create a new conversation session."""
    session_svc = request.app.state.session_service
    session = await session_svc.create_session()
    return SessionCreateResponse(
        session_id=session.session_id,
        created_at=session.created_at.isoformat(),
    )


@router.delete("/session/{session_id}", response_model=SessionDeleteResponse)
async def delete_session(session_id: str, request: Request) -> SessionDeleteResponse:
    """Delete a conversation session and its history."""
    session_svc = request.app.state.session_service
    deleted = await session_svc.delete_session(session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found.")
    return SessionDeleteResponse(session_id=session_id, status="deleted")
