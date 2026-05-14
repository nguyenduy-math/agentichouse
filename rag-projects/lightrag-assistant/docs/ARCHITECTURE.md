# Architecture — Vietnam Insurance Assistant

Mermaid diagrams of the system structure and its main runtime flows.

---

## 1. System components

How the pieces fit together at runtime.

```mermaid
flowchart TB
    subgraph Browser["🌐 Browser"]
        SPA["React + Vite chatbox SPA<br/>(ChatBox.jsx, api.js)"]
    end

    subgraph Backend["⚙️ FastAPI backend (uvicorn)"]
        direction TB
        Routers["Routers<br/>/health · /ingest · /query · /chat<br/>(also under /api)"]
        Lifespan["Lifespan<br/>init_rag / shutdown_rag"]
        RagEngine["rag_engine.py<br/>LightRAG instance + Gemini wrappers"]
        Ingestion["ingestion.py<br/>PDF / DOCX / MD / TXT → text"]
        LightRAG["LightRAG core<br/>chunking · entity extraction · retrieval"]
        Routers --> RagEngine
        Routers --> Ingestion
        Lifespan --> RagEngine
        RagEngine --> LightRAG
        Ingestion --> RagEngine
    end

    subgraph Storage["💾 Persistence"]
        Neo4j[("Neo4j<br/>knowledge graph<br/>entities + relations")]
        FileStore[("rag_storage/<br/>KV store + vector store<br/>JSON + NanoVectorDB")]
    end

    subgraph Google["☁️ Google Gemini API"]
        LLM["gemini-2.5-flash<br/>(LLM)"]
        Embed["gemini-embedding-001<br/>(embeddings, 1536-d)"]
    end

    Docs["📄 backend/data/documents/<br/>Vietnamese insurance files"]

    SPA -- "HTTP /api/* (Vite proxy → :8000)" --> Routers
    Ingestion -- "reads" --> Docs
    LightRAG -- "graph read/write" --> Neo4j
    LightRAG -- "chunks + vectors" --> FileStore
    RagEngine -- "generate_content" --> LLM
    RagEngine -- "embed_content" --> Embed
```

---

## 2. Startup & shutdown lifecycle

LightRAG needs async initialization — wired into FastAPI's `lifespan`.

```mermaid
sequenceDiagram
    participant U as uvicorn
    participant M as app.main (lifespan)
    participant R as rag_engine
    participant LR as LightRAG
    participant N as Neo4j
    participant F as rag_storage/

    U->>M: startup
    M->>R: init_rag()
    R->>R: set NEO4J_* env vars from settings
    R->>LR: LightRAG(graph_storage="Neo4JStorage",<br/>llm/embedding funcs, addon_params)
    R->>LR: await initialize_storages()
    LR->>N: connect (bolt://localhost:7687)
    LR->>F: load KV + vector store files
    R->>LR: await initialize_pipeline_status()
    LR-->>R: ready
    R-->>M: LightRAG instance
    M-->>U: app ready ✅

    Note over U,F: ... serving requests ...

    U->>M: shutdown
    M->>R: shutdown_rag()
    R->>LR: await finalize_storages()
    LR->>N: close driver
    LR->>F: flush files
```

---

## 3. Document ingestion flow

`POST /ingest` — builds the knowledge graph from documents.

```mermaid
sequenceDiagram
    actor User
    participant API as /ingest router
    participant ING as ingestion.py
    participant FS as data/documents/
    participant LR as LightRAG
    participant G as Gemini API
    participant N as Neo4j
    participant V as rag_storage/

    User->>API: POST /ingest { folder? }
    API->>ING: collect_documents(folder)
    ING->>FS: rglob + extract_text (pdf/docx/md/txt)
    FS-->>ING: raw text per file
    ING-->>API: texts[], sources[], skipped[]
    API->>LR: await ainsert(texts, file_paths=sources)

    rect rgb(235, 244, 255)
    note over LR,G: LightRAG pipeline
    LR->>LR: chunk documents
    LR->>G: embed_content(chunks)
    G-->>LR: chunk vectors
    LR->>G: generate_content (entity/relation extraction, Vietnamese)
    G-->>LR: entities + relationships
    end

    LR->>N: upsert entity & relation nodes/edges
    LR->>V: store chunks + vectors + doc status
    LR-->>API: done
    API-->>User: { ingested_files, skipped_files, count }
```

---

## 4. Chat / query flow

`POST /chat` — multi-turn, history owned by the browser (stateless server).

```mermaid
sequenceDiagram
    actor User
    participant SPA as React ChatBox
    participant API as /chat router
    participant LR as LightRAG
    participant N as Neo4j
    participant V as rag_storage/
    participant G as Gemini API

    User->>SPA: types question
    SPA->>SPA: append user turn to messages
    SPA->>API: POST /api/chat { message, history, mode }
    API->>API: build QueryParam(mode, conversation_history,<br/>history_turns, user_prompt=DOMAIN_USER_PROMPT)
    API->>LR: await aquery(message, param)

    rect rgb(235, 244, 255)
    note over LR,G: retrieval + generation
    LR->>G: embed_content(query)
    G-->>LR: query vector
    LR->>V: vector search → relevant chunks
    LR->>N: graph traversal → entities + relations
    LR->>G: generate_content(context + history + domain prompt)
    G-->>LR: grounded Vietnamese answer
    end

    LR-->>API: answer text
    API-->>SPA: { answer, history (with this turn), mode }
    SPA->>SPA: append assistant turn to messages
    SPA-->>User: render answer
```

---

## 5. Storage model

What lives where, and what a reset touches.

```mermaid
flowchart LR
    subgraph LR_Engine["LightRAG"]
        KG["knowledge graph"]
        VEC["chunks + embeddings"]
        KV["doc metadata · status · LLM cache"]
    end

    subgraph Neo4jVol["Neo4j (Docker volume: neo4j_data/)"]
        Entities["(:entity) nodes"]
        Relations["[:relation] edges"]
    end

    subgraph Files["backend/rag_storage/ (gitignored)"]
        VDB["vdb_*.json — NanoVectorDB"]
        KVJSON["kv_store_*.json"]
        DocStatus["doc_status.json"]
    end

    KG --> Entities
    KG --> Relations
    VEC --> VDB
    KV --> KVJSON
    KV --> DocStatus

    Note["⚠️ Embedding model + dim (1536) are baked in<br/>at first ingest. Changing them = delete<br/>rag_storage/ + docker compose down -v, then re-ingest."]
    Files -.-> Note
    Neo4jVol -.-> Note
```

---

## 6. Request routing

Every router is mounted twice so both direct calls and the Vite proxy work.

```mermaid
flowchart LR
    direction LR
    Dev["Dev: browser → http://localhost:5173"]
    Prod["Prod: browser → http://127.0.0.1:8000/"]

    Dev -->|"/api/*"| Vite["Vite dev server :5173"]
    Vite -->|"proxy /api → :8000"| FastAPI
    Prod -->|"static files + /api/*"| FastAPI

    subgraph FastAPI["FastAPI :8000"]
        RootMount["routers at /*<br/>(curl / PowerShell testing)"]
        ApiMount["routers at /api/*<br/>(frontend)"]
        Static["StaticFiles mount /<br/>(serves frontend/dist if built)"]
    end

    Curl["curl / Invoke-RestMethod"] -->|"/health /ingest /query /chat"| RootMount
```
