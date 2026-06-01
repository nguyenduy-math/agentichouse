from fastapi import APIRouter, Request
from app.schemas import ChatRequest, ChatResponse
from app.config import settings
from app.mcp_client import MCPClientManager
from app.agents.orchestrator import OrchestratorAgent

router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, req: Request) -> ChatResponse:
    mcp: MCPClientManager = req.app.state.mcp
    return await OrchestratorAgent(settings).handle(request.message, request.customer_id, mcp)


@router.get("/health")
async def health():
    return {"status": "ok"}
