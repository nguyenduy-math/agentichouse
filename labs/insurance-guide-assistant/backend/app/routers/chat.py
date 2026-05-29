from fastapi import APIRouter, HTTPException, Request

from app import advisor_agent, agent as claim_agent
from app.advisor_agent import get_profile_progress
from app.claim_schema import compute_progress
from app.schemas import AssistantMode, ChatRequest, ChatResponse, ClaimType, HealthProfile

router = APIRouter(tags=["chat"])

_FIRST_ADVISOR_MSG = (
    "Xin chào! Tôi sẽ giúp bạn tìm gói bảo hiểm phù hợp nhất. "
    "Trước tiên, bạn bao nhiêu tuổi?"
)


@router.post("/chat", response_model=ChatResponse)
async def chat(body: ChatRequest, request: Request) -> ChatResponse:
    store = request.app.state.session_store

    if body.session_id:
        session = await store.get(body.session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="Session not found or expired")
    else:
        raise HTTPException(status_code=400, detail="session_id is required")

    mode = session.mode

    # -----------------------------------------------------------------------
    # Dispatch to the correct agent
    # -----------------------------------------------------------------------
    if mode == AssistantMode.recommendation:
        reply, updated_profile, recommendation, is_complete, new_phase, options = (
            await advisor_agent.process_turn(session, body.message)
        )
        session.health_profile = updated_profile
        session.history.append({"role": "user", "content": body.message})
        session.history.append({"role": "model", "content": reply})
        session.turn_count += 1
        session.is_complete = is_complete
        session.phase = new_phase
        if recommendation:
            session.recommendation = recommendation
        await store.save(session)

        progress = get_profile_progress(updated_profile)
        return ChatResponse(
            session_id=session.session_id,
            reply=reply,
            collected=session.collected,
            health_profile=updated_profile,
            recommendation=recommendation,
            is_complete=is_complete,
            progress_pct=progress,
            session_phase=new_phase,
            options=options,
        )

    else:  # claim_filing (default)
        reply, updated_collected, proposal, is_complete, new_phase, options = (
            await claim_agent.process_turn(session, body.message)
        )
        session.collected = updated_collected
        session.history.append({"role": "user", "content": body.message})
        session.history.append({"role": "model", "content": reply})
        session.turn_count += 1
        session.is_complete = is_complete
        session.phase = new_phase
        if proposal:
            session.cached_proposal = proposal
        await store.save(session)

        claim_type = updated_collected.claim_type or ClaimType.unknown
        progress = compute_progress(updated_collected.model_dump(), claim_type)
        return ChatResponse(
            session_id=session.session_id,
            reply=reply,
            collected=updated_collected,
            health_profile=HealthProfile(),
            proposal=proposal,
            is_complete=is_complete,
            progress_pct=progress,
            session_phase=new_phase,
            options=options,
        )
