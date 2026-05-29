# Fraud Detection — Phase 2 ML Sandbox

A **self-contained** sandbox for developing and testing the XGBoost fraud
classifier before it's wired into the main backend.  No PostgreSQL, FastAPI,
Neo4j, Gemini, or APScheduler required.

---

## Folder structure

```
fraud-phase2/
├── feature_extractor.py   # Converts raw claim dicts → 15-dim numeric vectors
├── load_sample_data.py    # Loads the CSV + hand-annotated labels & Phase-1 analysis
├── ml_trainer.py          # XGBoost training pipeline — main entry point
├── requirements.txt       # Phase-2-only Python dependencies
├── data/
│   └── sample_claims.csv  # 25 synthetic Vietnamese BHYT claims (13 legit / 12 fraud)
└── models/                # Trained .joblib files land here (git-ignored)
```

---

## Quick start

```bash
# 1.  Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# 2.  Install Phase-2 dependencies only
pip install -r requirements.txt

# 3.  (Optional) inspect the sample data
python load_sample_data.py

# 4.  Run training
python ml_trainer.py
```

Expected output (abridged):

```
09:12:01  INFO     Loaded 25 labeled records from data/sample_claims.csv
09:12:01  INFO     Dataset: 25 samples · 15 features · class counts: {'0': 13, '1': 12}
09:12:01  INFO     Running 5-fold stratified CV on 25 samples, 15 features …
09:12:02  INFO       Per-fold AUC : 1.000  1.000  1.000  1.000  1.000
09:12:02  INFO       Mean ± std   : 1.0000 ± 0.0000
09:12:02  INFO     Model saved → models/fraud_classifier.joblib
...
```

> **Note:** CV AUC = 1.0 on the 25-sample synthetic set is expected — the
> synthetic labels are deterministic.  Real-world performance will be
> measured once the model is retrained on production labeled reviews.

---

## Feature set (15 features)

| # | Feature | Source |
|---|---|---|
| 1 | `claim_amount` | Claim field |
| 2 | `num_diagnosis_codes` | Claim field |
| 3 | `num_procedure_codes` | Claim field |
| 4 | `days_to_submission` | Derived (submission − service date) |
| 5 | `narrative_length` | Claim narrative character count |
| 6 | `narrative_word_count` | Claim narrative word count |
| 7–10 | `claim_type_*` (one-hot) | inpatient / outpatient / pharmacy / lab |
| 11 | `llm_risk_score` | Phase 1 LLM risk score (0–100) |
| 12 | `num_llm_flags` | Count of LLM-generated flags |
| 13 | `num_rule_flags` | Count of rule-engine flags (non-graph) |
| 14 | `max_flag_severity` | Highest severity: 0 = none, 1 = low, 2 = medium, 3 = high |
| 15 | `has_graph_flags` | 1 if any graph/network fraud flags present |

---

## How labels and analysis data are generated (sandbox only)

Because there is no live database, `load_sample_data.py` supplies:

- **Labels** — hard-coded per `claim_id`, derived from manual annotation of
  the 25 synthetic claims.
- **Analysis** — synthetic `risk_score`, `llm_flags`, and `rule_flags` dicts
  that mimic what the Phase-1 pipeline (LLM + rule engine + Neo4j graph)
  would have produced.

When you integrate this back into the main project, these are replaced by
real rows from the `fraud_analyses` and `reviews` PostgreSQL tables.

---

## CLI options

```
python ml_trainer.py --help

  --csv   PATH   Path to claims CSV (default: data/sample_claims.csv)
  --model PATH   Output path for the .joblib bundle (default: models/fraud_classifier.joblib)
```

---

## Integrating back into the main backend

1. Copy `models/fraud_classifier.joblib` → `backend/models/fraud_classifier.joblib`.
2. The existing `backend/app/ml_trainer.py` already has `load_model()` and
   `predict_score()` — they accept the same bundle format.
3. The async `train_and_save()` function in the main project retrains the model
   using real labeled reviews from PostgreSQL once ≥ 500 examples accumulate.
4. No changes to `feature_extractor.py` are needed — the sandbox version is
   identical to the backend version.

---

## Dependencies

| Package | Version | Purpose |
|---|---|---|
| pandas | ≥ 2.0 | CSV loading / data wrangling |
| numpy | ≥ 1.24 | Feature matrix construction |
| scikit-learn | ≥ 1.3 | Cross-validation, metrics |
| xgboost | ≥ 2.0 | Gradient-boosted classifier |
| joblib | ≥ 1.3 | Model persistence |
