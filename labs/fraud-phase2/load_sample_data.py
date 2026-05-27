"""Load the synthetic BHYT sample dataset for Phase 2 ML training.

Reads ``data/sample_claims.csv``, parses each row into the claim_data /
analysis_data structures expected by ml_trainer.build_training_dataset(),
and returns a list of labeled records.

Labels are hand-annotated based on known fraud patterns in the synthetic
25-claim dataset (13 legitimate, 12 confirmed_fraud).

Run this file directly to get a quick summary:
    python load_sample_data.py
"""
from __future__ import annotations

import csv
import os
from typing import Any

_DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
_DEFAULT_CSV = os.path.join(_DATA_DIR, "sample_claims_1000.csv")
_LEGACY_CSV  = os.path.join(_DATA_DIR, "sample_claims.csv")


# ── Hand-annotated labels ─────────────────────────────────────────────────

_LABELS: dict[str, str] = {
    "VN-001": "legitimate",        # Routine annual health check
    "VN-002": "legitimate",        # Prenatal visit, 20 wk
    "VN-003": "legitimate",        # Laparoscopic appendectomy (Viet Duc)
    "VN-004": "legitimate",        # Wisdom-tooth extraction
    "VN-005": "legitimate",        # Standard routine labs
    "VN-006": "legitimate",        # FOLFOX chemo cycle 4 (stage-III colon cancer)
    "VN-007": "legitimate",        # T2DM follow-up, HbA1c 6.8 %
    "VN-008": "legitimate",        # URI / mild cold
    "VN-009": "legitimate",        # Cataract Phaco + IOL
    "VN-010": "confirmed_fraud",   # 15 procedure codes + 12.5 M VND for mild cold
    "VN-011": "confirmed_fraud",   # 85 M for 15-min ovarian cystectomy, same-day discharge
    "VN-012": "confirmed_fraud",   # 10-day inpatient for simple pharyngitis, 25 M VND
    "VN-013": "confirmed_fraud",   # 8 drugs incl. albumin/glutathione IV for common cold
    "VN-014": "confirmed_fraud",   # 92 M, claimed 30-day inpatient; patient was outpatient
    "VN-015": "legitimate",        # Hypertension multi-code check (empty narrative)
    "VN-016":  "confirmed_fraud",  # Duplicate billing — triple submission same patient
    "VN-016B": "confirmed_fraud",
    "VN-016C": "confirmed_fraud",
    "VN-017": "confirmed_fraud",   # 3× contrast CT in 2 wks for known stable migraine
    "VN-018": "confirmed_fraud",   # Upcoded room: VIP billed, shared ward occupied
    "VN-019": "legitimate",        # Appendectomy (routine, Viet Duc)
    "VN-020": "confirmed_fraud",   # 38 M, 20 procedure codes for healthy routine check
    "VN-021": "confirmed_fraud",   # Mild flu billed as 7-day pneumonia inpatient
    "VN-022": "legitimate",        # Normal vaginal delivery (39 wk, Apgar 9/10)
    "VN-023": "legitimate",        # Stable migraine follow-up
    "VN-024": "legitimate",        # Routine labs for DM + HTN
    "VN-025": "legitimate",        # Hip fracture ORIF after road accident
}


# ── Synthetic Phase-1 analysis annotations ───────────────────────────────
# Mirrors what the live fraud analysis pipeline (LLM + rule engine + graph)
# would have produced for each claim.  In production these come from the
# fraud_analyses table; here they are pre-computed for offline training.

