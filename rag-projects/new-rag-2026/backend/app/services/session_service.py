"""
Session management service.

Stores conversation history and last OrchestratorResult per session.
TTL-based cleanup runs as a background asyncio task.
Thread-safe via asyncio.Lock() (not threading.Lock).
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from app.agents.orchestrator import OrchestratorResult


@dataclass
class Message:
    role: str  # "user" | "assistant"
    content: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class SessionState:
    session_id: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_active: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    messages: list[Message] = field(default_factory=list)
    last_question: str | None = None
    last_orchestrator_result: Any | None = None  # OrchestratorResult from last turn

    def add_message(self, role: str, content: str) -> None:
        self.messages.append(Message(role=role, content=content))
        self.last_active = datetime.now(timezone.utc)

    def get_history_text(self, max_turns: int = 6) -> str:
        """Return last N messages as formatted text for LLM context."""
        recent = self.messages[-(max_turns * 2):]
        lines = []
        for msg in recent:
            prefix = "Người dùng" if msg.role == "user" else "Trợ lý"
            lines.append(f"{prefix}: {msg.content}")
        return "\n".join(lines)

    def get_history_messages(self, max_turns: int = 5) -> list[dict[str, str]]:
        """Return last N turns as list of {role, content} dicts for LLM."""
        recent = self.messages[-(max_turns * 2):]
        return [{"role": m.role, "content": m.content} for m in recent]


class SessionService:
    """
    In-memory session store with TTL cleanup.

    All public methods are async and use asyncio.Lock() for thread safety.
    """

    def __init__(self, ttl_minutes: int = 60) -> None:
        self._sessions: dict[str, SessionState] = {}
        self._lock = asyncio.Lock()
        self._ttl_minutes = ttl_minutes
        self._cleanup_task: asyncio.Task | None = None

    def start_cleanup_loop(self) -> None:
        """Start the background TTL cleanup task. Call once at app startup."""
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        logger.info("Session cleanup loop started (TTL=%d min).", self._ttl_minutes)

    def stop_cleanup_loop(self) -> None:
        """Cancel the cleanup task. Call at app shutdown."""
        if self._cleanup_task:
            self._cleanup_task.cancel()

    async def create_session(self) -> SessionState:
        """Create a new session with a UUID and return it."""
        session_id = str(uuid.uuid4())
        session = SessionState(session_id=session_id)
        async with self._lock:
            self._sessions[session_id] = session
        logger.debug("Session created: %s", session_id)
        return session

    async def get_session(self, session_id: str) -> SessionState | None:
        """Return the session if it exists, else None."""
        async with self._lock:
            return self._sessions.get(session_id)

    async def get_or_create_session(self, session_id: str) -> SessionState:
        """Return existing session or create a new one with the given ID."""
        async with self._lock:
            if session_id not in self._sessions:
                self._sessions[session_id] = SessionState(session_id=session_id)
                logger.debug("Session auto-created: %s", session_id)
            return self._sessions[session_id]

    async def delete_session(self, session_id: str) -> bool:
        """Delete a session. Returns True if it existed."""
        async with self._lock:
            if session_id in self._sessions:
                del self._sessions[session_id]
                logger.debug("Session deleted: %s", session_id)
                return True
            return False

    async def update_last_result(
        self,
        session_id: str,
        result: Any,
        question: str,
    ) -> None:
        """Store the last OrchestratorResult for the /agent_trace endpoint."""
        async with self._lock:
            session = self._sessions.get(session_id)
            if session:
                session.last_orchestrator_result = result
                session.last_question = question
                session.last_active = datetime.now(timezone.utc)

    async def _cleanup_loop(self) -> None:
        """Background task: evict sessions that haven't been active within TTL."""
        while True:
            try:
                await asyncio.sleep(300)  # check every 5 minutes
                await self._evict_expired()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning("Session cleanup error: %s", exc)

    async def _evict_expired(self) -> None:
        now = datetime.now(timezone.utc)
        async with self._lock:
            expired = [
                sid
                for sid, s in self._sessions.items()
                if (now - s.last_active).total_seconds() > self._ttl_minutes * 60
            ]
            for sid in expired:
                del self._sessions[sid]
                logger.debug("Session evicted (TTL): %s", sid)
        if expired:
            logger.info("Evicted %d expired sessions.", len(expired))

    @property
    def active_session_count(self) -> int:
        return len(self._sessions)
