"""
SQLite-backed chat history store.

All writes are async and non-blocking via aiosqlite.
Designed to be called as asyncio.create_task() from the chat router so it
never adds latency to the response path.
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

import aiosqlite
import structlog

logger = structlog.get_logger()

DB_PATH = os.environ.get("HISTORY_DB_PATH", "./data/history.db")

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS turns (
    turn_id       TEXT PRIMARY KEY,
    session_id    TEXT NOT NULL,
    turn_number   INTEGER NOT NULL,
    question      TEXT NOT NULL,
    answer        TEXT NOT NULL,
    sources       TEXT NOT NULL DEFAULT '[]',
    domain_keys   TEXT NOT NULL DEFAULT '[]',
    query_type    TEXT NOT NULL DEFAULT '',
    is_fallback   INTEGER NOT NULL DEFAULT 0,
    timestamp     TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_turns_session ON turns(session_id);
CREATE INDEX IF NOT EXISTS idx_turns_timestamp ON turns(timestamp);

CREATE TABLE IF NOT EXISTS eval_runs (
    run_id          TEXT PRIMARY KEY,
    created_at      TEXT NOT NULL,
    turn_count      INTEGER NOT NULL,
    judge_provider  TEXT NOT NULL,
    judge_model     TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'pending',
    error           TEXT
);

CREATE TABLE IF NOT EXISTS eval_run_scores (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id               TEXT NOT NULL REFERENCES eval_runs(run_id),
    turn_id              TEXT NOT NULL REFERENCES turns(turn_id),
    faithfulness         REAL,
    answer_relevancy     REAL,
    context_precision    REAL,
    context_recall       REAL,
    answer_correctness   REAL,
    reference_answer     TEXT
);

CREATE INDEX IF NOT EXISTS idx_scores_run ON eval_run_scores(run_id);

CREATE TABLE IF NOT EXISTS token_usage (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id        TEXT    NOT NULL,
    turn_id           TEXT,
    call_type         TEXT    NOT NULL,
    provider          TEXT    NOT NULL,
    model             TEXT    NOT NULL,
    prompt_tokens     INTEGER NOT NULL DEFAULT 0,
    completion_tokens INTEGER NOT NULL DEFAULT 0,
    total_tokens      INTEGER NOT NULL DEFAULT 0,
    cost_usd          REAL    NOT NULL DEFAULT 0.0,
    error             INTEGER NOT NULL DEFAULT 0,
    timestamp         TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_token_session ON token_usage(session_id);
CREATE INDEX IF NOT EXISTS idx_token_turn    ON token_usage(turn_id);
CREATE INDEX IF NOT EXISTS idx_token_type    ON token_usage(call_type);
"""


