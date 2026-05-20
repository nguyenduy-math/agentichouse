"""MedicalAgent — PageIndex-backed agent cho chính sách y tế.

Phù hợp nhất cho các câu hỏi cụ thể về bảo hiểm y tế, mức hoàn trả, danh sách
bệnh viện được bảo lãnh, quy trình khám chữa bệnh — cần trích dẫn đúng trang,
đúng số tiền, đúng điều khoản.
"""

from __future__ import annotations

from pathlib import Path

from app.agents.base_agent import AgentResponse, BaseAgent
from app.config import settings
from app.prompts import compose_system_prompt
from app.schemas import Citation
from app.services.pageindex_service import PageIndexService

MEDICAL_PERSONA = (
    "Bạn là chuyên gia tư vấn chính sách y tế và bảo hiểm sức khỏe của công ty. "
    "Hãy nêu rõ mức hoàn trả, giới hạn bảo hiểm, danh sách bệnh viện và quy trình thực hiện."
)


class MedicalAgent(BaseAgent):
    domain = "MEDICAL"
    engine_type = "pageindex"

    def __init__(self) -> None:
        self.system_prompt = compose_system_prompt(MEDICAL_PERSONA)
        index_dir = Path(settings.pageindex_base_dir) / "medical"
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
