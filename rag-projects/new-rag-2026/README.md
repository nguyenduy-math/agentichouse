# new-rag-2026

A production-ready multi-agent virtual assistant that answers employee questions in Vietnamese using Microsoft GraphRAG, Neo4j, LangChain, and LangSmith. An `OrchestratorAgent` routes each question to one or more of 7 domain specialist agents, each backed by a knowledge graph built from company policy documents.

---

## Architecture Overview

```
Documents (PDF/DOCX/TXT)
        │
        ▼ graphrag index + import_to_neo4j.py
        │
   Neo4j Graph/Vector DB
   (Entity, Community, TextUnit, Document)
        │
        ▼
User → React UI → FastAPI (port 8000)
                      │
                      ▼
              OrchestratorAgent
              ┌── classify question
              ├── rewrite query
              ├── vector search → rerank → graph traversal
              │
              ├── HRAgent           (hr)
              ├── BenefitsAgent     (benefits)
              ├── ITAgent           (it)
              ├── FinanceAgent      (finance)
              ├── ComplianceAgent   (compliance)
              ├── ProceduresAgent   (procedures)
              └── GeneralAgent      (general)
                      │
              synthesize → verify → Vietnamese answer
```

Single-domain questions are routed directly. Cross-domain questions fan out to all relevant agents in parallel via `asyncio.gather`, then synthesize a unified answer.

---

## Key Features

- **Multi-agent orchestration** — 7 domain specialists with focused Vietnamese system prompts. Cross-domain questions get parallel fan-out and synthesis rather than a single generalist agent.
- **8-layer retrieval quality pipeline** — query rewrite → overfetch (k=25) → type-aware entity seeding → Cohere cross-encoder rerank (25→8) → seed entity re-anchoring → 2-hop graph traversal → seed-entity triple filtering → two-level answer verification.
- **Microsoft GraphRAG indexing** — entities, communities, and relationships extracted from Vietnamese documents using custom Vietnamese prompt templates.
- **Neo4j graph + vector storage** — persistent graph queryable via Cypher; cosine vector indexes on `Entity.embedding` and `Community.embedding` replace LanceDB.
- **Multi-LLM support** — switch between Gemini (default), OpenAI, and Siliconflow by changing one env var. Indexing LLM and agent-layer LLM are independently configurable.
- **LangSmith observability** — full trace tree per chat turn (query rewrite → classify → retrieve → rerank → traverse → domain agent → verify → synthesize).
- **RAGAS evaluation suite** — three scripts: single-turn, multi-turn, and per-domain agent.
- **Ragas Evaluation Report UI** — "Đánh giá" tab lets admins score real user conversations from chat history without leaving the app.
- **Per-session token counting** — LangChain callback captures every LLM call, attributes usage by `session_id`/`call_type`/`provider`, and stores cost estimates in SQLite.
- **Token Usage Dashboard** — "Chi phí" tab shows 4 metric cards, sessions table with expandable turn breakdowns, bar + doughnut charts.

---

## Project Structure

