# Company Policy Assistant – Agentic House

An intelligent question-answering system for company policies and regulations, built with **Graph RAG** (Retrieval-Augmented Generation with knowledge graph). Unlike traditional search systems, Graph RAG understands the **relationships** between policies, departments, roles, and processes.

---

## System Architecture

### System Overview

```mermaid
graph TB
    classDef userLayer   fill:#0f172a,stroke:#38bdf8,stroke-width:2px,color:#e2e8f0
    classDef apiLayer    fill:#0f172a,stroke:#818cf8,stroke-width:2px,color:#e2e8f0
    classDef coreLayer   fill:#0f172a,stroke:#a78bfa,stroke-width:2px,color:#e2e8f0
    classDef storeLayer  fill:#0f172a,stroke:#34d399,stroke-width:2px,color:#e2e8f0
    classDef aiLayer     fill:#0f172a,stroke:#fb923c,stroke-width:2px,color:#e2e8f0
    classDef subgraphBg  fill:#1e293b,stroke:#334155,color:#94a3b8

    subgraph USER["  User Layer"]
        Chat["💬 Conversational Interface"]:::userLayer
        GraphViz["🕸️ Knowledge Graph Viewer"]:::userLayer
        SourceRef["📄 Source Citations"]:::userLayer
    end

    subgraph APP["  Application Layer"]
        Gateway["🔀 API Gateway\nSession · Chat · Admin · Graph"]:::apiLayer

        subgraph QUERY["  Query Engine"]
            LocalSearch["🔍 Precise Search\nEntity-aware retrieval"]:::coreLayer
            GlobalSearch["🌐 Holistic Search\nCommunity-based synthesis"]:::coreLayer
        end

        subgraph INDEX["  Indexing Engine"]
            Pipeline["⚙️ Document Pipeline\nParse → Extract → Embed → Cluster → Summarize"]:::coreLayer
        end
    end

    subgraph KNOW["  Knowledge Layer"]
        GraphStore[("🗄️ Knowledge Graph\nEntities · Relations · Communities")]:::storeLayer
        VecSearch[("⚡ Semantic Index\nDense vector search")]:::storeLayer
    end

    subgraph AI["  AI Foundation"]
        LLM["🤖 Language Model\nExtract · Classify · Generate"]:::aiLayer
        Embedder["🧬 Embedding Model\nSemantic representation"]:::aiLayer
    end

    Documents(["📁 Policy Documents\nPDF · DOCX · TXT"])

    Chat & GraphViz & SourceRef -->|REST / JSON| Gateway
    Gateway --> LocalSearch & GlobalSearch
    Gateway --> Pipeline
    LocalSearch & GlobalSearch --> GraphStore & VecSearch & LLM
    Pipeline -->|ingest| Documents
    Pipeline --> GraphStore & VecSearch & LLM & Embedder
    LocalSearch & GlobalSearch --> Embedder
    GraphStore <-->|read / write| VecSearch
```

### Indexing Pipeline (5 Stages)

```mermaid
flowchart LR
    Docs["Documents\nPDF / DOCX / TXT"]

    subgraph S1["Stage 1"]
        Parse["Parse & Chunk\ndocument_parser\ntext_splitter"]
    end

    subgraph S2["Stage 2"]
        Extract["Extraction\nEntities + Relations\nGemini LLM"]
    end

    subgraph S3["Stage 3"]
        EmbChunk["Embed Chunks\nGemini Embeddings\n3072-dim"]
    end

    subgraph S4["Stage 4"]
        Louvain["Community Detection\npython-louvain"]
    end

    subgraph S5["Stage 5"]
        Summarize["Summarize Community\nGemini LLM + Embed"]
    end

    Neo4j[("Neo4j\nGraph Store")]

    Docs --> S1 --> S2 --> S3 --> S4 --> S5
    S2 -- "Entity & Relation nodes" --> Neo4j
    S3 -- "PolicyChunk + embedding" --> Neo4j
    S4 -- "community_id labels" --> Neo4j
    S5 -- "Community summary + embedding" --> Neo4j
```

### Query Flow (LOCAL / GLOBAL)

