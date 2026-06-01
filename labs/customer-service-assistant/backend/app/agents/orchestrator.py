import json
from google import genai
from google.genai import types
from app.config import Settings
from app.schemas import ActivityItem, ChatResponse
from app.mcp_client import MCPClientManager
from app.agents.prompts import ORCHESTRATOR_CLASSIFY


class OrchestratorAgent:
    def __init__(self, settings: Settings):
        self.client = genai.Client(api_key=settings.gemini_api_key)
        self.model = settings.gemini_model
        self.settings = settings

    async def handle(
        self, message: str, customer_id: str, mcp: MCPClientManager
    ) -> ChatResponse:
        from app.agents.faq_agent import FAQAgent
        from app.agents.order_agent import OrderAgent
        from app.agents.complaint_agent import ComplaintAgent

        activities: list[ActivityItem] = []

        category, reason = await self._classify(message)
        activities.append(ActivityItem(
            agent="OrchestratorAgent",
            action="Phân loại câu hỏi",
            detail=f"{category} — {reason}",
        ))

        try:
            if category == "FAQ":
                reply, more = await FAQAgent(self.settings).handle(message, mcp)
                agent_used = "faq_agent"
            elif category == "ORDER":
                reply, more = await OrderAgent(self.settings).handle(message, customer_id, mcp)
                agent_used = "order_agent"
            else:
                escalate = category == "ESCALATE"
                reply, more = await ComplaintAgent(self.settings).handle(
                    message, customer_id, mcp, escalate=escalate
                )
                agent_used = "complaint_agent"
        except Exception as exc:
            reply = (
                "Xin lỗi, hệ thống gặp sự cố khi xử lý yêu cầu của bạn. "
                "Vui lòng thử lại hoặc liên hệ bộ phận hỗ trợ qua hotline 1800-xxxx."
            )
            more = [ActivityItem(agent="System", action="Lỗi", detail=str(exc))]
            agent_used = "error"

        activities.extend(more)
        return ChatResponse(reply=reply, agent_used=agent_used, activities=activities)

    async def _classify(self, message: str) -> tuple[str, str]:
        try:
            response = await self.client.aio.models.generate_content(
                model=self.model,
                contents=ORCHESTRATOR_CLASSIFY.format(message=message),
                config=types.GenerateContentConfig(
                    temperature=0.0,
                    response_mime_type="application/json",
                ),
            )
            data = json.loads(response.text)
            category = data.get("category", "FAQ")
            if category not in ("FAQ", "ORDER", "COMPLAINT", "ESCALATE"):
                category = "FAQ"
            return category, data.get("reason", "")
        except Exception:
            return "FAQ", "Không thể phân loại, chuyển sang FAQ"
