"""ConductAgent — PageIndex-backed agent cho quy tắc ứng xử.

Phù hợp nhất cho các câu hỏi cụ thể về quy tắc nơi làm việc: hành vi bị cấm,
quy định trang phục, quy trình kỷ luật, đạo đức nghề nghiệp — cần trích dẫn
chính xác điều khoản và số trang từ tài liệu quy tắc ứng xử.
"""

from __future__ import annotations

from pathlib import Path

from app.agents.base_agent import AgentResponse, BaseAgent
from app.config import settings
from app.schemas import Citation
from app.services.pageindex_service import PageIndexService


class ConductAgent(BaseAgent):
    domain = "CONDUCT"
    engine_type = "pageindex"
    system_prompt = (
        "Bạn là chuyên gia tư vấn quy tắc ứng xử và đạo đức nghề nghiệp của công ty. "
        "Hãy trả lời bằng tiếng Việt với giọng điệu chuyên nghiệp và rõ ràng. "
        "Trích dẫn chính xác số điều, số trang khi đề cập quy định cụ thể. "
        "Nêu rõ những gì được phép, bị cấm và hậu quả vi phạm."
    )

    def __init__(self) -> None:
        index_dir = Path(settings.pageindex_base_dir) / "conduct"
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
        result = await self._engine.query(question)
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
