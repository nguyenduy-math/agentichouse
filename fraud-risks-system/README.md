# Healthcare Claim Fraud Detection System

A hybrid fraud detection system for healthcare claims combining LLM-powered narrative analysis, rule-based signals, a Neo4j patient profile graph, and a human-in-the-loop review workflow. Designed to operate without labeled fraud data on day one, accumulating investigator decisions as a labeled dataset for Phase 2 ML training.

---

## Architecture

```
CSV Upload → Claims DB (PostgreSQL)
                ↓
        [Nightly Batch @ 2am]
                ↓
    ┌─────────────────────────┐     ┌──────────────────────────┐
    │  Gemini LLM Analyzer    │  +  │  Rule-Based Signals      │
    │  (narrative analysis)   │     │  (codes, amounts, dates) │
    └─────────────────────────┘     └──────────────────────────┘
                ↓
        Per-Claim Risk Score
                ↓
    ┌─────────────────────────────────────────┐
    │  Patient Profile Graph  (Neo4j)         │  ← Post-batch enrichment pass
    │  Provider concentration · Fraud rings   │
    │  Patient velocity · Procedure dominance │
    └─────────────────────────────────────────┘
                ↓
        Combined Risk Score (0–100) + Network Risk flag
                ↓
    ┌─────────────────────────────┐
    │  Investigator Dashboard     │  http://localhost:5173
    │  Review Queue + Decisions   │  Purple "Network Risk" badge
    └─────────────────────────────┘
                ↓
        Labeled Dataset → Phase 2 ML Training (~500 reviews)
```

---

## Fraud Patterns Detected

### Per-Claim (LLM + Rules)

| Pattern | Description |
|---|---|
| **Upcoding** | Narrative describes lower complexity than billed CPT codes |
| **Phantom billing** | Service in narrative doesn't match procedure codes |
| **Unbundling** | Multiple CPT codes that should be a single billable unit |
| **Medical necessity** | Diagnosis codes don't support the billed treatment |
| **Vague language** | Extremely brief or non-clinical claim narratives |
| **Rehearsed language** | Overly precise, template-like, or emotionally manipulative text |
| **Timing anomaly** | Submission date before service date, or >1 year gap |
| **Excessive billing** | Claim amount far exceeds thresholds for the billed service type |

### Network-Level (Patient Profile Graph)

| Pattern | Description |
|---|---|
| **Provider concentration** | Provider where >40% of claims are high-risk, min 2 claims |
| **Fraud ring** | ≥2 distinct patients sharing the same provider and procedure code |
| **Patient velocity** | Patient with ≥5 claims across ≥3 different providers |
| **Procedure dominance** | Provider billing the same CPT code on >70% of claims, min 2 claims |

Network-flagged claims show a purple **Network Risk** badge in the review queue and a dedicated **Network Signals** section in the claim detail drawer.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | FastAPI + Uvicorn (Python) |
| Relational DB | PostgreSQL 16 (Docker) |
| Graph DB | Neo4j 5 + APOC plugin (Docker) |
| LLM | Google Gemini `gemini-2.5-flash` |
| Scheduler | APScheduler (nightly batch) |
| Frontend | React + Vite |

---

## Prerequisites

