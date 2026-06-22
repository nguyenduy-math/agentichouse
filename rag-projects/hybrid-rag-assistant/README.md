# Hybrid RAG Assistant

Multi-domain RAG system combining BM25 keyword search, semantic vector search, Reciprocal Rank Fusion, and cross-encoder reranking — coordinated by a multi-agent architecture that classifies questions and routes them to the right domain specialist.

---

## Quick Start (2 terminals)

### Prerequisites

- Python 3.12 (Intel Mac) or 3.12+ (Apple Silicon / Linux)
- Node.js 20+
- A Google Gemini API key from [aistudio.google.com](https://aistudio.google.com/app/apikey)

---

### Terminal 1 — Backend

```bash
cd rag-projects/hybrid-rag-assistant/backend

# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

> **Note on Python packages:** `requirements.txt` pins `numpy<2.0` and `scipy<1.14` because PyTorch 2.2.x (the highest version available on Intel Mac) was compiled against numpy 1.x. On Apple Silicon or Linux you can relax these pins and use the latest torch.

> **First run only:** `sentence-transformers` downloads the cross-encoder model (~80 MB) on first startup. Subsequent starts use the local cache.

Set up your API key:

```bash
cp .env.example .env
# Open .env and set GEMINI_API_KEY=<your key>
```

Create storage directory:

```bash
mkdir -p storage/chroma
```

Start the backend:

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

You should see:

```
INFO  startup.begin
INFO  startup.done
INFO  Application startup complete.
```

Interactive API docs: [http://localhost:8000/docs](http://localhost:8000/docs)

---

### Terminal 2 — Frontend

```bash
cd rag-projects/hybrid-rag-assistant/frontend

npm install
npm run dev
```

Open [http://localhost:5173](http://localhost:5173).

---

## Using the App

### Step 1 — Ingest a document

In the chat UI, expand **"Tải lên tài liệu"**, choose a domain, and upload a PDF, DOCX, or TXT file.

Or via `curl`:

```bash
curl -X POST "http://localhost:8000/api/admin/ingest?domain=hr" \
  -F "file=@/path/to/your-document.pdf"
```

Available domains: `hr`, `legal`, `finance`, `general`

> **Re-ingest after chunking changes:** if you change `CHUNK_SIZE` or update the chunking logic, delete `storage/` and re-upload your documents.

### Step 2 — Chat

Type a question in the input box. The system will:

1. Rewrite your question using conversation history (makes follow-ups like "Tell me more" work correctly)
2. Run BM25 keyword search + semantic vector search in parallel
3. Fuse both result lists with Reciprocal Rank Fusion (RRF)
4. Rerank the merged candidates with a cross-encoder for final precision
5. Generate a grounded answer from the top 5 chunks
6. Show source excerpts below the reply — query keywords are highlighted in yellow

### Step 3 — Cross-domain questions

If your question spans domains (e.g., "What is the HR policy on legal compliance?"), the orchestrator classifies it to both domains, retrieves from each in parallel, and synthesizes a merged answer.

### Out-of-scope questions

If no retrieved chunk scores above the `MIN_RERANK_SCORE` threshold, the system skips the LLM entirely and returns a polite refusal in Vietnamese. The frontend shows this in an amber bubble.

---

## Configuration

All settings are in `backend/.env`:

| Variable | Default | Description |
|---|---|---|
| `GEMINI_API_KEY` | — | **Required.** Your Google Gemini API key |
| `GEMINI_MODEL` | `gemini-2.5-flash` | LLM for chat and classification |
| `GEMINI_EMBEDDING_MODEL` | `models/gemini-embedding-exp-03-07` | Embedding model (3072 dims) |
| `BM25_TOP_K` | `20` | Keyword search candidate count |
| `VECTOR_TOP_K` | `20` | Semantic search candidate count |
| `RRF_K` | `60` | RRF smoothing constant |
| `RERANKER_MODEL` | `cross-encoder/ms-marco-MiniLM-L-6-v2` | Local cross-encoder |
| `RERANKER_TOP_N` | `5` | Chunks passed to the LLM |
| `MIN_RERANK_SCORE` | `-1.0` | Threshold below which a chunk is out-of-scope |
| `MAX_HISTORY_MESSAGES` | `10` | Conversation window sent to the LLM |
| `CHUNK_SIZE` | `2800` | Max characters per chunk (applies to fallback splitter) |
| `CHUNK_OVERLAP` | `400` | Overlap for fallback character splitter only |
| `SESSION_TTL_SECONDS` | `3600` | Session inactivity timeout |

### Tuning `MIN_RERANK_SCORE`

Cross-encoder scores roughly range from `-10` to `+10`:

| Score range | Meaning |
|---|---|
| `> 0` | Clearly relevant |
| `-1` to `0` | Marginally relevant |
| `< -1` | Likely not relevant |

Raise the threshold (e.g., `0.0`) to be stricter; lower it (e.g., `-3.0`) to be more permissive.

---

## Adding a Domain

Edit `backend/app/domains.py`:

```python
DOMAINS: dict[str, str] = {
    "hr":      "Nhân sự và Lao động",
    "legal":   "Pháp lý và Tuân thủ",
    "finance": "Tài chính và Kế toán",
    "general": "Thông tin chung",
    "it":      "Công nghệ Thông tin",   # ← add here
}
```

Restart the backend. The classifier prompt, admin API validation, agent registry, and frontend domain selector all update automatically.

---

## API Reference

All routes work under both `/api/...` and bare `/...`.

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/session` | Create a session → `{"session_id": "..."}` |
| `DELETE` | `/api/session/{id}` | Delete a session |
| `POST` | `/api/chat` | Send a message → `ChatResponse` |
| `GET` | `/api/chat/{id}/history` | Full conversation history |
| `POST` | `/api/admin/ingest?domain=hr` | Upload and index a document |
| `POST` | `/api/admin/index?domain=hr` | Rebuild BM25 index for a domain |
| `GET` | `/api/admin/stats` | Chunk counts across all domains |
| `GET` | `/api/admin/domains` | List all configured domains |

### `ChatResponse` shape

```json
{
  "session_id": "...",
  "reply": "...",
  "rewritten_query": "...",
  "domains_used": ["hr"],
  "is_out_of_scope": false,
  "sources": [
    {
      "chunk_id": "...",
      "source_file": "policy.pdf",
      "page_number": 3,
      "chunk_index": 7,
      "excerpt": "...",
      "rerank_score": 2.41,
      "domain": "hr"
    }
  ]
}
```

When `is_out_of_scope: true`, `sources` is empty and `reply` is the polite refusal message.

---

## Architecture

### Retrieval Pipeline

```
User question
      │
      ▼
 Query Rewriting  ← last 10 messages make the question standalone
      │
      ├── BM25 Search (rank_bm25)        → top-20 keyword candidates
      └── Vector Search (ChromaDB)       → top-20 semantic candidates
                    │
                    ▼
          RRF Merge + Deduplicate        score = Σ 1 / (60 + rank)
                    │
                    ▼
          Cross-encoder Reranking        (sentence-transformers, local)
                    │
                    ▼
          Top-5 chunks → system_instruction → Gemini 2.5 Flash
```

| Technique | Fills this gap |
|---|---|
| BM25 | Exact term matching — "Điều 15, Khoản 3", article codes |
| Vector search | Paraphrases and vague questions |
| RRF | Combines both signals without hand-tuned weights |
| Cross-encoder | Full query-chunk scoring for final precision |

### Chunking Strategy

Documents are split with a 3-tier strategy from `app/utils/text_splitter.py`:

| Tier | Trigger | Split boundary |
|---|---|---|
| 1 | Document contains `Điều N.` | Each Vietnamese article (`Điều 1.`, `Điều 2.`, …) becomes one chunk |
| 2 | Document contains `=== SECTION ===` | Each section marker becomes a split point |
| Fallback | Neither pattern found | Character split that snaps to the last `.\n`, `\n\n`, or `. ` within the window |

This ensures chunks are semantically complete — article text is never split mid-clause, and the fallback always ends at a sentence boundary rather than cutting mid-word.

Additional parsing improvements:
- **Vietnamese NFC normalization** — applied to all parsed text to fix garbled diacritics from some PDFs
- **DOCX table extraction** — table cell text is included alongside paragraph text

### BM25 Index Storage

BM25 indexes are stored as human-readable JSON (not pickle) at `storage/bm25_{domain}.json`:

```json
[
  {"id": "abc123", "text": "Điều 15. Chính sách nghỉ phép..."},
  ...
]
```

One file per domain. Inspect or diff them directly in any editor.

### Multi-Agent Architecture

```
OrchestratorAgent
      │
      ├── classify(question) → [domain_keys]   (Gemini)
      │
      ├── asyncio.gather(DomainAgent.retrieve() × N)   ← parallel fan-out
      │
      ├── if N == 1  → direct answer
      └── if N > 1   → synthesize(domain answers)       ← Gemini merge
```

Each `DomainAgent` owns an isolated BM25 JSON index (`storage/bm25_hr.json`) and ChromaDB collection (`chunks_hr`) for its domain. Out-of-scope detection happens before any LLM call: if all domains return zero qualifying chunks after reranking, a static refusal message is returned immediately.

### Source Excerpt Display

The excerpt shown in the UI is not a fixed character slice. For each retrieved chunk, the backend:
1. Scores every sentence by how many query keywords it contains
2. Starts from the highest-scoring sentence
3. Expands outward to adjacent sentences until the 400-character budget is filled

Query keywords are then highlighted in yellow in the frontend.

### Project Structure

```
hybrid-rag-assistant/
├── backend/
│   ├── app/
│   │   ├── main.py                  # FastAPI app + lifespan startup
│   │   ├── config.py                # Pydantic-settings (reads .env)
│   │   ├── schemas.py               # Request/response models
│   │   ├── dependencies.py          # Singleton wiring (DI)
│   │   ├── domains.py               # Domain registry (single source of truth)
│   │   ├── agents/
│   │   │   ├── domain_agent.py      # Per-domain hybrid RAG pipeline + ingest
│   │   │   └── orchestrator_agent.py# Classify → route → synthesize → excerpt
│   │   ├── services/
│   │   │   ├── bm25_service.py      # BM25Okapi index (JSON storage, per domain)
│   │   │   ├── vector_service.py    # ChromaDB collection (per domain)
│   │   │   ├── embedding_service.py # Gemini embeddings
│   │   │   ├── hybrid_service.py    # RRF merge
│   │   │   ├── rerank_service.py    # Cross-encoder reranking
│   │   │   ├── llm_service.py       # Gemini generate + query rewrite
│   │   │   ├── session_service.py   # In-memory sessions + TTL eviction
│   │   │   └── rag_service.py       # Top-level façade
│   │   ├── utils/
│   │   │   └── text_splitter.py     # 3-tier chunker (article / section / fallback)
│   │   ├── routers/
│   │   │   ├── chat.py
│   │   │   ├── session.py
│   │   │   └── admin.py
│   │   └── prompts/
│   │       └── chat_prompts.py
│   ├── storage/                     # Auto-created; gitignored
│   │   ├── chroma/                  # ChromaDB vector store
│   │   └── bm25_*.json              # Per-domain BM25 indexes (human-readable)
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   └── src/
│       ├── components/
│       │   ├── ChatWindow.tsx        # Message list + domain badges + amber refusal bubble
│       │   ├── SourcesPanel.tsx      # Source excerpts with keyword highlighting
│       │   └── UploadPanel.tsx       # File upload with domain selector
│       ├── hooks/useChat.ts
│       ├── api/client.ts
│       └── store/chatStore.ts
└── docker-compose.yml
```