_ANALYSIS: dict[str, dict[str, Any]] = {
    "VN-001": {"risk_score": 8,  "llm_flags": [], "rule_flags": []},
    "VN-002": {"risk_score": 5,  "llm_flags": [], "rule_flags": []},
    "VN-003": {"risk_score": 12, "llm_flags": [], "rule_flags": []},
    "VN-004": {"risk_score": 10, "llm_flags": [], "rule_flags": []},
    "VN-005": {"risk_score": 7,  "llm_flags": [], "rule_flags": []},
    "VN-006": {"risk_score": 15, "llm_flags": [], "rule_flags": []},
    "VN-007": {"risk_score": 9,  "llm_flags": [], "rule_flags": []},
    "VN-008": {"risk_score": 6,  "llm_flags": [], "rule_flags": []},
    "VN-009": {"risk_score": 18, "llm_flags": [], "rule_flags": []},
    "VN-010": {
        "risk_score": 88,
        "llm_flags": [
            {"type": "diagnosis_procedure_mismatch", "severity": "high",
             "description": "15 procedure codes inconsistent with mild URI (J11.1)"},
            {"type": "amount_anomaly", "severity": "high",
             "description": "12.5 M VND outpatient cold treatment is 39× the average"},
        ],
        "rule_flags": [
            {"type": "excessive_procedures", "severity": "high",
             "description": "15 procedure codes in a single outpatient visit"},
            {"type": "amount_outpatient_threshold", "severity": "high",
             "description": "Outpatient 12.5 M exceeds 500 K threshold by 25×"},
        ],
    },
    "VN-011": {
        "risk_score": 92,
        "llm_flags": [
            {"type": "cost_complexity_mismatch", "severity": "high",
             "description": "85 M VND for a stated 15-minute laparoscopy with same-day discharge"},
            {"type": "surgery_duration_anomaly", "severity": "high",
             "description": "5 complex surgical codes for a 15-minute operation"},
        ],
        "rule_flags": [
            {"type": "amount_threshold_inpatient", "severity": "high",
             "description": "85 M exceeds expected range for ovarian cystectomy by 3×"},
            {"type": "excessive_procedures", "severity": "medium",
             "description": "5 surgical codes for minor cystectomy"},
        ],
    },
    "VN-012": {
        "risk_score": 78,
        "llm_flags": [
            {"type": "inpatient_duration_mismatch", "severity": "high",
             "description": "10-day inpatient for acute pharyngitis (J02.9) treatable with oral antibiotics"},
        ],
        "rule_flags": [
            {"type": "inpatient_duration_threshold", "severity": "high",
             "description": "10-day LOS for J02.9; benchmark is 1–3 days"},
            {"type": "amount_threshold_inpatient", "severity": "high",
             "description": "25 M for pharyngitis inpatient exceeds benchmark"},
        ],
    },
    "VN-013": {
        "risk_score": 85,
        "llm_flags": [
            {"type": "drug_diagnosis_mismatch", "severity": "high",
             "description": "Albumin 20 %, IV Glutathione, Ceftriaxone prescribed for common cold (J00)"},
            {"type": "unnecessary_medications", "severity": "high",
             "description": "8 medications including IV formulations for URI"},
        ],
        "rule_flags": [
            {"type": "excessive_procedures", "severity": "high",
             "description": "8 drug codes for ICD J00 (common cold)"},
            {"type": "amount_outpatient_threshold", "severity": "high",
             "description": "18 M outpatient exceeds threshold by 36×"},
        ],
    },
    "VN-014": {
        "risk_score": 95,
        "llm_flags": [
            {"type": "phantom_admission", "severity": "high",
             "description": "Patient documented self-presenting while simultaneously billed as 30-day inpatient"},
            {"type": "amount_anomaly", "severity": "high",
             "description": "92 M for lumbar pain rehabilitation is anomalous"},
        ],
        "rule_flags": [
            {"type": "inpatient_duration_threshold", "severity": "high",
             "description": "30-day LOS for M54.5 (low back pain); benchmark 3–7 days"},
            {"type": "amount_threshold_inpatient", "severity": "high",
             "description": "92 M exceeds rehabilitation benchmark by 6×"},
            {"type": "graph_same_patient_concurrent", "severity": "high",
             "description": "graph_: Patient active in outpatient system during claimed inpatient stay"},
        ],
    },
    "VN-015": {
        "risk_score": 22,
        "llm_flags": [],
        "rule_flags": [
            {"type": "missing_narrative", "severity": "low",
             "description": "Claim narrative is empty"},
        ],
    },
    "VN-016": {
        "risk_score": 82,
        "llm_flags": [
            {"type": "duplicate_claim", "severity": "high",
             "description": "Identical claim submitted 3× for same patient/provider on consecutive days"},
        ],
        "rule_flags": [
            {"type": "graph_duplicate_billing", "severity": "high",
             "description": "graph_: 3 near-identical claims VN-016/016B/016C within 72 h"},
        ],
    },
    "VN-016B": {
        "risk_score": 82,
        "llm_flags": [
            {"type": "duplicate_claim", "severity": "high",
             "description": "Duplicate of VN-016 — same diagnosis, provider, amount, consecutive day"},
        ],
        "rule_flags": [
            {"type": "graph_duplicate_billing", "severity": "high",
             "description": "graph_: Linked to VN-016 and VN-016C duplicate billing cluster"},
        ],
    },
    "VN-016C": {
        "risk_score": 82,
        "llm_flags": [
            {"type": "duplicate_claim", "severity": "high",
             "description": "Duplicate of VN-016 — same diagnosis, provider, amount, consecutive day"},
        ],
        "rule_flags": [
            {"type": "graph_duplicate_billing", "severity": "high",
             "description": "graph_: Linked to VN-016 and VN-016B duplicate billing cluster"},
        ],
    },
    "VN-017": {
        "risk_score": 72,
        "llm_flags": [
            {"type": "unnecessary_imaging", "severity": "high",
             "description": "3 contrast CT brain scans in 2 weeks for established stable migraine (G43.909)"},
        ],
        "rule_flags": [
            {"type": "repeated_imaging_threshold", "severity": "high",
             "description": "3 CT-head studies within 14 days for G43.909 with no new symptoms"},
        ],
    },
    "VN-018": {
        "risk_score": 68,
        "llm_flags": [
            {"type": "upcoded_accommodation", "severity": "high",
             "description": "VIP single-room billing (3 M/day × 5 days) but patient placed in shared ward"},
        ],
        "rule_flags": [
            {"type": "accommodation_upcoding", "severity": "high",
             "description": "Billed room category inconsistent with ward assignment records"},
        ],
    },
    "VN-019": {"risk_score": 14, "llm_flags": [], "rule_flags": []},
    "VN-020": {
        "risk_score": 90,
        "llm_flags": [
            {"type": "excessive_testing", "severity": "high",
             "description": "20 procedure codes for a healthy patient routine checkup (Z00.0)"},
            {"type": "amount_anomaly", "severity": "high",
             "description": "38 M for routine health check; expected < 500 K"},
        ],
        "rule_flags": [
            {"type": "excessive_procedures", "severity": "high",
             "description": "20 procedure codes in single outpatient visit"},
            {"type": "amount_outpatient_threshold", "severity": "high",
             "description": "38 M outpatient exceeds threshold by 76×"},
        ],
    },
    "VN-021": {
        "risk_score": 75,
        "llm_flags": [
            {"type": "diagnosis_severity_mismatch", "severity": "high",
             "description": "J18.9 pneumonia inpatient (7 days) for patient with 37.5 °C, no respiratory distress"},
        ],
        "rule_flags": [
            {"type": "inpatient_duration_threshold", "severity": "medium",
             "description": "7-day inpatient for mild presentation of J18.9"},
            {"type": "amount_threshold_inpatient", "severity": "medium",
             "description": "22 M exceeds benchmark for mild community-acquired pneumonia"},
        ],
    },
    "VN-022": {"risk_score": 16, "llm_flags": [], "rule_flags": []},
    "VN-023": {"risk_score": 11, "llm_flags": [], "rule_flags": []},
    "VN-024": {"risk_score": 9,  "llm_flags": [], "rule_flags": []},
    "VN-025": {"risk_score": 20, "llm_flags": [], "rule_flags": []},
}


