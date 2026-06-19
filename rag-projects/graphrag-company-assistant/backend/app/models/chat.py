from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel, Field

from app.models.graph import PolicySource, GraphData


class Message(BaseModel):
    role: str
    content: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    sources: list[PolicySource] = Field(default_factory=list)


class ChatRequest(BaseModel):
    session_id: str
    message: str


class VerificationResult(BaseModel):
    is_grounded: bool
    confidence: int  # 1-5
    issues: list[str] = []


class ChatResponse(BaseModel):
    session_id: str
    reply: str
    sources: list[PolicySource] = Field(default_factory=list)
    query_type: str = "LOCAL"
    graph_data: GraphData | None = None
    verification: VerificationResult | None = None
    is_fallback: bool = False


class ChatHistoryResponse(BaseModel):
    session_id: str
    messages: list[Message]
