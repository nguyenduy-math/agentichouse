"""Specialist sub-agents, each owning one MCP server.

A :class:`SubAgent` wraps an MCP client, a system prompt, and an optional tool
whitelist. ``answer()`` discovers the agent's tools, then runs a self-contained
tool-calling loop over a single user query and returns the answer plus the MCP
tools it used. The orchestrator delegates to these agents.

Answers are returned in Vietnamese (repo-wide convention).
"""

from llm import run_llm_loop
from mcp_client import flight_mcp, utility_mcp

# Curated, travel-relevant subset of the utility MCP server's tools that the
# travel agent is allowed to call. Keeps the tool list focused and bounds cost.
ALLOWED_TOOLS = {
    "geocode",
    "get_weather",
    "get_forecast",
    "current_time",
    "convert_currency",
    "get_exchange_rate",
    "get_attractions",
    "get_public_holidays",
}

TRAVEL_PROMPT = (
    "Bạn là trợ lý du lịch thông minh, giúp người dùng tìm và lên kế hoạch cho "
    "các chuyến du lịch nghỉ dưỡng. Luôn trả lời bằng tiếng Việt, thân thiện và "
    "súc tích.\n"
    "Bạn có các công cụ để tra cứu thông tin thực tế. Hãy dùng chúng thay vì "
    "đoán:\n"
    "- Luôn gọi 'geocode' để lấy toạ độ trước khi gọi 'get_weather', "
    "'get_forecast' hoặc 'get_attractions'.\n"
    "- Dùng 'get_public_holidays' (mã quốc gia ISO 2 chữ, ví dụ VN, JP, FR) để "
    "gợi ý ngày đi phù hợp và cảnh báo ngày lễ.\n"
    "- Dùng 'convert_currency'/'get_exchange_rate' khi nói về chi phí/ngân sách.\n"
    "Khi gợi ý điểm đến, hãy nêu lý do (thời tiết, mùa, hoạt động) và ước tính "
    "chi phí nếu có thể."
)

FLIGHT_PROMPT = (
    "Bạn là trợ lý đặt vé máy bay. Luôn trả lời bằng tiếng Việt, rõ ràng và "
    "súc tích.\n"
    "Bạn có các công cụ đặt vé. Hãy dùng chúng thay vì đoán:\n"
    "- Dùng 'search_flights' để tìm chuyến bay trước khi đặt. Sân bay dùng mã "
    "IATA 3 chữ. Quy đổi tên thành phố tiếng Việt sang mã: TP.HCM/Sài Gòn=SGN, "
    "Hà Nội=HAN, Đà Nẵng=DAD, Singapore=SIN, Bangkok=BKK, Tokyo=NRT.\n"
    "- Chỉ gọi 'book_flight' khi đã biết số hiệu chuyến bay, tên hành khách và "
    "số ghế. Nếu thiếu thông tin, hãy hỏi lại người dùng thay vì tự đặt.\n"
    "- Sau khi đặt thành công, luôn nêu rõ MÃ ĐẶT CHỖ (ví dụ BK-7F3K9Q) cho "
    "người dùng.\n"
    "- Dùng 'get_booking' để tra cứu đặt chỗ theo mã."
)


class SubAgent:
    """A specialist agent bound to a single MCP server."""

    def __init__(self, name, mcp_client, system_prompt, allowed_tools=None):
        self.name = name
        self._mcp = mcp_client
        self._system_prompt = system_prompt
        self._allowed_tools = allowed_tools
        self._tools_cache: list[dict] | None = None

    async def _discover_tools(self) -> list[dict]:
        """Fetch and cache this agent's MCP tools (filtered by the whitelist)."""
        if self._tools_cache is None:
            all_tools = await self._mcp.list_tools()
            if self._allowed_tools is not None:
                all_tools = [t for t in all_tools if t.get("name") in self._allowed_tools]
            self._tools_cache = all_tools
        return self._tools_cache

    async def answer(self, provider: str, model: str, query: str) -> tuple[str, list[str]]:
        """Answer a single self-contained query; returns (text, mcp_tools_used)."""
        tools = await self._discover_tools()
        messages = [{"role": "user", "content": query}]
        return await run_llm_loop(
            provider, model, self._system_prompt, tools, self._mcp.call_tool, messages
        )


travel_agent = SubAgent("travel", utility_mcp, TRAVEL_PROMPT, allowed_tools=ALLOWED_TOOLS)
flight_agent = SubAgent("flights", flight_mcp, FLIGHT_PROMPT)
