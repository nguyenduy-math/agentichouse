from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models import Claim, FraudAnalysis, Review
from app.schemas import (
    DecisionRequest,
    FraudFlag,
    ReviewQueueItem,
    ReviewQueueResponse,
    ReviewResponse,
    ReviewStats,
)

router = APIRouter(prefix="/review", tags=["review"])


@router.get("/queue", response_model=ReviewQueueResponse)
async def review_queue(
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    min_score: int = Query(0, ge=0, le=100),
):
    """Return analyzed claims sorted by risk score descending."""
    base = (
        select(Claim, FraudAnalysis)
        .join(FraudAnalysis, FraudAnalysis.claim_id == Claim.id)
        .where(Claim.status.in_(["analyzed", "reviewed"]))
        .where(FraudAnalysis.combined_score >= min_score)
        .order_by(FraudAnalysis.combined_score.desc(), FraudAnalysis.analyzed_at.desc())
    )

    count_result = await db.execute(select(func.count()).select_from(base.subquery()))
    total = count_result.scalar_one()

    result = await db.execute(
        base.offset((page - 1) * page_size).limit(page_size)
        .options(selectinload(Claim.reviews))
    )
    rows = result.all()

    items = []
    for claim, analysis in rows:
        reviewed = any(r for r in (claim.reviews or []))
        rule_flags = list(analysis.rule_flags or [])
        all_flags = list(analysis.llm_flags or []) + rule_flags
        top_flags = [FraudFlag(**f) for f in all_flags[:3]]
        network_risk = any(f.get("type", "").startswith("graph_") for f in rule_flags)

        items.append(ReviewQueueItem(
            id=claim.id,
            claim_id=claim.claim_id,
            provider_name=claim.provider_name,
            claim_amount=float(claim.claim_amount) if claim.claim_amount else None,
            service_date=claim.service_date,
            claim_type=claim.claim_type,
            combined_score=analysis.combined_score,
            risk_level=analysis.risk_level,
            ml_score=analysis.ml_score,
            llm_explanation=analysis.llm_explanation,
            top_flags=top_flags,
            reviewed=reviewed,
            network_risk=network_risk,
        ))

    return ReviewQueueResponse(items=items, total=total, page=page, page_size=page_size)


@router.post("/{claim_id}/decision", response_model=ReviewResponse)
async def submit_decision(
    claim_id: uuid.UUID,
    body: DecisionRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    claim_result = await db.execute(
        select(Claim).where(Claim.id == claim_id).options(selectinload(Claim.analyses))
    )
    claim = claim_result.scalar_one_or_none()
    if claim is None:
        raise HTTPException(404, "Claim not found")
    if claim.status == "pending":
        raise HTTPException(400, "Claim has not been analyzed yet — run batch first")

    latest_analysis = _latest_analysis(claim.analyses)

    review = Review(
        claim_id=claim.id,
        analysis_id=latest_analysis.id if latest_analysis else None,
        reviewer_id=body.reviewer_id,
        decision=body.decision,
        notes=body.notes,
    )
    db.add(review)
    claim.status = "reviewed"
    await db.commit()
    await db.refresh(review)

    return ReviewResponse(
        id=review.id,
        claim_id=review.claim_id,
        decision=review.decision,
        notes=review.notes,
        reviewer_id=review.reviewer_id,
        reviewed_at=review.reviewed_at,
    )


@router.get("/stats", response_model=ReviewStats)
async def review_stats(db: Annotated[AsyncSession, Depends(get_db)]):
    total_claims = (await db.execute(select(func.count(Claim.id)))).scalar_one()
    total_analyzed = (await db.execute(
        select(func.count(Claim.id)).where(Claim.status.in_(["analyzed", "reviewed"]))
    )).scalar_one()
    total_reviewed = (await db.execute(
        select(func.count(Claim.id)).where(Claim.status == "reviewed")
    )).scalar_one()

    level_rows = (await db.execute(
        select(FraudAnalysis.risk_level, func.count()).group_by(FraudAnalysis.risk_level)
    )).all()
    by_risk_level = {row[0]: row[1] for row in level_rows}

    decision_rows = (await db.execute(
        select(Review.decision, func.count()).group_by(Review.decision)
    )).all()
    by_decision = {row[0]: row[1] for row in decision_rows}

    coverage = round(total_reviewed / total_analyzed * 100, 1) if total_analyzed > 0 else 0.0

    return ReviewStats(
        total_claims=total_claims,
        total_analyzed=total_analyzed,
        total_reviewed=total_reviewed,
        by_risk_level=by_risk_level,
        by_decision=by_decision,
        label_coverage_pct=coverage,
    )


def _latest_analysis(analyses) -> FraudAnalysis | None:
    if not analyses:
        return None
    return max(analyses, key=lambda a: a.analyzed_at)
