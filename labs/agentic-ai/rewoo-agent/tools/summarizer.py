import os
import anthropic

_SYSTEM = (
    "You are a tech journalist. Given news search results, identify the "
    "3 most significant AI stories. For each story return: Title, "
    "One-sentence summary. Format as a numbered list."
)


def summarize_top3(results1: str, results2: str) -> str:
    """Identify the 3 most significant AI stories from combined search results."""
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    combined = f"=== Source 1 ===\n{results1}\n\n=== Source 2 ===\n{results2}"
    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=512,
        system=_SYSTEM,
        messages=[{"role": "user", "content": combined}],
    )
    return message.content[0].text
