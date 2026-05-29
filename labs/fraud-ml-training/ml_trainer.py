"""Phase 2: Standalone XGBoost fraud classifier.

This module is the main entry point for the Phase 2 sandbox.
It trains an XGBoost binary classifier on 25 synthetic Vietnamese BHYT
claims, runs stratified k-fold cross-validation, saves the model bundle,
and prints demo predictions.

No database, FastAPI server, or cloud APIs are required.

Usage
-----
    python ml_trainer.py                    # train on default sample CSV
    python ml_trainer.py --csv path/to.csv  # train on a different CSV

The saved model bundle (``models/fraud_classifier.joblib``) is compatible
with the ``load_model`` / ``predict_score`` functions used by the main
backend in ``backend/app/ml_trainer.py``.
"""
from __future__ import annotations

import argparse
import logging
import os
from datetime import datetime, timezone
from typing import Optional

import joblib
import numpy as np
from sklearn.model_selection import cross_val_score, StratifiedKFold
from xgboost import XGBClassifier

from feature_extractor import extract_features
from load_sample_data import load_records, _DEFAULT_CSV

# ── Logging ───────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────

# Fixed feature order — must be identical at train time and predict time.
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
_LABEL_MAP    = {"legitimate": 0, "confirmed_fraud": 1}

MODEL_PATH = os.path.join(os.path.dirname(__file__), "models", "fraud_classifier.joblib")


# ── Dataset builder ───────────────────────────────────────────────────────

def build_training_dataset(
    records: list[dict],
) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """Convert labeled records into (X, y, feature_names) NumPy arrays.

    Parameters
    ----------
    records:
        List of dicts as returned by load_sample_data.load_records().
        Each dict must have keys: ``claim_data``, ``analysis``, ``label``.

    Returns
    -------
    X : ndarray, shape (n_samples, 15)
    y : ndarray, shape (n_samples,)  — 0 = legitimate, 1 = confirmed_fraud
    feature_names : list[str]
    """
    X_rows: list[list[float]] = []
    y_rows: list[int]         = []

    for rec in records:
        claim_data = rec["claim_data"]
        analysis   = rec["analysis"]
        label_str  = rec["label"]

        if label_str not in _LABEL_MAP:
            logger.warning("Skipping record with unknown label '%s' (claim %s)",
                           label_str, claim_data.get("claim_id"))
            continue

        label = _LABEL_MAP[label_str]

        # ── Base features (claim content) ──────────────────────────────
        base_feats = extract_features(claim_data)

        # ── Analysis-derived features (Phase 1 output) ─────────────────
        llm_flags  = list(analysis.get("llm_flags") or [])
        rule_flags = list(analysis.get("rule_flags") or [])
        # Separate graph-based rule flags (they indicate network fraud patterns)
        rule_only   = [f for f in rule_flags if not f.get("type", "").startswith("graph_")]
        graph_flags = [f for f in rule_flags if     f.get("type", "").startswith("graph_")]
        all_non_graph = llm_flags + rule_only

        severities = [_SEVERITY_MAP.get(f.get("severity", "low"), 1) for f in all_non_graph]
        max_sev    = max(severities, default=0)

        row: list[float] = [
            base_feats.get("claim_amount")         or 0,
            base_feats.get("num_diagnosis_codes",   0),
            base_feats.get("num_procedure_codes",   0),
            base_feats.get("days_to_submission")   or 0,
            base_feats.get("narrative_length",      0),
            base_feats.get("narrative_word_count",  0),
            base_feats.get("claim_type_inpatient",  0),
            base_feats.get("claim_type_outpatient", 0),
            base_feats.get("claim_type_pharmacy",   0),
            base_feats.get("claim_type_lab",        0),
            analysis.get("risk_score")             or 0,   # llm_risk_score
            len(llm_flags),                                 # num_llm_flags
            len(rule_only),                                 # num_rule_flags
            max_sev,                                        # max_flag_severity
            int(len(graph_flags) > 0),                     # has_graph_flags
        ]
        X_rows.append(row)
        y_rows.append(label)

    X = np.array(X_rows, dtype=float)
    y = np.array(y_rows, dtype=int)
    return X, y, FEATURE_NAMES


