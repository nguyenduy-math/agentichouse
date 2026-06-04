import os
from typing import Literal

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "anthropic").lower()

Mode = Literal["expand", "solve", "score"]

_MODELS = {
    "anthropic": {
        "expand": "claude-sonnet-4-6",
        "solve": "claude-sonnet-4-6",
        "score": "claude-haiku-4-5-20251001",
    },
    "gemini": {
        "expand": "gemini-2.5-flash",
        "solve": "gemini-2.5-flash",
        "score": "gemini-2.0-flash-lite",
    },
    "siliconflow": {
        "expand": "Qwen/Qwen3-8B",
        "solve": "Qwen/Qwen3-8B",
        "score": "Qwen/Qwen3-1.7B",
    },
}

_MAX_TOKENS_SCORE = 16


def call_llm(prompt: str, mode: Mode = "expand", max_tokens: int = 1024) -> str:
    if LLM_PROVIDER == "anthropic":
        return _call_anthropic(prompt, mode, max_tokens)
    elif LLM_PROVIDER == "gemini":
        return _call_gemini(prompt, mode, max_tokens)
    elif LLM_PROVIDER == "siliconflow":
        return _call_siliconflow(prompt, mode, max_tokens)
    else:
        raise ValueError(
            f"Unknown LLM_PROVIDER='{LLM_PROVIDER}'. "
            "Set LLM_PROVIDER to one of: anthropic | gemini | siliconflow"
        )


def _call_anthropic(prompt: str, mode: Mode, max_tokens: int) -> str:
    import anthropic

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise EnvironmentError("ANTHROPIC_API_KEY is not set in .env")

    model = _MODELS["anthropic"][mode]
    client = anthropic.Anthropic(api_key=api_key)
    msg = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    return msg.content[0].text.strip()


def _call_gemini(prompt: str, mode: Mode, max_tokens: int) -> str:
    from google import genai
    from google.genai import types

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise EnvironmentError("GEMINI_API_KEY is not set in .env")

    model = _MODELS["gemini"][mode]
    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0.0,
            max_output_tokens=max_tokens,
        ),
    )
    return response.text.strip()


def _call_siliconflow(prompt: str, mode: Mode, max_tokens: int) -> str:
    from openai import OpenAI

    api_key = os.getenv("SILICONFLOW_API_KEY")
    if not api_key:
        raise EnvironmentError("SILICONFLOW_API_KEY is not set in .env")

    model = _MODELS["siliconflow"][mode]
    client = OpenAI(
        api_key=api_key,
        base_url="https://api.siliconflow.cn/v1",
    )
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=max_tokens,
        temperature=0.0,
    )
    return response.choices[0].message.content.strip()
