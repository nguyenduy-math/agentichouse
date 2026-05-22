```mermaid
%%{init: {
  "theme": "base",
  "themeVariables": {
    "primaryColor": "#0f172a",
    "primaryTextColor": "#e2e8f0",
    "primaryBorderColor": "#334155",
    "lineColor": "#64748b",
    "secondaryColor": "#1e293b",
    "tertiaryColor": "#0f172a",
    "background": "#020617",
    "nodeBorder": "#475569",
    "clusterBkg": "#1e293b",
    "titleColor": "#94a3b8",
    "edgeLabelBackground": "#1e293b",
    "fontSize": "13px"
  }
}}%%

flowchart TB

    subgraph PRESENTATION["  ⬡  PRESENTATION LAYER"]
        direction LR
        WEB["◈  Investigator Dashboard\n─────────────────────\nReview Queue · Claim Detail\nDecision Panel · Stats"]
        CSV["◈  Data Ingestion UI\n─────────────────────\nCSV Drag-and-Drop Upload\nUpload Progress & Result"]
        EXT["◈  External Clients\n─────────────────────\nREST API Consumers\nAutomation · Integrations"]
    end

    subgraph GATEWAY["  ⬡  API GATEWAY"]
        direction LR
        GW["◈  FastAPI Server\n──────────────────────────\nCORS Policy · Routing\nRequest Validation\nLifecycle Management"]
    end

    subgraph CORE["  ⬡  FRAUD DETECTION CORE"]
        direction TB

        subgraph INGEST_PIPE["  Claim Ingestion Pipeline"]
            PARSER["◈  CSV Parser\n─────────────────\nColumn mapping\nDate / code normalisation\nRaw row archiving"]
        end

        subgraph SCORING["  Scoring Engine"]
            direction LR
            LLM_AN["◈  LLM Fraud Analyzer\n──────────────────────\nNarrative analysis\nStructured flag extraction\nPlain-English explanation"]
            RULE_EN["◈  Rule Engine\n──────────────────────\nAmount thresholds\nCode-count checks\nTiming anomaly detection"]
            COMBINER["◈  Score Combiner\n──────────────────────\n0.7 × LLM score\n+ 0.3 × Rule score\nRisk level assignment"]
        end

        subgraph BATCH["  Batch Orchestration"]
            SCHED["◈  APScheduler\n─────────────────\nNightly run @ 2 AM\nManual trigger support\nBatch audit logging"]
        end

        subgraph GRAPH_ENGINE["  Patient Profile Graph  — Network Fraud Detection"]
            direction LR
            GSYNC["◈  Graph Sync Engine\n──────────────────────\nMERGE Patient · Provider\nClaim · Diagnosis · Procedure\nUpsert nodes + relationships"]
            Q_CONC["◈  Provider Concentration\n──────────────────────\n>40% high-risk claims\nmin 2 claims per provider"]
            Q_VEL["◈  Patient Velocity\n──────────────────────\n≥5 claims · ≥3 providers\nRapid multi-provider pattern"]
            Q_RING["◈  Fraud Ring Detector\n──────────────────────\n≥2 patients: same provider\n+ same CPT code cluster"]
            Q_DOM["◈  Procedure Dominance\n──────────────────────\n>80% same CPT code billed\nProvider upcoding pattern"]
        end

        subgraph HITL["  Human-in-the-Loop"]
            REVIEW["◈  Review Workflow\n─────────────────\nQueue ranked by score\nInvestigator decisions\nNotes + audit trail"]
            LABELS["◈  Label Accumulator\n─────────────────\nLegitimate · Suspicious\nConfirmed Fraud\nPhase 2 readiness tracker"]
        end

        subgraph ML_PREP["  ML Readiness  — Phase 2"]
            FEAT["◈  Feature Extractor\n──────────────────────\nAmount vs. provider avg\nCode count · timing gap\nClaim-type indicators"]
            TRAIN["◈  Classifier Training\n──────────────────────\nXGBoost / LightGBM\nUnlocks at ~500 labels\nBlended with LLM score"]
        end
    end

    subgraph STORAGE["  ⬡  PERSISTENCE LAYER"]
        direction LR
        CLAIMS_TBL[("◈  claims\n────────────────\nClaim fields · codes\nNarrative · status\nRaw CSV row")]
        ANALYSIS_TBL[("◈  fraud_analyses\n────────────────\nRisk score · level\nLLM flags · rule flags\nExplanation · model ver")]
        REVIEWS_TBL[("◈  reviews\n────────────────\nInvestigator decision\nNotes · reviewer ID\nTimestamp")]
        BATCH_TBL[("◈  batch_runs\n────────────────\nRun status · timing\nClaims processed\nError log")]
        NEO4J_GRAPH[("◈  Neo4j Patient Graph\n────────────────\nPatient · Provider · Claim\nDiagnosis · Procedure nodes\nNetwork relationships")]
    end

    subgraph EXT_AI["  ⬡  EXTERNAL AI INFERENCE  ─ ─ ─ ─ (managed cloud)"]
        direction LR
        SFLOW["◈  Qwen2.5 · SiliconFlow\n──────────────────────\nQwen/Qwen2.5-7B-Instruct\nOpenAI-compatible tool calling\nHealthcare fraud prompts"]
    end

    %% ── Ingestion Flow ───────────────────────────────────────────
    WEB   -->|"POST /claims/upload"| GW
    CSV   -->|"multipart CSV"| GW
    EXT   -->|"REST"| GW
    GW    -->|"parse & store"| PARSER
    PARSER -->|"insert rows"| CLAIMS_TBL

    %% ── Batch Flow ───────────────────────────────────────────────
    GW    -->|"POST /batch/run\n(manual trigger)"| SCHED
    SCHED -->|"query pending claims"| CLAIMS_TBL
    SCHED -->|"analyze each claim"| LLM_AN
    SCHED -->|"check rule signals"| RULE_EN
    LLM_AN -->|"llm_score + flags"| COMBINER
    RULE_EN -->|"rule_score + flags"| COMBINER
    COMBINER -->|"write analysis"| ANALYSIS_TBL
    COMBINER -->|"update status → analyzed"| CLAIMS_TBL
    SCHED -->|"write run record"| BATCH_TBL

    %% ── LLM external call ────────────────────────────────────────
    LLM_AN -->|"narrative + codes + prompt"| SFLOW
    SFLOW -->|"structured JSON response"| LLM_AN

    %% ── Review Flow ──────────────────────────────────────────────
    GW    -->|"GET /review/queue"| REVIEW
    REVIEW -->|"read analyses"| ANALYSIS_TBL
    REVIEW -->|"read claims"| CLAIMS_TBL
    GW    -->|"POST /review/{id}/decision"| LABELS
    LABELS -->|"insert review"| REVIEWS_TBL
    LABELS -->|"update status → reviewed"| CLAIMS_TBL

    %% ── ML Phase 2 ───────────────────────────────────────────────
    LABELS -.->|"500+ labels trigger"| FEAT
    CLAIMS_TBL -.->|"structured fields"| FEAT
    FEAT -.->|"feature vectors"| TRAIN
    REVIEWS_TBL -.->|"ground truth labels"| TRAIN
    TRAIN -.->|"Phase 2: blended score"| COMBINER

    %% ── Graph Enrichment Flow (Pass 2) ──────────────────────────
    SCHED -->|"graph sync pass\n(post-batch)"| GSYNC
    GSYNC <-->|"MERGE upsert"| NEO4J_GRAPH
    GSYNC -->|"run detection queries"| Q_CONC
    GSYNC -->|"run detection queries"| Q_VEL
    GSYNC -->|"run detection queries"| Q_RING
    GSYNC -->|"run detection queries"| Q_DOM
    Q_CONC -->|"append graph_ flags\n+ score boost"| ANALYSIS_TBL
    Q_VEL  -->|"append graph_ flags\n+ score boost"| ANALYSIS_TBL
    Q_RING -->|"append graph_ flags\n+ score boost"| ANALYSIS_TBL
    Q_DOM  -->|"append graph_ flags\n+ score boost"| ANALYSIS_TBL
    REVIEW -->|"network_risk flag\n(graph_ prefix detection)"| WEB

    %% ── Health ───────────────────────────────────────────────────
    GW    -.->|"GET /health"| CLAIMS_TBL

    %% ── Stats ────────────────────────────────────────────────────
    GW    -->|"GET /review/stats"| REVIEWS_TBL

    %% ── Styles ───────────────────────────────────────────────────
    classDef node     fill:#1e293b,stroke:#475569,color:#e2e8f0,rx:6
    classDef storage  fill:#172033,stroke:#3b4f6b,color:#93c5fd,rx:6
    classDef extai    fill:#1a1225,stroke:#6d28d9,color:#c4b5fd,rx:6
    classDef gateway  fill:#0c1a12,stroke:#166534,color:#86efac,rx:6
    classDef hitl     fill:#1c1408,stroke:#b45309,color:#fcd34d,rx:6
    classDef ml       fill:#0f1a2e,stroke:#1d4ed8,color:#93c5fd,rx:6
    classDef netgraph fill:#1a0d2e,stroke:#6d28d9,color:#ede9fe,rx:6

    class GW gateway
    class WEB,CSV,EXT,PARSER,LLM_AN,RULE_EN,COMBINER,SCHED node
    class REVIEW,LABELS hitl
    class FEAT,TRAIN ml
    class CLAIMS_TBL,ANALYSIS_TBL,REVIEWS_TBL,BATCH_TBL,NEO4J_GRAPH storage
    class SFLOW extai
    class GSYNC,Q_CONC,Q_VEL,Q_RING,Q_DOM netgraph
```

