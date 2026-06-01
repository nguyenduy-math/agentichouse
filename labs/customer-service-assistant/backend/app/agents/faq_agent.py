import json
from google import genai
from google.genai import types
from app.config import Settings
from app.schemas import ActivityItem
from app.mcp_client import MCPClientManager
from app.agents.prompts import FAQ_SYSTEM, FAQ_USER


class FAQAgent:
    def __init__(self, settings: Settings):
        self.client = genai.Client(api_key=settings.gemini_api_key)
        self.model = settings.gemini_model

    async def handle(
        self, message: str, mcp: MCPClientManager
    ) -> tuple[str, list[ActivityItem]]:
        activities: list[ActivityItem] = []

        raw = await mcp.call_tool("search_knowledge_base", {"query": message})
        activities.append(ActivityItem(
            agent="FAQAgent",
            action="Gọi công cụ",
            detail="search_knowledge_base",
        ))

        kb_data = json.loads(raw)
        if kb_data.get("found"):
            context = "\n\n".join(
                f"Câu hỏi: {r['question']}\nTrả lời: {r['answer']}"
                for r in kb_data["results"]
            )
        else:
            context = "Không tìm thấy thông tin liên quan trong cơ sở kiến thức."

        response = await self.client.aio.models.generate_content(
            model=self.model,
            contents=FAQ_USER.format(context=context, message=message),
            config=types.GenerateContentConfig(
                temperature=0.3,
                system_instruction=FAQ_SYSTEM,
            ),
        )

        activities.append(ActivityItem(
            agent="FAQAgent",
            action="Tạo phản hồi",
            detail=f"Gemini ({self.model})",
        ))

        return response.text, activities