# ── Public API ────────────────────────────────────────────────────────────

def _row_has_inline_labels(fieldnames: list[str]) -> bool:
    """Return True if the CSV already contains fraud_label / risk score columns."""
    return "fraud_label" in fieldnames and "llm_risk_score" in fieldnames


def load_records(csv_path: str = _DEFAULT_CSV) -> list[dict]:
    """Return a list of labeled record dicts for ml_trainer.build_training_dataset().

    Supports two CSV formats automatically:

    *Legacy (25-row)*  — labels come from the hard-coded ``_LABELS`` / ``_ANALYSIS``
        dicts; rows whose claim_id is not in ``_LABELS`` are skipped.

    *Extended (1 000-row)*  — the CSV itself contains ``fraud_label``,
        ``llm_risk_score``, ``rule_risk_score``, and ``combined_risk_score``
        columns; all rows are included.

    Each returned dict contains:
        ``claim_data``  — matches the input schema of feature_extractor.extract_features()
        ``analysis``    — dict with risk_score, llm_flags, rule_flags
        ``label``       — "legitimate" or "confirmed_fraud"
    """
    records: list[dict] = []

    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        inline = _row_has_inline_labels(fieldnames)

        for row in reader:
            claim_id = row["claim_id"].strip()

            # ── Resolve label ─────────────────────────────────────────────
            if inline:
                label = row.get("fraud_label", "").strip()
                if label not in ("legitimate", "confirmed_fraud"):
                    continue
            else:
                label = _LABELS.get(claim_id)
                if label is None:
                    continue  # Unknown legacy claim — skip

            # ── Parse claim fields ────────────────────────────────────────
            diag_codes = [c.strip() for c in row.get("diagnosis_codes", "").split("|") if c.strip()]
            proc_codes = [c.strip() for c in row.get("procedure_codes", "").split("|") if c.strip()]

            claim_data: dict = {
                "claim_id":        claim_id,
                "claim_amount":    float(row["claim_amount"]) if row.get("claim_amount") else None,
                "service_date":    row.get("service_date") or None,
                "submission_date": row.get("submission_date") or None,
                "diagnosis_codes": diag_codes,
                "procedure_codes": proc_codes,
                "claim_narrative": row.get("claim_narrative") or "",
                "claim_type":      row.get("claim_type") or "unknown",
            }

            # ── Resolve analysis ──────────────────────────────────────────
            if inline:
                try:
                    risk_score = float(row.get("llm_risk_score") or 0)
                except ValueError:
                    risk_score = 0.0
                analysis: dict = {
                    "risk_score": risk_score,
                    "llm_flags":  [],   # not stored in CSV; model uses risk_score directly
                    "rule_flags": [],
                }
            else:
                analysis = _ANALYSIS.get(
                    claim_id,
                    {"risk_score": 20, "llm_flags": [], "rule_flags": []},
                )

            records.append({"claim_data": claim_data, "analysis": analysis, "label": label})

    return records


# ── CLI summary ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    records = load_records()
    legit = sum(1 for r in records if r["label"] == "legitimate")
    fraud = sum(1 for r in records if r["label"] == "confirmed_fraud")
    print(f"Loaded {len(records)} records: {legit} legitimate, {fraud} confirmed_fraud\n")
    print(f"{'claim_id':<10} {'label':<20} {'amount':>14}  {'risk':>5}  {'flags'}")
    print("─" * 70)
    for r in records:
        cd = r["claim_data"]
        an = r["analysis"]
        n_flags = len(an["llm_flags"]) + len(an["rule_flags"])
        print(
            f"{cd['claim_id']:<10} {r['label']:<20} "
            f"{(cd['claim_amount'] or 0):>14,.0f}  "
            f"{an['risk_score']:>5}  "
            f"{n_flags} flag(s)"
        )
