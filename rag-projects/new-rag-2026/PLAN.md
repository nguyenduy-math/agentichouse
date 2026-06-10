# Implementation Plan: Virtual Assistant with Microsoft GraphRAG

> **Project**: `new-rag-2026`
> **Replaces**: `agentichouse/rag-projects/graphrag-assistant` (custom implementation)
> **Library**: [`microsoft/graphrag`](https://github.com/microsoft/graphrag) — `pip install graphrag>=2.0.0`
> **Date**: 2026-06-07

---

## Table of Contents

1. [Overview](#1-overview)
2. [Microsoft GraphRAG Pipeline](#2-microsoft-graphrag-pipeline)
3. [`settings.yaml` Design](#3-settingsyaml-design)
4. [Document Ingestion Flow](#4-document-ingestion-flow)
5. [`graphrag_service.py` Design](#5-graphrag_servicepy-design)
6. [API Endpoints](#6-api-endpoints)
7. [Session Management](#7-session-management)
8. [Frontend Components](#8-frontend-components)
9. [Environment Variables](#9-environment-variables)
10. [`requirements.txt`](#10-requirementstxt)
11. [`docker-compose.yml`](#11-docker-composeyml)
12. [Key Differences from Existing `graphrag-assistant`](#12-key-differences-from-existing-graphrag-assistant)
13. [Limitations and Gotchas](#13-limitations-and-gotchas)
14. [Implementation Order](#14-implementation-order)

---

## 1. Overview

### What Microsoft GraphRAG Is

Microsoft GraphRAG (Graph Retrieval-Augmented Generation) is an open-source Python library from Microsoft Research that builds a **knowledge graph** from a corpus of documents and uses it to answer questions. Unlike naive vector-search RAG (which retrieves chunks by embedding similarity), GraphRAG:

1. **Extracts entities and relationships** from documents using an LLM.
2. **Runs community detection** (Leiden algorithm) to cluster related entities into hierarchical communities.
3. **Generates community summaries** — compact prose descriptions of each cluster, written by the LLM.
4. **Answers questions** by retrieving relevant entities + community summaries (local search) or synthesizing across all community summaries (global search).

This architecture gives dramatically better answers to questions that require connecting information across many documents or understanding the "big picture" of a corpus — something naive RAG consistently fails at.

### Why Replace the Custom Implementation

The existing `graphrag-assistant` project hand-rolls every component: entity extraction prompts, graph construction, embedding, community detection, and query logic. This means:

- Bug fixes and prompt improvements must be maintained manually.
- Any upstream research improvements are not automatically available.
- The codebase is large and fragile — changes to one component often break others.

Microsoft's official `graphrag` package provides all of this out of the box:

| Concern | Custom project | This project (`new-rag-2026`) |
|---|---|---|
| Entity extraction | Custom prompt + parsing | `graphrag index` (maintained by MSFT) |
| Community detection | Custom Leiden impl | Built into `graphrag index` |
| Embeddings | Custom OpenAI calls | Configured via `settings.yaml` |
| Query | Custom retrieval logic | `LocalSearch` / `GlobalSearch` classes |
| Maintenance | Team-owned | Microsoft Research |

### User Experience

1. **Upload** — Admin uploads PDF/DOCX/TXT documents via the web UI.
2. **Index** — Admin triggers indexing. The pipeline runs in the background (minutes to tens of minutes depending on corpus size and LLM rate limits). Progress is polled.
3. **Chat** — Users chat with the assistant. Each query runs either **LOCAL** search (entity-focused, good for specific questions) or **GLOBAL** search (community-summary synthesis, good for broad/thematic questions). The UI shows source citations.

---

## 2. Microsoft GraphRAG Pipeline

The pipeline has three sequential phases. All three are driven by a single `settings.yaml` config file.

### Phase 1: Init

```bash
graphrag init --root ./graphrag_workspace
```

This generates:
- `graphrag_workspace/settings.yaml` — the master config file (edit this for your LLM/embedding provider).
- `graphrag_workspace/prompts/` — default Jinja2 prompt templates for entity extraction, community summarization, etc. These can be customized (e.g. for Vietnamese-language documents).
- `graphrag_workspace/input/` — empty directory; place documents here before indexing.

Run once during project setup. The `prompts/` directory should be committed to version control after customization.

### Phase 2: Index

```bash
graphrag index --root ./graphrag_workspace
```

The indexer reads every `.txt` file in `graphrag_workspace/input/` and runs the following sub-pipeline:

```
input/*.txt
  │
  ▼
Text chunking (chunk_size, overlap from settings.yaml)
  │
  ▼
Entity & relationship extraction (LLM call per chunk)
  │
  ▼
Entity disambiguation & deduplication
  │
  ▼
Community detection (Leiden algorithm on entity graph)
  │
  ▼
Community summary generation (LLM call per community)
  │
  ▼
Embedding (entities, text units, community reports)
  │
  ▼
output/artifacts/
  ├── create_final_entities.parquet
  ├── create_final_relationships.parquet
  ├── create_final_communities.parquet
  ├── create_final_community_reports.parquet
  ├── create_final_text_units.parquet
  ├── create_final_nodes.parquet
  └── create_final_covariates.parquet (if enabled)
```

**Cost note**: Indexing makes many LLM calls — roughly `N_chunks * 1` for extraction plus `N_communities * 1` for summarization. Budget accordingly. Use a fast, cheap model (e.g., `gemini-2.0-flash`) for indexing.

**Incremental indexing**: As of GraphRAG 2.x, re-running `graphrag index` on an already-indexed workspace re-processes only changed/new input files. Full re-index is triggered by deleting `output/`.

### Phase 3: Query

Query is done via the Python API (not CLI) so it integrates with FastAPI:

```python
# LOCAL search — answers specific questions about named entities
result = await local_search.asearch("What are the main risk factors?")

# GLOBAL search — synthesizes broad themes across all communities
result = await global_search.asearch("What is the overall sentiment of the corpus?")
```

Both return a `SearchResult` object with `.response` (str) and `.context_data` (dict with source references).

The query objects read Parquet artifacts from `output/artifacts/` at startup — they do not call the indexer. This means the FastAPI app can start and serve queries as long as the artifacts directory exists and is populated.

---

## 3. `settings.yaml` Design

The complete `settings.yaml` for this project, using Gemini via the OpenAI-compatible endpoint:

```yaml
# graphrag_workspace/settings.yaml

# ─── LLM (used for extraction and community summarization) ───────────────────
llm:
  api_key: ${GEMINI_API_KEY}
  type: openai_chat
  model: gemini-2.0-flash
  api_base: https://generativelanguage.googleapis.com/v1beta/openai/
  max_tokens: 4000
  temperature: 0
  request_timeout: 180.0
  max_retries: 10
  max_retry_wait: 10.0
  sleep_on_rate_limit_recommendation: true
  concurrent_requests: 4

# ─── Embeddings ──────────────────────────────────────────────────────────────
embeddings:
  llm:
    api_key: ${GEMINI_API_KEY}
    type: openai_embedding
    model: text-embedding-004
    api_base: https://generativelanguage.googleapis.com/v1beta/openai/
    max_retries: 10
    request_timeout: 60.0
  vector_store:
    type: lancedb
    db_uri: output/lancedb
    container_name: default

# ─── Input ───────────────────────────────────────────────────────────────────
input:
  type: file
  file_type: text          # only .txt files; PDFs/DOCX are pre-converted
  base_dir: input
  file_pattern: ".*\\.txt$"
  encoding: utf-8

# ─── Output ──────────────────────────────────────────────────────────────────
output:
  type: file
  base_dir: output

# ─── Chunking ─────────────────────────────────────────────────────────────────
chunks:
  size: 1200
  overlap: 100
  group_by_columns: [id]

# ─── Entity extraction ───────────────────────────────────────────────────────
entity_extraction:
  prompt: prompts/entity_extraction.txt
  entity_types: [organization, person, location, event, concept]
  max_gleanings: 1

# ─── Community reports ───────────────────────────────────────────────────────
community_reports:
  prompt: prompts/community_report.txt
  max_length: 2000
  max_input_length: 8000

# ─── Summarize descriptions ──────────────────────────────────────────────────
summarize_descriptions:
  prompt: prompts/summarize_descriptions.txt
  max_length: 500

# ─── Claim extraction (optional; disabled by default — expensive) ─────────────
claim_extraction:
  enabled: false

# ─── Local search context ────────────────────────────────────────────────────
local_search:
  text_unit_prop: 0.5
  community_prop: 0.1
  conversation_history_max_turns: 5
  top_k_mapped_entities: 10
  top_k_relationships: 10
  max_tokens: 12000

# ─── Global search context ───────────────────────────────────────────────────
global_search:
  max_tokens: 12000
  data_max_tokens: 12000
  map_max_tokens: 1000
  reduce_max_tokens: 2000
  concurrency: 32

# ─── Reporting ───────────────────────────────────────────────────────────────
reporting:
  type: file
  base_dir: logs
```

**Notes on Gemini compatibility**:
- `text-embedding-004` produces 768-dimensional vectors. GraphRAG's LanceDB store handles this automatically — no dimension override needed in `settings.yaml`.
- Gemini's OpenAI-compatible endpoint supports `openai_chat` and `openai_embedding` types natively.
- Set `concurrent_requests: 4` to stay within Gemini's free-tier rate limits; increase for paid tiers.

---

## 4. Document Ingestion Flow

### Upload → Index → Query lifecycle

```
User (browser)
  │
  │  POST /api/v1/admin/ingest  (multipart/form-data, file)
  ▼
FastAPI: admin.py router
  │
  ├─ Save raw file → data/documents/{uuid}_{filename}
  │
  ├─ Convert to plain text:
  │     .pdf  → PyMuPDF (fitz)  → plain text
  │     .docx → python-docx     → plain text
  │     .txt  → copy as-is
  │
  └─ Write text → graphrag_workspace/input/{uuid}.txt
       (filename without extension becomes the document ID in GraphRAG)

  │
  │  POST /api/v1/admin/index
  ▼
FastAPI: admin.py router
  │
  └─ indexing_service.run_index() → BackgroundTask
       │
       └─ subprocess: graphrag index --root ./graphrag_workspace
            (or Python API: from graphrag.index import run_pipeline_with_config)

  │
  │  GET /api/v1/admin/status
  ▼
IndexingService.get_status()
  └─ Returns: {status: "running"|"completed"|"failed"|"idle", started_at, finished_at, error}

  │
  │  (after status = "completed")
  ▼
GraphRAGService.reload()
  └─ Re-reads Parquet artifacts, rebuilds LocalSearch + GlobalSearch objects
```

### PDF conversion example (PyMuPDF)

```python
import fitz  # PyMuPDF

def pdf_to_text(path: str) -> str:
    doc = fitz.open(path)
    return "\n\n".join(page.get_text() for page in doc)
```

### DOCX conversion example

```python
from docx import Document

def docx_to_text(path: str) -> str:
    doc = Document(path)
    return "\n\n".join(p.text for p in doc.paragraphs if p.text.strip())
```

### File naming convention

- Raw files: `data/documents/{uuid}_{original_name}`
- GraphRAG input: `graphrag_workspace/input/{uuid}.txt`

Using a UUID prefix avoids filename collisions and makes it easy to track which raw file produced which text unit.

---

## 5. `graphrag_service.py` Design

This service is the central integration point between FastAPI and the GraphRAG library. It is initialized once at app startup (via FastAPI lifespan) and exposes a single `search()` async method.

```python
# backend/app/services/graphrag_service.py

from __future__ import annotations

import asyncio
import os
from enum import Enum
from pathlib import Path
from typing import Any

import pandas as pd
from graphrag.query.context_builder.entity_extraction import EntityVectorStoreKey
from graphrag.query.indexer_adapters import (
    read_indexer_communities,
    read_indexer_covariates,
    read_indexer_entities,
    read_indexer_relationships,
    read_indexer_reports,
    read_indexer_text_units,
)
from graphrag.query.llm.oai.chat_openai import ChatOpenAI
from graphrag.query.llm.oai.embedding import OpenAIEmbedding
from graphrag.query.llm.oai.typing import OpenaiApiType
from graphrag.query.structured_search.global_search.community_context import (
    GlobalCommunityContext,
)
from graphrag.query.structured_search.global_search.search import GlobalSearch
from graphrag.query.structured_search.local_search.mixed_context import (
    LocalSearchMixedContext,
)
from graphrag.query.structured_search.local_search.search import LocalSearch
from graphrag.vector_stores.lancedb import LanceDBVectorStore


class SearchMode(str, Enum):
    LOCAL = "local"
    GLOBAL = "global"


class GraphRAGService:
    """Wraps Microsoft GraphRAG LocalSearch and GlobalSearch."""

    def __init__(self, workspace_root: str):
        self._root = Path(workspace_root)
        self._artifacts = self._root / "output" / "artifacts"
        self._lancedb_uri = str(self._root / "output" / "lancedb")
        self._local_search: LocalSearch | None = None
        self._global_search: GlobalSearch | None = None
        self._lock = asyncio.Lock()

    # ─── Public API ──────────────────────────────────────────────────────────

    async def search(self, question: str, mode: SearchMode) -> dict[str, Any]:
        """Run a search query. Returns {reply, sources}."""
        if mode == SearchMode.LOCAL:
            engine = self._local_search
        else:
            engine = self._global_search

        if engine is None:
            raise RuntimeError(
                "GraphRAG artifacts not loaded. Run indexing first."
            )

        result = await engine.asearch(question)
        sources = self._extract_sources(result.context_data)
        return {"reply": result.response, "sources": sources}

    async def reload(self) -> None:
        """Reload Parquet artifacts after a new indexing run."""
        async with self._lock:
            self._local_search = await asyncio.to_thread(self._build_local_search)
            self._global_search = await asyncio.to_thread(self._build_global_search)

    @property
    def is_ready(self) -> bool:
        return self._local_search is not None and self._global_search is not None

    # ─── Internal builders ────────────────────────────────────────────────────

    def _llm(self) -> ChatOpenAI:
        return ChatOpenAI(
            api_key=os.environ["GEMINI_API_KEY"],
            model=os.environ.get("LLM_MODEL", "gemini-2.0-flash"),
            api_base="https://generativelanguage.googleapis.com/v1beta/openai/",
            api_type=OpenaiApiType.OpenAI,
            max_retries=10,
        )

    def _embedder(self) -> OpenAIEmbedding:
        return OpenAIEmbedding(
            api_key=os.environ["GEMINI_API_KEY"],
            model=os.environ.get("EMBEDDING_MODEL", "text-embedding-004"),
            api_base="https://generativelanguage.googleapis.com/v1beta/openai/",
            api_type=OpenaiApiType.OpenAI,
            max_retries=10,
        )

    def _build_local_search(self) -> LocalSearch:
        artifacts = self._artifacts

        entity_df = pd.read_parquet(artifacts / "create_final_entities.parquet")
        relationship_df = pd.read_parquet(artifacts / "create_final_relationships.parquet")
        community_df = pd.read_parquet(artifacts / "create_final_communities.parquet")
        report_df = pd.read_parquet(artifacts / "create_final_community_reports.parquet")
        text_unit_df = pd.read_parquet(artifacts / "create_final_text_units.parquet")
        node_df = pd.read_parquet(artifacts / "create_final_nodes.parquet")

        entities = read_indexer_entities(entity_df, node_df, community_level=2)
        relationships = read_indexer_relationships(relationship_df)
        reports = read_indexer_reports(report_df, node_df, community_level=2)
        text_units = read_indexer_text_units(text_unit_df)

        # Load entity embeddings from LanceDB
        entity_store = LanceDBVectorStore(collection_name="default-entity-description")
        entity_store.connect(db_uri=self._lancedb_uri)

        context_builder = LocalSearchMixedContext(
            community_reports=reports,
            text_units=text_units,
            entities=entities,
            relationships=relationships,
            entity_text_embeddings=entity_store,
            embedding_vectorstore_key=EntityVectorStoreKey.ID,
            text_embedder=self._embedder(),
        )

        return LocalSearch(
            llm=self._llm(),
            context_builder=context_builder,
            token_encoder=None,  # auto-detected from model
            llm_params={
                "max_tokens": 2000,
                "temperature": 0,
            },
            context_builder_params={
                "text_unit_prop": 0.5,
                "community_prop": 0.1,
                "conversation_history_max_turns": 5,
                "top_k_mapped_entities": 10,
                "top_k_relationships": 10,
                "max_tokens": 12000,
            },
        )

    def _build_global_search(self) -> GlobalSearch:
        artifacts = self._artifacts

        report_df = pd.read_parquet(artifacts / "create_final_community_reports.parquet")
        node_df = pd.read_parquet(artifacts / "create_final_nodes.parquet")
        entity_df = pd.read_parquet(artifacts / "create_final_entities.parquet")

        reports = read_indexer_reports(report_df, node_df, community_level=2)
        entities = read_indexer_entities(entity_df, node_df, community_level=2)

        context_builder = GlobalCommunityContext(
            community_reports=reports,
            entities=entities,
            token_encoder=None,
        )

        return GlobalSearch(
            llm=self._llm(),
            context_builder=context_builder,
            token_encoder=None,
            max_data_tokens=12000,
            map_llm_params={"max_tokens": 1000, "temperature": 0},
            reduce_llm_params={"max_tokens": 2000, "temperature": 0},
            concurrent_coroutines=32,
            response_type="multiple paragraphs",
        )

    def _extract_sources(self, context_data: dict) -> list[dict]:
        """Normalize GraphRAG context_data into a flat list of source references."""
        sources = []
        # Text units
        for unit in context_data.get("text_units", []):
            sources.append({
                "type": "text_unit",
                "id": unit.get("id"),
                "text": unit.get("text", "")[:400],
                "document": unit.get("document_id"),
            })
        # Community reports
        for report in context_data.get("reports", []):
            sources.append({
                "type": "community_report",
                "id": report.get("id"),
                "title": report.get("title"),
                "summary": report.get("summary", "")[:400],
            })
        return sources
```

### Startup integration (FastAPI lifespan)

```python
# backend/app/main.py (relevant excerpt)

from contextlib import asynccontextmanager
from app.services.graphrag_service import GraphRAGService

graphrag_service: GraphRAGService | None = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global graphrag_service
    graphrag_service = GraphRAGService(workspace_root=settings.GRAPHRAG_ROOT)
    # Load artifacts if they exist from a previous indexing run
    artifacts = Path(settings.GRAPHRAG_ROOT) / "output" / "artifacts"
    if artifacts.exists() and any(artifacts.iterdir()):
        await graphrag_service.reload()
    yield
    # Cleanup (none needed for Parquet-based storage)
```

---

## 6. API Endpoints

All routes are prefixed with `/api/v1`.

### `POST /api/v1/session`

Create a new chat session.

**Request**: (no body)

**Response**:
```json
{
  "session_id": "uuid4",
  "created_at": "2026-06-07T10:00:00Z"
}
```

---

### `DELETE /api/v1/session/{session_id}`

Delete a session and its message history.

**Response**: `204 No Content`

---

### `POST /api/v1/chat`

Send a message and get a reply.

**Request**:
```json
{
  "session_id": "uuid4",
  "message": "What are the main themes in the corpus?",
  "mode": "global"   // "local" | "global" — default "local"
}
```

**Response**:
```json
{
  "reply": "The main themes are ...",
  "sources": [
    {
      "type": "text_unit",
      "id": "tu-001",
      "text": "excerpt...",
      "document": "uuid.txt"
    }
  ],
  "query_type": "global",
  "session_id": "uuid4"
}
```

**Error responses**:
- `400` — session not found
- `503` — GraphRAG artifacts not loaded (indexing not yet run)

---

### `POST /api/v1/admin/ingest`

Upload a document for indexing.

**Request**: `multipart/form-data` with field `file` (PDF, DOCX, or TXT).

**Response**:
```json
{
  "document_id": "uuid4",
  "filename": "annual_report.pdf",
  "status": "uploaded",
  "input_file": "graphrag_workspace/input/uuid4.txt"
}
```

---

### `POST /api/v1/admin/index`

Trigger the GraphRAG indexing pipeline as a background task.

**Request**: (no body)

**Response**:
```json
{
  "status": "started",
  "started_at": "2026-06-07T10:01:00Z"
}
```

Returns `409` if indexing is already running.

---

### `GET /api/v1/admin/status`

Poll indexing status.

**Response**:
```json
{
  "status": "running",          // "idle" | "running" | "completed" | "failed"
  "started_at": "2026-06-07T10:01:00Z",
  "finished_at": null,
  "error": null,
  "documents_indexed": 12
}
```

---

### `GET /health`

Liveness check.

**Response**:
```json
{
  "status": "ok",
  "graphrag_ready": true,
  "indexing_status": "idle"
}
```

---

## 7. Session Management

Sessions are stored in-memory using a plain Python dict. This is intentional — sessions are ephemeral, and the overhead of a database for conversation history is not justified at this scale.

```python
# backend/app/services/session_service.py

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta


@dataclass
class Message:
    role: str   # "user" | "assistant"
    content: str
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class Session:
    session_id: str
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_active: datetime = field(default_factory=datetime.utcnow)
    messages: list[Message] = field(default_factory=list)

    def add_message(self, role: str, content: str) -> None:
        self.messages.append(Message(role=role, content=content))
        # Keep only last 10 messages (5 turns)
        if len(self.messages) > 10:
            self.messages = self.messages[-10:]
        self.last_active = datetime.utcnow()

    def history_as_text(self) -> str:
        """Render message history for inclusion in GraphRAG context."""
        return "\n".join(f"{m.role}: {m.content}" for m in self.messages[:-1])


class SessionService:
    def __init__(self, ttl_minutes: int = 60):
        self._sessions: dict[str, Session] = {}
        self._ttl = timedelta(minutes=ttl_minutes)
        self._lock = asyncio.Lock()

    def create(self) -> Session:
        session_id = str(uuid.uuid4())
        session = Session(session_id=session_id)
        self._sessions[session_id] = session
        return session

    def get(self, session_id: str) -> Session | None:
        return self._sessions.get(session_id)

    def delete(self, session_id: str) -> bool:
        return self._sessions.pop(session_id, None) is not None

    async def cleanup_expired(self) -> int:
        """Remove sessions older than TTL. Run as a background task."""
        async with self._lock:
            now = datetime.utcnow()
            expired = [
                sid for sid, s in self._sessions.items()
                if now - s.last_active > self._ttl
            ]
            for sid in expired:
                del self._sessions[sid]
            return len(expired)
```

### TTL cleanup background task

```python
# In main.py lifespan, after startup:
async def _cleanup_loop():
    while True:
        await asyncio.sleep(300)  # every 5 minutes
        n = await session_service.cleanup_expired()
        if n:
            logger.info("Cleaned up %d expired sessions", n)

asyncio.create_task(_cleanup_loop())
```

---

## 8. Frontend Components

The frontend is a React + Vite + TypeScript single-page app. All UI labels are in Vietnamese.

### Component tree

```
App
├── ChatWindow
│   ├── MessageBubble (×N)
│   └── ChatInput
├── SourcesPanel
│   └── SourceCard (×N)
└── AdminPanel (collapsible sidebar)
    ├── UploadPanel
    └── IndexStatus
```

### `ChatWindow.tsx`

- Renders a scrollable list of `MessageBubble` components.
- Auto-scrolls to the bottom on new messages.
- Shows a typing indicator while waiting for the API response.
- Passes `mode` toggle ("Tìm kiếm cục bộ" / "Tìm kiếm toàn cục") to `ChatInput`.

### `MessageBubble.tsx`

- Props: `{ role: "user" | "assistant", content: string, sources?: Source[] }`
- User messages: right-aligned, primary color.
- Assistant messages: left-aligned, renders Markdown via `react-markdown`.
- If `sources` is non-empty, renders a "Xem nguồn" link that expands `SourcesPanel`.

### `ChatInput.tsx`

- Textarea with `Shift+Enter` for newline, `Enter` to send.
- Mode selector: `<select>` with options "Cục bộ" (local) and "Toàn cục" (global).
- Disabled while loading.

### `SourcesPanel.tsx` / `SourceCard.tsx`

- Slide-in panel (right side) showing citations returned by the API.
- `SourceCard`: shows `type`, truncated `text` or `summary`, and document ID.
- "Đóng" button to dismiss.

### `UploadPanel.tsx`

- Drag-and-drop zone (via `react-dropzone`) accepting `.pdf`, `.docx`, `.txt`.
- On drop: calls `POST /api/v1/admin/ingest`, shows upload progress.
- "Lập chỉ mục ngay" button: calls `POST /api/v1/admin/index`.
- Disabled while indexing is running.

### `IndexStatus.tsx`

- Polls `GET /api/v1/admin/status` every 3 seconds when status is `"running"`.
- Displays:
  - "Đang chờ" (idle)
  - "Đang lập chỉ mục..." + spinner (running)
  - "Hoàn thành ✓" (completed)
  - "Lỗi: {error}" (failed)

### `useChat.ts` hook

```typescript
// src/hooks/useChat.ts
export function useChat(sessionId: string) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [loading, setLoading] = useState(false);
  const [sources, setSources] = useState<Source[]>([]);

  const send = async (text: string, mode: "local" | "global") => {
    setLoading(true);
    setMessages(prev => [...prev, { role: "user", content: text }]);
    try {
      const res = await chatApi.send({ session_id: sessionId, message: text, mode });
      setMessages(prev => [...prev, { role: "assistant", content: res.reply }]);
      setSources(res.sources ?? []);
    } finally {
      setLoading(false);
    }
  };

  return { messages, loading, sources, send };
}
```

### State management (Zustand)

```typescript
// src/store/index.ts
interface AppStore {
  sessionId: string | null;
  indexStatus: "idle" | "running" | "completed" | "failed";
  setSessionId: (id: string) => void;
  setIndexStatus: (s: AppStore["indexStatus"]) => void;
}
```

---

## 9. Environment Variables

```bash
# .env.example

# ─── LLM / Embedding ─────────────────────────────────────────────────────────
GEMINI_API_KEY=your_gemini_api_key_here
LLM_MODEL=gemini-2.0-flash
EMBEDDING_MODEL=text-embedding-004

# ─── GraphRAG workspace ───────────────────────────────────────────────────────
GRAPHRAG_ROOT=./graphrag_workspace

# ─── Session ─────────────────────────────────────────────────────────────────
SESSION_TTL_MINUTES=60

# ─── CORS ────────────────────────────────────────────────────────────────────
CORS_ORIGINS=http://localhost:5173

# ─── App ─────────────────────────────────────────────────────────────────────
LOG_LEVEL=INFO
```

All backend config is loaded via `pydantic-settings`:

```python
# backend/app/config.py
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    GEMINI_API_KEY: str
    LLM_MODEL: str = "gemini-2.0-flash"
    EMBEDDING_MODEL: str = "text-embedding-004"
    GRAPHRAG_ROOT: str = "./graphrag_workspace"
    SESSION_TTL_MINUTES: int = 60
    CORS_ORIGINS: list[str] = ["http://localhost:5173"]
    LOG_LEVEL: str = "INFO"

    class Config:
        env_file = ".env"

settings = Settings()
```

---

## 10. `requirements.txt`

```
# Web framework
fastapi>=0.111.0
uvicorn[standard]>=0.29.0

# Microsoft GraphRAG
graphrag>=2.0.0

# Pydantic / config
pydantic-settings>=2.0.0
pydantic>=2.0.0

# File handling
python-multipart>=0.0.9
aiofiles>=24.0.0

# Document conversion
pymupdf>=1.24.0        # PDF → text
python-docx>=1.1.0     # DOCX → text

# Env
python-dotenv>=1.0.0

# Logging
structlog>=24.0.0

# Data (graphrag depends on these; pin for reproducibility)
pandas>=2.0.0
pyarrow>=16.0.0
lancedb>=0.8.0
```

**Frontend** (`frontend/package.json` key deps):
```json
{
  "dependencies": {
    "react": "^18.3.0",
    "react-dom": "^18.3.0",
    "zustand": "^4.5.0",
    "react-markdown": "^9.0.0",
    "react-dropzone": "^14.2.0",
    "axios": "^1.7.0"
  },
  "devDependencies": {
    "@vitejs/plugin-react": "^4.3.0",
    "typescript": "^5.5.0",
    "vite": "^5.3.0",
    "tailwindcss": "^3.4.0"
  }
}
```

---

## 11. `docker-compose.yml`

No Neo4j or external graph database needed — GraphRAG stores everything in Parquet files and LanceDB (both on-disk). Two services only.

```yaml
# docker-compose.yml
version: "3.9"

services:

  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile
    environment:
      - GEMINI_API_KEY=${GEMINI_API_KEY}
      - LLM_MODEL=${LLM_MODEL:-gemini-2.0-flash}
      - EMBEDDING_MODEL=${EMBEDDING_MODEL:-text-embedding-004}
      - GRAPHRAG_ROOT=/app/graphrag_workspace
      - SESSION_TTL_MINUTES=${SESSION_TTL_MINUTES:-60}
      - CORS_ORIGINS=http://localhost:80
    volumes:
      # Persist graphrag workspace (indexes, artifacts) across container restarts
      - graphrag_data:/app/graphrag_workspace
      # Persist raw uploaded documents
      - documents_data:/app/data/documents
    ports:
      - "8000:8000"
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3

  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
    ports:
      - "80:80"
    depends_on:
      - backend
    restart: unless-stopped

volumes:
  graphrag_data:
  documents_data:
```

### `backend/Dockerfile`

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Initialize graphrag workspace if not present
RUN mkdir -p graphrag_workspace/input graphrag_workspace/output data/documents

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### `frontend/Dockerfile`

```dockerfile
FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
```

### `frontend/nginx.conf`

```nginx
server {
    listen 80;

    location /api/ {
        proxy_pass http://backend:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location / {
        root /usr/share/nginx/html;
        try_files $uri $uri/ /index.html;
    }
}
```

---

## 12. Key Differences from Existing `graphrag-assistant`

| Aspect | Custom `graphrag-assistant` | This project (`new-rag-2026`) |
|---|---|---|
| **Entity extraction** | Custom LLM prompts + regex parsing | `graphrag index` (MSFT-maintained prompts + robust parser) |
| **Community detection** | Custom Leiden implementation | Built into `graphrag index` (tested at scale by MSFT) |
| **Graph storage** | Neo4j (requires running instance) | Parquet files + LanceDB (zero infrastructure) |
| **Query engine** | Custom retrieval + re-ranking | `LocalSearch` / `GlobalSearch` from `graphrag` package |
| **Embedding handling** | Custom batching + retry logic | Handled by `graphrag` internally |
| **Configuration** | Multiple Python config files | Single `settings.yaml` |
| **Upgrade path** | Manual (all code in-repo) | `pip install --upgrade graphrag` |
| **Maintenance burden** | High — team owns all logic | Low — MSFT owns core logic |
| **Graph visualization** | Available (Neo4j Browser) | Not available (Parquet/LanceDB) |
| **Incremental indexing** | Manual delta logic | Built into `graphrag index` (2.x+) |
| **Vietnamese prompts** | In-repo, hand-tuned | Customize `graphrag_workspace/prompts/` |

---

## 13. Limitations and Gotchas

### Indexing cost

GraphRAG indexing is LLM-intensive. Every text chunk gets an extraction call, every community gets a summarization call. For a 100-document corpus (~500 chunks), expect 500+ LLM calls for extraction and 50–200 calls for community summarization. At Gemini free-tier rate limits this may take 15–60 minutes. For production, use a paid Gemini tier or batch the indexing during off-hours.

Mitigation: only re-index when the corpus changes significantly. Incremental indexing (GraphRAG 2.x) avoids re-processing unchanged documents.

### Re-indexing clears artifacts

Running `graphrag index` on an existing workspace overwrites `output/`. There is no "merge" mode. If incremental indexing is needed, ensure GraphRAG 2.x is pinned and that input file names are stable (the UUID prefix scheme in Section 4 handles this).

### Embedding dimensions

`text-embedding-004` (Gemini) produces **768-dimensional** vectors, not 1536 (OpenAI ada-002) or 3072 (OpenAI text-embedding-3-large). LanceDB stores whatever dimension is produced, so this is not a problem as long as you don't mix models mid-project. If you switch embedding models, delete `output/lancedb` and re-index.

### No graph visualization

The existing `graphrag-assistant` used Neo4j, which provides a visual graph browser. This project uses Parquet + LanceDB — there is no built-in visualization. If graph visualization is required, consider the `graphrag-neo4j` plugin (separate install), but this adds infrastructure complexity.

### Community level selection

`read_indexer_entities(..., community_level=2)` controls which level of the Leiden hierarchy is used. Level 2 works well for medium-sized corpora. For very small corpora (<20 documents), use level 1; for very large corpora (1000+ documents), experiment with level 3. Wrong community level → poor search quality.

### Cold-start on large corpora

At startup, `GraphRAGService.reload()` reads all Parquet files into memory. For very large corpora (hundreds of thousands of entities), this may take 10–30 seconds and consume significant RAM. Plan for a health check grace period.

### `graphrag` package API stability

The `graphrag` Python API (especially `query.indexer_adapters`) changed significantly between 0.x and 2.x. Pin `graphrag>=2.0.0,<3.0.0` in requirements and test before upgrading.

---

## 14. Implementation Order

Work in this order to enable end-to-end testing at each step before adding the next layer.

1. **Project scaffold** — Create directory structure, `requirements.txt`, `.env.example`. Initialize a Python virtual environment. Install `graphrag`.

2. **GraphRAG workspace init** — Run `graphrag init --root ./graphrag_workspace`. Edit `settings.yaml` with Gemini credentials. Test with a small sample corpus: place 2–3 `.txt` files in `input/` and run `graphrag index`. Verify Parquet artifacts appear in `output/artifacts/`.

3. **`config.py`** — Pydantic settings class. Load from `.env`. Verify all env vars resolve correctly.

4. **`indexing_service.py`** — Wrap `graphrag index` as a subprocess. Implement `run_index()` (async, background), `get_status()`, and state machine (`idle` → `running` → `completed`/`failed`). Test standalone.

5. **`graphrag_service.py`** — Implement `_build_local_search()` and `_build_global_search()` using the Parquet artifacts from step 2. Implement `search()` and `reload()`. Test standalone with `asyncio.run()`.

6. **`session_service.py`** — In-memory session store with `create`, `get`, `delete`, TTL cleanup. Unit test with `pytest`.

7. **`schemas.py`** — Pydantic request/response models for all endpoints.

8. **`routers/health.py`** — `GET /health`. Simplest router; use to validate FastAPI wiring.

9. **`routers/admin.py`** — `POST /ingest` (file upload + conversion), `POST /index`, `GET /status`. Wire `IndexingService` and `GraphRAGService.reload()` on completion.

10. **`routers/session.py`** — `POST /session`, `DELETE /session/{id}`.

11. **`routers/chat.py`** — `POST /chat`. Wire `SessionService` + `GraphRAGService.search()`.

12. **`main.py`** — FastAPI app with lifespan, CORS middleware, router registration, background TTL cleanup task. Run `uvicorn` and test all endpoints with `curl` or Postman.

13. **Frontend scaffold** — `npm create vite@latest frontend -- --template react-ts`. Install deps. Configure Vite proxy (`/api` → `http://localhost:8000`).

14. **`api/client.ts` + `chatApi.ts` + `sessionApi.ts`** — Axios-based API wrappers.

15. **`useSession.ts`** — Hook that creates a session on mount and exposes `sessionId`.

16. **`useChat.ts`** — Hook that sends messages and manages local message state.

17. **`ChatInput.tsx` + `MessageBubble.tsx` + `ChatWindow.tsx`** — Core chat UI. Wire to `useChat` and `useSession`. Test end-to-end chat flow.

18. **`SourceCard.tsx` + `SourcesPanel.tsx`** — Sources display. Wire to chat response `sources` field.

19. **`UploadPanel.tsx` + `IndexStatus.tsx`** — Admin UI. Wire upload and index trigger. Poll status.

20. **`store/index.ts`** — Add Zustand store for global state (session ID, index status).

21. **`App.tsx`** — Compose all components. Add Vietnamese labels throughout.

22. **`docker-compose.yml` + Dockerfiles + `nginx.conf`** — Containerize. Test `docker compose up` end-to-end.

23. **Prompt customization (optional)** — Edit `graphrag_workspace/prompts/entity_extraction.txt` for Vietnamese-language documents. Re-run indexing and compare extraction quality.

24. **End-to-end smoke test** — Upload 5 real documents, trigger indexing, wait for completion, run 5 LOCAL and 5 GLOBAL queries, verify responses cite real sources.
