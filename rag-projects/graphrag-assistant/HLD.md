# High-Level Design — GraphRAG Policy Assistant

This document captures the high-level design of the **Agentic House Policy Assistant**, a Graph-RAG system that answers questions about company HR policies in Vietnamese.

All diagrams are written in [Mermaid](https://mermaid.js.org/) and render directly on GitHub / VS Code.

> Source files referenced:
> - Backend entrypoint: [backend/app/main.py](../backend/app/main.py)
> - Indexing pipeline: [backend/app/services/indexing_service.py](../backend/app/services/indexing_service.py)
> - Query engine: [backend/app/services/graph_rag_service.py](../backend/app/services/graph_rag_service.py)
> - Graph + vector store: [backend/app/services/neo4j_store.py](../backend/app/services/neo4j_store.py)
> - Deployment: [docker-compose.yml](../docker-compose.yml)

---

## 1. System Context (C4 Level 1)

Shows the system as a single box and the external actors / systems it talks to.

```mermaid
flowchart LR
    user(["👤 Employee / HR User"])
    admin(["🛠️ Admin / Knowledge Engineer"])

    subgraph SUT["GraphRAG Policy Assistant"]
        app["Web App + REST API\n(FastAPI · React · Neo4j)"]
    end

    gemini["☁️ Google Gemini API\n(LLM + Embeddings)"]
    docs[["📁 Policy Documents\nPDF · DOCX · TXT"]]
    browser["Neo4j Browser\n(ops / debugging)"]

    user -- "asks policy questions\n(HTTPS · React UI)" --> app
    admin -- "uploads docs, triggers indexing" --> app
    admin -- "inspects graph" --> browser
    app -- "extract · classify · generate · embed" --> gemini
    app -- "reads at ingest time" --> docs
    browser -- "Bolt" --> app
```

---

## 2. Deployment View (Docker Compose)

Runtime topology as defined in [docker-compose.yml](../docker-compose.yml).

```mermaid
flowchart TB
    classDef ext fill:#1e293b,stroke:#fb923c,color:#e2e8f0

    user["🌐 Browser"]

    subgraph host["🖥️ Docker Host"]
        subgraph fe["frontend (nginx :80)"]
            react["React 18 + Vite build\nstatic assets · /api proxy"]
        end

        subgraph be["backend (uvicorn :8000)"]
            fastapi["FastAPI app\nlifespan singletons:\nSessionService · EmbeddingService\nLLMService · IndexingService\nGraphRAGService · Neo4jStore"]
            volraw[["volume: ./backend/data\n(raw policy docs)"]]
        end

        subgraph db["neo4j 5 (:7474 / :7687)"]
            graph["Graph DB + Vector Indexes\n(APOC plugin)"]
            volneo[["volume: neo4j_data"]]
        end
    end

    gemini["☁️ Google Gemini API"]:::ext

    user -- ":5173 (HTTP)" --> fe
    fe -- "/api/v1/* reverse proxy" --> be
    be -- "Bolt :7687" --> db
    be -- "HTTPS REST" --> gemini
    be --- volraw
    db --- volneo
```

**Healthchecks & startup ordering**
- `neo4j` exposes a `cypher-shell RETURN 1` healthcheck; `backend` waits on `service_healthy`.
- `backend` exposes `GET /health`; `frontend` waits on it before starting nginx.

---

## 3. Container / Module Decomposition (C4 Level 2)

```mermaid
flowchart TB
    classDef api fill:#0f172a,stroke:#818cf8,color:#e2e8f0
    classDef svc fill:#0f172a,stroke:#a78bfa,color:#e2e8f0
    classDef ext fill:#0f172a,stroke:#fb923c,color:#e2e8f0
    classDef store fill:#0f172a,stroke:#34d399,color:#e2e8f0

    subgraph FE["Frontend (React + Zustand)"]
        UI["Components\nAppShell · ChatWindow\nGraphPanel · SourcesPanel"]
        Hooks["Hooks\nuseChat · useSession"]
        Store["Zustand store\nchat + session"]
        ApiL["API layer (axios)\nclient · chatApi · sessionApi"]
    end

    subgraph BE["Backend (FastAPI)"]
        subgraph Routes["API routes (/api/v1)"]
            R1["session.py"]:::api
            R2["chat.py"]:::api
            R3["admin.py"]:::api
            R4["graph.py"]:::api
        end

        subgraph Services["Service layer (singletons via app.state)"]
            Sess["SessionService\nin-mem + TTL cleanup"]:::svc
            LLM["LLMService\nextract · classify · summarize · generate"]:::svc
            Emb["EmbeddingService\nGemini embeddings"]:::svc
            Idx["IndexingService\n5-stage pipeline"]:::svc
            RAG["GraphRAGService\nLOCAL / GLOBAL query"]:::svc
            Store["Neo4jStore\nschema · upsert · vector · traversal"]:::store
        end

        subgraph Utils["Utils & prompts"]
            Parse["document_parser\ntext_splitter"]
            Prompts["extraction · rag · system\nVietnamese prompts"]
        end
    end

    Neo4j[("Neo4j 5")]:::store
    Gemini["Google Gemini API"]:::ext

    UI --> Hooks --> Store
    Hooks --> ApiL
    ApiL -- "REST /api/v1/*" --> Routes

    R1 --> Sess
    R2 --> RAG
    R3 --> Idx
    R3 --> Store
    R4 --> Store

    RAG --> Sess
    RAG --> LLM
    RAG --> Emb
    RAG --> Store

    Idx --> LLM
    Idx --> Emb
    Idx --> Store
    Idx --> Parse

    LLM --> Prompts
    LLM --> Gemini
    Emb --> Gemini
    Store --> Neo4j
```

---

## 4. Knowledge Data Model (Neo4j schema)

Derived from [neo4j_store.py:34-64](../backend/app/services/neo4j_store.py#L34-L64) and [README — Schema Neo4j](../README.md#schema-neo4j).

```mermaid
erDiagram
    POLICYCHUNK ||--o{ MENTIONS : "MENTIONS"
    MENTIONS }o--|| ENTITY : "→"
    ENTITY ||--o{ ENTITY_REL : "Entity↔Entity"
    ENTITY }o--|| COMMUNITY : "THUOC_CONG_DONG"

    POLICYCHUNK {
        string id PK
        string text
        string source_file
        string doc_type
        int    page_number
        int    chunk_index
        vector embedding "3072-dim, cosine"
        list   entity_names
    }

    ENTITY {
        string name PK
        string type "CHINH_SACH · QUY_TAC · PHONG_BAN · VAI_TRO · QUY_TRINH · QUYEN_LOI · NGOAI_LE"
        string description
        int    community_id
    }

    COMMUNITY {
        int    community_id PK
        string summary
        vector embedding "3072-dim, cosine"
        int    node_count
    }

    ENTITY_REL {
        string type "AP_DUNG_CHO · MIEN_TRU · GHI_DE · THAM_CHIEU · YEU_CAU · CUNG_CAP · THUC_THI_BOI"
    }
```

**Constraints & indexes**

| Object | Type | Purpose |
|--------|------|---------|
| `entity_name` | UNIQUE constraint on `Entity.name` | de-duplicates entities by canonical name |
| `chunk_id` | UNIQUE constraint on `PolicyChunk.id` | idempotent upsert during indexing |
| `community_id` | UNIQUE constraint on `Community.community_id` | one node per Louvain community |
| `policy_chunks` | VECTOR INDEX on `PolicyChunk.embedding` (cosine, 3072 dims) | LOCAL search |
| `community_summaries` | VECTOR INDEX on `Community.embedding` (cosine, 3072 dims) | GLOBAL search |

---

## 5. API Surface

```mermaid
flowchart LR
    classDef get fill:#064e3b,stroke:#34d399,color:#ecfdf5
    classDef post fill:#1e3a8a,stroke:#60a5fa,color:#eff6ff
    classDef del fill:#7f1d1d,stroke:#f87171,color:#fee2e2

    subgraph Session["/api/v1/session"]
        S1["POST /\ncreate session"]:::post
        S2["DELETE /{id}\nend session"]:::del
    end

    subgraph Chat["/api/v1/chat"]
        C1["POST /\nsend message\n→ reply · sources · graph_data"]:::post
        C2["GET /{id}/history"]:::get
    end

    subgraph Admin["/api/v1/admin"]
        A1["POST /ingest\nupload doc"]:::post
        A2["POST /index\ntrigger pipeline (async)"]:::post
        A3["GET /index/status"]:::get
        A4["GET /stats"]:::get
    end

    subgraph Graph["/api/v1/graph"]
        G1["GET /nodes\nall entities + edges"]:::get
        G2["GET /community/{id}\nsummary + members"]:::get
    end

    subgraph Sys["System"]
        H["GET /health"]:::get
        D["GET /docs (Swagger)"]:::get
    end
```

---

## 6. Sequence — Indexing Pipeline

End-to-end ingestion of policy docs into the graph. Triggered by `POST /api/v1/admin/index` (async task) or the offline CLI `scripts/build_graph_index.py`.

```mermaid
sequenceDiagram
    autonumber
    participant Admin
    participant API as POST /admin/index
    participant Idx as IndexingService
    participant FS as Filesystem<br/>(data/raw)
    participant LLM as LLMService<br/>(Gemini)
    participant Emb as EmbeddingService<br/>(Gemini)
    participant N4J as Neo4jStore

    Admin->>API: trigger
    API->>Idx: run_full_pipeline (background task)
    Idx->>N4J: clear() — wipe graph

    rect rgb(30,41,59)
    note right of Idx: Stage 1 — Parse & chunk
    Idx->>FS: walk handbooks/hr_policies/conduct/benefits/procedures
    FS-->>Idx: PDF/DOCX/TXT pages
    Idx->>Idx: split_text (≈2800 chars/chunk)
    end

    rect rgb(30,41,59)
    note right of Idx: Stage 2 — Extract entities + relations
    loop for each chunk (batched)
        Idx->>LLM: extract_entities_and_relations(text)
        LLM-->>Idx: {entities, relations}
        Idx->>N4J: upsert_entity × N
        Idx->>N4J: upsert_relationship × M
    end
    end

    rect rgb(30,41,59)
    note right of Idx: Stage 3 — Embed chunks
    loop for each chunk
        Idx->>Emb: embed_documents([text])
        Emb-->>Idx: vector[3072]
        Idx->>N4J: upsert_chunk + link_chunk_to_entity (MENTIONS)
    end
    end

    rect rgb(30,41,59)
    note right of Idx: Stage 4 — Community detection (python-louvain)
    Idx->>N4J: get_all_entities_and_edges()
    Idx->>Idx: build networkx graph + best_partition
    loop for each entity
        Idx->>N4J: set_entity_community(name, comm_id)
    end
    end

    rect rgb(30,41,59)
    note right of Idx: Stage 5 — Summarize eligible communities (≥3 nodes)
    loop for each community
        Idx->>LLM: generate_community_summary(nodes, edges)
        LLM-->>Idx: summary text
        Idx->>Emb: embed_documents([summary])
        Idx->>N4J: upsert_community + THUOC_CONG_DONG edges
    end
    end

    Idx-->>API: IndexingResult (counts)
    API-->>Admin: status = completed
```

---

## 7. Chat Query (LOCAL)

The default path for specific, entity-grounded questions. Source: [`GraphRAGService._local_search`](../backend/app/services/graph_rag_service.py#L65-L84).

### 7a. Flowchart — conceptual view

```mermaid
flowchart TD
    classDef io     fill:#0f172a,stroke:#38bdf8,color:#e2e8f0
    classDef proc   fill:#0f172a,stroke:#a78bfa,color:#e2e8f0
    classDef decide fill:#1e293b,stroke:#facc15,color:#fef9c3

    Start([User question]):::io
    Classify{{"Specific or holistic?"}}:::decide
    Global[/"Holistic → GLOBAL path (§8)"/]:::io

    Retrieve["Retrieve relevant policy passages"]:::proc
    Expand["Expand with related entities\nand their relationships"]:::proc
    Compose["Compose grounded context"]:::proc
    Answer["Generate answer in Vietnamese"]:::proc
    Resp([Reply + citations + graph view]):::io

    Start --> Classify
    Classify -- holistic --> Global
    Classify -- specific --> Retrieve --> Expand --> Compose --> Answer --> Resp
```

### 7b. Sequence — timing view

```mermaid
sequenceDiagram
    autonumber
    participant FE as React UI
    participant API as POST /chat
    participant RAG as GraphRAGService
    participant Sess as SessionService
    participant LLM as LLMService
    participant Emb as EmbeddingService
    participant N4J as Neo4jStore

    FE->>API: {session_id, message}
    API->>RAG: process_message
    RAG->>Sess: get_session → history
    par classify + embed in parallel paths
        RAG->>LLM: classify_query(message)
        LLM-->>RAG: "LOCAL"
    and
        RAG->>Emb: embed_query(message)
        Emb-->>RAG: vector[3072]
    end

    RAG->>N4J: vector_search_chunks(emb, k=MAX_LOCAL_CHUNKS)
    N4J-->>RAG: top-K PolicyChunks (+ entity_names)
    RAG->>RAG: collect seed entities (max 20)
    RAG->>N4J: get_entity_neighborhood(seeds, depth=GRAPH_HOP_DEPTH)
    N4J-->>RAG: {entities, triples}

    RAG->>RAG: build_local_context(chunks + entities + triples)
    RAG->>LLM: generate(system_prompt, history, message)
    LLM-->>RAG: Vietnamese answer
    RAG->>Sess: append user + assistant messages
    RAG-->>API: ChatResponse{reply, sources, graph_data, query_type=LOCAL}
    API-->>FE: 200 OK
    FE->>FE: update store → render bubble + SourcesPanel + GraphPanel
```

---

## 8. Sequence — Chat Query (GLOBAL)

For holistic / comparative questions ("summarize all benefits").

```mermaid
sequenceDiagram
    autonumber
    participant FE as React UI
    participant RAG as GraphRAGService
    participant LLM as LLMService
    participant Emb as EmbeddingService
    participant N4J as Neo4jStore

    FE->>RAG: process_message
    RAG->>LLM: classify_query → "GLOBAL"
    RAG->>Emb: embed_query
    Emb-->>RAG: vector[3072]

    RAG->>N4J: vector_search_communities(emb, k=MAX_COMMUNITY_SUMMARIES)
    N4J-->>RAG: top community summaries
    RAG->>N4J: vector_search_chunks(emb, k=3)  ← grounding examples
    N4J-->>RAG: sample chunks

    RAG->>RAG: build_global_context(summaries + sample chunks)
    RAG->>LLM: generate
    LLM-->>RAG: synthesized answer
    RAG-->>FE: ChatResponse{query_type=GLOBAL, graph_data=null}
```

> GLOBAL path returns `graph_data=null` — the GraphPanel falls back to an empty / dimmed state.

---

## 9. State — Indexing Job Lifecycle

Tracked in `app.state.indexing_status` and polled by the UI via `GET /api/v1/admin/index/status`.

```mermaid
stateDiagram-v2
    [*] --> idle
    idle --> running : POST /admin/index
    running --> running : progress_callback(stage, done, total)
    running --> completed : pipeline returns IndexingResult
    running --> failed : exception → last_error set
    completed --> running : re-trigger
    failed --> running : re-trigger
    running --> running : POST while running → HTTP 409
```

Stages emitted by `progress_callback`:
`parsing` → `extracting` → `embedding_chunks` → `community_detection` → `summarizing`.

---

## 10. Frontend Component Tree & Data Flow

```mermaid
flowchart TB
    classDef cmp fill:#0f172a,stroke:#38bdf8,color:#e2e8f0
    classDef hk  fill:#0f172a,stroke:#a78bfa,color:#e2e8f0
    classDef st  fill:#0f172a,stroke:#34d399,color:#e2e8f0

    App["App.tsx"]:::cmp
    Shell["AppShell"]:::cmp
    Header["Header"]:::cmp
    Chat["ChatWindow"]:::cmp
    Bubble["MessageBubble[]"]:::cmp
    Input["ChatInput"]:::cmp
    Right["RightPanel"]:::cmp
    Sources["SourcesPanel · SourceCard"]:::cmp
    Graph["GraphPanel"]:::cmp

    useSession(["useSession"]):::hk
    useChat(["useChat"]):::hk
    useScroll(["useScrollToBottom"]):::hk

    chatStore[["chatStore (Zustand)\nmessages · loading\nactiveSources · activeGraphData"]]:::st
    sessStore[["sessionStore (Zustand)\nsessionId"]]:::st

    sessApi(["sessionApi"])
    chatApi(["chatApi"])
    BE["Backend /api/v1"]

    App --> Shell --> Header
    Shell --> Chat --> Bubble
    Chat --> Input
    Shell --> Right --> Sources
    Right --> Graph

    Header --> useSession
    Input --> useChat
    Chat --> useScroll

    useSession --> sessStore
    useSession --> sessApi --> BE
    useChat --> chatStore
    useChat --> sessStore
    useChat --> chatApi --> BE

    Sources -. reads .- chatStore
    Graph -. reads .- chatStore
    Bubble -. reads .- chatStore
```

---

## 11. Cross-cutting Concerns

| Concern | Where it lives | Notes |
|---|---|---|
| **Configuration** | [backend/app/config.py](../backend/app/config.py) + `.env` | Pydantic `Settings`; one source of truth |
| **DI / lifecycle** | [backend/app/main.py — lifespan](../backend/app/main.py#L47-L98) | Singletons attached to `app.state`; resolved via [dependencies.py](../backend/app/dependencies.py) |
| **CORS** | `main.create_app` | Allowed origins from `CORS_ORIGINS` |
| **Logging** | `structlog` across all services | Structured JSON logs |
| **Session TTL** | `SessionService.start_cleanup()` | Background task purges expired sessions |
| **Idempotent indexing** | `Neo4jStore` MERGE + `clear()` at pipeline start | Safe to re-run |
| **Rate limiting (LLM)** | `IndexingService` — `asyncio.sleep(1.0)` between batches | Avoid Gemini quota bursts |
| **Vector index dims** | `EMBEDDING_DIM` (default 3072) | Must match Gemini embedding model |

---

## 12. Open Considerations

These are not implemented but are natural extensions worth diagramming when added:

- **Auth** — currently no authentication; all routes are open. A reverse proxy or API key middleware would slot in front of the FastAPI app.
- **Session persistence** — sessions live in-process memory and are lost on restart. Redis would replace `SessionService` storage transparently.
- **Multi-tenant graphs** — single shared Neo4j database; a tenant property + filtered indexes would be needed for isolation.
- **Streaming responses** — `/chat` returns the full reply at once. SSE/WebSocket would change the sequence diagrams in §7–8.
