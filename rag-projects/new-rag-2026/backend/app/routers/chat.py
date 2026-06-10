"""
Chat router -- main conversation endpoint.
"""
from __future__ import annotations

import asyncio
import logging
import os

from fastapi import APIRouter, HTTPException, Request
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

    try:
        result = await orchestrator.run(
            question=body.message,
            session_history=session_history,
            config=config,
        )
    except Exception as exc:
        logger.error("Orchestrator error for session %s: %s", body.session_id, exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Processing error: {exc}")

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