---

## Database Entity Relationship Diagram

```mermaid
erDiagram
    CLAIMS {
        uuid    id              PK
        string  claim_id        "external ID from CSV"
        string  patient_id
        string  provider_id
        string  provider_name
        jsonb   diagnosis_codes "ICD-10 array"
        jsonb   procedure_codes "CPT/VN service codes"
        decimal claim_amount    "VND"
        date    service_date
        date    submission_date
        text    claim_narrative "free-text — LLM input"
        string  claim_type      "inpatient|outpatient|lab"
        string  status          "pending|analyzed|reviewed"
        jsonb   raw_csv_row
        ts      created_at
    }

    FRAUD_ANALYSES {
        uuid    id              PK
        uuid    claim_id        FK
        int     risk_score      "0–100 LLM score"
        string  risk_level      "low|medium|high|critical"
        jsonb   llm_flags       "[{type,description,severity}]"
        jsonb   rule_flags      "rule + graph_ flags"
        int     combined_score  "0.7×LLM + 0.3×rule/graph"
        text    llm_explanation "Vietnamese plain-text"
        string  model_version
        ts      analyzed_at
    }

    REVIEWS {
        uuid    id              PK
        uuid    claim_id        FK
        uuid    analysis_id     FK
        string  reviewer_id
        string  decision        "legitimate|suspicious|confirmed_fraud"
        text    notes
        ts      reviewed_at
    }

    BATCH_RUNS {
        uuid    id              PK
        ts      started_at
        ts      finished_at
        int     claims_processed
        int     claims_failed
        string  status          "running|completed|failed"
        text    error
    }

    CLAIMS         ||--o{ FRAUD_ANALYSES : "analyzed in"
    CLAIMS         ||--o{ REVIEWS        : "decided in"
    FRAUD_ANALYSES ||--o{ REVIEWS        : "referenced by"
```

