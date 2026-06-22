import threading
import time
import uuid

import structlog

from app.config import settings

log = structlog.get_logger()


class SessionService:
    def __init__(self) -> None:
        self._sessions: dict[str, dict] = {}
        self._lock = threading.Lock()
        self._start_cleanup()

    def create_session(self) -> str:
        session_id = str(uuid.uuid4())
        with self._lock:
            self._sessions[session_id] = {
                "messages": [],
                "last_active": time.time(),
            }
        log.info("session.created", session_id=session_id)
        return session_id

    def get_history(self, session_id: str, max_messages: int | None = None) -> list[dict]:
        max_messages = max_messages or settings.max_history_messages
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return []
            session["last_active"] = time.time()
            return session["messages"][-max_messages:]

    def append_message(self, session_id: str, role: str, content: str) -> None:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return
            session["messages"].append({"role": role, "content": content})
            session["last_active"] = time.time()

    def delete_session(self, session_id: str) -> bool:
        with self._lock:
            if session_id in self._sessions:
                del self._sessions[session_id]
                log.info("session.deleted", session_id=session_id)
                return True
            return False

    def get_full_history(self, session_id: str) -> list[dict]:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return []
            return list(session["messages"])

    def _start_cleanup(self) -> None:
        def _run() -> None:
            while True:
                time.sleep(300)
                self._evict_expired()

        t = threading.Thread(target=_run, daemon=True)
        t.start()

    def _evict_expired(self) -> None:
        now = time.time()
        ttl = settings.session_ttl_seconds
        with self._lock:
            expired = [sid for sid, s in self._sessions.items() if now - s["last_active"] > ttl]
            for sid in expired:
                del self._sessions[sid]
        if expired:
            log.info("session.evicted", count=len(expired))
