"""Provider-agnostic, MCP-native chat agent for finding holiday trips.

The agent discovers its tools from the MCP server (`tools/list`), translates the
JSON-Schema into each provider's native tool format, and runs a bounded
tool-calling loop. Two providers are supported and selectable per request:

- ``gemini``       — Google Gemini via the ``google-genai`` SDK
- ``siliconflow``  — SiliconFlow's OpenAI-compatible API via the ``openai`` SDK

Answers are returned in Vietnamese (repo-wide convention).
"""

import asyncio
import json
import os

from mcp_client import mcp

# --- Configuration (from environment) ---------------------------------------

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

SILICONFLOW_API_KEY = os.getenv("SILICONFLOW_API_KEY", "")
SILICONFLOW_MODEL = os.getenv("SILICONFLOW_MODEL", "Qwen/Qwen2.5-7B-Instruct")
SILICONFLOW_BASE_URL = os.getenv("SILICONFLOW_BASE_URL", "https://api.siliconflow.com/v1")

# Curated, travel-relevant subset of the MCP server's tools that the assistant
# is allowed to call. Keeps the tool list focused and bounds cost.
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

MAX_ITERATIONS = 6

SYSTEM_PROMPT = (
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

# Cached tool definitions discovered from the MCP server.
_tools_cache: list[dict] | None = None


async def _discover_tools() -> list[dict]:
    """Fetch and cache the allowed MCP tools (name, description, inputSchema)."""
    global _tools_cache
    if _tools_cache is None:
        all_tools = await mcp.list_tools()
        _tools_cache = [t for t in all_tools if t.get("name") in ALLOWED_TOOLS]
    return _tools_cache


async def _run_tool_calls(calls: list[tuple[str, dict]]) -> list[str]:
    """Execute MCP tool calls concurrently; return their text results in order."""
    results = await asyncio.gather(
        *(mcp.call_tool(name, args) for name, args in calls),
        return_exceptions=True,
    )
    return [
        f"Lỗi khi gọi công cụ: {r}" if isinstance(r, Exception) else r
        for r in results
    ]


# --- Schema translation -----------------------------------------------------

def _sanitize_json_schema(schema: dict) -> dict:
    """Drop keys that some providers reject (e.g. $schema, additionalProperties)."""
    if not isinstance(schema, dict):
        return schema
    cleaned = {}
    for key, value in schema.items():
        if key in ("$schema", "additionalProperties"):
            continue
        if key == "properties" and isinstance(value, dict):
            cleaned[key] = {k: _sanitize_json_schema(v) for k, v in value.items()}
        elif key == "items":
            cleaned[key] = _sanitize_json_schema(value)
        else:
            cleaned[key] = value
    return cleaned


def _openai_tools(tools: list[dict]) -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t.get("description", ""),
                "parameters": _sanitize_json_schema(t.get("inputSchema") or {"type": "object"}),
            },
        }
        for t in tools
    ]


def _gemini_schema(schema: dict):
    """Convert a JSON Schema dict into a google-genai types.Schema."""
    from google.genai import types

    type_map = {
        "object": types.Type.OBJECT,
        "string": types.Type.STRING,
        "number": types.Type.NUMBER,
        "integer": types.Type.INTEGER,
        "boolean": types.Type.BOOLEAN,
        "array": types.Type.ARRAY,
    }
    kwargs = {"type": type_map.get(schema.get("type", "string"), types.Type.STRING)}
    if "description" in schema:
        kwargs["description"] = schema["description"]
    if "enum" in schema:
        kwargs["enum"] = schema["enum"]
    if schema.get("type") == "object":
        props = schema.get("properties", {})
        kwargs["properties"] = {k: _gemini_schema(v) for k, v in props.items()}
        if schema.get("required"):
            kwargs["required"] = schema["required"]
    if schema.get("type") == "array" and "items" in schema:
        kwargs["items"] = _gemini_schema(schema["items"])
    return types.Schema(**kwargs)


