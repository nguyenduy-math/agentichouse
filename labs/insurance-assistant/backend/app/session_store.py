import asyncio
import uuid
from datetime import datetime, timedelta

from app.schemas import ClaimData, SessionState


class SessionStore:
    def __init__(self, ttl_minutes: int = 60) -> None:
        self._sessions: dict[str, tuple[SessionState, datetime]] = {}
        self._lock = asyncio.Lock()
        self._ttl = timedelta(minutes=ttl_minutes)

    async def create(self) -> SessionState:
        session = SessionState(
            session_id=str(uuid.uuid4()),
            collected=ClaimData(),
        )
        async with self._lock:
            self._sessions[session.session_id] = (session, datetime.utcnow())
        return session

    async def get(self, session_id: str) -> SessionState | None:
        async with self._lock:
            entry = self._sessions.get(session_id)
            if entry is None:
                return None
            session, last_accessed = entry
            if datetime.utcnow() - last_accessed > self._ttl:
                del self._sessions[session_id]
                return None
            return session

    async def save(self, session: SessionState) -> None:
        async with self._lock:
            self._sessions[session.session_id] = (session, datetime.utcnow())

    async def delete(self, session_id: str) -> bool:
        async with self._lock:
            if session_id in self._sessions:
                del self._sessions[session_id]
                return True
            return False

    async def purge_expired(self) -> int:
        now = datetime.utcnow()
        async with self._lock:
            expired = [sid for sid, (_, ts) in self._sessions.items() if now - ts > self._ttl]
            for sid in expired:
                del self._sessions[sid]
        return len(expired)
