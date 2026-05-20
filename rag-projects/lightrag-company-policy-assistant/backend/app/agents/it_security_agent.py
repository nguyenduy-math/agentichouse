"""ITSecurityAgent — PageIndex-backed agent cho chính sách CNTT & bảo mật.

Phù hợp nhất cho các câu hỏi về quy định sử dụng thiết bị, chính sách mật khẩu,
bảo mật dữ liệu, quyền truy cập hệ thống — cần trích dẫn chính xác điều khoản và trang.
"""

from __future__ import annotations

from pathlib import Path

from app.agents.base_agent import AgentResponse, BaseAgent
from app.config import settings
from app.prompts import compose_system_prompt
from app.schemas import Citation
from app.services.pageindex_service import PageIndexService

IT_SECURITY_PERSONA = (
    "Bạn là chuyên gia tư vấn chính sách CNTT và bảo mật thông tin của công ty. "
    "Hãy nêu rõ các quy tắc được phép và bị cấm, hướng dẫn sử dụng thiết bị và bảo mật dữ liệu."
)


class ITSecurityAgent(BaseAgent):
    domain = "IT_SECURITY"
    engine_type = "pageindex"

    def __init__(self) -> None:
        self.system_prompt = compose_system_prompt(IT_SECURITY_PERSONA)
        index_dir = Path(settings.pageindex_base_dir) / "it_security"
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
