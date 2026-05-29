from __future__ import annotations

import csv
import io
import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models import Claim, FraudAnalysis
from app.schemas import ClaimDetail, ClaimListResponse, ClaimSummary, AnalysisSummary

router = APIRouter(prefix="/claims", tags=["claims"])

REQUIRED_COLUMNS = {"claim_id"}
DATE_FIELDS = {"service_date", "submission_date"}
FLOAT_FIELDS = {"claim_amount"}
JSON_FIELDS = {"diagnosis_codes", "procedure_codes"}


@router.post("/upload")
async def upload_claims(
    file: UploadFile,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    if not file.filename or not file.filename.endswith(".csv"):
        raise HTTPException(400, "Only CSV files are accepted")

    content = await file.read()
    text = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    rows = list(reader)

    if not rows:
        raise HTTPException(400, "CSV file is empty")

    fieldnames = set(reader.fieldnames or [])
    missing = REQUIRED_COLUMNS - fieldnames
    if missing:
        raise HTTPException(400, f"CSV missing required columns: {missing}")

    inserted = 0
    skipped = 0

    for row in rows:
        claim_id = row.get("claim_id", "").strip()
        if not claim_id:
            skipped += 1
            continue

        claim = Claim(
            claim_id=claim_id,
            patient_id=_str(row, "patient_id"),
            provider_id=_str(row, "provider_id"),
            provider_name=_str(row, "provider_name"),
            claim_amount=_float(row, "claim_amount"),
            service_date=_date(row, "service_date"),
            submission_date=_date(row, "submission_date"),
            claim_narrative=_str(row, "claim_narrative"),
            claim_type=_str(row, "claim_type"),
            diagnosis_codes=_codes(row, "diagnosis_codes"),
            procedure_codes=_codes(row, "procedure_codes"),
            status="pending",
            raw_csv_row=dict(row),
        )
        db.add(claim)
        inserted += 1

    await db.commit()
    return {"inserted": inserted, "skipped": skipped, "total_rows": len(rows)}


@router.get("", response_model=ClaimListResponse)
async def list_claims(
    db: Annotated[AsyncSession, Depends(get_db)],
    status: str | None = None,
    risk_level: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    query = select(Claim)
    if status:
        query = query.where(Claim.status == status)

    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_result.scalar_one()

    query = query.order_by(Claim.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query.options(selectinload(Claim.analyses)))
    claims = result.scalars().all()

    items = []
    for claim in claims:
        latest = _latest_analysis(claim.analyses)
        if risk_level and (not latest or latest.risk_level != risk_level):
            continue
        items.append(ClaimSummary(
            id=claim.id,
            claim_id=claim.claim_id,
            patient_id=claim.patient_id,
            provider_name=claim.provider_name,
            claim_amount=float(claim.claim_amount) if claim.claim_amount else None,
            service_date=claim.service_date,
            claim_type=claim.claim_type,
            status=claim.status,
            combined_score=latest.combined_score if latest else None,
            risk_level=latest.risk_level if latest else None,
        ))

    return ClaimListResponse(items=items, total=total, page=page, page_size=page_size)


@router.get("/{claim_id}", response_model=ClaimDetail)
async def get_claim(
    claim_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(
        select(Claim)
        .where(Claim.id == claim_id)
        .options(selectinload(Claim.analyses))
    )
    claim = result.scalar_one_or_none()
    if claim is None:
        raise HTTPException(404, "Claim not found")

    latest = _latest_analysis(claim.analyses)
    return ClaimDetail(
        id=claim.id,
        claim_id=claim.claim_id,
        patient_id=claim.patient_id,
        provider_id=claim.provider_id,
        provider_name=claim.provider_name,
        diagnosis_codes=claim.diagnosis_codes,
        procedure_codes=claim.procedure_codes,
        claim_amount=float(claim.claim_amount) if claim.claim_amount else None,
        service_date=claim.service_date,
        submission_date=claim.submission_date,
        claim_narrative=claim.claim_narrative,
        claim_type=claim.claim_type,
        status=claim.status,
        created_at=claim.created_at,
        latest_analysis=AnalysisSummary.model_validate(latest) if latest else None,
    )


# ---- helpers ----

def _latest_analysis(analyses) -> FraudAnalysis | None:
    if not analyses:
        return None
    return max(analyses, key=lambda a: a.analyzed_at)


def _str(row: dict, key: str) -> str | None:
    v = row.get(key, "").strip()
    return v or None


def _float(row: dict, key: str) -> float | None:
    v = row.get(key, "").strip()
    try:
        return float(v) if v else None
    except ValueError:
        return None


def _date(row: dict, key: str) -> date | None:
    v = row.get(key, "").strip()
    if not v:
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y"):
        try:
            from datetime import datetime
            return datetime.strptime(v, fmt).date()
        except ValueError:
            continue
    return None


def _codes(row: dict, key: str) -> list[str] | None:
    v = row.get(key, "").strip()
    if not v:
        return None
    return [c.strip() for c in v.split("|") if c.strip()]
