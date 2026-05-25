from __future__ import annotations

from datetime import datetime

import aiosqlite
import structlog

from app.models.chat import TokenUsage

logger = structlog.get_logger()

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS conversation_token_usage (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id        TEXT    NOT NULL,
    turn_number       INTEGER NOT NULL DEFAULT 0,
    timestamp         TEXT    NOT NULL,
    prompt_tokens     INTEGER NOT NULL DEFAULT 0,
    completion_tokens INTEGER NOT NULL DEFAULT 0,
    total_tokens      INTEGER NOT NULL DEFAULT 0,
    model             TEXT    NOT NULL,
    llm_provider      TEXT    NOT NULL
)
"""
_CREATE_INDEX = "CREATE INDEX IF NOT EXISTS idx_ctu_session ON conversation_token_usage (session_id)"


class TokenLogger:
    def __init__(self, db_path: str = "./data/token_usage.db") -> None:
        self._db_path = db_path

    async def initialize(self) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(_CREATE_TABLE)
            await db.execute(_CREATE_INDEX)
            await db.commit()
        logger.info("token_logger_initialized", db_path=self._db_path)

    async def log_turn(self, session_id: str, turn_number: int, usage: TokenUsage) -> None:
        try:
            async with aiosqlite.connect(self._db_path) as db:
                await db.execute(
                    "INSERT INTO conversation_token_usage "
                    "(session_id, turn_number, timestamp, prompt_tokens, completion_tokens, total_tokens, model, llm_provider) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        session_id,
                        turn_number,
                        datetime.utcnow().isoformat(),
                        usage.prompt_tokens,
                        usage.completion_tokens,
                        usage.total_tokens,
                        usage.model,
                        usage.llm_provider,
                    ),
                )
                await db.commit()
        except Exception as e:
            logger.warning("token_log_failed", session_id=session_id, error=str(e))

    async def get_session_totals(self, session_id: str) -> dict:
        async with aiosqlite.connect(self._db_path) as db:
            async with db.execute(
                "SELECT COUNT(*), SUM(prompt_tokens), SUM(completion_tokens), SUM(total_tokens) "
                "FROM conversation_token_usage WHERE session_id = ?",
                (session_id,),
            ) as cursor:
                row = await cursor.fetchone()
        return {
            "session_id": session_id,
            "turns": row[0] or 0,
            "prompt_tokens": row[1] or 0,
            "completion_tokens": row[2] or 0,
            "total_tokens": row[3] or 0,
        }

    async def get_all_sessions_summary(self) -> list[dict]:
        async with aiosqlite.connect(self._db_path) as db:
            async with db.execute(
                "SELECT session_id, COUNT(*), SUM(prompt_tokens), SUM(completion_tokens), "
                "SUM(total_tokens), MAX(timestamp) "
                "FROM conversation_token_usage "
                "GROUP BY session_id ORDER BY MAX(timestamp) DESC"
            ) as cursor:
                rows = await cursor.fetchall()
        return [
            {
                "session_id": r[0],
                "turns": r[1],
                "prompt_tokens": r[2] or 0,
                "completion_tokens": r[3] or 0,
                "total_tokens": r[4] or 0,
                "last_active": r[5],
            }
            for r in rows
        ]
