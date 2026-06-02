import time

from duckduckgo_search import DDGS


def search(query: str) -> str:
    """Search DuckDuckGo and return top 5 result snippets as a single string."""
    for attempt in range(2):
        try:
            results = DDGS().text(query, max_results=5)
            if not results:
                return f"[No results found for: {query}]"
            parts = []
            for r in results:
                title = r.get("title", "")
                body = r.get("body", "")
                parts.append(f"- {title}: {body}")
            return "\n".join(parts)
        except Exception as e:
            if attempt == 0:
                time.sleep(2)
                continue
            return f"[Search error: {e}]"
    return f"[Search failed for: {query}]"
