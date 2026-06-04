import llm_client

SOLVER_SYSTEM = """Bạn là một trợ lý hữu ích. Dựa trên nhiệm vụ và các bằng chứng
thu thập từ các lệnh gọi công cụ trước đó, hãy đưa ra câu trả lời cuối cùng.
Với bản nháp email: trình bày email rõ ràng với một dòng phân cách.
Không thêm bình luận ngoài những gì được yêu cầu."""

SOLVER_USER = """Nhiệm vụ: {query}

Bằng chứng:
{evidence_block}

Câu trả lời cuối cùng:"""


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

    evidence_block = format_evidence(evidence)
    return llm_client.chat_completion(
        system=SOLVER_SYSTEM,
        user=SOLVER_USER.format(query=query, evidence_block=evidence_block),
        max_tokens=1024,
    )
