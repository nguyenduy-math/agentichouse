"""Async SQLite storage layer for the Ticket MCP Server."""

import json
from datetime import datetime, timezone

import aiosqlite

from models.ticket import (
    Ticket,
    TicketCreate,
    TicketHistory,
    TicketPriority,
    TicketStatus,
    TicketType,
    STATUS_TRANSITIONS,
)

_CREATE_TICKETS = """
CREATE TABLE IF NOT EXISTS tickets (
    ticket_id       TEXT PRIMARY KEY,
    ticket_type     TEXT NOT NULL,
    title           TEXT NOT NULL,
    description     TEXT NOT NULL DEFAULT '',
    requester_name  TEXT NOT NULL,
    requester_email TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'pending',
    priority        TEXT NOT NULL DEFAULT 'normal',
    extra_fields    TEXT NOT NULL DEFAULT '{}',
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);
"""

_CREATE_HISTORY = """
CREATE TABLE IF NOT EXISTS ticket_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id   TEXT NOT NULL REFERENCES tickets(ticket_id),
    action      TEXT NOT NULL,
    actor_name  TEXT NOT NULL,
    actor_email TEXT NOT NULL DEFAULT '',
    old_value   TEXT NOT NULL DEFAULT '',
    new_value   TEXT NOT NULL DEFAULT '',
    comment     TEXT NOT NULL DEFAULT '',
    timestamp   TEXT NOT NULL
);
"""

