from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select, update

from app.config import settings
from app.database import AsyncSessionLocal
from app.fraud_analyzer import analyze_claim, apply_rule_signals
from app.graph_engine import sync_and_enrich
from app.models import BatchRun, Claim, FraudAnalysis
from app import ml_trainer

logger = logging.getLogger(__name__)

_scheduler = AsyncIOScheduler()
_last_run_id: uuid.UUID | None = None

_SEVERITY_MAP = {"low": 1, "medium": 2, "high": 3}


async def run_batch() -> uuid.UUID:
    """Analyze all pending claims. Returns the BatchRun ID."""
    global _last_run_id

    async with AsyncSessionLocal() as session:
        run = BatchRun(status="running")
        session.add(run)
        await session.commit()
        run_id = run.id
        _last_run_id = run_id

    logger.info("Batch run %s started", run_id)
    processed = 0
    failed = 0

    # Load ML model once per batch (Phase 2: used when model file exists)
    ml_bundle = ml_trainer.load_model(settings.ml_model_path)
    if ml_bundle:
        logger.info("ML model loaded (n_samples=%d, cv_auc=%.3f)",
                    ml_bundle["metadata"].get("n_samples", 0),
                    ml_bundle["metadata"].get("cv_auc", 0))

    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Claim)
                .where(Claim.status == "pending")
                .limit(settings.batch_max_claims)
            )
            claims = result.scalars().all()

        logger.info("Batch run %s: found %d pending claims", run_id, len(claims))

        # Track (claim, analysis_id, combined_score) for graph enrichment pass
        graph_sync_rows: list[dict] = []

        for claim in claims:
            try:
                claim_data = {
                    "claim_id": claim.claim_id,
                    "claim_type": claim.claim_type,
                    "provider_name": claim.provider_name,
                    "claim_amount": float(claim.claim_amount) if claim.claim_amount else None,
                    "service_date": claim.service_date,
                    "submission_date": claim.submission_date,
                    "diagnosis_codes": claim.diagnosis_codes or [],
                    "procedure_codes": claim.procedure_codes or [],
                    "claim_narrative": claim.claim_narrative,
                }

                llm_result = await analyze_claim(claim_data)
                rule_score, rule_flags = apply_rule_signals(claim_data)

                # --- Phase 2: ML scoring (when model is available) ---
                ml_score_val: int | None = None
                if ml_bundle is not None:
                    from app.feature_extractor import extract_features
                    base_feats = extract_features(claim_data)

                    llm_flags_list = llm_result.get("flags") or []
                    rule_only = [f for f in rule_flags if not f.get("type", "").startswith("graph_")]
                    all_non_graph = llm_flags_list + rule_only
                    severities = [_SEVERITY_MAP.get(f.get("severity", "low"), 1) for f in all_non_graph]

                    predict_feats = {
                        **base_feats,
                        "llm_risk_score": llm_result["risk_score"],
                        "num_llm_flags": len(llm_flags_list),
                        "num_rule_flags": len(rule_only),
                        "max_flag_severity": max(severities, default=0),
                        "has_graph_flags": 0,  # graph enrichment hasn't run yet
                    }
                    ml_score_val = ml_trainer.predict_score(
                        ml_bundle["model"],
                        ml_bundle["metadata"]["feature_names"],
                        predict_feats,
                    )

                # --- Score blending ---
                if ml_score_val is not None:
                    # Three-way blend, normalized so weights always sum to 1
                    total_w = settings.llm_score_weight + settings.rule_score_weight + settings.ml_score_weight
                    combined = int((
                        settings.llm_score_weight * llm_result["risk_score"]
                        + settings.rule_score_weight * rule_score
                        + settings.ml_score_weight * ml_score_val
                    ) / total_w)
                else:
                    # Phase 1: two-way blend
                    combined = int(
                        settings.llm_score_weight * llm_result["risk_score"]
                        + settings.rule_score_weight * rule_score
                    )
                combined = min(combined, 100)

                risk_level = _score_to_level(combined)

                async with AsyncSessionLocal() as session:
                    analysis = FraudAnalysis(
                        claim_id=claim.id,
                        risk_score=llm_result["risk_score"],
                        risk_level=llm_result["risk_level"],
                        llm_flags=llm_result["flags"],
                        rule_flags=rule_flags,
                        combined_score=combined,
                        ml_score=ml_score_val,
                        llm_explanation=llm_result["explanation"],
                        model_version=settings.gemini_llm_model,
                    )
                    session.add(analysis)
                    await session.execute(
                        update(Claim).where(Claim.id == claim.id).values(status="analyzed")
                    )
                    await session.commit()
                    analysis_id = analysis.id

                graph_sync_rows.append({
                    "db_id": str(claim.id),
                    "analysis_id": str(analysis_id),
                    "claim_id": claim.claim_id,
                    "patient_id": claim.patient_id,
                    "provider_id": claim.provider_id,
                    "provider_name": claim.provider_name,
                    "amount": float(claim.claim_amount) if claim.claim_amount else 0,
                    "service_date": str(claim.service_date) if claim.service_date else None,
                    "diagnosis_codes": claim.diagnosis_codes or [],
                    "procedure_codes": claim.procedure_codes or [],
                    "combined_score": combined,
                    "risk_level": risk_level,
                })

                processed += 1
                ml_info = f", ml_score: {ml_score_val}" if ml_score_val is not None else ""
                logger.debug(
                    "Claim %s analyzed — combined: %d (%s)%s",
                    claim.claim_id, combined, risk_level, ml_info,
                )

            except Exception as exc:
                failed += 1
                logger.error("Failed to analyze claim %s: %s", claim.claim_id, exc)

        # --- Graph enrichment pass ---
        if graph_sync_rows:
            logger.info("Batch run %s: starting graph enrichment for %d claims", run_id, len(graph_sync_rows))
            graph_flags = await sync_and_enrich(graph_sync_rows)
            if graph_flags:
                await _apply_graph_flags(graph_flags)

        # --- Phase 2: auto-train after batch when enough new labels exist ---
        if settings.ml_auto_train:
            await _maybe_auto_train(ml_bundle)

    except Exception as exc:
        logger.error("Batch run %s failed: %s", run_id, exc)
        async with AsyncSessionLocal() as session:
            await session.execute(
                update(BatchRun)
                .where(BatchRun.id == run_id)
                .values(
                    status="failed",
                    finished_at=datetime.now(timezone.utc),
                    claims_processed=processed,
                    claims_failed=failed,
                    error=str(exc),
                )
            )
            await session.commit()
        return run_id

    async with AsyncSessionLocal() as session:
        await session.execute(
            update(BatchRun)
            .where(BatchRun.id == run_id)
            .values(
                status="completed",
                finished_at=datetime.now(timezone.utc),
                claims_processed=processed,
                claims_failed=failed,
            )
        )
        await session.commit()

    logger.info("Batch run %s complete — processed: %d, failed: %d", run_id, processed, failed)
    return run_id