---

## Claim Lifecycle — State Machine

```mermaid
stateDiagram-v2
    [*] --> pending : CSV upload\nPOST /claims/upload

    pending --> analyzing : Batch job picks up\n(nightly 2AM or manual trigger)

    analyzing --> analyzed : LLM + Rule scoring\n+ Graph enrichment complete\nFraudAnalysis row written

    analyzing --> pending : LLM call failed\n(retry next batch)

    analyzed --> reviewed : Investigator submits decision\nPOST /review/{id}/decision

    reviewed --> [*]

    state analyzed {
        [*] --> low_risk    : combined_score 0–30
        [*] --> medium_risk : combined_score 31–60
        [*] --> high_risk   : combined_score 61–80
        [*] --> critical    : combined_score 81–100
    }

    state reviewed {
        [*] --> legitimate
        [*] --> suspicious
        [*] --> confirmed_fraud
    }
```

---

## Batch Analysis — Sequence Diagram

```mermaid
sequenceDiagram
    actor Inv as Investigator
    participant FE  as React Frontend
    participant API as FastAPI
    participant DB  as PostgreSQL
    participant LLM as Qwen2.5 · SiliconFlow
    participant GE  as Graph Engine
    participant NEO as Neo4j

    Inv->>FE: Upload sample_claims.csv
    FE->>API: POST /claims/upload (multipart)
    API->>DB: INSERT INTO claims (status=pending) × N
    API-->>FE: {claims_imported: N}

    Inv->>FE: Trigger batch run
    FE->>API: POST /batch/run
    API->>DB: INSERT batch_runs (status=running)

    loop For each pending claim
        API->>DB: SELECT claim WHERE status=pending
        API->>LLM: Structured prompt\n(Vietnamese BHYT context)\nOpenAI tool_choice forced
        LLM-->>API: {risk_score, flags, explanation}
        API->>API: apply_rule_signals()\n(VND thresholds, code counts)
        API->>API: combined = 0.7×llm + 0.3×rule
        API->>DB: INSERT fraud_analyses
        API->>DB: UPDATE claims SET status=analyzed
    end

    Note over API,NEO: Graph Enrichment Pass (post-batch)
    API->>GE: sync_and_enrich(claims, analyses)
    GE->>NEO: MERGE Patient, Provider, Claim nodes
    GE->>NEO: CREATE relationships (SUBMITTED, TREATED_BY, …)
    GE->>NEO: Run 4 Cypher fraud queries
    NEO-->>GE: [{claim_db_id, flag_type, severity}]
    GE->>DB: UPDATE rule_flags → append graph_ flags
    GE->>DB: Recompute combined_score with graph boost

    API->>DB: UPDATE batch_runs SET status=completed
    API-->>FE: {status: completed, processed: N}
    FE-->>Inv: Review queue ready
```

