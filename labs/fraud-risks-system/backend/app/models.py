from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.database import Base


class Claim(Base):
    __tablename__ = "claims"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    claim_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    patient_id: Mapped[str | None] = mapped_column(String(100))
    provider_id: Mapped[str | None] = mapped_column(String(100), index=True)
    provider_name: Mapped[str | None] = mapped_column(String(255))
    diagnosis_codes: Mapped[list | None] = mapped_column(JSONB)
    procedure_codes: Mapped[list | None] = mapped_column(JSONB)
    claim_amount: Mapped[float | None] = mapped_column(Numeric(12, 2))
    service_date: Mapped[date | None] = mapped_column(Date)
    submission_date: Mapped[date | None] = mapped_column(Date)
    claim_narrative: Mapped[str | None] = mapped_column(Text)
    claim_type: Mapped[str | None] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    raw_csv_row: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    analyses: Mapped[list[FraudAnalysis]] = relationship(back_populates="claim", lazy="raise")
    reviews: Mapped[list[Review]] = relationship(back_populates="claim", lazy="raise")


class FraudAnalysis(Base):
    __tablename__ = "fraud_analyses"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    claim_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("claims.id"), nullable=False, index=True)
    risk_score: Mapped[int] = mapped_column(Integer)
    risk_level: Mapped[str] = mapped_column(String(20))
    llm_flags: Mapped[list | None] = mapped_column(JSONB)
    rule_flags: Mapped[list | None] = mapped_column(JSONB)
    combined_score: Mapped[int] = mapped_column(Integer)
    ml_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    llm_explanation: Mapped[str | None] = mapped_column(Text)
    model_version: Mapped[str | None] = mapped_column(String(100))
    analyzed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    claim: Mapped[Claim] = relationship(back_populates="analyses", lazy="raise")
    reviews: Mapped[list[Review]] = relationship(back_populates="analysis", lazy="raise")


class Review(Base):
    __tablename__ = "reviews"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    claim_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("claims.id"), nullable=False, index=True)
    analysis_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("fraud_analyses.id"))
    reviewer_id: Mapped[str] = mapped_column(String(100), default="investigator")
    decision: Mapped[str] = mapped_column(String(30))
    notes: Mapped[str | None] = mapped_column(Text)
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    claim: Mapped[Claim] = relationship(back_populates="reviews", lazy="raise")
    analysis: Mapped[FraudAnalysis | None] = relationship(back_populates="reviews", lazy="raise")


class BatchRun(Base):
    __tablename__ = "batch_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    claims_processed: Mapped[int] = mapped_column(Integer, default=0)
    claims_failed: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="running")
    error: Mapped[str | None] = mapped_column(Text)
