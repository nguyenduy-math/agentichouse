from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel, Field


class SessionMessage(BaseModel):
    role: str
    content: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class SessionState(BaseModel):
    session_id: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_active: datetime = Field(default_factory=datetime.utcnow)
    messages: list[SessionMessage] = Field(default_factory=list)
