"""Orchestrator agent that delegates to the travel and flight sub-agents.

The orchestrator is itself an LLM whose "tools" are the two sub-agents. It reads
the full conversation, delegates to the appropriate specialist(s) by calling
``ask_travel_agent`` / ``ask_flight_agent`` (it may call both in one turn for
cross-domain requests), then synthesises a single Vietnamese reply.
"""

from agents import flight_agent, travel_agent
from llm import default_model, run_llm_loop

ORCH_PROMPT = (
    "Bạn là điều phối viên của một trợ lý du lịch. Luôn trả lời bằng tiếng Việt, "
    "thân thiện và súc tích.\n"
    "Bạn có hai trợ lý chuyên môn, gọi qua công cụ:\n"
    "- 'ask_travel_agent': thông tin du lịch — thời tiết, dự báo, giờ địa "
    "phương, tỷ giá, địa điểm tham quan, ngày lễ, gợi ý điểm đến.\n"
    "- 'ask_flight_agent': tìm và đặt vé máy bay, tra cứu mã đặt chỗ.\n"
    "Với mỗi yêu cầu, hãy uỷ thác cho (các) trợ lý phù hợp bằng cách gọi công "
    "cụ. Nếu một yêu cầu cần cả hai (ví dụ vừa hỏi thời tiết vừa đặt vé), hãy "
    "gọi cả hai.\n"
    "Truyền vào tham số 'query' một câu hỏi rõ ràng, đầy đủ ngữ cảnh: tự giải "
    "quyết các tham chiếu từ lịch sử trò chuyện (ví dụ chèn số hiệu chuyến bay "
    "đã chọn, tên hành khách, số ghế).\n"
    "Sau khi nhận kết quả, hãy tổng hợp thành một câu trả lời mạch lạc, hữu ích."
)

_DELEGATE_TOOLS = [
    {
        "name": "ask_travel_agent",
        "description": (
            "Hỏi trợ lý thông tin du lịch (thời tiết, dự báo, giờ địa phương, tỷ giá, "
            "địa điểm tham quan, ngày lễ, gợi ý điểm đến)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Câu hỏi đầy đủ ngữ cảnh cho trợ lý du lịch, bằng tiếng Việt.",
                }
            },
            "required": ["query"],
        },
    },
    {
        "name": "ask_flight_agent",
        "description": (
            "Hỏi trợ lý đặt vé máy bay (tìm chuyến bay, đặt vé, tra cứu mã đặt chỗ)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Yêu cầu đầy đủ ngữ cảnh cho trợ lý đặt vé, bằng tiếng Việt.",
                }
            },
            "required": ["query"],
        },
    },
]

_AGENTS = {
    "ask_travel_agent": travel_agent,
    "ask_flight_agent": flight_agent,
}


async def run_orchestrator(provider: str, messages: list[dict], model: str | None = None) -> dict:
    """Route a conversation through the delegating orchestrator.

    Returns ``{"reply", "provider", "agents", "tool_calls"}`` where ``agents`` is
    the specialist(s) consulted and ``tool_calls`` the underlying MCP tools used.
    """
    chosen_model = model or default_model(provider)

    agents_used: list[str] = []
    mcp_tools_used: list[str] = []

    async def dispatch(name: str, args: dict) -> str:
        agent = _AGENTS.get(name)
        if agent is None:
            return f"Không có trợ lý tên '{name}'."
        query = (args or {}).get("query", "")
        text, used = await agent.answer(provider, chosen_model, query)
        agents_used.append(agent.name)
        mcp_tools_used.extend(used)
        return text

    reply, _ = await run_llm_loop(
        provider, chosen_model, ORCH_PROMPT, _DELEGATE_TOOLS, dispatch, messages
    )

    return {
        "reply": reply,
        "provider": provider,
        "agents": list(dict.fromkeys(agents_used)),
        "tool_calls": list(dict.fromkeys(mcp_tools_used)),
    }