```
new-rag-2026/
├── backend/
│   ├── app/
│   │   ├── main.py                   # FastAPI app, lifespan, router registration
│   │   ├── config.py                 # Pydantic Settings — all env vars
│   │   ├── schemas.py                # Request/response Pydantic models
│   │   ├── domains.py                # Single source of truth for 7 domains
│   │   ├── agents/
│   │   │   ├── base_agent.py         # BaseDomainAgent ABC + AgentResult
│   │   │   ├── orchestrator.py       # OrchestratorAgent (classify → route → synthesize)
│   │   │   ├── hr_agent.py
│   │   │   ├── benefits_agent.py
│   │   │   ├── it_agent.py
│   │   │   ├── finance_agent.py
│   │   │   ├── compliance_agent.py
│   │   │   ├── procedures_agent.py
│   │   │   └── general_agent.py
│   │   ├── services/
│   │   │   ├── graphrag_service.py   # GraphRAG LocalSearch + GlobalSearch wrappers
│   │   │   ├── indexing_service.py   # Document parsing, pre-processing, graphrag index
│   │   │   ├── neo4j_store.py        # Async Neo4j driver, vector search, graph traversal
│   │   │   ├── llm_service.py        # LangChain factory: create_chat_model(), create_embeddings()
│   │   │   ├── rerank_service.py     # Cohere cross-encoder reranking
│   │   │   ├── verification_service.py # Two-level answer grounding check
│   │   │   ├── session_service.py    # In-memory session state + TTL
│   │   │   ├── history_store.py      # SQLite persistence (turns, eval runs, token usage)
│   │   │   ├── eval_service.py       # RAGAS scoring on stored turns
│   │   │   └── token_callback.py     # LangChain callback for per-call token counting
│   │   ├── prompts/
│   │   │   ├── system_prompts.py     # Vietnamese system prompts per domain
│   │   │   ├── orchestrator_prompts.py # Classification, query rewrite, synthesis prompts
│   │   │   ├── extraction_prompts.py
│   │   │   └── synthesis_prompts.py
│   │   └── routers/
│   │       ├── chat.py               # POST /chat, GET /chat/{id}/agent_trace
│   │       ├── admin.py              # ingest, index, status
│   │       ├── session.py            # create/delete sessions
│   │       ├── eval.py               # eval sessions, runs, scores
│   │       ├── tokens.py             # token usage endpoints
│   │       └── health.py
│   ├── graphrag_workspace/
│   │   ├── settings.yaml             # GraphRAG config with Vietnamese entity types
│   │   ├── input/                    # Pre-processed .txt files fed to graphrag index
│   │   ├── output/                   # Parquet artifacts from indexing
│   │   └── prompts/
│   │       ├── entity_extraction.txt # Vietnamese extraction template
│   │       ├── community_report.txt  # Vietnamese community summarization template
│   │       └── summarize_descriptions.txt
│   ├── scripts/
│   │   ├── run_index.py              # Thin wrapper around graphrag index CLI
│   │   └── import_to_neo4j.py        # Parquet → Neo4j bulk import
│   ├── data/
│   │   ├── documents/                # Source documents (gitignored)
│   │   └── history.db                # SQLite: turns, eval_runs, token_usage (gitignored)
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   └── src/
│       ├── App.tsx                   # Tab switcher: Hỏi đáp | Quản trị | Đánh giá | Chi phí
│       ├── components/
│       │   ├── chat/                 # Chat UI, MessageBubble, SourcePanel
│       │   ├── eval/                 # SessionList, TurnTable, EvalConfigModal, EvalResultTable
│       │   ├── tokens/               # TokenSummaryPanel, bar + doughnut charts
│       │   └── admin/                # File upload, indexing status, agent trace panel
│       ├── hooks/
│       └── store/                    # Zustand stores
├── eval/
│   ├── eval_single.py                # 20 single-turn RAGAS evaluations
│   ├── eval_multiturn.py             # 5 conversation sets × 4 turns
│   ├── eval_per_domain.py            # Per-domain agent scoring
│   ├── requirements.txt
│   ├── .env.example
│   └── README.md
└── docker-compose.yml
```

---

## Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| Python | **3.10 – 3.12** | `graphrag 2.x` requires Python `<3.13`; use `python3.12` (available on most systems) |
| Node.js | 20+ | For frontend dev server |
| npm | 9+ | |
| Docker + Docker Compose | v2+ | For recommended deployment |
| Neo4j | 5.20+ | Provided via Docker (`neo4j:5.20-community`) |
| API key | at least one of: `GEMINI_API_KEY` / `OPENAI_API_KEY` / `SILICONFLOW_API_KEY` | Gemini is the default and has a generous free tier |
| Cohere API key | optional | Required for cross-encoder reranking (`ENABLE_RERANK=true`); system degrades gracefully without it |

---

## Quick Start (Docker — recommended)

