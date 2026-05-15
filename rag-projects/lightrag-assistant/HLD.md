flowchart TD
    subgraph Client["Client Layer"]
        FE["React SPA\n(Vite :5173 dev / static prod)"]
        CLI["curl / API client"]
    end

    subgraph Backend["Backend — FastAPI :8000"]
        MW["CORS Middleware"]

        subgraph Routers["Routers"]
            R1["POST /ingest\n(folder scan)"]
            R2["POST /ingest/upload\n(multipart upload)"]
            R3["POST /query\n(one-shot Q&A)"]
            R4["POST /chat\n(multi-turn, stateless)"]
            R5["GET /health"]
        end

        subgraph Ingestion["ingestion.py"]
            EXT["extract_text()\nPDF · DOCX · MD · TXT"]
        end

        subgraph Engine["rag_engine.py — LightRAG singleton"]
            LRAG["LightRAG.ainsert()\nLightRAG.aquery()"]
            LLM["gemini_llm_func()\ngemini-2.5-flash"]
            EMB["gemini_embedding_func()\ngemini-embedding-001 @ 1536d"]
        end

        subgraph Domain["domain.py"]
            ENT["Insurance entity types\n16 Vietnamese types"]
            PROMPT["Domain system prompt\n(Vietnamese, citation rules)"]
        end

        CFG["config.py / .env\nSettings (pydantic-settings)"]
    end

    subgraph Storage["Storage Layer"]
        NEO4J[("Neo4j\nGraph DB\nEntities + Relations")]
        FS[("Local filesystem\nrag_storage/\nVector store · KV store · Doc status")]
        DOCS[("data/documents/\nSource files")]
    end

    subgraph Gemini["Google Gemini API"]
        GLLM["LLM\ngemini-2.5-flash\nAFC max 10 calls"]
        GEMB["Embeddings\ngemini-embedding-001"]
    end

    %% Client → Backend
    FE -->|"HTTP (dev proxy /api/*)"| MW
    CLI -->|"HTTP"| MW
    MW --> Routers

    %% Ingest flow
    R1 --> EXT
    R2 --> EXT
    EXT --> DOCS
    EXT --> LRAG

    %% Query / Chat flow
    R3 --> LRAG
    R4 --> LRAG

    %% LightRAG internals
    LRAG --> LLM
    LRAG --> EMB
    Domain --> LRAG

    %% Storage
    LRAG <-->|"graph read/write"| NEO4J
    LRAG <-->|"vector + KV"| FS

    %% External API
    LLM -->|"google-genai SDK"| GLLM
    EMB -->|"google-genai SDK"| GEMB

    %% Health check
    R5 -->|"driver.verify_connectivity()"| NEO4J

    CFG -.->|"env vars"| Backend
