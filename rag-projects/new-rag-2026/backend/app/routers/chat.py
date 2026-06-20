"""
Chat router -- main conversation endpoint.
"""
from __future__ import annotations

import asyncio
import logging
import os

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from langchain_core.runnables.config import RunnableConfig

from app.config import settings
from app.domains import DOMAIN_MAP
from app.schemas import AgentResultItem, AgentTraceResponse, ChatRequest, ChatResponse, SourceItem
from app.services.token_callback import SessionTokenCallback

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1")


@router.post("/chat", response_model=ChatResponse)
async def chat(body: ChatRequest, request: Request) -> ChatResponse:
    session_svc = request.app.state.session_service
    history_store = getattr(request.app.state, "history_store", None)
    orchestrator = request.app.state.orchestrator

    if orchestrator is None:
        raise HTTPException(
            status_code=503,
            detail="Orchestrator not available. Upload documents and trigger indexing first.",
        )

    session = await session_svc.get_or_create_session(body.session_id)

    # Resolve provider/model for token attribution
    _provider = settings.LLM_PROVIDER.lower()
    _model = {
        "gemini":      os.environ.get("GEMINI_CHAT_MODEL", "gemini-2.0-flash"),
        "openai":      os.environ.get("OPENAI_CHAT_MODEL", "gpt-4o"),
        "siliconflow": os.environ.get("SILICONFLOW_MODEL", "deepseek-ai/DeepSeek-V3"),
    }.get(_provider, "unknown")

    # One SessionTokenCallback per request -- routes by call_type via on_llm_start
    token_callback: SessionTokenCallback | None = None
    if history_store is not None:
        token_callback = SessionTokenCallback(
            session_id=body.session_id,
            token_store=history_store,
            provider=_provider,
            model=_model,
            turn_id=None,  # back-filled after save_turn() below
        )

    config = RunnableConfig(
        run_name=f"chat/{body.session_id[:8]}",
        tags=[
            f"provider:{settings.LLM_PROVIDER}",
            f"session:{body.session_id[:8]}",
        ],
        metadata={
            "session_id": body.session_id,
            "llm_provider": settings.LLM_PROVIDER,
            "project": "new-rag-2026",
        },
        callbacks=[token_callback] if token_callback is not None else [],
    )

    session_history = session.get_history_text(max_turns=6)

    # Create a fresh ProgressTracker for this turn so the SSE endpoint can stream it
    from app.services.progress_tracker import ProgressTracker
    tracker = ProgressTracker()
    request.app.state.progress_store[body.session_id] = tracker

    try:
        result = await orchestrator.run(
            question=body.message,
            session_history=session_history,
            config=config,
            progress=tracker,
        )
    except Exception as exc:
        tracker.emit("error", message=str(exc))
        logger.error("Orchestrator error for session %s: %s", body.session_id, exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Processing error: {exc}")
    finally:
        # Keep the tracker alive for 10 s so slow SSE clients can drain the final events
        async def _cleanup_tracker() -> None:
            await asyncio.sleep(10)
            request.app.state.progress_store.pop(body.session_id, None)
        asyncio.create_task(_cleanup_tracker())

    session.add_message("user", body.message)
    session.add_message("assistant", result.final_answer)

    await session_svc.update_last_result(
        session_id=body.session_id,
        result=result,
        question=body.message,
    )

    sources = [
        SourceItem(
            type=s.get("type", "text_unit"),
            id=s.get("id"),
            text=s.get("text"),
            title=s.get("title"),
            summary=s.get("summary"),
            document=s.get("document"),
            rerank_score=s.get("rerank_score"),
            entity_hit_count=s.get("entity_hit_count"),
        )
        for s in result.sources
    ]

    chat_response = ChatResponse(
        reply=result.final_answer,
        sources=sources,
        query_type=result.search_mode,
        session_id=body.session_id,
        domain_keys=result.domain_keys,
        agent_count=len(result.agent_results),
        rewritten_query=result.rewritten_query,
        verification=result.verification,
    )

    # Persist turn to SQLite and back-fill turn_id on the token callback
    if history_store is not None:
        turn_number = len(session.messages) // 2

        async def _save_and_backfill() -> None:
            turn_id = await history_store.save_turn(
                session_id=body.session_id,
                turn_number=turn_number,
                question=body.message,
                answer=result.final_answer,
                sources=[s.model_dump() for s in sources],
                domain_keys=result.domain_keys,
                query_type=result.search_mode,
                is_fallback=False,
            )
            if token_callback is not None:
                token_callback.set_turn_id(turn_id)

        asyncio.create_task(_save_and_backfill())

    return chat_response


@router.get("/chat/{session_id}/progress")
async def chat_progress(session_id: str, request: Request) -> StreamingResponse:
    """
    SSE stream of pipeline progress events for one chat turn.

    The browser opens this endpoint before (or simultaneously with) POST /chat.
    The server waits up to 5 s for the tracker to appear (handles the race where
    the SSE connection is established before the POST starts processing), then
    streams events until the pipeline emits 'done' or 'error'.

    Event shape: JSON objects — see ProgressTracker docstring for the full schema.
    """
    # Wait up to 5 s for the tracker created by POST /chat to appear
    tracker = None
    for _ in range(10):
        tracker = request.app.state.progress_store.get(session_id)
        if tracker is not None:
            break
        await asyncio.sleep(0.5)

    async def event_generator():
        if tracker is None:
            yield 'data: {"type": "done"}\n\n'
            return
        async for chunk in tracker.stream():
            if await request.is_disconnected():
                break
            yield chunk

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/chat/{session_id}/agent_trace", response_model=AgentTraceResponse)
async def agent_trace(session_id: str, request: Request) -> AgentTraceResponse:
    session_svc = request.app.state.session_service
    session = await session_svc.get_session(session_id)

    if session is None:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found.")

    result = session.last_orchestrator_result

    if result is None:
        return AgentTraceResponse(
            session_id=session_id,
            last_question=None,
            domain_keys=[],
            search_mode=None,
            agent_results=[],
        )

    agent_result_items = []
    for ar in result.agent_results:
        domain = DOMAIN_MAP.get(ar.domain_key)
        agent_result_items.append(
            AgentResultItem(
                domain_key=ar.domain_key,
                domain_name_vi=domain.name_vi if domain else ar.domain_key,
                answer=ar.answer,
                sources_count=len(ar.sources),
                search_mode=ar.search_mode,
            )
        )

    return AgentTraceResponse(
        session_id=session_id,
        last_question=session.last_question,
        domain_keys=result.domain_keys,
        search_mode=result.search_mode,
        agent_results=agent_result_items,
    )
