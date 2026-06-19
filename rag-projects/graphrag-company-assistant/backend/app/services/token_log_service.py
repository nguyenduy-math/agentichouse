from __future__ import annotations

from datetime import datetime, timezone

import aiosqlite

_DDL = """
CREATE TABLE IF NOT EXISTS token_logs (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp         TEXT    NOT NULL,
    provider          TEXT    NOT NULL,
    model             TEXT    NOT NULL,
    call_type         TEXT    NOT NULL,
    prompt_tokens     INTEGER NOT NULL DEFAULT 0,
    completion_tokens INTEGER NOT NULL DEFAULT 0,
    total_tokens      INTEGER NOT NULL DEFAULT 0
)
"""


class TokenLogService:
    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    async def initialize(self) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(_DDL)
            await db.commit()

    async def log(
        self,
        provider: str,
        model: str,
        call_type: str,
        prompt_tokens: int,
        completion_tokens: int,
    ) -> None:
        total = prompt_tokens + completion_tokens
        ts = datetime.now(timezone.utc).isoformat()
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "INSERT INTO token_logs"
                " (timestamp, provider, model, call_type, prompt_tokens, completion_tokens, total_tokens)"
                " VALUES (?,?,?,?,?,?,?)",
                (ts, provider, model, call_type, prompt_tokens, completion_tokens, total),
            )
            await db.commit()

    async def get_recent(self, limit: int = 100) -> list[dict]:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM token_logs ORDER BY id DESC LIMIT ?", (limit,)
            ) as cur:
                rows = await cur.fetchall()
        return [dict(r) for r in rows]

    async def get_summary(self) -> dict:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT call_type, provider, model,"
                "  COUNT(*) AS calls,"
                "  SUM(prompt_tokens) AS prompt_tokens,"
                "  SUM(completion_tokens) AS completion_tokens,"
                "  SUM(total_tokens) AS total_tokens"
                " FROM token_logs"
                " GROUP BY call_type, provider, model"
                " ORDER BY total_tokens DESC"
            ) as cur:
                by_call = [dict(r) for r in await cur.fetchall()]
            async with db.execute(
                "SELECT SUM(prompt_tokens), SUM(completion_tokens), SUM(total_tokens), COUNT(*)"
                " FROM token_logs"
            ) as cur:
                row = await cur.fetchone()
        return {
            "totals": {
                "prompt_tokens": row[0] or 0,
                "completion_tokens": row[1] or 0,
                "total_tokens": row[2] or 0,
                "calls": row[3] or 0,
            },
            "by_call_type": by_call,
        }
