"""Phase 2: XGBoost fraud classifier — training, persistence, and scoring."""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Optional

import joblib
import numpy as np
from sklearn.model_selection import cross_val_score
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from xgboost import XGBClassifier

from app.feature_extractor import extract_features
from app.models import Claim, FraudAnalysis, Review

logger = logging.getLogger(__name__)

# Fixed feature order — must match across train and predict
FEATURE_NAMES: list[str] = [
    "claim_amount",
    "num_diagnosis_codes",
    "num_procedure_codes",
    "days_to_submission",
    "narrative_length",
    "narrative_word_count",
    "claim_type_inpatient",
    "claim_type_outpatient",
    "claim_type_pharmacy",
    "claim_type_lab",
    "llm_risk_score",
    "num_llm_flags",
    "num_rule_flags",
    "max_flag_severity",
    "has_graph_flags",
]

_SEVERITY_MAP = {"low": 1, "medium": 2, "high": 3}
_LABEL_MAP = {"legitimate": 0, "confirmed_fraud": 1}


async def count_usable_labels(session: AsyncSession) -> int:
    """Count reviews labeled legitimate or confirmed_fraud (usable for training)."""
    result = await session.execute(
        select(func.count(Review.id))
        .where(Review.decision.in_(["legitimate", "confirmed_fraud"]))
        .where(Review.analysis_id.isnot(None))
    )
    return result.scalar_one()


async def build_training_dataset(
    session: AsyncSession,
) -> tuple[np.ndarray, np.ndarray, list[str], int]:
    """Query labeled reviews and return (X, y, feature_names, n_samples)."""
    result = await session.execute(
        select(Review, FraudAnalysis, Claim)
        .join(FraudAnalysis, FraudAnalysis.id == Review.analysis_id)
        .join(Claim, Claim.id == Review.claim_id)
        .where(Review.decision.in_(["legitimate", "confirmed_fraud"]))
        .where(Review.analysis_id.isnot(None))
    )
    rows = result.all()

    X_rows: list[list[float]] = []
    y_rows: list[int] = []

    for review, analysis, claim in rows:
        label = _LABEL_MAP[review.decision]
        claim_data = {
            "claim_amount": float(claim.claim_amount) if claim.claim_amount else None,
            "service_date": claim.service_date,
            "submission_date": claim.submission_date,
            "diagnosis_codes": claim.diagnosis_codes or [],
            "procedure_codes": claim.procedure_codes or [],
            "claim_narrative": claim.claim_narrative,
            "claim_type": claim.claim_type,
        }
        base_feats = extract_features(claim_data)

        llm_flags = list(analysis.llm_flags or [])
        rule_flags = list(analysis.rule_flags or [])
        rule_only = [f for f in rule_flags if not f.get("type", "").startswith("graph_")]
        graph_flags = [f for f in rule_flags if f.get("type", "").startswith("graph_")]
        all_non_graph = llm_flags + rule_only

        severities = [_SEVERITY_MAP.get(f.get("severity", "low"), 1) for f in all_non_graph]
        max_sev = max(severities, default=0)

        row = [
            base_feats.get("claim_amount") or 0,
            base_feats.get("num_diagnosis_codes", 0),
            base_feats.get("num_procedure_codes", 0),
            base_feats.get("days_to_submission") or 0,
            base_feats.get("narrative_length", 0),
            base_feats.get("narrative_word_count", 0),
            base_feats.get("claim_type_inpatient", 0),
            base_feats.get("claim_type_outpatient", 0),
            base_feats.get("claim_type_pharmacy", 0),
            base_feats.get("claim_type_lab", 0),
            analysis.risk_score or 0,
            len(llm_flags),
            len(rule_only),
            max_sev,
            int(len(graph_flags) > 0),
        ]
        X_rows.append(row)
        y_rows.append(label)

    X = np.array(X_rows, dtype=float)
    y = np.array(y_rows, dtype=int)
    return X, y, FEATURE_NAMES, len(y_rows)


def _train_model_sync(X: np.ndarray, y: np.ndarray) -> tuple[XGBClassifier, float]:
    """Synchronous XGBoost training. Returns (model, cv_auc)."""
    model = XGBClassifier(
        n_estimators=100,
        max_depth=4,
        learning_rate=0.1,
        random_state=42,
    )

    unique_classes = np.unique(y)
    if len(unique_classes) < 2:
        # Only one class available — fit without CV
        model.fit(X, y)
        return model, 0.0

    cv_folds = min(5, int(np.bincount(y).min()))
    cv_folds = max(cv_folds, 2)
    scores = cross_val_score(model, X, y, cv=cv_folds, scoring="roc_auc")
    model.fit(X, y)
    return model, float(scores.mean())


def save_model(model: XGBClassifier, path: str, metadata: dict) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    joblib.dump({"model": model, "metadata": metadata}, path)
    logger.info(
        "ML model saved to %s (n_samples=%d, cv_auc=%.3f)",
        path, metadata.get("n_samples", 0), metadata.get("cv_auc", 0),
    )


def load_model(path: str) -> Optional[dict]:
    """Load model bundle or return None if file is absent or corrupt."""
    if not os.path.exists(path):
        return None
    try:
        return joblib.load(path)
    except Exception as exc:
        logger.warning("Failed to load ML model from %s: %s", path, exc)
        return None


def predict_score(model: XGBClassifier, feature_names: list[str], features_dict: dict) -> int:
    """Return fraud probability as a 0-100 integer score."""
    try:
        row = [features_dict.get(name) or 0 for name in feature_names]
        X = np.array([row], dtype=float)
        prob = model.predict_proba(X)[0][1]
        return int(round(prob * 100))
    except Exception as exc:
        logger.warning("ML prediction failed: %s", exc)
        return 0


def get_feature_importances(model: XGBClassifier, feature_names: list[str]) -> list[dict]:
    importances = model.feature_importances_
    pairs = sorted(zip(feature_names, importances), key=lambda x: x[1], reverse=True)
    return [{"name": name, "importance": round(float(imp), 4)} for name, imp in pairs]


async def train_and_save(session: AsyncSession, model_path: str) -> dict:
    """Full pipeline: build dataset → train → save. Returns metadata dict."""
    X, y, feature_names, n_samples = await build_training_dataset(session)
    if n_samples < 2:
        raise ValueError(f"Need at least 2 labeled samples, got {n_samples}")

    # Run synchronous training in thread pool to avoid blocking the event loop
    model, cv_auc = await asyncio.to_thread(_train_model_sync, X, y)

    metadata = {
        "n_samples": n_samples,
        "cv_auc": round(cv_auc, 4),
        "feature_names": feature_names,
        "trained_at": datetime.now(timezone.utc).isoformat(),
    }
    save_model(model, model_path, metadata)
    return metadata
