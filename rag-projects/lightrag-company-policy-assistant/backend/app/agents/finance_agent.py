"""FinanceAgent — PageIndex-backed agent cho chính sách tài chính.

Phù hợp nhất cho các câu hỏi về hạn mức chi phí, quy trình hoàn ứng, chính sách
chi tiêu công tác, khoán phụ cấp, quy định phê duyệt ngân sách — cần trích dẫn
chính xác số tiền, hạn mức và trang tài liệu.
"""

from __future__ import annotations

from pathlib import Path

from app.agents.base_agent import AgentResponse, BaseAgent
from app.config import settings
from app.prompts import compose_system_prompt
from app.schemas import Citation
from app.services.pageindex_service import PageIndexService

FINANCE_PERSONA = (
    "Bạn là chuyên gia tư vấn chính sách tài chính và kế toán của công ty. "
    "Hãy nêu rõ mức trần chi phí, danh mục được phép hoàn ứng, quy trình phê duyệt "
    "và thời hạn nộp hồ sơ."
)


class FinanceAgent(BaseAgent):
    domain = "FINANCE"
    engine_type = "pageindex"

    def __init__(self) -> None:
        self.system_prompt = compose_system_prompt(FINANCE_PERSONA)
        index_dir = Path(settings.pageindex_base_dir) / "finance"
        self._engine = PageIndexService(index_dir=index_dir, domain=self.domain)

    async def initialize(self) -> None:
        pass

    async def shutdown(self) -> None:
        pass

    def is_ready(self) -> bool:
        return self._engine.is_ready()

    def indexed_count(self) -> int:
        return self._engine.indexed_count()

    async def answer(self, question: str, history: list[dict]) -> AgentResponse:
        result = await self._engine.query(question, history=history, system_prompt=self.system_prompt)
        citations = [
            Citation(
                document=c["document"],
                page=c["page"],
                section=c.get("section", ""),
                domain=self.domain,
            )
            for c in result.citations
        ]
        return AgentResponse(domain=self.domain, answer=result.answer, citations=citations)

    async def index_document(self, file_path: Path) -> None:
        await self._engine.index_document(file_path)
