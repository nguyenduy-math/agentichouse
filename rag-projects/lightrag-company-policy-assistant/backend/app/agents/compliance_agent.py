"""ComplianceAgent — PageIndex-backed agent cho chính sách tuân thủ & pháp lý.

Phù hợp nhất cho các câu hỏi về tuân thủ pháp luật lao động, quy định thuế,
bảo vệ dữ liệu cá nhân (PDPA/GDPR), phòng chống tham nhũng, báo cáo vi phạm —
cần trích dẫn chính xác điều luật và số trang.
"""

from __future__ import annotations

from pathlib import Path

from app.agents.base_agent import AgentResponse, BaseAgent
from app.config import settings
from app.schemas import Citation
from app.services.pageindex_service import PageIndexService

COMPLIANCE_SYSTEM_PROMPT = """\
Bạn là chuyên gia tư vấn tuân thủ pháp lý và quy định của công ty. \
Hãy trả lời bằng tiếng Việt, trích dẫn chính xác số trang, điều khoản, và số hiệu văn bản pháp luật. \
Nêu rõ nghĩa vụ pháp lý, hậu quả vi phạm, và quy trình báo cáo. \
Nếu cần tư vấn pháp lý chuyên sâu, hướng dẫn liên hệ phòng Pháp chế hoặc luật sư của công ty.
"""


class ComplianceAgent(BaseAgent):
    domain = "COMPLIANCE"
    engine_type = "pageindex"
    system_prompt = COMPLIANCE_SYSTEM_PROMPT

    def __init__(self) -> None:
        index_dir = Path(settings.pageindex_base_dir) / "compliance"
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