# ── Model training ────────────────────────────────────────────────────────

def train_model(X: np.ndarray, y: np.ndarray) -> tuple[XGBClassifier, float]:
    """Train XGBoost with stratified k-fold cross-validation.

    Returns
    -------
    model   : fitted XGBClassifier
    cv_auc  : mean ROC-AUC across folds (0.0 if only one class present)
    """
    model = XGBClassifier(
        n_estimators=100,
        max_depth=4,
        learning_rate=0.1,
        subsample=0.8,
        colsample_bytree=0.8,
        eval_metric="logloss",
        random_state=42,
        verbosity=0,
    )

    unique_classes = np.unique(y)
    if len(unique_classes) < 2:
        logger.warning("Only one class in training data — skipping cross-validation.")
        model.fit(X, y)
        return model, 0.0

    # Use the smaller class count to cap folds (avoids stratification errors
    # on small datasets like the 25-sample sandbox).
    min_class_count = int(np.bincount(y).min())
    cv_folds = max(2, min(5, min_class_count))

    logger.info(
        "Running %d-fold stratified CV on %d samples, %d features …",
        cv_folds, len(y), X.shape[1],
    )
    cv = StratifiedKFold(n_splits=cv_folds, shuffle=True, random_state=42)
    scores = cross_val_score(model, X, y, cv=cv, scoring="roc_auc")

    logger.info("  Per-fold AUC : %s", "  ".join(f"{s:.3f}" for s in scores))
    logger.info("  Mean ± std   : %.4f ± %.4f", scores.mean(), scores.std())

    # Final fit on full dataset
    model.fit(X, y)
    return model, float(scores.mean())


# ── Persistence ───────────────────────────────────────────────────────────

def save_model(model: XGBClassifier, path: str, metadata: dict) -> None:
    """Persist the model + metadata bundle to disk via joblib."""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    joblib.dump({"model": model, "metadata": metadata}, path)
    logger.info(
        "Model saved → %s  (n_samples=%d, cv_auc=%.4f)",
        path,
        metadata.get("n_samples", 0),
        metadata.get("cv_auc", 0),
    )


def load_model(path: str) -> Optional[dict]:
    """Load a previously saved model bundle.  Returns None if not found."""
    if not os.path.exists(path):
        return None
    try:
        return joblib.load(path)
    except Exception as exc:
        logger.warning("Failed to load model from %s: %s", path, exc)
        return None


# ── Inference helpers ─────────────────────────────────────────────────────

def predict_score(model: XGBClassifier, features_dict: dict) -> int:
    """Return fraud probability as a 0–100 integer for one claim.

    Parameters
    ----------
    model         : fitted XGBClassifier (or loaded from bundle["model"])
    features_dict : dict mapping FEATURE_NAMES → numeric value
    """
    try:
        row = [features_dict.get(name) or 0 for name in FEATURE_NAMES]
        X   = np.array([row], dtype=float)
        prob = model.predict_proba(X)[0][1]
        return int(round(prob * 100))
    except Exception as exc:
        logger.warning("Prediction failed: %s", exc)
        return 0


def get_feature_importances(model: XGBClassifier) -> list[dict]:
    """Return feature importances sorted by importance (descending)."""
    pairs = sorted(
        zip(FEATURE_NAMES, model.feature_importances_),
        key=lambda x: x[1],
        reverse=True,
    )
    return [{"name": n, "importance": round(float(imp), 4)} for n, imp in pairs]


# ── Full pipeline ─────────────────────────────────────────────────────────

