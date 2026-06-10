# Ragas Evaluation Report — Implementation Plan

> **Project**: `new-rag-2026`
> **Purpose**: Score real user conversations with RAGAS metrics directly from chat history, with a UI for session browsing, turn selection, and result comparison.

---

## Table of Contents

1. [Overview](#1-overview)
2. [SQLite Persistence Schema](#2-sqlite-persistence-schema)
3. [`history_store.py` Design](#3-history_storepy-design)
4. [`eval_service.py` Design](#4-eval_servicepy-design)
5. [New API Endpoints](#5-new-api-endpoints)
6. [Integration into Chat Router](#6-integration-into-chat-router)
7. [Frontend Component Tree](#7-frontend-component-tree)
8. [Frontend Components](#8-frontend-components)
9. [Comparison Feature](#9-comparison-feature)
10. [Privacy Considerations](#10-privacy-considerations)
11. [Implementation Order](#11-implementation-order)

---

## 1. Overview

### What this feature does

The Ragas Evaluation Report lets an admin score **real user conversations** — not curated test sets — with RAGAS metrics. From the "Đánh giá" tab in the frontend:

1. Browse all past sessions with turn counts and timestamps
2. Click a session to see each Q&A turn
3. Select one turn, a set of turns, or the entire session
4. Optionally provide reference answers for metrics that need ground truth
5. Choose a judge LLM (OpenAI / Gemini / Siliconflow) and click "Chạy đánh giá"
6. View a color-coded results table (green ≥ 0.8, yellow ≥ 0.6, red < 0.6)
7. Compare two runs side-by-side to track score changes across config updates

### Why it's valuable

The batch `eval/eval_single.py` script tests curated questions. This report tests what **real users actually asked**, revealing quality gaps that curated sets miss. It also enables regression testing: after changing chunk size, hop depth, or LLM provider, re-run the same set of real turns and compare scores.

### Key design decision: SQLite persistence

Sessions are currently in-memory. The eval report requires persistent chat history across restarts. The solution is a lightweight SQLite store (`history_store.py` with `aiosqlite`) that saves every chat turn as a background task — non-blocking, no impact on chat latency. RAGAS scoring then reads directly from SQLite without HTTP round-trips to the backend.

---

## 2. SQLite Persistence Schema

Database file: `data/history.db` (created automatically on startup).

```sql
-- Every completed chat turn
CREATE TABLE IF NOT EXISTS turns (
    turn_id       TEXT PRIMARY KEY,          -- uuid4
    session_id    TEXT NOT NULL,
    turn_number   INTEGER NOT NULL,
    question      TEXT NOT NULL,
    answer        TEXT NOT NULL,
    sources       TEXT NOT NULL DEFAULT '[]', -- JSON: list of Source objects
    domain_keys   TEXT NOT NULL DEFAULT '[]', -- JSON: ["hr", "benefits"]
    query_type    TEXT NOT NULL DEFAULT '',
    is_fallback   INTEGER NOT NULL DEFAULT 0,
    timestamp     TEXT NOT NULL              -- ISO 8601
);

CREATE INDEX IF NOT EXISTS idx_turns_session ON turns(session_id);
CREATE INDEX IF NOT EXISTS idx_turns_timestamp ON turns(timestamp);

-- Evaluation run metadata
CREATE TABLE IF NOT EXISTS eval_runs (
    run_id          TEXT PRIMARY KEY,
    created_at      TEXT NOT NULL,
    turn_count      INTEGER NOT NULL,
    judge_provider  TEXT NOT NULL,
    judge_model     TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'pending',  -- pending | running | done | failed
    error           TEXT
);

-- Per-turn scores for each run
CREATE TABLE IF NOT EXISTS eval_run_scores (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id               TEXT NOT NULL REFERENCES eval_runs(run_id),
    turn_id              TEXT NOT NULL REFERENCES turns(turn_id),
    faithfulness         REAL,
    answer_relevancy     REAL,
    context_precision    REAL,
    context_recall       REAL,
    answer_correctness   REAL,
    reference_answer     TEXT    -- optional ground truth used for this score
);

CREATE INDEX IF NOT EXISTS idx_scores_run ON eval_run_scores(run_id);
```

---

## 3. `history_store.py` Design

```python
# backend/app/services/history_store.py

import asyncio
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

import aiosqlite
import structlog

logger = structlog.get_logger()

DB_PATH = os.environ.get("HISTORY_DB_PATH", "./data/history.db")


class HistoryStore:
    def __init__(self) -> None:
        self._db_path = Path(DB_PATH)

    async def initialize(self) -> None:
        """Create DB file and tables if they don't exist. Called at FastAPI startup."""
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self._db_path) as db:
            await db.executescript(SCHEMA_SQL)   # SCHEMA_SQL = CREATE TABLE statements from Section 2
            await db.commit()
        logger.info("history_store_initialized", path=str(self._db_path))

    async def save_turn(
        self,
        session_id: str,
        turn_number: int,
        question: str,
        answer: str,
        sources: list[dict],
        domain_keys: list[str],
        query_type: str,
        is_fallback: bool = False,
    ) -> str:
        """Persist a completed chat turn. Returns turn_id."""
        turn_id = str(uuid.uuid4())
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """
                INSERT INTO turns
                    (turn_id, session_id, turn_number, question, answer,
                     sources, domain_keys, query_type, is_fallback, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    turn_id, session_id, turn_number, question, answer,
                    json.dumps(sources, ensure_ascii=False),
                    json.dumps(domain_keys),
                    query_type,
                    int(is_fallback),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            await db.commit()
        return turn_id

    async def list_sessions(self, limit: int = 50, offset: int = 0) -> list[dict]:
        """Return sessions ordered by most recent activity."""
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT session_id,
                       COUNT(*) AS turn_count,
                       MAX(timestamp) AS last_active,
                       MIN(timestamp) AS created_at
                FROM turns
                GROUP BY session_id
                ORDER BY last_active DESC
                LIMIT ? OFFSET ?
                """,
                (limit, offset),
            )
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    async def get_session_turns(self, session_id: str) -> list[dict]:
        """Return all turns for a session ordered by turn_number."""
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT * FROM turns
                WHERE session_id = ?
                ORDER BY turn_number ASC
                """,
                (session_id,),
            )
            rows = await cursor.fetchall()
            return [_deserialize_turn(dict(r)) for r in rows]

    async def get_turns_by_ids(self, turn_ids: list[str]) -> list[dict]:
        """Fetch specific turns by id."""
        placeholders = ",".join("?" * len(turn_ids))
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                f"SELECT * FROM turns WHERE turn_id IN ({placeholders})", turn_ids
            )
            rows = await cursor.fetchall()
            return [_deserialize_turn(dict(r)) for r in rows]

    async def save_eval_run(
        self,
        run_id: str,
        turn_count: int,
        judge_provider: str,
        judge_model: str,
    ) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """
                INSERT INTO eval_runs (run_id, created_at, turn_count, judge_provider, judge_model, status)
                VALUES (?, ?, ?, ?, ?, 'pending')
                """,
                (run_id, datetime.now(timezone.utc).isoformat(), turn_count, judge_provider, judge_model),
            )
            await db.commit()

    async def update_run_status(self, run_id: str, status: str, error: str | None = None) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "UPDATE eval_runs SET status = ?, error = ? WHERE run_id = ?",
                (status, error, run_id),
            )
            await db.commit()

    async def save_scores(self, run_id: str, scores: list[dict]) -> None:
        """Persist per-turn RAGAS scores."""
        async with aiosqlite.connect(self._db_path) as db:
            await db.executemany(
                """
                INSERT INTO eval_run_scores
                    (run_id, turn_id, faithfulness, answer_relevancy,
                     context_precision, context_recall, answer_correctness, reference_answer)
                VALUES (:run_id, :turn_id, :faithfulness, :answer_relevancy,
                        :context_precision, :context_recall, :answer_correctness, :reference_answer)
                """,
                [{"run_id": run_id, **s} for s in scores],
            )
            await db.commit()

    async def list_runs(self, limit: int = 20) -> list[dict]:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM eval_runs ORDER BY created_at DESC LIMIT ?", (limit,)
            )
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    async def get_run_scores(self, run_id: str) -> list[dict]:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT s.*, t.question, t.answer, t.domain_keys, t.query_type
                FROM eval_run_scores s
                JOIN turns t ON s.turn_id = t.turn_id
                WHERE s.run_id = ?
                ORDER BY s.id ASC
                """,
                (run_id,),
            )
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    async def delete_old_turns(self, retention_days: int) -> int:
        """Delete turns older than retention_days. Returns deleted count."""
        cutoff = datetime.now(timezone.utc).replace(
            tzinfo=None
        ).isoformat()  # simplification; real impl subtracts retention_days
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                "DELETE FROM turns WHERE timestamp < date('now', ?)",
                (f"-{retention_days} days",),
            )
            await db.commit()
            return cursor.rowcount


def _deserialize_turn(row: dict) -> dict:
    row["sources"] = json.loads(row.get("sources") or "[]")
    row["domain_keys"] = json.loads(row.get("domain_keys") or "[]")
    row["is_fallback"] = bool(row.get("is_fallback", 0))
    return row
```

### Non-blocking writes

`save_turn()` is called from the chat router as a fire-and-forget background task:

```python
# In chat router, after building the response:
asyncio.create_task(
    history_store.save_turn(
        session_id=body.session_id,
        turn_number=session.turn_count,
        question=body.message,
        answer=result.final_answer,
        sources=[s.model_dump() for s in response.sources],
        domain_keys=result.domain_keys,
        query_type=result.search_mode,
        is_fallback=is_fallback,
    )
)
```

This never blocks the chat response — the turn is saved in the background.

---

## 4. `eval_service.py` Design

```python
# backend/app/services/eval_service.py

import asyncio
import uuid
from datetime import datetime, timezone

import pandas as pd
from ragas import EvaluationDataset, RunConfig, SingleTurnSample, evaluate
from ragas.metrics import (
    answer_correctness, answer_relevancy, context_precision,
    context_recall, faithfulness,
)

from app.services.history_store import HistoryStore
from app.services.llm_service import create_chat_model, create_embeddings

METRICS = [faithfulness, answer_relevancy, context_precision, context_recall, answer_correctness]
METRIC_NAMES = ["faithfulness", "answer_relevancy", "context_precision", "context_recall", "answer_correctness"]


class EvalService:
    def __init__(self, history_store: HistoryStore) -> None:
        self._store = history_store
        # Track in-progress runs to prevent duplicate submissions
        self._running: set[str] = set()

    async def start_run(
        self,
        turn_ids: list[str],
        judge_provider: str,
        judge_model: str,
        reference_answers: dict[str, str],  # {turn_id: reference_text}
    ) -> str:
        """Persist run metadata and start background scoring. Returns run_id."""
        run_id = str(uuid.uuid4())
        await self._store.save_eval_run(run_id, len(turn_ids), judge_provider, judge_model)
        asyncio.create_task(
            self._run_scoring(run_id, turn_ids, judge_provider, judge_model, reference_answers)
        )
        return run_id

    async def _run_scoring(
        self,
        run_id: str,
        turn_ids: list[str],
        judge_provider: str,
        judge_model: str,
        reference_answers: dict[str, str],
    ) -> None:
        self._running.add(run_id)
        await self._store.update_run_status(run_id, "running")
        try:
            turns = await self._store.get_turns_by_ids(turn_ids)
            if not turns:
                await self._store.update_run_status(run_id, "failed", "No turns found")
                return

            # Build RAGAS dataset — same pattern as eval/eval_single.py
            samples = []
            for t in turns:
                contexts = [s.get("text", "") for s in t["sources"] if s.get("text")]
                reference = reference_answers.get(t["turn_id"], "")
                samples.append(SingleTurnSample(
                    user_input=t["question"],
                    response=t["answer"],
                    retrieved_contexts=contexts if contexts else [""],
                    reference=reference,
                ))
            dataset = EvaluationDataset(samples=samples)

            # Build judge — reuse LangChain factory, wrapped for RAGAS
            from ragas.llms import LangchainLLMWrapper
            from ragas.embeddings import LangchainEmbeddingsWrapper
            from langchain_openai import OpenAIEmbeddings
            import os

            llm_model = create_chat_model(judge_provider)
            # RAGAS embeddings always use OpenAI (most compatible)
            embed_model = OpenAIEmbeddings(
                model="text-embedding-3-small",
                api_key=os.environ.get("OPENAI_API_KEY", ""),
            )
            ragas_llm = LangchainLLMWrapper(llm_model)
            ragas_emb = LangchainEmbeddingsWrapper(embed_model)

            run_config = RunConfig(max_retries=3, max_wait=60, timeout=120)
            result = evaluate(
                dataset=dataset,
                metrics=METRICS,
                llm=ragas_llm,
                embeddings=ragas_emb,
                run_config=run_config,
            )
            df: pd.DataFrame = result.to_pandas()

            # Persist scores
            scores = []
            for i, t in enumerate(turns):
                row = df.iloc[i] if i < len(df) else {}
                scores.append({
                    "turn_id": t["turn_id"],
                    "faithfulness": _safe_float(row.get("faithfulness")),
                    "answer_relevancy": _safe_float(row.get("answer_relevancy")),
                    "context_precision": _safe_float(row.get("context_precision")),
                    "context_recall": _safe_float(row.get("context_recall")),
                    "answer_correctness": _safe_float(row.get("answer_correctness")),
                    "reference_answer": reference_answers.get(t["turn_id"], ""),
                })
            await self._store.save_scores(run_id, scores)
            await self._store.update_run_status(run_id, "done")

        except Exception as e:
            await self._store.update_run_status(run_id, "failed", str(e))
        finally:
            self._running.discard(run_id)

    def is_running(self, run_id: str) -> bool:
        return run_id in self._running


def _safe_float(val) -> float | None:
    try:
        return float(val) if val is not None and str(val) != "nan" else None
    except (TypeError, ValueError):
        return None
```

---

## 5. New API Endpoints

Add `backend/app/routers/eval.py`. All routes under `/api/v1/eval`.

### `GET /api/v1/eval/sessions`
List sessions with turn counts.

**Query params**: `limit=50`, `offset=0`

**Response**:
```json
{
  "sessions": [
    {
      "session_id": "abc123",
      "turn_count": 8,
      "last_active": "2026-06-07T10:30:00Z",
      "created_at": "2026-06-07T09:15:00Z"
    }
  ],
  "total": 42
}
```

### `GET /api/v1/eval/sessions/{session_id}/turns`
All turns for a session.

**Response**:
```json
{
  "session_id": "abc123",
  "turns": [
    {
      "turn_id": "uuid",
      "turn_number": 1,
      "question": "Nhân viên mới được hưởng bao nhiêu ngày phép?",
      "answer": "Theo chính sách công ty...",
      "sources": [...],
      "domain_keys": ["hr"],
      "query_type": "local",
      "is_fallback": false,
      "timestamp": "2026-06-07T09:16:00Z"
    }
  ]
}
```

### `POST /api/v1/eval/run`
Trigger a RAGAS evaluation on selected turns. Runs as a background task.

**Request**:
```json
{
  "turn_ids": ["uuid1", "uuid2", "uuid3"],
  "judge_provider": "openai",
  "judge_model": "gpt-4o-mini",
  "reference_answers": {
    "uuid1": "Optional reference answer for context_recall scoring",
    "uuid2": ""
  }
}
```

**Response** (202 Accepted):
```json
{
  "run_id": "run-uuid",
  "status": "pending",
  "turn_count": 3
}
```

### `GET /api/v1/eval/runs`
List past evaluation runs.

**Response**:
```json
{
  "runs": [
    {
      "run_id": "run-uuid",
      "created_at": "2026-06-07T11:00:00Z",
      "turn_count": 5,
      "judge_provider": "openai",
      "judge_model": "gpt-4o-mini",
      "status": "done"
    }
  ]
}
```

### `GET /api/v1/eval/runs/{run_id}`
Full run results with per-turn scores.

**Response**:
```json
{
  "run_id": "run-uuid",
  "status": "done",
  "judge_provider": "openai",
  "judge_model": "gpt-4o-mini",
  "created_at": "2026-06-07T11:00:00Z",
  "scores": [
    {
      "turn_id": "uuid1",
      "question": "Nhân viên mới được hưởng bao nhiêu ngày phép?",
      "answer": "Theo chính sách...",
      "domain_keys": ["hr"],
      "faithfulness": 0.92,
      "answer_relevancy": 0.88,
      "context_precision": 0.75,
      "context_recall": null,
      "answer_correctness": null,
      "reference_answer": ""
    }
  ],
  "averages": {
    "faithfulness": 0.89,
    "answer_relevancy": 0.85,
    "context_precision": 0.72,
    "context_recall": null,
    "answer_correctness": null
  }
}
```

### `GET /api/v1/eval/runs/{run_id}/export`
Download results as CSV (Content-Disposition: attachment).

---

## 6. Integration into Chat Router

In `backend/app/routers/chat.py`, after building the final `ChatResponse`, add the non-blocking save:

```python
# backend/app/routers/chat.py

from app.services.history_store import HistoryStore  # injected via app.state

@router.post("/chat", response_model=ChatResponse)
async def chat(body: ChatRequest, request: Request):
    history_store: HistoryStore = request.app.state.history_store
    # ... existing chat logic ...

    # Non-blocking — never delays the response
    asyncio.create_task(
        history_store.save_turn(
            session_id=body.session_id,
            turn_number=session.turn_count,
            question=body.message,
            answer=orch_result.final_answer,
            sources=[s.model_dump() for s in chat_response.sources],
            domain_keys=orch_result.domain_keys,
            query_type=orch_result.search_mode,
            is_fallback=is_fallback,
        )
    )
    return chat_response
```

In `backend/app/main.py` lifespan, initialize both stores:

```python
app.state.history_store = HistoryStore()
await app.state.history_store.initialize()
app.state.eval_service = EvalService(app.state.history_store)
```

---

## 7. Frontend Component Tree

The "Đánh giá" tab sits alongside "Hỏi đáp" and "Quản trị" in the header tab switcher.

```
AppShell
  ├── Header (tabs: Hỏi đáp | Quản trị | Đánh giá)
  └── EvalTab                          ← new top-level tab
      ├── EvalLayout (two-column)
      │   ├── Left: SessionBrowser
      │   │   ├── SessionList          ← paginated list of sessions
      │   │   └── TurnTable            ← turns for selected session
      │   └── Right: ResultsPanel
      │       ├── RunList              ← past eval runs
      │       └── EvalResultTable      ← scores for selected run
      └── EvalConfigModal              ← opens on "Chạy đánh giá"
          └── MetricBarChart           ← score averages bar chart
```

---

## 8. Frontend Components

### `api/evalApi.ts`
```typescript
export const listSessions = (limit=50, offset=0) =>
  client.get(`/eval/sessions`, { params: { limit, offset } });

export const getSessionTurns = (sessionId: string) =>
  client.get(`/eval/sessions/${sessionId}/turns`);

export const startEvalRun = (body: EvalRunRequest) =>
  client.post(`/eval/run`, body);

export const listRuns = () => client.get(`/eval/runs`);

export const getRunResult = (runId: string) =>
  client.get(`/eval/runs/${runId}`);

export const exportRun = (runId: string) =>
  client.get(`/eval/runs/${runId}/export`, { responseType: 'blob' });
```

### `components/eval/SessionList.tsx`
- Calls `listSessions()` on mount, auto-refreshes every 30s
- Each row: session ID (truncated), turn count badge, last active time
- Click row → sets `selectedSessionId` in store → loads `TurnTable`
- Pagination with "Xem thêm" button

### `components/eval/TurnTable.tsx`
- Calls `getSessionTurns(selectedSessionId)` when session changes
- Each row: turn number, question (first 60 chars), domain badges, fallback badge if `is_fallback`
- Checkbox on each row + "Chọn tất cả" header checkbox
- Selected count badge: "Đã chọn 3 lượt"
- "Chạy đánh giá" button (disabled if 0 selected) → opens `EvalConfigModal`

### `components/eval/EvalConfigModal.tsx`
Props: `selectedTurns: Turn[]`, `onClose`, `onSubmit`

- **Judge provider** pills: OpenAI / Gemini / Siliconflow
- **Judge model** text input (pre-filled per provider: gpt-4o-mini / gemini-2.0-flash / DeepSeek-V3)
- **Reference answers** section (collapsible): one textarea per selected turn, labelled with question preview. Note: "Bỏ qua nếu không có câu trả lời tham chiếu — context_recall và answer_correctness sẽ bị bỏ qua"
- "Bắt đầu đánh giá" button → calls `startEvalRun()` → shows toast "Đang chạy đánh giá..." → closes modal

### `components/eval/RunList.tsx`
- Calls `listRuns()` on mount + after any new run starts
- Each row: run ID (short), timestamp, turn count, judge info, status badge (pending=yellow, running=blue spinner, done=green, failed=red)
- Click done row → sets `selectedRunId` → loads `EvalResultTable`
- Status auto-polls every 3s while any run is `pending` or `running`

### `components/eval/EvalResultTable.tsx`
Props: `runId: string`, `compareRunId?: string`

- Calls `getRunResult(runId)` and optionally `getRunResult(compareRunId)`
- Table columns: Question | Domains | faithfulness | answer_relevancy | context_precision | context_recall | answer_correctness
- Score cells: color-coded (green ≥ 0.8, amber ≥ 0.6, red < 0.6, gray = null/no reference)
- Footer row: averages per metric
- If `compareRunId` is set, add Δ sub-columns (e.g. `+0.05` in green, `-0.03` in red)
- "Tải CSV" button → calls `exportRun(runId)` → downloads file
- "So sánh với..." dropdown → select another run to compare

### `components/eval/MetricBarChart.tsx`
Props: `averages: Record<string, number | null>`

- Horizontal bars for each of the 5 metrics
- Color: green if ≥ 0.8, amber if ≥ 0.6, red if < 0.6
- Shows "–" for null metrics (no reference provided)
- Uses Chart.js `Bar` (already in frontend dependencies)

---

## 9. Comparison Feature

When two runs are compared, `EvalResultTable` shows a Δ column for each metric:

```typescript
function delta(current: number | null, baseline: number | null): string | null {
  if (current == null || baseline == null) return null;
  const d = current - baseline;
  return `${d >= 0 ? "+" : ""}${d.toFixed(3)}`;
}
```

Delta badge styling:
- `+0.05` or higher → green text
- `-0.01` to `+0.04` → gray (negligible)
- `-0.02` or lower → red text

The comparison is only meaningful when both runs cover the same `turn_ids`. The UI shows a warning badge if the turn sets differ: "⚠️ Các lượt không khớp hoàn toàn".

---

## 10. Privacy Considerations

| Concern | Mitigation |
|---|---|
| Sensitive user queries stored on disk | `data/history.db` is gitignored; add to `.gitignore` |
| History grows indefinitely | `HISTORY_RETENTION_DAYS=90` env var; cleanup runs at startup via `delete_old_turns()` |
| Eval API exposed without auth | Add `EVAL_ADMIN_KEY` env var; router checks `X-Admin-Key` header |
| Judge API key in frontend request | Judge provider/model is sent from frontend but API keys stay server-side |

```bash
# .env additions
HISTORY_DB_PATH=./data/history.db
HISTORY_RETENTION_DAYS=90
EVAL_ADMIN_KEY=               # optional; if set, /eval/* requires X-Admin-Key header
```

---

## 11. Implementation Order

1. **`data/` directory** — create with `.gitkeep`; add `data/history.db` to `.gitignore`

2. **`backend/app/models/eval.py`** — Pydantic models: `EvalTurn`, `EvalRunRequest`, `EvalRunResult`, `EvalTurnScore`

3. **`backend/app/services/history_store.py`** — full implementation with SQLite schema creation on init. Test: `python -c "import asyncio; from app.services.history_store import HistoryStore; asyncio.run(HistoryStore().initialize()); print('OK')"`

4. **`backend/app/services/eval_service.py`** — scoring logic reusing RAGAS pattern. Test dry-run with mock turns (no judge API key needed in dry mode).

5. **`backend/app/routers/eval.py`** — all 6 endpoints. Inject `history_store` and `eval_service` from `app.state`.

6. **`backend/app/main.py`** — add `HistoryStore` and `EvalService` to lifespan; register `eval.router`.

7. **`backend/app/routers/chat.py`** — add `asyncio.create_task(history_store.save_turn(...))` after each successful response.

8. **`backend/requirements.txt`** — add `aiosqlite>=0.20.0` and `ragas==0.4.3` (already in eval/ but needed in backend too for `eval_service.py`).

9. **Frontend: `src/types/eval.ts`** — TypeScript types for all eval API shapes.

10. **Frontend: `src/api/evalApi.ts`** — API helpers.

11. **Frontend: `src/store/evalStore.ts`** — Zustand: `selectedSessionId`, `selectedTurnIds`, `selectedRunId`, `compareRunId`.

12. **Frontend: `src/components/eval/`** — implement in order: `SessionList` → `TurnTable` → `EvalConfigModal` → `RunList` → `EvalResultTable` → `MetricBarChart`.

13. **Frontend: `src/App.tsx`** — add "Đánh giá" tab to the header + routing to `EvalTab`.

14. **Integration test** — start backend, send 3 real chat messages, open Eval tab, select all 3 turns, run with `--dry-run` equivalent (no judge key), verify turns appear in `GET /eval/sessions`.

15. **Full eval test** — provide `OPENAI_API_KEY`, run a real RAGAS evaluation on 3 turns, verify scores appear in `EvalResultTable` with color coding.
