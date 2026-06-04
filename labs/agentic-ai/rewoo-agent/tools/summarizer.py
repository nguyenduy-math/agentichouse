import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import llm_client

_SYSTEM = (
    "You are a tech journalist. Given news search results, identify the "
    "3 most significant AI stories. For each story return: Title, "
    "One-sentence summary. Format as a numbered list."
)


def summarize_top3(results1: str, results2: str) -> str:
    """Identify the 3 most significant AI stories from combined search results."""
    combined = f"=== Source 1 ===\n{results1}\n\n=== Source 2 ===\n{results2}"
    return llm_client.chat_completion(system=_SYSTEM, user=combined, max_tokens=512)
