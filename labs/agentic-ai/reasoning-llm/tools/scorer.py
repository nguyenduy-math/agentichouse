import os
import anthropic
from prompts import SCORER_PROMPT


def score_branch(branch_description: str) -> float:
    """Score a partial travel plan using Claude Haiku. Returns float in [0.0, 1.0]."""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "ANTHROPIC_API_KEY is not set. Copy .env.example to .env and add your key."
        )

    client = anthropic.Anthropic(api_key=api_key)
    prompt = SCORER_PROMPT.format(branch_description=branch_description)

    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=16,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = message.content[0].text.strip()
    try:
        score = float(raw)
        return max(0.0, min(1.0, score))
    except ValueError:
        # If the model returns something unexpected, extract first float-like token
        for token in raw.split():
            try:
                return max(0.0, min(1.0, float(token)))
            except ValueError:
                continue
        return 0.5  # fallback neutral score
