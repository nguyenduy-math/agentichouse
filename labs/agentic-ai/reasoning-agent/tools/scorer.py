import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from llm_client import call_llm
from prompts import SCORER_PROMPT


def score_branch(branch_description: str) -> float:
    """Score a partial travel plan via the configured LLM. Returns float in [0.0, 1.0]."""
    prompt = SCORER_PROMPT.format(branch_description=branch_description)
    raw = call_llm(prompt, mode="score", max_tokens=16)
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