```mermaid
flowchart TD
    Q(["Employee"])
    Classify["Query Classification\nGemini LLM"]
    Embed["Embed query\nGemini Embeddings"]

    subgraph LOCAL["LOCAL search"]
        VecChunk["Vector search\nTopK PolicyChunks\n(Neo4j cosine)"]
        Cypher["Cypher 2-hop traversal\nEntity neighborhood"]
        LocalCtx["Build Context\nchunks + entities + triples"]
    end

    subgraph GLOBAL["GLOBAL search"]
        VecComm["Vector search\nTopK Community summaries\n(Neo4j cosine)"]
        GlobalCtx["Build Context\ncommunity summaries + sample chunks"]
    end

    Generate["Gemini 2.5 Flash\nGenerate Answer in Vietnamese"]
    Response(["ChatResponse\nreply · sources · graph_data · query_type"])

    Q --> Classify & Embed
    Classify -- "LOCAL" --> VecChunk
    Classify -- "GLOBAL" --> VecComm
    Embed --> VecChunk & VecComm
    VecChunk --> Cypher --> LocalCtx --> Generate
    VecComm --> GlobalCtx --> Generate
    Generate --> Response
```

### Query Types

| Type | When | How |
|------|------|-----|
| **LOCAL** | Specific questions (number of vacation days, dress code by department) | Vector search chunks → Cypher 2-hop traversal → answer with citations |
| **GLOBAL** | General questions, summaries, policy comparisons | Vector search community summaries → synthesized answer |

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | FastAPI + Uvicorn (Python 3.12) |
| LLM | Google Gemini 2.5 Flash |
| Embeddings | `models/gemini-embedding-exp-03-07` (3072 dims) |
| Graph + Vector Store | **Neo4j 5** (replaces both ChromaDB + NetworkX) |
| Community Detection | python-louvain (results stored in Neo4j) |
| Frontend | React 18 + TypeScript + Vite + Tailwind CSS |
| State | Zustand |
| Container | Docker + Docker Compose |

---

## Project Structure

```
graphrag-assistant/
├── backend/
│   ├── app/
│   │   ├── main.py                    # FastAPI app + service initialization
│   │   ├── config.py                  # Configuration from .env
│   │   ├── dependencies.py            # FastAPI dependency injection
│   │   ├── api/routes/
│   │   │   ├── session.py             # POST/DELETE /session
│   │   │   ├── chat.py                # POST /chat, GET /chat/{id}/history
│   │   │   ├── admin.py               # POST /index, GET /stats, POST /ingest
│   │   │   └── graph.py               # GET /graph/nodes, GET /graph/community/{id}
│   │   ├── models/                    # Pydantic schemas
│   │   ├── services/
│   │   │   ├── llm_service.py         # Gemini: extract, classify, answer
│   │   │   ├── embedding_service.py   # Gemini embeddings
│   │   │   ├── neo4j_store.py         # Neo4j: graph + vector index (KEY FILE)
│   │   │   ├── indexing_service.py    # 5-stage indexing pipeline
│   │   │   ├── graph_rag_service.py   # LOCAL / GLOBAL query pipeline
│   │   │   └── session_service.py     # In-memory sessions
│   │   ├── prompts/                   # Vietnamese prompts
│   │   └── utils/                     # Document parser + text splitter
│   ├── data/raw/
│   │   ├── handbooks/                 # Employee handbooks
│   │   ├── hr_policies/               # HR policies
│   │   ├── conduct/                   # Code of conduct, dress code
│   │   ├── benefits/                  # Benefits
│   │   └── procedures/                # Procedures
│   ├── scripts/
│   │   └── build_graph_index.py       # Offline indexing CLI
│   ├── requirements.txt
│   ├── Dockerfile
│   └── .env.example
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── chat/                  # ChatWindow, ChatInput, MessageBubble
│   │   │   ├── layout/                # AppShell, Header
│   │   │   └── sources/               # SourcesPanel, SourceCard
│   │   ├── hooks/                     # useChat, useSession, useScrollToBottom
│   │   ├── store/                     # Zustand (chat + session)
│   │   ├── api/                       # Axios API layer
│   │   └── types/                     # TypeScript interfaces
│   ├── package.json
│   ├── Dockerfile
│   └── nginx.conf
└── docker-compose.yml
```

---

## Quick Start

### Requirements

- Python 3.12+
- Node.js 20+
- Docker & Docker Compose
- Google API Key (with access to Gemini)

### 1. Environment Configuration

```bash
cd backend
cp .env.example .env
```

Edit `.env` and fill in API key:

```ini
GOOGLE_API_KEY=your_google_api_key_here
```

### 2. Install Dependencies

```bash
python -m venv venv
source venv/bin/activate   # macOS/Linux
pip install -r requirements.txt
```