async def _maybe_auto_train(current_bundle: dict | None) -> None:
    """Retrain ML model if new labels have been added since the last training."""
    try:
        async with AsyncSessionLocal() as session:
            label_count = await ml_trainer.count_usable_labels(session)

        current_n = current_bundle["metadata"].get("n_samples", 0) if current_bundle else 0

        if label_count < settings.ml_min_samples:
            logger.info(
                "Auto-train skipped: %d/%d usable labels", label_count, settings.ml_min_samples
            )
            return

        if label_count <= current_n:
            logger.info("Auto-train skipped: no new labels since last training (%d samples)", label_count)
            return

        logger.info("Auto-training ML model on %d labeled samples...", label_count)
        async with AsyncSessionLocal() as session:
            metadata = await ml_trainer.train_and_save(session, settings.ml_model_path)
        logger.info(
            "Auto-train complete — n_samples=%d, cv_auc=%.3f",
            metadata["n_samples"], metadata["cv_auc"],
        )
    except Exception as exc:
        logger.error("Auto-train failed: %s", exc)


async def _apply_graph_flags(graph_flags: dict[str, list[dict]]) -> None:
    """Append graph flags to FraudAnalysis.rule_flags for each flagged claim."""
    from sqlalchemy import select as sa_select
    async with AsyncSessionLocal() as session:
        for claim_db_id, flags in graph_flags.items():
            try:
                result = await session.execute(
                    sa_select(FraudAnalysis)
                    .where(FraudAnalysis.claim_id == claim_db_id)
                    .order_by(FraudAnalysis.analyzed_at.desc())
                    .limit(1)
                )
                analysis = result.scalar_one_or_none()
                if analysis is None:
                    continue
                existing = list(analysis.rule_flags or [])
                analysis.rule_flags = existing + flags
                # Re-derive risk level from combined score + graph boost
                graph_boost = sum(20 if f["severity"] == "high" else 10 for f in flags)
                new_combined = min(analysis.combined_score + graph_boost, 100)
                analysis.combined_score = new_combined
                analysis.risk_level = _score_to_level(new_combined)
            except Exception as exc:
                logger.error("Failed to apply graph flags to claim %s: %s", claim_db_id, exc)
        await session.commit()
    logger.info("Graph flags applied to %d claim(s)", len(graph_flags))


def _score_to_level(score: int) -> str:
    if score <= 25:
        return "low"
    if score <= 50:
        return "medium"
    if score <= 75:
        return "high"
    return "critical"


def start_scheduler() -> None:
    _scheduler.add_job(
        lambda: asyncio.ensure_future(run_batch()),
        "cron",
        hour=settings.batch_cron_hour,
        minute=settings.batch_cron_minute,
        id="nightly_fraud_batch",
        replace_existing=True,
    )
    _scheduler.start()
    logger.info(
        "Batch scheduler started — nightly at %02d:%02d",
        settings.batch_cron_hour,
        settings.batch_cron_minute,
    )


def stop_scheduler() -> None:
    if _scheduler.running:
        _scheduler.shutdown(wait=False)


async def get_last_run_status() -> dict:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(BatchRun).order_by(BatchRun.started_at.desc()).limit(1)
        )
        run = result.scalar_one_or_none()
        if run is None:
            return {
                "id": None, "status": "never_run", "started_at": None,
                "finished_at": None, "claims_processed": 0, "claims_failed": 0, "error": None,
            }
        return {
            "id": run.id,
            "status": run.status,
            "started_at": run.started_at,
            "finished_at": run.finished_at,
            "claims_processed": run.claims_processed,
            "claims_failed": run.claims_failed,
            "error": run.error,
        }
