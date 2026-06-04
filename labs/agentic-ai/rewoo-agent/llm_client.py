import os


def chat_completion(system: str, user: str, max_tokens: int = 1024) -> str:
    """Route to the configured LLM provider via LLM_PROVIDER env var."""
    provider = os.getenv("LLM_PROVIDER", "anthropic").lower()
    if provider == "anthropic":
        return _anthropic(system, user, max_tokens)
    if provider == "gemini":
        return _gemini(system, user, max_tokens)
    if provider == "siliconflow":
        return _siliconflow(system, user, max_tokens)
    raise ValueError(f"Unknown LLM_PROVIDER: {provider!r}. Choose: anthropic | gemini | siliconflow")


def _anthropic(system: str, user: str, max_tokens: int) -> str:
    import anthropic
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    message = client.messages.create(
        model=os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001"),
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return message.content[0].text


def _gemini(system: str, user: str, max_tokens: int) -> str:
    from google import genai
    from google.genai import types
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    response = client.models.generate_content(
        model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
        contents=f"{system}\n\n{user}",
        config=types.GenerateContentConfig(
            max_output_tokens=max_tokens,
            temperature=0.0,
        ),
    )
    return response.text


def _siliconflow(system: str, user: str, max_tokens: int) -> str:
    from openai import OpenAI
    client = OpenAI(
        api_key=os.environ["SILICONFLOW_API_KEY"],
        base_url="https://api.siliconflow.cn/v1",
    )
    response = client.chat.completions.create(
        model=os.getenv("SILICONFLOW_MODEL", "Qwen/Qwen2.5-7B-Instruct"),
        max_tokens=max_tokens,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    return response.choices[0].message.content
