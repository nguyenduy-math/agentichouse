"""Compliance domain specialist agent."""
from __future__ import annotations
from langchain_core.language_models.chat_models import BaseChatModel
from app.agents.base_agent import BaseDomainAgent
from app.prompts.system_prompts import COMPLIANCE_SYSTEM_PROMPT


class ComplianceAgent(BaseDomainAgent):
    domain_key = "compliance"
    _system_prompt = COMPLIANCE_SYSTEM_PROMPT

    def __init__(self, llm: BaseChatModel) -> None:
        super().__init__(llm)

    def _build_user_message(self, question: str, context_chunks: list[str], graph_context: str) -> str:
        context = "\n\n---\n\n".join(context_chunks[:5]) if context_chunks else "(không có ngữ cảnh)"
        graph = graph_context.strip() if graph_context else "(không có thông tin đồ thị)"
        return (
            f"Thông tin từ tài liệu nội bộ:\n{context}\n\n"
            f"Tóm tắt từ đồ thị tri thức:\n{graph}\n\n"
            f"Câu hỏi của nhân viên: {question}\n\n"
            "Hãy trả lời câu hỏi dựa trên thông tin trên. Nếu không đủ thông tin, hãy nói rõ."
        )
