import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import llm_client

_SYSTEM_TEMPLATE = (
    "You are a professional assistant. Draft a team briefing email in "
    "{language} based on these AI news stories. Include: Subject line, "
    "Greeting, 3 bullet points (one per story), Professional closing. "
    "Be concise and engaging."
)


def draft_email(briefing: str, language: str = "Vietnamese") -> str:
    """Draft a professional team email in the specified language."""
    return llm_client.chat_completion(
        system=_SYSTEM_TEMPLATE.format(language=language),
        user=briefing,
        max_tokens=1024,
    )
