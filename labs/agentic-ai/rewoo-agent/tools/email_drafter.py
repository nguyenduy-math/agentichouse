import os
import anthropic

_SYSTEM_TEMPLATE = (
    "You are a professional assistant. Draft a team briefing email in "
    "{language} based on these AI news stories. Include: Subject line, "
    "Greeting, 3 bullet points (one per story), Professional closing. "
    "Be concise and engaging."
)


def draft_email(briefing: str, language: str = "Vietnamese") -> str:
    """Draft a professional team email in the specified language."""
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        system=_SYSTEM_TEMPLATE.format(language=language),
        messages=[{"role": "user", "content": briefing}],
    )
    return message.content[0].text
