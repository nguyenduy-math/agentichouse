# Trợ lý Bảo hiểm Việt Nam — Vietnam Insurance Assistant

A retrieval-augmented assistant that answers questions about **Vietnamese insurance
documents** (policies, regulations, contracts, product terms).

- **RAG engine:** [LightRAG](https://github.com/HKUDS/LightRAG) — builds a knowledge graph from your documents
- **Graph storage:** Neo4j (local, via Docker) — browse the entity graph at `http://localhost:7474`
- **LLM + embeddings:** Google Gemini (`gemini-2.5-flash` + `gemini-embedding-001`)
- **Backend:** FastAPI service (`backend/`)
- **Frontend:** React + Vite chatbox SPA (`frontend/`)

The assistant answers in Vietnamese, grounds every answer in the ingested documents,
cites the source clause, and appends an "informational only" disclaimer.

---

## Architecture

```
documents ──▶ /ingest ──▶ LightRAG ──▶ entities + relations ──▶ Neo4j
                                   └──▶ chunks + embeddings ──▶ rag_storage/ (files)

browser (React chatbox) ──▶ /api/chat ──▶ FastAPI ──▶ LightRAG.aquery ──▶ Gemini
```

- The **knowledge graph** lives in Neo4j (Docker volume `neo4j_data/`).
- The **vector store + KV store** are file-based under `backend/rag_storage/`.
- The server is **stateless** — the browser holds the conversation history and sends it
  with each chat request.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for detailed Mermaid diagrams of the
components, startup lifecycle, ingestion flow, chat flow, and storage model.

---

## Prerequisites

- **Docker Desktop** (for Neo4j)
- **Python 3.10+**
- **Node.js 18+** (for the frontend)
- A **Gemini API key** — get one at <https://aistudio.google.com/apikey>

---

## Setup

All commands are PowerShell, run from the project root
(`rag-projects/lightrag-assistant/`).

### 1. Start Neo4j

The Neo4j password is read from the `NEO4J_PASSWORD` environment variable (falls back
to `please-change-me`). Set it to match what you'll put in `backend/.env`:

```powershell
$env:NEO4J_PASSWORD = "your-strong-password"
docker compose up -d
Start-Process http://localhost:7474   # log in as neo4j / your-strong-password
```

### 2. Backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt

Copy-Item .env.example .env
# Edit .env — set GEMINI_API_KEY and NEO4J_PASSWORD (must match step 1)
notepad .env
```

### 3. Frontend

```powershell
cd ..\frontend
npm install
```

---

## Running

Open three terminals (Neo4j from step 1 keeps running in the background).

**Terminal A — backend:**

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

**Terminal B — frontend:**

```powershell
cd frontend
npm run dev
# open http://localhost:5173
```

**Terminal C — ingest documents and test:**

```powershell
# Drop .pdf / .txt / .md / .docx files into backend/data/documents/ first, then:
Invoke-RestMethod http://127.0.0.1:8000/health
Invoke-RestMethod -Method Post http://127.0.0.1:8000/ingest `
  -ContentType "application/json" -Body '{}'

Invoke-RestMethod -Method Post http://127.0.0.1:8000/query `
  -ContentType "application/json" `
  -Body '{"question":"Phạm vi bảo hiểm của sản phẩm này là gì?","mode":"hybrid"}'
```

Then chat through the UI at <http://localhost:5173>, or use the interactive API docs
at <http://127.0.0.1:8000/docs>.

---

## API endpoints

| Method | Path             | Purpose                                                     |
|--------|------------------|-------------------------------------------------------------|
| GET    | `/health`        | Readiness — RAG engine + Neo4j connectivity                 |
| POST   | `/ingest`        | Ingest a server-side folder (`{"folder": null}` = default)  |
| POST   | `/ingest/upload` | Upload + ingest files (multipart `files`)                   |
| POST   | `/query`         | One-shot Q&A (`{question, mode, top_k?}`)                   |
| POST   | `/chat`          | Multi-turn chat (`{message, history, mode, history_turns?}`)|

Every endpoint is also served under `/api/...` (what the Vite dev proxy forwards to).

Query `mode` is one of `naive`, `local`, `global`, `hybrid` (default), `mix`.

---

## Production build

```powershell
cd frontend
npm run build          # emits frontend/dist/
```

When `frontend/dist/` exists, the FastAPI process serves the chatbox at
`http://127.0.0.1:8000/` — a single process for both API and UI, no CORS needed.

---

## Configuration (`backend/.env`)

| Variable | Default | Notes |
|---|---|---|
| `GEMINI_API_KEY` | — | **Required.** App fails fast if missing. |
| `GEMINI_LLM_MODEL` | `gemini-2.5-flash` | Chat/completion model |
| `GEMINI_EMBEDDING_MODEL` | `gemini-embedding-001` | Embedding model |
| `EMBEDDING_DIM` | `1536` | **Immutable after first ingest** (see below) |
| `NEO4J_URI` / `NEO4J_USERNAME` / `NEO4J_PASSWORD` / `NEO4J_DATABASE` | `bolt://localhost:7687` / `neo4j` / `please-change-me` / `neo4j` | Must match `docker-compose.yml` |
| `WORKING_DIR` | `./rag_storage` | LightRAG file storage |
| `DOCUMENT_FOLDER` | `./data/documents` | Default ingest folder |
| `DEFAULT_QUERY_MODE` | `hybrid` | |
| `DEFAULT_HISTORY_TURNS` | `3` | Prior turns folded into chat retrieval |
| `RESPONSE_LANGUAGE` | `Vietnamese` | Entity-extraction + answer language |
| `CORS_ORIGINS` | `http://localhost:5173,...` | Comma-separated |

---

## Gotchas

- **Start Neo4j before the backend** — LightRAG connects to Neo4j during startup.
- **Embedding model + dimension are baked in at first ingest.** Changing
  `GEMINI_EMBEDDING_MODEL` or `EMBEDDING_DIM` later requires a full reset.
- **Full reset:** stop the backend, delete `backend/rag_storage/`, and run
  `docker compose down -v` to wipe the Neo4j graph, then re-ingest.
- **Scanned-image PDFs** won't extract text (no OCR) — they're reported under
  `skipped_files` in the ingest response.
- **Gemini rate limits:** large folder ingests can hit free-tier RPM limits.
