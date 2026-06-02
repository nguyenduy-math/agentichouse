"""Provider-agnostic LLM tool-calling primitives.

This module knows how to translate MCP tool schemas into each provider's native
format and how to run a bounded tool-calling loop. It is deliberately decoupled
from any particular MCP server: the caller supplies the tool definitions and a
``dispatch`` callback that actually executes a tool by name. This lets the same
loop power both a sub-agent (tools = MCP tools, dispatch = mcp.call_tool) and the
orchestrator (tools = sub-agents, dispatch = delegate to a sub-agent).

Two providers are supported, selectable per request:

- ``gemini``       — Google Gemini via the ``google-genai`` SDK
- ``siliconflow``  — SiliconFlow's OpenAI-compatible API via the ``openai`` SDK
"""

import asyncio
import json
import os
from datetime import date
from typing import Awaitable, Callable

from dotenv import load_dotenv

# Load .env before reading provider config below. Done here (not only in main.py)
# so the values are present regardless of module import order.
load_dotenv()

# --- Configuration (from environment) ---------------------------------------

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

SILICONFLOW_API_KEY = os.getenv("SILICONFLOW_API_KEY", "")
SILICONFLOW_MODEL = os.getenv("SILICONFLOW_MODEL", "Qwen/Qwen2.5-7B-Instruct")
SILICONFLOW_BASE_URL = os.getenv("SILICONFLOW_BASE_URL", "https://api.siliconflow.com/v1")

MAX_ITERATIONS = 6

# A tool executor: given a tool name and its arguments, return its text result.
Dispatch = Callable[[str, dict], Awaitable[str]]


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


def _safe_json(raw: str) -> dict:
    try:
        return json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        return {}


async def _run_tool_calls(dispatch: Dispatch, calls: list[tuple[str, dict]]) -> list[str]:
    """Execute tool calls concurrently via ``dispatch``; return results in order."""
    results = await asyncio.gather(
        *(dispatch(name, args) for name, args in calls),
        return_exceptions=True,
    )
    return [
        f"Lỗi khi gọi công cụ: {r}" if isinstance(r, Exception) else r
        for r in results
    ]


# --- Provider loops ---------------------------------------------------------

async def _run_siliconflow(
    model: str, system_prompt: str, tools: list[dict], dispatch: Dispatch, messages: list[dict]
) -> tuple[str, list[str]]:
    from openai import AsyncOpenAI

    if not SILICONFLOW_API_KEY:
        raise RuntimeError("SILICONFLOW_API_KEY is not set.")

    client = AsyncOpenAI(api_key=SILICONFLOW_API_KEY, base_url=SILICONFLOW_BASE_URL)
    tool_defs = _openai_tools(tools)

    convo = [{"role": "system", "content": system_prompt}] + messages
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
        results = await _run_tool_calls(dispatch, calls)
        for tc, result in zip(msg.tool_calls, results):
            convo.append({"role": "tool", "tool_call_id": tc.id, "content": result})

    return "Xin lỗi, tôi cần quá nhiều bước để trả lời. Bạn thử hỏi cụ thể hơn nhé.", used


async def _run_gemini(
    model: str, system_prompt: str, tools: list[dict], dispatch: Dispatch, messages: list[dict]
) -> tuple[str, list[str]]:
    from google import genai
    from google.genai import types

    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is not set.")

    client = genai.Client(api_key=GEMINI_API_KEY)
    config = types.GenerateContentConfig(
        system_instruction=system_prompt,
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
        results = await _run_tool_calls(dispatch, calls)
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


# --- Public API -------------------------------------------------------------

PROVIDERS = {
    "gemini": (_run_gemini, lambda: GEMINI_MODEL),
    "siliconflow": (_run_siliconflow, lambda: SILICONFLOW_MODEL),
}


def default_model(provider: str) -> str:
    """Return the configured default model for a provider (validates the name)."""
    if provider not in PROVIDERS:
        raise ValueError(f"Unknown provider '{provider}'. Use one of: {list(PROVIDERS)}")
    return PROVIDERS[provider][1]()


async def run_llm_loop(
    provider: str,
    model: str,
    system_prompt: str,
    tools: list[dict],
    dispatch: Dispatch,
    messages: list[dict],
) -> tuple[str, list[str]]:
    """Run a bounded tool-calling loop for the chosen provider.

    ``tools`` are MCP-style dicts ``{name, description, inputSchema}``. ``dispatch``
    executes a tool by name and returns its text result. Returns the final reply
    text and the ordered list of tool names that were invoked.
    """
    if provider not in PROVIDERS:
        raise ValueError(f"Unknown provider '{provider}'. Use one of: {list(PROVIDERS)}")
    runner = PROVIDERS[provider][0]
    # Ground every loop in the current date so relative dates ("ngày mai") and the
    # flight server's date-relative sample data resolve correctly.
    system_prompt = f"{system_prompt}\n\nHôm nay là {date.today().isoformat()}."
    return await runner(model, system_prompt, tools, dispatch, messages)