def run_training_pipeline(
    csv_path: str = _DEFAULT_CSV,
    model_path: str = MODEL_PATH,
) -> dict:
    """End-to-end: load data → features → train → save.  Returns metadata dict."""
    records = load_records(csv_path)
    logger.info("Loaded %d labeled records from %s", len(records), csv_path)

    X, y, feature_names = build_training_dataset(records)
    n_samples = len(y)

    class_counts = {str(k): int(v) for k, v in zip(*np.unique(y, return_counts=True))}
    logger.info(
        "Dataset: %d samples · %d features · class counts: %s",
        n_samples, X.shape[1], class_counts,
    )

    if n_samples < 2:
        raise ValueError(f"Need ≥ 2 labeled samples; got {n_samples}")

    model, cv_auc = train_model(X, y)

    importances = get_feature_importances(model)
    logger.info("Top 5 features by importance:")
    for feat in importances[:5]:
        logger.info("  %-35s %.4f", feat["name"], feat["importance"])

    metadata = {
        "n_samples":          n_samples,
        "cv_auc":             round(cv_auc, 4),
        "feature_names":      feature_names,
        "class_counts":       class_counts,
        "feature_importances": importances,
        "trained_at":         datetime.now(timezone.utc).isoformat(),
    }
    save_model(model, model_path, metadata)
    return metadata


# ── Demo predictions ──────────────────────────────────────────────────────

def _run_demo_predictions(model_bundle: dict, records: list[dict]) -> None:
    """Print fraud scores for every record alongside the true label."""
    model = model_bundle["model"]

    print("\n" + "─" * 72)
    print(f"{'Claim':<10} {'True label':<20} {'Score':>6}  {'Verdict'}")
    print("─" * 72)

    for rec in records:
        cd       = rec["claim_data"]
        analysis = rec["analysis"]
        true_lbl = rec["label"]

        base_feats = extract_features(cd)
        llm_flags  = analysis.get("llm_flags") or []
        rule_flags = analysis.get("rule_flags") or []
        rule_only  = [f for f in rule_flags if not f.get("type", "").startswith("graph_")]
        graph_flags= [f for f in rule_flags if     f.get("type", "").startswith("graph_")]
        all_non_graph = llm_flags + rule_only
        severities = [_SEVERITY_MAP.get(f.get("severity", "low"), 1) for f in all_non_graph]

        features_dict = {
            **base_feats,
            "llm_risk_score":   analysis.get("risk_score") or 0,
            "num_llm_flags":    len(llm_flags),
            "num_rule_flags":   len(rule_only),
            "max_flag_severity":max(severities, default=0),
            "has_graph_flags":  int(len(graph_flags) > 0),
        }

        score   = predict_score(model, features_dict)
        verdict = "FRAUD" if score >= 50 else "OK"
        marker  = " ✓" if (verdict == "FRAUD") == (true_lbl == "confirmed_fraud") else " ✗"

        print(
            f"{cd['claim_id']:<10} {true_lbl:<20} {score:>5}%  {verdict}{marker}"
        )
    print("─" * 72)


# ── Entry point ───────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Phase 2 XGBoost fraud trainer")
    p.add_argument("--csv",   default=_DEFAULT_CSV, help="Path to claims CSV")
    p.add_argument("--model", default=MODEL_PATH,   help="Output path for model bundle")
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()

    logger.info("══════════════════════════════════════════")
    logger.info("  Phase 2 XGBoost Fraud Training Pipeline ")
    logger.info("══════════════════════════════════════════")

    metadata = run_training_pipeline(csv_path=args.csv, model_path=args.model)

    logger.info("\nSummary")
    logger.info("  Samples  : %d", metadata["n_samples"])
    logger.info("  CV AUC   : %.4f", metadata["cv_auc"])
    logger.info("  Classes  : %s", metadata["class_counts"])
    logger.info("  Saved to : %s", args.model)

    # Demo predictions on the full sample set
    bundle  = load_model(args.model)
    records = load_records(args.csv)
    if bundle:
        _run_demo_predictions(bundle, records)