```bash
git clone <repo-url>
cd new-rag-2026

cp backend/.env.example backend/.env
# Edit backend/.env — set at least GEMINI_API_KEY and NEO4J_PASSWORD

docker compose up -d

# Check services are healthy
docker compose ps

# Visit the UI
open http://localhost:80

# Neo4j Browser (optional)
open http://localhost:7474
```

The backend waits for Neo4j's health check before starting. First boot takes ~60 seconds.

> **Note:** The assistant will show "GraphRAG not ready" until you complete the [GraphRAG Setup](#graphrag-setup-required-before-first-use) step below.

---

## Local Development Setup

### Backend

```bash
cd backend

# Create and activate virtualenv — must use Python 3.12 (graphrag 2.x requires <3.13)
python3.12 -m venv .venv
source .venv/bin/activate          # macOS/Linux
# .venv\Scripts\activate           # Windows PowerShell

pip install --upgrade pip setuptools wheel
pip install --prefer-binary -r requirements.txt

cp .env.example .env
# Edit .env — fill in API keys and NEO4J_PASSWORD

# Start Neo4j separately (required)
docker compose up neo4j -d

# Run backend
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

### Frontend

```bash
cd frontend
npm install
npm run dev
# Visit http://localhost:5173
```

The frontend dev server proxies API calls to `http://localhost:8000`.

---

## GraphRAG Setup (required before first use)

GraphRAG indexing builds the knowledge graph from your documents. You must complete this before the chat interface will return answers.

### Step 1 — Initialize the workspace

```bash
graphrag init --root backend/graphrag_workspace
```

This creates the default `settings.yaml`. **Replace it** with the project's custom `settings.yaml` (already in `backend/graphrag_workspace/settings.yaml`) which sets Vietnamese entity types, custom prompt templates, and configures the LLM.

### Step 2 — Add documents

Copy your PDF, DOCX, or TXT policy documents into:

```
backend/graphrag_workspace/input/
```

The indexing service will pre-process them into article-sized chunks before feeding them to GraphRAG. Vietnamese documents structured around `Điều N.` articles are split at article boundaries automatically.

### Step 3 — Trigger indexing

Option A — via the Admin tab in the UI (recommended):

1. Open `http://localhost:80`
2. Go to the **Quản trị** tab
3. Upload documents using the file picker, then click **Bắt đầu index**
4. Poll the status indicator until it shows "Hoàn thành"

Option B — via the API directly:

```bash
curl -X POST http://localhost:8000/api/v1/admin/index
# Poll status
curl http://localhost:8000/api/v1/admin/status
```

### Step 4 — Import to Neo4j

After indexing completes, import the Parquet artifacts into Neo4j:

```bash
python backend/scripts/import_to_neo4j.py \
  --artifacts backend/graphrag_workspace/output/artifacts \
  --uri bolt://localhost:7687 \
  --user neo4j \
  --password <NEO4J_PASSWORD>
```

This step is triggered automatically by the `IndexingService` when using the Admin tab. Run it manually only if you indexed via CLI or need to re-import.

### Verify

```bash
# In Neo4j Browser (http://localhost:7474):
MATCH (n) RETURN labels(n), count(n) ORDER BY count(n) DESC
```

You should see `Entity`, `Community`, `TextUnit`, `Document` nodes. The chat interface is now ready.

---

## Environment Variables

Copy `backend/.env.example` to `backend/.env` and fill in values. The full list is in `.env.example`; key variables are grouped below.

### LLM (agent layer)

| Variable | Default | Description |
|---|---|---|
| `LLM_PROVIDER` | `gemini` | `gemini` \| `openai` \| `siliconflow` — controls which provider handles chat and embeddings |
| `GEMINI_API_KEY` | — | Required when `LLM_PROVIDER=gemini` |
| `GEMINI_CHAT_MODEL` | `gemini-2.0-flash` | |
| `GEMINI_EMBED_MODEL` | `text-embedding-004` | |
| `OPENAI_API_KEY` | — | Required when `LLM_PROVIDER=openai` |
| `OPENAI_CHAT_MODEL` | `gpt-4o` | |
| `OPENAI_EMBED_MODEL` | `text-embedding-3-small` | |
| `SILICONFLOW_API_KEY` | — | Required when `LLM_PROVIDER=siliconflow` |
| `SILICONFLOW_MODEL` | `deepseek-ai/DeepSeek-V3` | |
| `SILICONFLOW_EMBED_MODEL` | `BAAI/bge-large-zh-v1.5` | Produces 1024-dim vectors — set `EMBEDDING_DIM=1024` if used |

### Neo4j

| Variable | Default | Description |
|---|---|---|
| `NEO4J_URI` | `bolt://localhost:7687` | Use `bolt://neo4j:7687` inside Docker |
| `NEO4J_USER` | `neo4j` | |
| `NEO4J_PASSWORD` | — | **Required** — set a strong password |
| `EMBEDDING_DIM` | `768` | Must match the embedding model: 768 (Gemini text-embedding-004), 1536 (OpenAI), 1024 (Siliconflow BAAI) |

### GraphRAG

| Variable | Default | Description |
|---|---|---|
| `GRAPHRAG_ROOT` | `./graphrag_workspace` | Path to GraphRAG workspace |
| `GRAPHRAG_QUERY_MODEL` | `gemini-2.0-flash` | Model used by GraphRAG's query layer (separate from agent layer) |
| `EMBEDDING_MODEL` | `text-embedding-004` | Embedding model for GraphRAG indexing |

### Retrieval Quality

| Variable | Default | Description |
|---|---|---|
| `ENABLE_RERANK` | `true` | Use Cohere cross-encoder. Set `false` to skip (lower quality, no Cohere key needed) |
| `COHERE_API_KEY` | — | Required when `ENABLE_RERANK=true` |
| `COHERE_RERANK_MODEL` | `rerank-multilingual-v3.0` | Multilingual cross-encoder (supports Vietnamese) |
| `RERANK_CANDIDATE_POOL` | `25` | Overfetch size before reranking |
| `MAX_LOCAL_CHUNKS` | `8` | Final context size after reranking |
| `GRAPH_HOP_DEPTH` | `2` | Depth of Neo4j graph traversal from seed entities |
| `ENABLE_ANSWER_VERIFICATION` | `true` | Two-level grounding check (domain + final). Set `false` to save tokens |
| `VERIFICATION_CONFIDENCE_THRESHOLD` | `3` | Below this confidence (1–5), the fallback answer is returned |

### LangSmith (optional)

| Variable | Default | Description |
|---|---|---|
| `LANGCHAIN_TRACING_V2` | `false` | Set `true` to enable LangSmith tracing |
| `LANGCHAIN_API_KEY` | — | Your LangSmith API key |
| `LANGCHAIN_PROJECT` | `new-rag-2026` | Project name in LangSmith UI |

### History & Eval

| Variable | Default | Description |
|---|---|---|
| `HISTORY_DB_PATH` | `./data/history.db` | SQLite file for chat history, eval runs, token usage |
| `HISTORY_RETENTION_DAYS` | `90` | Turns older than this are deleted on startup |
| `EVAL_ADMIN_KEY` | — | If set, all `/eval/*` endpoints require `X-Admin-Key` header |

---

## The 7 Domain Agents

Defined in `backend/app/domains.py`. Add a new entry there and the orchestrator picks it up automatically.

| Key | Vietnamese Name | Topics Covered |
|---|---|---|
| `hr` | Nhân sự | Recruitment, employment contracts, discipline, leave policies, performance review |
| `benefits` | Phúc lợi | Health insurance, social insurance, allowances, maternity benefits, retirement fund |
| `it` | Bảo mật CNTT | Information security policies, password management, system access, incident reporting |
| `finance` | Tài chính | Payment workflows, expense reimbursement, budget, financial reporting, internal controls |
| `compliance` | Tuân thủ | Vietnamese law, industry standards, audit reports, anti-corruption (AML/ABAC) |
| `procedures` | Quy trình | Standard operating procedures (SOP), work instructions, forms, approval workflows |
| `general` | Tổng hợp | Catch-all for questions that don't fit any specialist domain |

---

## Switching LLM Providers

Change one env var and restart:

```bash
# Default — best Vietnamese quality, generous free tier
LLM_PROVIDER=gemini

# OpenAI — production consistency
LLM_PROVIDER=openai

# Siliconflow — cost-optimized, air-gap friendly
LLM_PROVIDER=siliconflow
```

**Important:** if you switch the embedding model (e.g., from Gemini to Siliconflow's BAAI), you must re-index all documents and re-import to Neo4j. Chat and indexing LLMs can differ, but the embedding model used at index time and query time must match.

### Siliconflow model options

| Model | Context | Vietnamese quality | Notes |
|---|---|---|---|
| `deepseek-ai/DeepSeek-V3` | 64K | Excellent | Default |
| `Qwen/Qwen2.5-72B-Instruct` | 128K | Very good | |
| `deepseek-ai/DeepSeek-R1` | 64K | Excellent | Reasoning model, slower |
| `BAAI/bge-large-zh-v1.5` | — | Strong (embed only) | Set `EMBEDDING_DIM=1024` |

---

## Running Ragas Evaluations

The `eval/` directory has an independent Python environment and its own `.env`.

```bash
cd eval

# Setup — use Python 3.10–3.12; do NOT use 3.13+ (graphrag 2.x incompatible)
python3.12 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install --upgrade pip setuptools wheel
pip install --prefer-binary -r requirements.txt

cp .env.example .env
# Set OPENAI_API_KEY (always required — used for embeddings)
# Set GEMINI_API_KEY or SILICONFLOW_API_KEY if using those as judge

# Requires the backend running at http://localhost:8000
```

### `eval_single.py` — 20 single-turn questions

```bash
python eval_single.py                              # OpenAI judge (default)
python eval_single.py --judge-provider gemini
python eval_single.py --judge-provider siliconflow
python eval_single.py --dry-run                    # collect responses only, no cost
```

Output: `results/eval_single_YYYYMMDD_HHMMSS.csv`

### `eval_multiturn.py` — 5 conversation sets × 4 turns

```bash
python eval_multiturn.py
python eval_multiturn.py --set CS-001              # single set only
python eval_multiturn.py --judge-provider gemini
```

Tests conversation memory and follow-up question handling. Output: `results/eval_multiturn_YYYYMMDD_HHMMSS.csv`

### `eval_per_domain.py` — per-domain agent scoring

```bash
python eval_per_domain.py                          # all 7 domains
python eval_per_domain.py --domain hr
python eval_per_domain.py --domain benefits
```

Calls `GET /api/v1/chat/{session_id}/agent_trace` after each request and scores each domain agent's answer independently. Prints a per-domain summary table and highlights the weakest domain. Output: `results/eval_per_domain_YYYYMMDD_HHMMSS.csv`

### Interpreting scores

| Score | Assessment |
|---|---|
| 0.85 – 1.00 | Excellent |
| 0.70 – 0.84 | Good — acceptable for production |
| 0.55 – 0.69 | Fair — room for improvement |
| < 0.55 | Poor — investigate retrieval or prompts |

Low `faithfulness` → hallucination; tighten system prompt or lower temperature. Low `context_recall` → retrieval missing documents; add more. Low `context_precision` → reranker not ordering well; tune Cohere params.

---

## Ragas Evaluation Report UI

The **Đánh giá** tab scores real user conversations directly from chat history — not just curated test sets.

1. **Browse sessions** — paginated list of past sessions with turn counts and timestamps.
2. **Select turns** — checkbox-select individual turns or an entire session.
3. **Configure run** — choose judge provider (OpenAI / Gemini / Siliconflow), judge model, and optionally provide reference answers for `context_recall` / `answer_correctness`.
4. **Run scoring** — RAGAS evaluation runs as a background task; status polls every 3 seconds.
5. **View results** — color-coded score table (green ≥ 0.8, amber ≥ 0.6, red < 0.6); average row at the bottom.
6. **Compare runs** — select a second run to show Δ columns, useful for regression testing after config changes.
7. **Export CSV** — download results for external analysis.

Chat history is persisted to `data/history.db` (SQLite) as a non-blocking background task on every chat response. History is gitignored. Set `HISTORY_RETENTION_DAYS` to control cleanup.

---

## Token Usage Dashboard

The **Chi phí** tab tracks the cost of every LLM call in the system.

**Metric cards:**
- Total tokens consumed
- Estimated cost (USD)
- Total LLM calls
- Active sessions

**Sessions table** — ordered by cost descending; each row is expandable to show:
- Breakdown by `call_type` (classify, query_rewrite, domain_answer_hr, synthesize, verify_final, etc.)
- Breakdown by provider + model
- Per-turn token counts

**Charts:**
- Bar chart — tokens by call type (shows which pipeline step is most expensive)
- Doughnut chart — cost share by provider/model

Token counting uses a LangChain `SessionTokenCallback` attached to each request via `RunnableConfig.callbacks`. Cost estimates are stored per-call in `data/history.db` using pricing rates from `token_callback.py`; update the `COST_PER_1K` table when model pricing changes.

---

## LangSmith Setup (optional)

When enabled, LangSmith produces a full trace tree for every chat turn, showing prompt/output text, token counts, and latency for every step from query rewrite through final verification.

```bash
# backend/.env
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=your_key_here
LANGCHAIN_PROJECT=new-rag-2026
LANGCHAIN_ENDPOINT=https://api.smith.langchain.com
```

LangChain components (LLM calls, `Neo4jVector` searches, prompt templates) are traced automatically. Non-LangChain steps (Cohere reranking, Neo4j graph traversal, answer verification) are decorated with `@traceable`.

LangSmith tracing is disabled by default in `docker-compose.yml` (`LANGCHAIN_TRACING_V2=false`) to avoid accidental billing.

---

## API Reference

All routes are under `/api/v1` unless noted. Full OpenAPI docs at `http://localhost:8000/docs`.

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Liveness + readiness (reports `neo4j_connected`, `graphrag_ready`) |
| `POST` | `/api/v1/session` | Create a new chat session |
| `DELETE` | `/api/v1/session/{session_id}` | Delete session and clear history |
| `POST` | `/api/v1/chat` | Send a message; returns Vietnamese answer with sources and domain metadata |
| `GET` | `/api/v1/chat/{session_id}/agent_trace` | Per-domain agent answers for the last turn |
| `POST` | `/api/v1/admin/ingest` | Upload a document (PDF/DOCX/TXT) |
| `POST` | `/api/v1/admin/index` | Trigger GraphRAG indexing + Neo4j import |
| `GET` | `/api/v1/admin/status` | Poll indexing status |
| `GET` | `/api/v1/eval/sessions` | List sessions with turn counts |
| `GET` | `/api/v1/eval/sessions/{session_id}/turns` | All turns for a session |
| `POST` | `/api/v1/eval/run` | Start a RAGAS evaluation run (background task) |
| `GET` | `/api/v1/eval/runs` | List past evaluation runs |
| `GET` | `/api/v1/eval/runs/{run_id}` | Full run results with per-turn scores |
| `GET` | `/api/v1/eval/runs/{run_id}/export` | Download results as CSV |
| `GET` | `/api/v1/sessions/{session_id}/tokens` | Token + cost breakdown for a session |
| `GET` | `/api/v1/admin/tokens/summary` | Per-session token totals for all sessions |

### Chat request/response example

```json
// POST /api/v1/chat
{
  "session_id": "uuid4",
  "message": "Chính sách nghỉ phép và bảo hiểm y tế của công ty như thế nào?",
  "mode": "auto"
}

// Response
{
  "reply": "Về chính sách nghỉ phép: nhân viên được hưởng...",
  "sources": [...],
  "query_type": "global",
  "session_id": "uuid4",
  "domain_keys": ["hr", "benefits"],
  "agent_count": 2
}
```

---

## Docker Services

| Service | Image | Ports | Purpose |
|---|---|---|---|
| `neo4j` | `neo4j:5.20-community` | 7474 (browser), 7687 (Bolt) | Graph + vector database with APOC plugin |
| `backend` | `./backend/Dockerfile` (Python 3.11-slim) | 8000 | FastAPI application server |
| `frontend` | `./frontend/Dockerfile` (Node + nginx) | 80 | React SPA served by nginx |

The backend service depends on `neo4j` via health check — it will not start until Neo4j reports healthy. Persistent volumes: `neo4j_data`, `neo4j_logs`, `graphrag_data` (workspace + Parquet artifacts), `documents_data` (source documents).

---

## Comparison: new-rag-2026 vs graphrag-assistant

| Dimension | `graphrag-assistant` (old) | **new-rag-2026** |
|---|---|---|
| Agent architecture | Single generalist agent | OrchestratorAgent + 7 domain specialists |
| Cross-domain questions | Weak — one agent handles all | Strong — parallel fan-out + synthesis |
| Graph storage | Neo4j (custom schema) | Neo4j (GraphRAG-native schema) |
| GraphRAG version | Custom implementation | Microsoft GraphRAG 2.x |
| Vietnamese extraction | Custom prompts (team-maintained) | MSFT GraphRAG + Vietnamese templates |
| Language | Mixed EN/VI | Vietnamese throughout (prompts, answers, entity types) |
| LLM flexibility | Gemini only | Gemini / OpenAI / Siliconflow — switchable at runtime |
| Observability | None | LangSmith full trace tree + local SQLite token accounting |
| Evaluation | Manual | RAGAS eval suite (3 scripts) + in-app Evaluation Report UI |
| Retrieval pipeline | 4 layers | 8 layers (adds entity seeding, re-anchoring, triple filtering, two-level verification) |

---

## Troubleshooting

**"GraphRAG not ready"** — indexing hasn't completed or `import_to_neo4j.py` hasn't run. Check `GET /api/v1/admin/status`.

**Neo4j connection refused** — if running locally (not Docker), start Neo4j separately (`docker compose up neo4j -d`) and set `NEO4J_URI=bolt://localhost:7687` in `.env`.

**`Could not find a version that satisfies the requirement graphrag<3.0.0,>=2.0.0`** — you are running Python 3.13+. `graphrag 2.x` declares `python_requires=">=3.10,<3.13"`, so pip correctly rejects all 2.x wheels. Fix: recreate the venv with Python 3.12:
```bash
rm -rf .venv
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

**Python version compatibility** — use Python **3.10 – 3.12** for both `backend/` and `eval/`. Python 3.13+ is blocked by `graphrag 2.x`.

**`Building wheel for llvmlite (pyproject.toml) ... error`** — pip is trying to compile `llvmlite` from source, which requires LLVM to be installed. Use `--prefer-binary` to force pip to download a pre-built wheel instead:
```bash
pip install --prefer-binary -r requirements.txt
```

**Embedding dimension mismatch** — if you see Neo4j vector index errors, verify that `EMBEDDING_DIM` in `.env` matches the model: `768` for `text-embedding-004`, `1536` for `text-embedding-3-small`, `1024` for `BAAI/bge-large-zh-v1.5`. Re-import after changing models.

**High cost / slow responses** — set `ENABLE_RERANK=false` to skip Cohere (faster, lower quality), or set `ENABLE_ANSWER_VERIFICATION=false` to skip the two verification passes.
