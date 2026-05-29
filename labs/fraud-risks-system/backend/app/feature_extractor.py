"""Phase 2 preparation: extract structured ML features from claim records.

These features are not used in Phase 1 scoring. They accumulate alongside
labeled reviews so that a classifier (XGBoost/LightGBM) can be trained once
~500+ labeled examples exist.
"""
from __future__ import annotations

from datetime import date


def extract_features(claim_data: dict, provider_stats: dict | None = None) -> dict:
    """Return a flat feature dict ready for ML training."""
    features: dict = {}

    amount = float(claim_data.get("claim_amount") or 0)
    features["claim_amount"] = amount

    diag_codes = claim_data.get("diagnosis_codes") or []
    proc_codes = claim_data.get("procedure_codes") or []
    features["num_diagnosis_codes"] = len(diag_codes)
    features["num_procedure_codes"] = len(proc_codes)

    service_date = claim_data.get("service_date")
    submission_date = claim_data.get("submission_date")
    features["days_to_submission"] = _days_between(service_date, submission_date)

    narrative = claim_data.get("claim_narrative") or ""
    features["narrative_length"] = len(narrative)
    features["narrative_word_count"] = len(narrative.split()) if narrative else 0

    claim_type = claim_data.get("claim_type") or "unknown"
    features["claim_type_inpatient"] = int(claim_type == "inpatient")
    features["claim_type_outpatient"] = int(claim_type == "outpatient")
    features["claim_type_pharmacy"] = int(claim_type == "pharmacy")
    features["claim_type_lab"] = int(claim_type == "lab")

    if provider_stats:
        avg = provider_stats.get("avg_claim_amount", amount)
        features["amount_vs_provider_avg_ratio"] = amount / avg if avg > 0 else 1.0
        features["provider_claim_count_30d"] = provider_stats.get("claim_count_30d", 0)

    return features


def _days_between(d1, d2) -> int | None:
    if d1 is None or d2 is None:
        return None
    try:
        if isinstance(d1, str):
            d1 = date.fromisoformat(d1)
        if isinstance(d2, str):
            d2 = date.fromisoformat(d2)
        return (d2 - d1).days
    except (ValueError, TypeError):
        return None
