from pydantic import BaseModel
from typing import Optional


class ActivityItem(BaseModel):
    agent: str
    action: str
    detail: Optional[str] = None


class ChatRequest(BaseModel):
    message: str
    customer_id: str = "GUEST"


class ChatResponse(BaseModel):
    reply: str
    agent_used: str
    activities: list[ActivityItem]
