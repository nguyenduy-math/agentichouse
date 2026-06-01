import json
import re
from openai import AsyncOpenAI
from app.config import Settings
from app.schemas import ActivityItem
from app.mcp_client import MCPClientManager
from app.agents.prompts import ORDER_SYSTEM

_ORDER_ID_RE = re.compile(r"ORD[-\s]?\d{4}[-\s]?\d{3,6}", re.IGNORECASE)


class OrderAgent:
    def __init__(self, settings: Settings):
        self.client = AsyncOpenAI(
            api_key=settings.siliconflow_api_key,
            base_url=settings.siliconflow_base_url,
        )
        self.model = settings.siliconflow_model

    async def handle(
        self, message: str, customer_id: str, mcp: MCPClientManager
    ) -> tuple[str, list[ActivityItem]]:
        activities: list[ActivityItem] = []
        context_parts: list[str] = []

        match = _ORDER_ID_RE.search(message)
        if match:
            order_id = match.group(0).replace(" ", "-").upper()
            raw = await mcp.call_tool("get_order_status", {"order_id": order_id})
            activities.append(ActivityItem(
                agent="OrderAgent",
                action="Gọi công cụ",
                detail=f"get_order_status({order_id})",
            ))
            order_data = json.loads(raw)
            if order_data.get("found"):
                context_parts.append(
                    "Thông tin đơn hàng:\n"
                    + json.dumps(order_data["order"], ensure_ascii=False, indent=2)
                )
            else:
                context_parts.append(order_data.get("message", "Không tìm thấy đơn hàng."))

        raw = await mcp.call_tool("get_customer_profile", {"customer_id": customer_id})
        activities.append(ActivityItem(
            agent="OrderAgent",
            action="Gọi công cụ",
            detail=f"get_customer_profile({customer_id})",
        ))
        profile_data = json.loads(raw)
        profile = profile_data["profile"]
        context_parts.append(f"Khách hàng: {profile['name']} ({profile['tier']})")

        if not match and profile_data.get("recent_orders"):
            context_parts.append(
                "Đơn hàng gần đây:\n"
                + json.dumps(profile_data["recent_orders"], ensure_ascii=False, indent=2)
            )

        prompt = "\n\n".join(context_parts) + f"\n\nCâu hỏi: {message}"

        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": ORDER_SYSTEM},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
        )

        activities.append(ActivityItem(
            agent="OrderAgent",
            action="Tạo phản hồi",
            detail=f"SiliconFlow ({self.model})",
        ))

        return response.choices[0].message.content or "", activities