---

## HITL Review — Sequence Diagram

```mermaid
sequenceDiagram
    actor Inv as Investigator
    participant FE  as React Frontend
    participant API as FastAPI
    participant DB  as PostgreSQL

    Inv->>FE: Open Review Queue
    FE->>API: GET /review/queue?page=1
    API->>DB: SELECT claims + fraud_analyses\nORDER BY combined_score DESC
    DB-->>API: [{claim, analysis, network_risk}]
    API-->>FE: ReviewQueueItem list\n(network_risk=true for graph_ flags)
    FE-->>Inv: Sorted queue with risk badges\n🔴 Critical  🟠 High  🟡 Medium  Network

    Inv->>FE: Click claim row
    FE->>API: GET /claims/{id}
    API->>DB: SELECT claim + latest analysis
    DB-->>API: ClaimDetail (flags, explanation)
    API-->>FE: ClaimDetail
    FE-->>Inv: Detail drawer:\n• LLM explanation (Vietnamese)\n• Per-claim flags\n• Network Signals (graph_ flags, purple)\n• Decision Panel

    Inv->>FE: Submit decision + notes
    FE->>API: POST /review/{claim_id}/decision\n{decision, notes}
    API->>DB: INSERT reviews
    API->>DB: UPDATE claims SET status=reviewed
    API-->>FE: 200 OK
    FE-->>Inv: Row removed from queue\nStats counter updated

    Inv->>FE: View dashboard stats
    FE->>API: GET /review/stats
    API->>DB: COUNT by decision, risk_level
    DB-->>API: Stats payload
    API-->>FE: {total, reviewed, confirmed_fraud, by_risk_level}
    FE-->>Inv: Dashboard summary
```