class HistoryStore:
    def __init__(self) -> None:
        self._db_path = Path(DB_PATH)

    async def initialize(self) -> None:
        """Create DB file and tables if they don't exist. Called at FastAPI startup."""
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self._db_path) as db:
            await db.executescript(SCHEMA_SQL)
            await db.commit()
        logger.info("history_store_initialized", path=str(self._db_path))

    # -- Chat turns ------------------------------------------------------------

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
        try:
            async with aiosqlite.connect(self._db_path) as db:
                await db.execute(
                    """
                    INSERT INTO turns
                        (turn_id, session_id, turn_number, question, answer,
                         sources, domain_keys, query_type, is_fallback, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        turn_id,
                        session_id,
                        turn_number,
                        question,
                        answer,
                        json.dumps(sources, ensure_ascii=False),
                        json.dumps(domain_keys),
                        query_type,
                        int(is_fallback),
                        datetime.now(timezone.utc).isoformat(),
                    ),
                )
                await db.commit()
        except Exception as exc:
            logger.error("history_store_save_turn_failed", error=str(exc), session_id=session_id)
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

    async def count_sessions(self) -> int:
        """Return the total number of distinct sessions."""
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute("SELECT COUNT(DISTINCT session_id) FROM turns")
            row = await cursor.fetchone()
            return row[0] if row else 0

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
        if not turn_ids:
            return []
        placeholders = ",".join("?" * len(turn_ids))
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                f"SELECT * FROM turns WHERE turn_id IN ({placeholders})",
                turn_ids,
            )
            rows = await cursor.fetchall()
            return [_deserialize_turn(dict(r)) for r in rows]

    # -- Eval runs -------------------------------------------------------------

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
                (
                    run_id,
                    datetime.now(timezone.utc).isoformat(),
                    turn_count,
                    judge_provider,
                    judge_model,
                ),
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
                "SELECT * FROM eval_runs ORDER BY created_at DESC LIMIT ?",
                (limit,),
            )
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    async def get_run(self, run_id: str) -> dict | None:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM eval_runs WHERE run_id = ?",
                (run_id,),
            )
            row = await cursor.fetchone()
            return dict(row) if row else None

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
            result = []
            for r in rows:
                d = dict(r)
                d["domain_keys"] = json.loads(d.get("domain_keys") or "[]")
                result.append(d)
            return result

    async def delete_old_turns(self, retention_days: int) -> int:
        """Delete turns older than retention_days. Returns deleted count."""
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                "DELETE FROM turns WHERE timestamp < datetime('now', ?)",
                (f"-{retention_days} days",),
            )
            await db.commit()
            return cursor.rowcount

    # -- Token usage -----------------------------------------------------------

    async def log_tokens(
        self,
        session_id: str,
        call_type: str,
        provider: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        total_tokens: int,
        cost_usd: float,
        error: bool,
        turn_id: str | None = None,
    ) -> None:
        """Persist one LLM call's token usage. Called from SessionTokenCallback."""
        try:
            async with aiosqlite.connect(self._db_path) as db:
                await db.execute(
                    """
                    INSERT INTO token_usage
                        (session_id, turn_id, call_type, provider, model,
                         prompt_tokens, completion_tokens, total_tokens,
                         cost_usd, error, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        session_id,
                        turn_id,
                        call_type,
                        provider,
                        model,
                        prompt_tokens,
                        completion_tokens,
                        total_tokens,
                        cost_usd,
                        int(error),
                        datetime.now(timezone.utc).isoformat(),
                    ),
                )
                await db.commit()
        except Exception as exc:
            logger.error("log_tokens_failed", error=str(exc), session_id=session_id)

    async def get_session_token_summary(self, session_id: str) -> dict:
        """Returns totals, by_call_type, by_model, and per-turn breakdown."""
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row

            cursor = await db.execute(
                """
                SELECT
                    SUM(prompt_tokens)     AS total_prompt,
                    SUM(completion_tokens) AS total_completion,
                    SUM(total_tokens)      AS total_tokens,
                    SUM(cost_usd)          AS total_cost_usd,
                    COUNT(*)               AS total_calls
                FROM token_usage
                WHERE session_id = ? AND error = 0
                """,
                (session_id,),
            )
            totals = dict(await cursor.fetchone() or {})

            cursor = await db.execute(
                """
                SELECT call_type,
                       SUM(total_tokens) AS total_tokens,
                       SUM(cost_usd)     AS cost_usd,
                       COUNT(*)          AS calls
                FROM token_usage
                WHERE session_id = ? AND error = 0
                GROUP BY call_type
                ORDER BY total_tokens DESC
                """,
                (session_id,),
            )
            by_call_type = [dict(r) for r in await cursor.fetchall()]

            cursor = await db.execute(
                """
                SELECT provider, model,
                       SUM(prompt_tokens)     AS prompt_tokens,
                       SUM(completion_tokens) AS completion_tokens,
                       SUM(total_tokens)      AS total_tokens,
                       SUM(cost_usd)          AS cost_usd
                FROM token_usage
                WHERE session_id = ? AND error = 0
                GROUP BY provider, model
                ORDER BY total_tokens DESC
                """,
                (session_id,),
            )
            by_model = [dict(r) for r in await cursor.fetchall()]

            cursor = await db.execute(
                """
                SELECT tu.turn_id,
                       t.turn_number,
                       SUM(tu.total_tokens) AS total_tokens,
                       SUM(tu.cost_usd)     AS cost_usd,
                       COUNT(*)             AS calls
                FROM token_usage tu
                LEFT JOIN turns t ON tu.turn_id = t.turn_id
                WHERE tu.session_id = ? AND tu.error = 0 AND tu.turn_id IS NOT NULL
                GROUP BY tu.turn_id, t.turn_number
                ORDER BY t.turn_number ASC
                """,
                (session_id,),
            )
            turn_breakdown = [dict(r) for r in await cursor.fetchall()]

        return {
            "session_id":              session_id,
            "total_prompt_tokens":     totals.get("total_prompt") or 0,
            "total_completion_tokens": totals.get("total_completion") or 0,
            "total_tokens":            totals.get("total_tokens") or 0,
            "total_cost_usd":          round(totals.get("total_cost_usd") or 0.0, 6),
            "total_calls":             totals.get("total_calls") or 0,
            "by_call_type":            by_call_type,
            "by_model":                by_model,
            "turn_breakdown":          turn_breakdown,
        }

    async def get_all_sessions_token_summary(self, limit: int = 100) -> list[dict]:
        """Per-session totals ordered by cost descending, for admin overview."""
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT session_id,
                       SUM(total_tokens) AS total_tokens,
                       SUM(cost_usd)     AS total_cost_usd,
                       COUNT(*)          AS total_calls,
                       MIN(timestamp)    AS first_call,
                       MAX(timestamp)    AS last_call
                FROM token_usage
                WHERE error = 0
                GROUP BY session_id
                ORDER BY total_cost_usd DESC
                LIMIT ?
                """,
                (limit,),
            )
            return [dict(r) for r in await cursor.fetchall()]


def _deserialize_turn(row: dict) -> dict:
    row["sources"] = json.loads(row.get("sources") or "[]")
    row["domain_keys"] = json.loads(row.get("domain_keys") or "[]")
    row["is_fallback"] = bool(row.get("is_fallback", 0))
    return row