def _gemini_tools(tools: list[dict]):
    from google.genai import types

    declarations = [
        types.FunctionDeclaration(
            name=t["name"],
            description=t.get("description", ""),
            parameters=_gemini_schema(_sanitize_json_schema(t.get("inputSchema") or {"type": "object"})),
        )
        for t in tools
    ]
    return [types.Tool(function_declarations=declarations)]


# --- Providers --------------------------------------------------------------

async def _run_siliconflow(messages: list[dict], model: str) -> tuple[str, list[str]]:
    from openai import AsyncOpenAI

    if not SILICONFLOW_API_KEY:
        raise RuntimeError("SILICONFLOW_API_KEY is not set.")

    client = AsyncOpenAI(api_key=SILICONFLOW_API_KEY, base_url=SILICONFLOW_BASE_URL)
    tools = await _discover_tools()
    tool_defs = _openai_tools(tools)

    convo = [{"role": "system", "content": SYSTEM_PROMPT}] + messages
    used: list[str] = []

    for _ in range(MAX_ITERATIONS):
        resp = await client.chat.completions.create(
            model=model,
            messages=convo,
            tools=tool_defs,
            tool_choice="auto",
            temperature=0.3,
        )
        msg = resp.choices[0].message
        if not msg.tool_calls:
            return msg.content or "", used

        convo.append(msg.model_dump(exclude_none=True))
        calls = [
            (tc.function.name, _safe_json(tc.function.arguments))
            for tc in msg.tool_calls
        ]
        used.extend(name for name, _ in calls)
        results = await _run_tool_calls(calls)
        for tc, result in zip(msg.tool_calls, results):
            convo.append({"role": "tool", "tool_call_id": tc.id, "content": result})

    return "Xin lỗi, tôi cần quá nhiều bước để trả lời. Bạn thử hỏi cụ thể hơn nhé.", used


async def _run_gemini(messages: list[dict], model: str) -> tuple[str, list[str]]:
    from google import genai
    from google.genai import types

    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is not set.")

    client = genai.Client(api_key=GEMINI_API_KEY)
    tools = await _discover_tools()
    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        tools=_gemini_tools(tools),
        temperature=0.3,
    )

    contents = [
        types.Content(
            role="model" if m["role"] == "assistant" else "user",
            parts=[types.Part(text=m["content"])],
        )
        for m in messages
    ]
    used: list[str] = []

    for _ in range(MAX_ITERATIONS):
        resp = await client.aio.models.generate_content(
            model=model, contents=contents, config=config
        )
        candidate = resp.candidates[0]
        parts = candidate.content.parts or []
        fn_calls = [p.function_call for p in parts if getattr(p, "function_call", None)]

        if not fn_calls:
            text = "".join(p.text for p in parts if getattr(p, "text", None))
            return text, used

        contents.append(candidate.content)
        calls = [(fc.name, dict(fc.args or {})) for fc in fn_calls]
        used.extend(name for name, _ in calls)
        results = await _run_tool_calls(calls)
        contents.append(
            types.Content(
                role="user",
                parts=[
                    types.Part.from_function_response(name=name, response={"result": result})
                    for (name, _), result in zip(calls, results)
                ],
            )
        )

    return "Xin lỗi, tôi cần quá nhiều bước để trả lời. Bạn thử hỏi cụ thể hơn nhé.", used


def _safe_json(raw: str) -> dict:
    try:
        return json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        return {}


# --- Public entry point -----------------------------------------------------

PROVIDERS = {
    "gemini": (_run_gemini, lambda: GEMINI_MODEL),
    "siliconflow": (_run_siliconflow, lambda: SILICONFLOW_MODEL),
}


async def run_agent(
    provider: str, messages: list[dict], model: str | None = None
) -> dict:
    """Run the agentic loop for the chosen provider.

    Returns ``{"reply", "tool_calls", "provider"}``.
    """
    if provider not in PROVIDERS:
        raise ValueError(f"Unknown provider '{provider}'. Use one of: {list(PROVIDERS)}")
    runner, default_model = PROVIDERS[provider]
    reply, used = await runner(messages, model or default_model())
    return {"reply": reply, "tool_calls": used, "provider": provider}
