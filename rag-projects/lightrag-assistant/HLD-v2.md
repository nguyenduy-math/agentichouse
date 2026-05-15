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
        WEB["◈  Web Application\n─────────────────\nSingle-Page App\nChat · Upload · Query"]
        EXT["◈  External Clients\n─────────────────\nREST API Consumers\nAutomation · Integrations"]
    end

    subgraph GATEWAY["  ⬡  API GATEWAY"]
        direction LR
        GW["◈  Secure API Server\n──────────────────────\nCORS Policy Enforcement\nRequest Routing & Validation\nLifecycle Management"]
    end

    subgraph CORE["  ⬡  INTELLIGENCE CORE"]
        direction TB

        subgraph INGEST_PIPE["  Ingestion Pipeline"]
            PARSE["◈  Document Parser\n─────────────────\nMulti-format extraction\nPDF · DOCX · MD · TXT"]
            DOMAIN["◈  Domain Classifier\n─────────────────\n16 domain entity types\nRelation schema tuning"]
        end

        subgraph RETRIEVAL["  Semantic Retrieval Engine"]
            KGE["◈  Knowledge Graph Engine\n──────────────────────────\nEntity · Relation extraction\nHybrid retrieval orchestration\nMulti-turn context management"]
        end

        subgraph AI_SVC["  AI Services"]
            direction LR
            LLM_SVC["◈  Language Reasoning\n──────────────────\nGeneration · Synthesis\nDomain prompt injection\nCitation enforcement"]
            VEC_SVC["◈  Semantic Encoding\n──────────────────\n1536-dim dense vectors\nCosine similarity search\nBatch normalization"]
        end
    end

    subgraph STORAGE["  ⬡  PERSISTENCE LAYER"]
        direction LR
        GRAPH_DB[("◈  Graph Store\n────────────────\nEntity nodes\nRelation edges\nSchema-aware queries")]
        VECTOR_IDX[("◈  Vector Index\n────────────────\nApproximate NN search\nDocument embeddings\nKV metadata cache")]
        DOC_STORE[("◈  Document Vault\n────────────────\nRaw source files\nIngestion audit log\nPipeline state")]
    end

    subgraph EXT_AI["  ⬡  EXTERNAL AI INFERENCE  ─ ─ ─ ─ (managed cloud)"]
        direction LR
        LLM_API["◈  LLM Inference API\n──────────────────\nAuto function-calling\nInstruction following\nContext synthesis"]
        EMB_API["◈  Embedding API\n──────────────────\nSemantic representation\nMultilingual support\nDimensionality control"]
    end

    %% ── Flow: Ingestion ──────────────────────────────────────────
    WEB  -->|"upload / ingest trigger"| GW
    EXT  -->|"REST"| GW
    GW   -->|"POST /ingest\nPOST /ingest/upload"| PARSE
    PARSE -->|"extracted text"| DOMAIN
    DOMAIN -->|"typed chunks"| KGE
    PARSE -->|"persist source"| DOC_STORE

    %% ── Flow: Query / Chat ───────────────────────────────────────
    GW   -->|"POST /query\nPOST /chat"| KGE

    %% ── Intelligence Core internals ──────────────────────────────
    KGE  -->|"LLM call"| LLM_SVC
    KGE  -->|"embed query"| VEC_SVC

    %% ── Storage I/O ──────────────────────────────────────────────
    KGE  <-->|"graph read/write"| GRAPH_DB
    KGE  <-->|"vector search\nKV lookup"| VECTOR_IDX

    %% ── External AI ──────────────────────────────────────────────
    LLM_SVC -->|"inference request"| LLM_API
    VEC_SVC -->|"embedding request"| EMB_API

    %% ── Health ───────────────────────────────────────────────────
    GW   -.->|"GET /health\nconnectivity probe"| GRAPH_DB

    %% ── Styles ───────────────────────────────────────────────────
    classDef layer fill:#0f172a,stroke:#334155,color:#cbd5e1,rx:8
    classDef node fill:#1e293b,stroke:#475569,color:#e2e8f0,rx:6
    classDef storage fill:#172033,stroke:#3b4f6b,color:#93c5fd,rx:6
    classDef extai fill:#1a1225,stroke:#6d28d9,color:#c4b5fd,rx:6
    classDef gateway fill:#0c1a12,stroke:#166534,color:#86efac,rx:6

    class GW gateway
    class WEB,EXT,PARSE,DOMAIN,KGE,LLM_SVC,VEC_SVC node
    class GRAPH_DB,VECTOR_IDX,DOC_STORE storage
    class LLM_API,EMB_API extai
