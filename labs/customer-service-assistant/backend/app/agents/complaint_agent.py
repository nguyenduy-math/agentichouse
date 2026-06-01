import json
from google import genai
from google.genai import types
from app.config import Settings
from app.schemas import ActivityItem
from app.mcp_client import MCPClientManager
from app.agents.prompts import COMPLAINT_SYSTEM, COMPLAINT_USER


class ComplaintAgent:
    def __init__(self, settings: Settings):
        self.client = genai.Client(api_key=settings.gemini_api_key)
        self.model = settings.gemini_model

    async def handle(
        self,
        message: str,
        customer_id: str,
        mcp: MCPClientManager,
        escalate: bool = False,
    ) -> tuple[str, list[ActivityItem]]:
        activities: list[ActivityItem] = []
        context_parts: list[str] = []

        raw = await mcp.call_tool("get_customer_profile", {"customer_id": customer_id})
        activities.append(ActivityItem(
            agent="ComplaintAgent",
            action="Gọi công cụ",
            detail=f"get_customer_profile({customer_id})",
        ))
        profile = json.loads(raw)["profile"]
        context_parts.append(f"Khách hàng: {profile['name']} ({profile['tier']})")

        is_vip = profile.get("tier") == "Thành viên Vàng"

        if escalate:
            raw = await mcp.call_tool("escalate_to_human", {
                "customer_id": customer_id,
                "reason": message[:200],
                "urgency": "high" if is_vip else "normal",
            })
            activities.append(ActivityItem(
                agent="ComplaintAgent",
                action="Gọi công cụ",
                detail="escalate_to_human",
            ))
            esc = json.loads(raw)["escalation"]
            context_parts.append(
                f"Đã chuyển tiếp đến nhân viên. Mã: {esc['id']}. "
                f"Thời gian chờ ước tính: {esc['estimated_wait']}."
            )
        else:
            raw = await mcp.call_tool("create_support_ticket", {
                "customer_id": customer_id,
                "issue": message[:300],
                "priority": "high" if is_vip else "normal",
            })
            activities.append(ActivityItem(
                agent="ComplaintAgent",
                action="Gọi công cụ",
                detail="create_support_ticket",
            ))
            ticket = json.loads(raw)["ticket"]
            context_parts.append(
                f"Đã tạo phiếu hỗ trợ: {ticket['id']} (ưu tiên: {ticket['priority']})"
            )

            await mcp.call_tool("send_notification", {
                "customer_id": customer_id,
                "message": (
                    f"Khiếu nại của bạn đã được ghi nhận (mã: {ticket['id']}). "
                    "Chúng tôi sẽ phản hồi trong vòng 24 giờ làm việc."
                ),
                "channel": "email",
            })
            activities.append(ActivityItem(
                agent="ComplaintAgent",
                action="Gọi công cụ",
                detail="send_notification (email)",
            ))

        response = await self.client.aio.models.generate_content(
            model=self.model,
            contents=COMPLAINT_USER.format(
                context="\n".join(context_parts),
                message=message,
            ),
            config=types.GenerateContentConfig(
                temperature=0.4,
                system_instruction=COMPLAINT_SYSTEM,
            ),
        )

        activities.append(ActivityItem(
            agent="ComplaintAgent",
            action="Tạo phản hồi",
            detail=f"Gemini ({self.model})",
        ))

        return response.text, activities
