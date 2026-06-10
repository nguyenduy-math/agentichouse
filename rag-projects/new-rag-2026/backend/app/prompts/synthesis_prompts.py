"""
Additional synthesis and context-building prompts.
"""
from __future__ import annotations

DOMAIN_AGENT_USER_TEMPLATE = """Thông tin từ tài liệu nội bộ:
{context}

Tóm tắt từ đồ thị tri thức:
{graph_context}

Câu hỏi của nhân viên: {question}

Hãy trả lời câu hỏi dựa trên thông tin trên. Nếu không đủ thông tin, hãy nói rõ."""


GRAPH_CONTEXT_TEMPLATE = """Các thực thể liên quan:
{entities}

Các mối quan hệ:
{triples}"""


def build_graph_context(neighborhood: dict) -> str:
    """Format graph neighborhood data into a readable string for LLM context."""
    entities = neighborhood.get("entities", [])
    triples = neighborhood.get("triples", [])

    entity_lines = []
    for e in entities[:20]:  # limit to 20 entities
        name = e.get("name", "")
        etype = e.get("type", "")
        desc = e.get("description", "")
        if name:
            entity_lines.append(f"- {name} ({etype}): {desc[:200]}")

    triple_lines = []
    for t in triples[:30]:  # limit to 30 triples
        src = t.get("source", "")
        rel = t.get("relation", "RELATED_TO")
        tgt = t.get("target", "")
        if src and tgt:
            triple_lines.append(f"- {src} → {rel} → {tgt}")

    if not entity_lines and not triple_lines:
        return ""

    return GRAPH_CONTEXT_TEMPLATE.format(
        entities="\n".join(entity_lines) or "(không có)",
        triples="\n".join(triple_lines) or "(không có)",
    )
