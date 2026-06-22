from fastapi import APIRouter, Depends, HTTPException

from app.dependencies import get_session_service
from app.schemas import SessionCreateResponse
from app.services.session_service import SessionService

router = APIRouter(prefix="/session", tags=["session"])


@router.post("", response_model=SessionCreateResponse)
def create_session(svc: SessionService = Depends(get_session_service)) -> SessionCreateResponse:
    session_id = svc.create_session()
    return SessionCreateResponse(session_id=session_id)


@router.delete("/{session_id}")
def delete_session(
    session_id: str, svc: SessionService = Depends(get_session_service)
) -> dict:
    found = svc.delete_session(session_id)
    if not found:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"status": "deleted"}
