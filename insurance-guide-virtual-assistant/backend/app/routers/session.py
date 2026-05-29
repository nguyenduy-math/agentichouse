from fastapi import APIRouter, HTTPException, Request

from app.schemas import AssistantMode, NewSessionRequest, NewSessionResponse, SessionPhase

router = APIRouter(prefix="/session", tags=["session"])


@router.post("/new", response_model=NewSessionResponse)
async def new_session(body: NewSessionRequest, request: Request) -> NewSessionResponse:
    store = request.app.state.session_store
    session = await store.create()
    session.mode = body.mode
    # Recommendation mode starts directly in collecting (no claim-type identification needed)
    if body.mode == AssistantMode.recommendation:
        session.phase = SessionPhase.collecting
    await store.save(session)
    return NewSessionResponse(session_id=session.session_id)


@router.delete("/{session_id}")
async def delete_session(session_id: str, request: Request) -> dict:
    store = request.app.state.session_store
    deleted = await store.delete(session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"deleted": session_id}
