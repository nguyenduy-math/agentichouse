"""POST /query — one-shot RAG question answering (no conversation history)."""

from __future__ import annotations

from fastapi import APIRouter
from lightrag import QueryParam

from app.domain import DOMAIN_USER_PROMPT
from app.rag_engine import get_rag
from app.schemas import QueryRequest, QueryResponse

router = APIRouter(tags=["query"])


@router.post("/query", response_model=QueryResponse)
async def query(request: QueryRequest) -> QueryResponse:
    rag = get_rag()

    param = QueryParam(
        mode=request.mode,
        only_need_context=request.only_need_context,
        user_prompt=DOMAIN_USER_PROMPT,
    )
    if request.top_k is not None:
        param.top_k = request.top_k

    answer = str(await rag.aquery(request.question, param=param))
    return QueryResponse(answer=answer, mode=request.mode)
