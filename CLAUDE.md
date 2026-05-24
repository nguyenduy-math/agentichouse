# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Overview

A monorepo of AI-powered projects (RAG assistants, fraud detection, data science experiments), all targeting the Vietnamese market. Every backend LLM call uses Google Gemini (`gemini-2.5-flash`) via the `google-genai` SDK and answers in Vietnamese.

```
agentichouse/
├── fraud-risks-system/               # Healthcare claim fraud detection (BHYT)
├── rag-projects/
│   ├── graphrag-assistant/           # Graph RAG policy Q&A (Neo4j + custom pipeline)
│   ├── lightrag-assistant/           # LightRAG insurance document Q&A
│   └── lightrag-company-policy-assistant/  # Multi-agent policy Q&A (10 domain agents)
├── labs/
│   └── pageindex/
│       └── policy-assistant-cloud/   # PageIndex Cloud tree-navigation Q&A lab
└── data-science/
    └── stage1-churn/                 # Telco churn ML workflow practice (Jupyter)
```

Each sub-project is fully self-contained with its own `backend/`, `frontend/`, `docker-compose.yml`, and `.env.example`.

---

## Common Development Commands

All backends follow the same startup pattern (ports vary):

```bash
# Start infrastructure (Neo4j, PostgreSQL where needed)
docker compose up -d                        # from project root

# Backend (Python)
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                        # then fill in API keys
uvicorn app.main:app --host 127.0.0.1 --port <PORT> --reload

# Frontend (Node)
cd frontend
npm install
npm run dev                                 # dev server at http://localhost:5173

# Frontend production build
npm run build                               # emits frontend/dist/
# When dist/ exists, FastAPI serves the SPA directly — no separate frontend process needed
```

### Per-Project Ports

| Project | Backend Port | Notes |
|---|---|---|
| `fraud-risks-system` | `8001` | Also requires PostgreSQL |
| `graphrag-assistant` | `8000` | Run `python -m scripts.build_graph_index` before first use |
| `lightrag-assistant` | `8000` | Run `POST /ingest` after startup |
| `lightrag-company-policy-assistant` | `8000` | 10 agents initialize on startup |
| `labs/pageindex/policy-assistant-cloud` | `8000` | PageIndex Cloud API key required |

### graphrag-assistant — Index & QC Tests

```bash
cd rag-projects/graphrag-assistant/backend

# Build the Neo4j graph index (required before first query)
python -m scripts.build_graph_index

# QC tests (sections: neo4j | retrieval | api | eval | manual)
python qc_tests.py                    # all sections
python qc_tests.py --section neo4j    # only Neo4j checks
python qc_tests.py --section api      # only API integration checks
python qc_tests.py --section eval     # LLM-as-judge golden QA (costs API calls)
```

### data-science/stage1-churn

```bash
cd data-science/stage1-churn
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python download_data.py     # pulls IBM Telco CSV into data/
jupyter lab
```

---

## Architecture Patterns

### Backend: FastAPI + Pydantic-settings

Every backend follows the same structure:
- `app/main.py` — FastAPI entry point with `@asynccontextmanager lifespan` for startup/shutdown
- `app/config.py` — Pydantic-settings reading from `.env`
- `app/schemas.py` — Pydantic request/response models
- `app/routers/` — one router per resource group
- All routes are registered twice: bare (`/chat`) **and** under `/api` prefix (`/api/chat`). The Vite dev proxy forwards `/api/*` to the backend.

### Gemini SDK Pattern

All projects use the `google-genai` SDK (not the older `google-generativeai`):

```python
from google import genai
from google.genai import types

client = genai.Client(api_key=settings.gemini_api_key)
response = await client.aio.models.generate_content(
    model=settings.gemini_llm_model,
    contents=prompt,
    config=types.GenerateContentConfig(temperature=0.0),
)
```

For structured output, pass `response_mime_type="application/json"` and `response_schema=<PydanticModel>` in the config.

### Neo4j Usage

Neo4j is used differently per project:
- **fraud-risks-system**: Patient profile graph for network-level fraud detection. Nodes: `Patient`, `Provider`, `Claim`, `Diagnosis`, `Procedure`. All nodes are upserted with `MERGE`. Graph flags written back to PostgreSQL `fraud_analyses.rule_flags` with `graph_` prefix.
- **graphrag-assistant**: Acts as both graph store and vector store (using Neo4j vector indexes `policy_chunks` and `community_summaries`, 3072-dim Gemini embeddings).
- **lightrag-assistant / lightrag-company-policy-assistant**: LightRAG uses Neo4j as its graph backend; file-based KV/vector stores live under `backend/rag_storage/`.

