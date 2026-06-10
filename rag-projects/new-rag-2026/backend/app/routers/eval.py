"""
Eval router — Ragas Evaluation Report endpoints.

All routes under /api/v1/eval.
Optional admin-key protection via EVAL_ADMIN_KEY env var.
"""
from __future__ import annotations

import csv
import io
import os
from statistics import mean

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.models.eval import (
    EvalRunListResponse,
    EvalRunRequest,
    EvalRunResult,
    EvalRunStartResponse,
    EvalRunSummary,
    EvalTurnScore,
    SessionListResponse,
    SessionSummary,
    SessionTurnsResponse,
    EvalTurn,
)

router = APIRouter(prefix="/api/v1/eval", tags=["eval"])

METRIC_NAMES = [
    "faithfulness",
    "answer_relevancy",
    "context_precision",
    "context_recall",
    "answer_correctness",
]

_ADMIN_KEY = os.environ.get("EVAL_ADMIN_KEY", "")


def _check_admin_key(x_admin_key: str | None = Header(default=None)) -> None:
    """If EVAL_ADMIN_KEY is set, verify the header matches."""
    if _ADMIN_KEY and x_admin_key != _ADMIN_KEY:
        raise HTTPException(status_code=403, detail="Invalid or missing X-Admin-Key header")


# ── Sessions ──────────────────────────────────────────────────────────────────

@router.get("/sessions", response_model=SessionListResponse)
async def list_sessions(
    request: Request,
    limit: int = 50,
    offset: int = 0,
    _: None = Depends(_check_admin_key),
) -> SessionListResponse:
    store = request.app.state.history_store
    sessions_raw = await store.list_sessions(limit=limit, offset=offset)
    total = await store.count_sessions()
    return SessionListResponse(
        sessions=[SessionSummary(**s) for s in sessions_raw],
        total=total,
    )


@router.get("/sessions/{session_id}/turns", response_model=SessionTurnsResponse)
async def get_session_turns(
    session_id: str,
    request: Request,
    _: None = Depends(_check_admin_key),
) -> SessionTurnsResponse:
    store = request.app.state.history_store
    turns_raw = await store.get_session_turns(session_id)
    return SessionTurnsResponse(
        session_id=session_id,
        turns=[EvalTurn(**t) for t in turns_raw],
    )


# ── Eval runs ─────────────────────────────────────────────────────────────────

@router.post("/run", response_model=EvalRunStartResponse, status_code=202)
async def start_eval_run(
    body: EvalRunRequest,
    request: Request,
    _: None = Depends(_check_admin_key),
) -> EvalRunStartResponse:
    eval_svc = request.app.state.eval_service
    run_id = await eval_svc.start_run(
        turn_ids=body.turn_ids,
        judge_provider=body.judge_provider,
        judge_model=body.judge_model,
        reference_answers=body.reference_answers,
    )
    return EvalRunStartResponse(
        run_id=run_id,
        status="pending",
        turn_count=len(body.turn_ids),
    )


@router.get("/runs", response_model=EvalRunListResponse)
async def list_runs(
    request: Request,
    limit: int = 20,
    _: None = Depends(_check_admin_key),
) -> EvalRunListResponse:
    store = request.app.state.history_store
    runs_raw = await store.list_runs(limit=limit)
    return EvalRunListResponse(
        runs=[EvalRunSummary(**r) for r in runs_raw],
    )


@router.get("/runs/{run_id}", response_model=EvalRunResult)
async def get_run_result(
    run_id: str,
    request: Request,
    _: None = Depends(_check_admin_key),
) -> EvalRunResult:
    store = request.app.state.history_store
    run = await store.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")

    scores_raw = await store.get_run_scores(run_id)
    scores = [
        EvalTurnScore(
            turn_id=r["turn_id"],
            question=r["question"],
            answer=r["answer"],
            domain_keys=r.get("domain_keys") or [],
            query_type=r.get("query_type") or "",
            faithfulness=r.get("faithfulness"),
            answer_relevancy=r.get("answer_relevancy"),
            context_precision=r.get("context_precision"),
            context_recall=r.get("context_recall"),
            answer_correctness=r.get("answer_correctness"),
            reference_answer=r.get("reference_answer") or "",
        )
        for r in scores_raw
    ]

    averages: dict[str, float | None] = {}
    for metric in METRIC_NAMES:
        vals = [getattr(s, metric) for s in scores if getattr(s, metric) is not None]
        averages[metric] = round(mean(vals), 4) if vals else None

    return EvalRunResult(
        run_id=run["run_id"],
        status=run["status"],
        judge_provider=run["judge_provider"],
        judge_model=run["judge_model"],
        created_at=run["created_at"],
        turn_count=run["turn_count"],
        error=run.get("error"),
        scores=scores,
        averages=averages,
    )


@router.get("/runs/{run_id}/export")
async def export_run_csv(
    run_id: str,
    request: Request,
    _: None = Depends(_check_admin_key),
) -> StreamingResponse:
    store = request.app.state.history_store
    run = await store.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")

    scores_raw = await store.get_run_scores(run_id)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "turn_id", "question", "answer", "domain_keys", "query_type",
        "faithfulness", "answer_relevancy", "context_precision",
        "context_recall", "answer_correctness", "reference_answer",
    ])
    for r in scores_raw:
        writer.writerow([
            r.get("turn_id", ""),
            r.get("question", ""),
            r.get("answer", ""),
            ",".join(r.get("domain_keys") or []),
            r.get("query_type", ""),
            r.get("faithfulness", ""),
            r.get("answer_relevancy", ""),
            r.get("context_precision", ""),
            r.get("context_recall", ""),
            r.get("answer_correctness", ""),
            r.get("reference_answer", ""),
        ])

    output.seek(0)
    filename = f"eval_run_{run_id[:8]}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