- Python 3.10+
- Node.js 18+
- Docker + Docker Compose
- Google Gemini API key — [get one here](https://aistudio.google.com/apikey)

---

## Quick Start

### 1. Start the databases

```bash
docker compose up -d
```

Starts PostgreSQL (port `5432`) and Neo4j (ports `7474` browser UI, `7687` Bolt). Wait for both to be healthy:

```bash
docker ps --filter name=fraud-postgres
docker ps --filter name=fraud-neo4j
```

Neo4j Browser is available at `http://localhost:7474` (login: `neo4j` / `fraud-neo4j-secret`).

### 2. Set up the backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Copy and edit the environment file:

```bash
cp .env.example .env
```

Set at minimum:

```env
GEMINI_API_KEY=your-key-here
```

The Neo4j and PostgreSQL defaults match `docker-compose.yml` and need no changes unless you modified the passwords.

Start the API server:

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload
```

The server initializes the database tables on first startup. Open `http://127.0.0.1:8001/docs` to explore the API.

### 3. Set up the frontend

```bash
cd frontend
npm install
npm run dev
```

Open **http://localhost:5173** in your browser.

---

## Using the System

### Step 1 — Upload Claims

Go to the **Upload Claims** tab and drop a CSV file. The only required column is `claim_id`.

**Supported columns:**

| Column | Description |
|---|---|
| `claim_id` | Unique claim identifier (required) |
| `patient_id` | De-identified patient ID |
| `provider_id` | Provider identifier |
| `provider_name` | Provider name |
| `claim_amount` | Billed dollar amount |
| `service_date` | Date of service (`YYYY-MM-DD` or `MM/DD/YYYY`) |
| `submission_date` | Date claim was submitted |
| `claim_type` | `inpatient`, `outpatient`, `pharmacy`, `lab` |
| `diagnosis_codes` | ICD-10 codes separated by `\|` (e.g. `M17.11\|M17.31`) |
| `procedure_codes` | CPT codes separated by `\|` (e.g. `27447\|27446`) |
| `claim_narrative` | Free-text description — the primary field analyzed by the LLM |

A sample file with 25 synthetic claims is provided at `backend/data/sample_claims.csv`.

### Step 2 — Run Batch Analysis

Click **Run Batch Now** in the Review Queue tab, or wait for the nightly run at 2:00 AM. The batch runs in two passes:

**Pass 1 — Per-claim analysis** (runs in parallel per claim)
- Gemini LLM analyzes the claim narrative → risk score + flags + plain-English explanation
- Rule engine checks amounts, code counts, and submission timing
- Combined score written to `fraud_analyses`

**Pass 2 — Graph enrichment** (runs once after all claims are scored)
- All claims synced to the Neo4j patient profile graph as nodes and edges
- 4 Cypher queries detect network-level fraud patterns across providers and patients
- Graph flags appended to `rule_flags`; combined score boosted by up to +20 per high-severity graph flag

```
Combined Score = 0.7 × LLM Score + 0.3 × max(Rule Score, Graph Score)
                                    + graph severity boost (capped at 100)
```

Risk levels:

| Score | Level |
|---|---|
| 0–25 | Low |
| 26–50 | Medium |
| 51–75 | High |
| 76–100 | Critical |

### Step 3 — Review Claims

The **Review Queue** shows analyzed claims sorted by risk score. Claims with network-level fraud signals display a purple **Network Risk** badge.

Click any row to open the claim detail drawer:

- Claim fields and billing codes
- Original claim narrative
- AI explanation (plain English)
- **Network Signals** section (purple) — graph-detected patterns, shown separately from per-claim flags
- Per-claim fraud flags with severity

Submit an investigator decision:

- **Legitimate** — claim looks valid
- **Suspicious** — needs further investigation
- **Confirmed Fraud** — escalate for action

Each decision is stored and contributes to your labeled dataset.

### Step 4 — Explore the Graph

Open **http://localhost:7474** to query the patient profile graph directly:

```cypher
// View the full graph (small datasets)
MATCH (n) RETURN n LIMIT 100

// Find providers with the most high-risk claims
MATCH (pr:Provider)<-[:TREATED_BY]-(c:Claim)
WHERE c.combined_score >= 51
RETURN pr.provider_name, count(c) AS high_risk_claims
ORDER BY high_risk_claims DESC

// Find shared-provider patient clusters
MATCH (pt:Patient)-[:SUBMITTED]->(c:Claim)-[:TREATED_BY]->(pr:Provider)
WITH pr, collect(DISTINCT pt.patient_id) AS patients
WHERE size(patients) >= 2
RETURN pr.provider_name, patients
```

### Step 5 — Track Progress

The **Stats** tab shows your label accumulation. Phase 2 ML training (XGBoost/LightGBM classifier) becomes viable at approximately 500 labeled reviews.

---

## API Reference

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | System health (DB + Gemini) |
| `POST` | `/claims/upload` | Upload CSV file |
| `GET` | `/claims` | List claims with filters |
| `GET` | `/claims/{id}` | Claim detail + latest analysis |
| `GET` | `/review/queue` | Paginated queue sorted by risk (`network_risk` field included) |
| `POST` | `/review/{id}/decision` | Submit investigator decision |
| `GET` | `/review/stats` | Dashboard statistics |
| `POST` | `/batch/run` | Trigger batch analysis + graph enrichment manually |
| `GET` | `/batch/status` | Last batch run status |

All endpoints are also available under the `/api/` prefix (used by the frontend).

Interactive API docs: `http://127.0.0.1:8001/docs`

---

## Configuration

All settings are in `backend/.env`:

| Variable | Default | Description |
|---|---|---|
| `GEMINI_API_KEY` | — | Required. Your Google Gemini API key |
| `GEMINI_LLM_MODEL` | `gemini-2.5-flash` | Gemini model to use |
| `DATABASE_URL` | `postgresql+asyncpg://fraud:fraud-secret@localhost:5432/fraud_detection` | PostgreSQL connection string |
| `NEO4J_URI` | `bolt://localhost:7687` | Neo4j Bolt URI |
| `NEO4J_USERNAME` | `neo4j` | Neo4j username |
| `NEO4J_PASSWORD` | `fraud-neo4j-secret` | Must match `docker-compose.yml` `NEO4J_AUTH` |
| `BATCH_CRON_HOUR` | `2` | Hour for nightly batch (0–23) |
| `BATCH_CRON_MINUTE` | `0` | Minute for nightly batch |
| `BATCH_MAX_CLAIMS` | `500` | Max claims per batch run |
| `LLM_SCORE_WEIGHT` | `0.7` | Weight for LLM score in combined score |
| `RULE_SCORE_WEIGHT` | `0.3` | Weight for rule-based + graph score |
| `PORT` | `8001` | Backend server port |

---

## Project Structure

```
fraud-risks-system/
├── docker-compose.yml              # PostgreSQL + Neo4j services
├── backend/
│   ├── .env.example                # Configuration template
│   ├── requirements.txt
│   ├── data/
│   │   └── sample_claims.csv       # 25 synthetic test claims
│   └── app/
│       ├── main.py                 # FastAPI entry point + lifespan
│       ├── config.py               # Pydantic settings
│       ├── database.py             # SQLAlchemy async engine
│       ├── models.py               # ORM: Claim, FraudAnalysis, Review, BatchRun
│       ├── schemas.py              # Pydantic request/response models
│       ├── fraud_analyzer.py       # Gemini LLM analysis engine
│       ├── batch_pipeline.py       # APScheduler nightly job + graph enrichment trigger
│       ├── graph_engine.py         # Neo4j patient profile graph sync + 4 Cypher fraud queries
│       ├── feature_extractor.py    # ML feature extraction (Phase 2 prep)
│       └── routers/
│           ├── claims.py           # Claim upload and listing
│           ├── review.py           # Review queue (network_risk field) and decisions
│           ├── batch.py            # Batch trigger and status
│           └── health.py           # Health check
└── frontend/
    ├── vite.config.js
    └── src/
        ├── App.jsx                 # Root component + tab nav
        ├── api.js                  # Fetch wrapper
        └── components/
            ├── ReviewQueue.jsx     # Claims table + Network Risk badge column
            ├── ClaimDetail.jsx     # Claim drawer: AI analysis + Network Signals section
            ├── RiskBadge.jsx       # Color-coded risk indicator
            ├── DecisionPanel.jsx   # Legitimate / Suspicious / Fraud buttons
            └── UploadClaims.jsx    # CSV drag-and-drop upload
```

---

## Graph Schema

```
(:Patient {patient_id, claim_count, total_billed})
(:Provider {provider_id, provider_name, claim_count, total_billed, high_risk_count})
(:Claim {claim_id, db_id, amount, service_date, combined_score, risk_level})
(:Diagnosis {code})
(:Procedure {code})

(Patient)-[:SUBMITTED]→(Claim)
(Claim)-[:TREATED_BY]→(Provider)
(Claim)-[:CODED_WITH]→(Diagnosis)
(Claim)-[:BILLED_FOR]→(Procedure)
```

Nodes are upserted (MERGE) after each batch run. Graph flags are prefixed `graph_` in `fraud_analyses.rule_flags` so the frontend can distinguish them from per-claim rule flags.

---

## Evolution Roadmap

### Phase 1 — Current
LLM narrative scoring + rule-based signals + Neo4j network fraud detection + HITL review + label accumulation.

### Phase 2 — After ~500 labeled reviews
Train an XGBoost/LightGBM classifier on structured features extracted by `feature_extractor.py` (claim amount ratios, code counts, submission timing, provider frequency). Blend ML score with LLM + graph scores for higher precision.

### Phase 3 — Scale
- **Active learning** — prioritize borderline cases for investigator review
- **Embedding fine-tuning** on the healthcare claim domain
- **Real-time scoring** for high-priority claims before batch
- **Adjuster graph** — extend the graph to link adjusters for collusion detection

---

## HIPAA Note

This system uses the Google Gemini cloud API. Healthcare claims may contain Protected Health Information (PHI). Before processing real patient data:

- Obtain a **HIPAA Business Associate Agreement (BAA)** with Google, or
- Switch to a **local LLM** (e.g., Llama 3 via Ollama) by replacing `fraud_analyzer.py`'s Gemini client — the structured output interface is the same
- Consider **de-identifying** narratives before sending to any external API
- Neo4j runs entirely on-premises — no PHI leaves your infrastructure via the graph layer
