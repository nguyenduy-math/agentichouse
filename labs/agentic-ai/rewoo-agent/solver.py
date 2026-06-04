import os
import anthropic

SOLVER_SYSTEM = """You are a helpful assistant. Given a task and the evidence
collected by previous tool calls, produce the final answer.
For email drafts: present the email clearly with a separator line.
Do not add commentary beyond what was requested."""

SOLVER_USER = """Task: {query}

Evidence:
{evidence_block}

Final answer:"""


def format_evidence(evidence: dict[str, str]) -> str:
    lines = []
    for var, value in evidence.items():
        # Truncate very long values (raw search results) for the solver prompt
        display = value if len(value) <= 300 else value[:300] + "...[truncated]"
        lines.append(f"{var} = {display}")
    return "\n\n".join(lines)


def solve(query: str, evidence: dict[str, str]) -> str:
    """Generate the final answer using the LLM and all collected evidence."""
    print("\n[Solver] Finalizing answer...")

    # If #E4 exists and looks like an email, present it directly
    last_var = list(evidence.keys())[-1]
    last_value = evidence[last_var]

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    evidence_block = format_evidence(evidence)
    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        system=SOLVER_SYSTEM,
        messages=[{
            "role": "user",
            "content": SOLVER_USER.format(query=query, evidence_block=evidence_block),
        }],
    )
    return message.content[0].text
