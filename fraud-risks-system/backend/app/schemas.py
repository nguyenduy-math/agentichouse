from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel


# ---------- Shared ----------

class FraudFlag(BaseModel):
    type: str
    description: str
    severity: Literal["low", "medium", "high"]


# ---------- Claims ----------

class ClaimSummary(BaseModel):
    id: uuid.UUID
    claim_id: str
    patient_id: str | None
    provider_name: str | None
    claim_amount: float | None
    service_date: date | None
    claim_type: str | None
    status: str
    combined_score: int | None = None
    risk_level: str | None = None

    model_config = {"from_attributes": True}


class ClaimDetail(BaseModel):
    id: uuid.UUID
    claim_id: str
    patient_id: str | None
    provider_id: str | None
    provider_name: str | None
    diagnosis_codes: list[str] | None
    procedure_codes: list[str] | None
    claim_amount: float | None
    service_date: date | None
    submission_date: date | None
    claim_narrative: str | None
    claim_type: str | None
    status: str
    created_at: datetime
    latest_analysis: AnalysisSummary | None = None

    model_config = {"from_attributes": True}


class ClaimListResponse(BaseModel):
    items: list[ClaimSummary]
    total: int
    page: int
    page_size: int


# ---------- Analysis ----------

class AnalysisSummary(BaseModel):
    id: uuid.UUID
    risk_score: int
    risk_level: str
    combined_score: int
    llm_flags: list[FraudFlag] | None
    rule_flags: list[FraudFlag] | None
    llm_explanation: str | None
    model_version: str | None
    analyzed_at: datetime

    model_config = {"from_attributes": True}


# ---------- Review ----------

class DecisionRequest(BaseModel):
    decision: Literal["legitimate", "suspicious", "confirmed_fraud"]
    notes: str | None = None
    reviewer_id: str = "investigator"


class ReviewResponse(BaseModel):
    id: uuid.UUID
    claim_id: uuid.UUID
    decision: str
    notes: str | None
    reviewer_id: str
    reviewed_at: datetime

    model_config = {"from_attributes": True}


class ReviewQueueItem(BaseModel):
    id: uuid.UUID
    claim_id: str
    provider_name: str | None
    claim_amount: float | None
    service_date: date | None
    claim_type: str | None
    combined_score: int
    risk_level: str
    llm_explanation: str | None
    top_flags: list[FraudFlag]
    reviewed: bool
    network_risk: bool = False

    model_config = {"from_attributes": True}


class ReviewQueueResponse(BaseModel):
    items: list[ReviewQueueItem]
    total: int
    page: int
    page_size: int


class ReviewStats(BaseModel):
    total_claims: int
    total_analyzed: int
    total_reviewed: int
    by_risk_level: dict[str, int]
    by_decision: dict[str, int]
    label_coverage_pct: float


# ---------- Batch ----------

class BatchStatusResponse(BaseModel):
    id: uuid.UUID | None
    status: str
    started_at: datetime | None
    finished_at: datetime | None
    claims_processed: int
    claims_failed: int
    error: str | None

    model_config = {"from_attributes": True}


# ---------- Health ----------

class HealthResponse(BaseModel):
    status: str
    db_connected: bool
    llm_model: str
