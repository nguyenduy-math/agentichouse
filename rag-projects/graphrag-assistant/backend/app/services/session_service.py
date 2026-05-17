from __future__ import annotations

import threading
import time
from datetime import datetime
from uuid import uuid4

import structlog

from app.models.session import SessionState, SessionMessage

logger = structlog.get_logger()


class SessionService:
    def __init__(self, ttl_seconds: int = 3600) -> None:
        self._sessions: dict[str, SessionState] = {}
        self._lock = threading.Lock()
        self._ttl = ttl_seconds
        self._cleanup_thread: threading.Thread | None = None
        self._running = False

    def create_session(self) -> SessionState:
        session = SessionState(session_id=str(uuid4()))
        with self._lock:
            self._sessions[session.session_id] = session
        return session

    def get_session(self, session_id: str) -> SessionState | None:
        with self._lock:
            session = self._sessions.get(session_id)
            if session:
                session.last_active = datetime.utcnow()
            return session

    def delete_session(self, session_id: str) -> bool:
        with self._lock:
            return self._sessions.pop(session_id, None) is not None

    def append_message(self, session_id: str, role: str, content: str) -> None:
        with self._lock:
            session = self._sessions.get(session_id)
            if session:
                session.messages.append(SessionMessage(role=role, content=content))
                session.last_active = datetime.utcnow()

    def start_cleanup(self) -> None:
        self._running = True
        self._cleanup_thread = threading.Thread(target=self._cleanup_loop, daemon=True)
        self._cleanup_thread.start()

    def stop_cleanup(self) -> None:
        self._running = False

    def _cleanup_loop(self) -> None:
        while self._running:
            time.sleep(300)
            self._evict_expired()

    def _evict_expired(self) -> None:
        now = datetime.utcnow()
        with self._lock:
            expired = [
                sid
                for sid, s in self._sessions.items()
                if (now - s.last_active).total_seconds() > self._ttl
            ]
            for sid in expired:
                del self._sessions[sid]
        if expired:
            logger.info("sessions_evicted", count=len(expired))