_CREATE_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_tickets_email  ON tickets(requester_email);
CREATE INDEX IF NOT EXISTS idx_tickets_status ON tickets(status);
CREATE INDEX IF NOT EXISTS idx_tickets_type   ON tickets(ticket_type);
CREATE INDEX IF NOT EXISTS idx_history_ticket ON ticket_history(ticket_id);
"""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_dt(s: str) -> datetime:
    """Parse an ISO-8601 string (with or without timezone) into a datetime."""
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        # Fallback: strip trailing Z
        return datetime.fromisoformat(s.rstrip("Z"))


def _row_to_ticket(row: aiosqlite.Row) -> Ticket:
    return Ticket(
        ticket_id=row["ticket_id"],
        ticket_type=TicketType(row["ticket_type"]),
        title=row["title"],
        description=row["description"],
        requester_name=row["requester_name"],
        requester_email=row["requester_email"],
        status=TicketStatus(row["status"]),
        priority=TicketPriority(row["priority"]),
        extra_fields=json.loads(row["extra_fields"]),
        created_at=_parse_dt(row["created_at"]),
        updated_at=_parse_dt(row["updated_at"]),
    )


def _row_to_history(row: aiosqlite.Row) -> TicketHistory:
    return TicketHistory(
        id=row["id"],
        ticket_id=row["ticket_id"],
        action=row["action"],
        actor_name=row["actor_name"],
        actor_email=row["actor_email"],
        old_value=row["old_value"],
        new_value=row["new_value"],
        comment=row["comment"],
        timestamp=_parse_dt(row["timestamp"]),
    )


async def _next_ticket_id(conn: aiosqlite.Connection, date_str: str) -> str:
    """Return next sequential TKT-YYYYMMDD-NNNN for the given date."""
    prefix = f"TKT-{date_str}-"
    async with conn.execute(
        "SELECT COUNT(*) FROM tickets WHERE ticket_id LIKE ?",
        (prefix + "%",),
    ) as cur:
        row = await cur.fetchone()
    seq = (row[0] if row else 0) + 1
    return f"{prefix}{seq:04d}"


class SqliteStore:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path

    async def init_db(self) -> None:
        """Create tables and indexes if they don't exist."""
        async with aiosqlite.connect(self.db_path) as conn:
            await conn.execute(_CREATE_TICKETS)
            await conn.execute(_CREATE_HISTORY)
            for stmt in _CREATE_INDEXES.strip().split(";"):
                stmt = stmt.strip()
                if stmt:
                    await conn.execute(stmt)
            await conn.commit()

    async def create(self, data: TicketCreate) -> Ticket:
        """Insert a new ticket and initial history row. Returns the full Ticket."""
        now = _now_iso()
        date_str = datetime.now(timezone.utc).strftime("%Y%m%d")

        async with aiosqlite.connect(self.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            ticket_id = await _next_ticket_id(conn, date_str)

            await conn.execute(
                """
                INSERT INTO tickets
                    (ticket_id, ticket_type, title, description,
                     requester_name, requester_email, status, priority,
                     extra_fields, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ticket_id,
                    data.ticket_type.value,
                    data.title,
                    data.description,
                    data.requester_name,
                    data.requester_email,
                    TicketStatus.pending.value,
                    data.priority.value,
                    json.dumps(data.extra_fields, ensure_ascii=False),
                    now,
                    now,
                ),
            )
            await conn.execute(
                """
                INSERT INTO ticket_history
                    (ticket_id, action, actor_name, actor_email,
                     old_value, new_value, comment, timestamp)
                VALUES (?, 'created', ?, ?, '', 'pending', '', ?)
                """,
                (ticket_id, data.requester_name, data.requester_email, now),
            )
            await conn.commit()

            async with conn.execute(
                "SELECT * FROM tickets WHERE ticket_id = ?", (ticket_id,)
            ) as cur:
                row = await cur.fetchone()

        return _row_to_ticket(row)

    async def get(self, ticket_id: str) -> Ticket | None:
        """Return Ticket or None if not found."""
        async with aiosqlite.connect(self.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute(
                "SELECT * FROM tickets WHERE ticket_id = ?", (ticket_id,)
            ) as cur:
                row = await cur.fetchone()
        return _row_to_ticket(row) if row else None

    async def list_tickets(
        self,
        requester_email: str | None = None,
        status: str | None = None,
        ticket_type: str | None = None,
        limit: int = 20,
    ) -> list[Ticket]:
        """Filtered query. All filters are optional AND-combined."""
        conditions: list[str] = []
        params: list[str | int] = []

        if requester_email:
            conditions.append("requester_email = ?")
            params.append(requester_email)
        if status:
            conditions.append("status = ?")
            params.append(status)
        if ticket_type:
            conditions.append("ticket_type = ?")
            params.append(ticket_type)

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        params.append(limit)

        async with aiosqlite.connect(self.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute(
                f"SELECT * FROM tickets {where} ORDER BY created_at DESC LIMIT ?",
                params,
            ) as cur:
                rows = await cur.fetchall()

        return [_row_to_ticket(r) for r in rows]

    async def update_status(
        self,
        ticket_id: str,
        new_status: str,
        comment: str,
        actor_name: str,
        actor_email: str = "",
    ) -> Ticket:
        """Update status and record history. Raises ValueError on invalid transition."""
        async with aiosqlite.connect(self.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute(
                "SELECT * FROM tickets WHERE ticket_id = ?", (ticket_id,)
            ) as cur:
                row = await cur.fetchone()

            if not row:
                raise ValueError(f"Ticket {ticket_id} không tồn tại")

            current = TicketStatus(row["status"])
            try:
                target = TicketStatus(new_status)
            except ValueError:
                raise ValueError(
                    f"Trạng thái không hợp lệ: '{new_status}'. "
                    f"Các giá trị hợp lệ: {[s.value for s in TicketStatus]}"
                )

            allowed = STATUS_TRANSITIONS.get(current, [])
            if target not in allowed:
                allowed_str = ", ".join(s.value for s in allowed) if allowed else "(không có)"
                raise ValueError(
                    f"Không thể chuyển từ '{current.value}' sang '{target.value}'. "
                    f"Các chuyển đổi hợp lệ từ '{current.value}': {allowed_str}"
                )

            now = _now_iso()
            await conn.execute(
                "UPDATE tickets SET status = ?, updated_at = ? WHERE ticket_id = ?",
                (target.value, now, ticket_id),
            )
            await conn.execute(
                """
                INSERT INTO ticket_history
                    (ticket_id, action, actor_name, actor_email,
                     old_value, new_value, comment, timestamp)
                VALUES (?, 'status_changed', ?, ?, ?, ?, ?, ?)
                """,
                (ticket_id, actor_name, actor_email, current.value, target.value, comment, now),
            )
            await conn.commit()

            async with conn.execute(
                "SELECT * FROM tickets WHERE ticket_id = ?", (ticket_id,)
            ) as cur:
                updated_row = await cur.fetchone()

        return _row_to_ticket(updated_row)

    async def add_comment(
        self,
        ticket_id: str,
        author_name: str,
        author_email: str,
        comment: str,
    ) -> None:
        """Append a comment_added history row."""
        now = _now_iso()
        async with aiosqlite.connect(self.db_path) as conn:
            await conn.execute(
                """
                INSERT INTO ticket_history
                    (ticket_id, action, actor_name, actor_email,
                     old_value, new_value, comment, timestamp)
                VALUES (?, 'comment_added', ?, ?, '', '', ?, ?)
                """,
                (ticket_id, author_name, author_email, comment, now),
            )
            await conn.commit()

    async def get_history(self, ticket_id: str) -> list[TicketHistory]:
        """Return all history rows for a ticket, oldest first."""
        async with aiosqlite.connect(self.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute(
                "SELECT * FROM ticket_history WHERE ticket_id = ? ORDER BY id ASC",
                (ticket_id,),
            ) as cur:
                rows = await cur.fetchall()
        return [_row_to_history(r) for r in rows]