### 3. Start Neo4j

```bash
docker compose up neo4j -d
# Wait for Neo4j to be ready (~30 seconds)
# Neo4j Browser UI: http://localhost:7474
```

### 4. Add Policy Documents

Place PDF, DOCX, or TXT files in these folders:

```
backend/data/raw/handbooks/       ← Employee handbooks
backend/data/raw/hr_policies/     ← HR policies (vacation, WFH...)
backend/data/raw/conduct/         ← Code of conduct, dress code
backend/data/raw/benefits/        ← Benefits, allowances
backend/data/raw/procedures/      ← Procedures for requests, onboarding...
```

> Pre-loaded with 6 sample Vietnamese documents for testing.

### 5. Build Knowledge Graph Index

```bash
cd backend
python -m scripts.build_graph_index
```

Expected output:
```
Initializing services...
Starting indexing pipeline...
  parsing [N/N]
  extracting [N/N]
  embedding_chunks [N/N]
  community_detection [1/1]
  summarizing [K/K]

=== Indexing Complete ===
  Chunks:      N
  Entities:   M
  Relations:    P
  Communities: K
  Summaries:    K
```

### 6. Start Backend

```bash
uvicorn app.main:app --reload --port 8000
```

Verify: `GET http://localhost:8000/health` → `{"status": "ok"}`

### 7. Start Frontend

```bash
cd ../frontend
npm install
npm run dev
```

Open **http://localhost:5173**

---

## Docker (Recommended for Production)

```bash
# Create .env at root directory
echo "GOOGLE_API_KEY=your_key_here" > .env

docker compose up --build
```

| Service | URL |
|---------|-----|
| Frontend | http://localhost:5173 |
| Backend API | http://localhost:8000 |
| Neo4j Browser | http://localhost:7474 |
| API Docs | http://localhost:8000/docs |

> **Note:** After Docker starts, you still need to run the indexing pipeline:
> ```bash
> docker compose exec backend python -m scripts.build_graph_index
> ```

---

## Example Questions

**LOCAL** (specific questions):
- `"What can the IT Department wear on Monday?"`
- `"How many vacation days does an employee get after 5 years of service?"`
- `"How is overtime pay calculated on holidays?"`
- `"What are the steps in the maternity leave request process?"`

**GLOBAL** (general questions):
- `"Summarize the company's entire benefits policy"`
- `"Compare vacation rights across employee levels"`
- `"What policies does the company have to support remote work?"`

---

## Configuration

All settings in `backend/.env`:

| Variable | Default | Description |
|----------|---------|-------------|
| `GOOGLE_API_KEY` | — | **Required.** Google Gemini API key |
| `GEMINI_MODEL` | `gemini-2.5-flash` | LLM model |
| `GEMINI_EMBEDDING_MODEL` | `models/gemini-embedding-exp-03-07` | Embedding model |
| `EMBEDDING_DIM` | `3072` | Embedding dimension |
| `NEO4J_URI` | `bolt://localhost:7687` | Neo4j connection |
| `NEO4J_USER` | `neo4j` | Neo4j username |
| `NEO4J_PASSWORD` | `techviet2024` | Neo4j password |
| `CHUNK_SIZE` | `2800` | Characters per chunk (~700 tokens in Vietnamese) |
| `MAX_LOCAL_CHUNKS` | `8` | Top-K chunks for LOCAL search |
| `MAX_COMMUNITY_SUMMARIES` | `5` | Top-K summaries for GLOBAL search |
| `GRAPH_HOP_DEPTH` | `2` | Cypher traversal depth |

---

## Neo4j Schema

### Node Labels
- `PolicyChunk`: Text segments from documents (with embedding)
- `Entity`: Knowledge entities (POLICY, RULE, DEPARTMENT, ROLE, PROCEDURE, BENEFIT, EXCEPTION)
- `Community`: Topic groups (with embedding of summary)

### Relationship Types
- `MENTIONS`: PolicyChunk → Entity
- `BELONGS_TO_COMMUNITY`: Entity → Community
- `APPLIES_TO`, `EXEMPTS`, `OVERRIDES`, `REFERENCES`, `REQUIRES`, `PROVIDES`, `ENFORCED_BY`: Entity → Entity

### Vector Indexes
- `policy_chunks` on `PolicyChunk.embedding` (cosine, 3072 dims)
- `community_summaries` on `Community.embedding` (cosine, 3072 dims)