Neo4j password must match between `docker-compose.yml` `NEO4J_AUTH` and `backend/.env` `NEO4J_PASSWORD`.

---

## Project-Specific Architecture

### fraud-risks-system

Two-pass batch pipeline triggered nightly (2 AM via APScheduler) or manually via `POST /batch/run`:

1. **Pass 1** — per-claim: Gemini analyzes Vietnamese narrative → `llm_score` + flags; rule engine checks VND thresholds and code counts → `rule_score`. Combined: `0.7 × llm + 0.3 × max(rule, graph)`.
2. **Pass 2** — graph enrichment: claims synced to Neo4j, then 4 Cypher queries detect network fraud patterns (provider concentration, patient velocity, fraud rings, procedure dominance). Graph flags are appended to `rule_flags`; combined score boosted up to +20 per high-severity flag.

Claim lifecycle: `pending → analyzing → analyzed → reviewed`. Failed LLM calls revert to `pending` for retry on the next batch.

PostgreSQL schema (4 tables): `claims`, `fraud_analyses`, `reviews`, `batch_runs`.

### graphrag-assistant

5-stage indexing pipeline (run via `scripts/build_graph_index.py`):
1. Parse & chunk documents → `PolicyChunk` nodes
2. LLM entity/relation extraction → `Entity` nodes + typed relationships
3. Embed chunks (Gemini, 3072-dim) → stored on `PolicyChunk.embedding`
4. Louvain community detection → `community_id` labels on entities
5. Summarize communities (LLM + embed) → `Community` nodes

Query flow: `classify_query()` → `LOCAL` (vector search chunks + Cypher 2-hop traversal) or `GLOBAL` (vector search community summaries). Sessions are in-memory; graph data is returned alongside each answer.

### lightrag-company-policy-assistant (Multi-Agent)

10 domain agents orchestrated by `OrchestratorAgent`:
- **Classify** question → one or more domain keys (using Gemini `response_schema=DomainClassification` for constrained output)
- **Single domain** → direct route
- **Cross-domain** → `asyncio.gather` fan-out → `_synthesize()` merges answers

Two retrieval tools:
- **LightRAG** (9 agents): knowledge graph + vector hybrid, hybrid query mode
- **PageIndex Cloud** (1 agent: `BENEFITS`): PDF → cloud knowledge tree → local JSON → Gemini tree navigation → page-cited answers

The domain list is the single source of truth in `app/domains.py`. Adding a domain there (+ registering its agent in `main.py`) updates the classifier prompt, API schema, and ingest routing together.

LightRAG storage is isolated per domain under `backend/rag_storage/lightrag/<domain>/`. PageIndex trees are cached locally under `backend/rag_storage/pageindex/benefits/`.

**Critical gotcha**: `EMBEDDING_DIM` and `GEMINI_EMBEDDING_MODEL` are baked in at first ingest for LightRAG. Changing them requires deleting `rag_storage/` and wiping the Neo4j graph.

---

## Team Standards

### Commit Conventions (Conventional Commits)

```
<type>(scope): <subject>

feat(auth): add JWT refresh token endpoint
fix(claims): handle null provider_id gracefully
chore(deps): upgrade FastAPI to 0.115
```

Types: `feat | fix | docs | style | refactor | test | chore`

### Branch Strategy

```
main          ← production-ready, protected
└── develop   ← integration branch
    ├── feat/TICKET-short-description
    ├── fix/TICKET-short-description
    └── chore/short-description
```

### Code Style

- Python: `ruff` (target: add `ruff.toml` / `[tool.ruff]` in `pyproject.toml`)
- Max function length: 50 lines; max file length: 400 lines
- No commented-out code merged to `main`

---

## Environment Variables

Every project reads config from `backend/.env` (gitignored). Copy from `.env.example` and set:

| Variable | Required by | Notes |
|---|---|---|
| `GEMINI_API_KEY` | All | Google Gemini API key |
| `GOOGLE_API_KEY` | graphrag-assistant | Same key, different var name |
| `NEO4J_PASSWORD` | Projects with Neo4j | Must match `docker-compose.yml` `NEO4J_AUTH` |
| `DATABASE_URL` | fraud-risks-system | PostgreSQL async connection string |
| `PAGEINDEX_API_KEY` | lightrag-company-policy-assistant, labs/pageindex | From dash.pageindex.ai/api-keys |

Database volumes (`neo4j_data/`, `postgres_data/`, etc.) are gitignored.
