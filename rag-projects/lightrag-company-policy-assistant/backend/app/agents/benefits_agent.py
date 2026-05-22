"""BenefitsAgent — PageIndex Cloud-backed agent cho chính sách phúc lợi & đãi ngộ.

Phù hợp nhất cho các câu hỏi cụ thể về lương thưởng, bảo hiểm sức khỏe,
hưu trí, phụ cấp, trợ cấp — cần trích dẫn chính xác số tiền, tỷ lệ và số trang.

Luồng:
  - PageIndexCloudService   — upload PDF → poll → tải cây JSON về disk
  - SearchService           — điều hướng cây (Gemini) → đọc node.text + PDF → trả lời có citation
"""

from __future__ import annotations

from pathlib import Path

from app.agents.base_agent import AgentResponse, BaseAgent
from app.config import settings
from app.prompts import compose_system_prompt
from app.schemas import Citation
from app.services.pageindex_cloud_service import PageIndexCloudService
from app.services.search_service import SearchService

BENEFITS_PERSONA = (
    "Bạn là chuyên gia tư vấn phúc lợi và đãi ngộ của công ty. "
    "Cung cấp thông tin chính xác về lương thưởng, bảo hiểm sức khỏe, hưu trí, "
    "phụ cấp và các quyền lợi khác."
)


class BenefitsAgent(BaseAgent):
    domain = "BENEFITS"
    engine_type = "pageindex"

    def __init__(self) -> None:
        self.system_prompt = compose_system_prompt(BENEFITS_PERSONA)
        tree_dir = Path(settings.pageindex_base_dir) / "benefits"
        self._cloud = PageIndexCloudService(
            api_key=settings.pageindex_api_key,
            tree_dir=tree_dir,
        )
        self._search = SearchService(tree_source=self._cloud)

    async def initialize(self) -> None:
        pass  # both services initialize synchronously in __init__

    async def shutdown(self) -> None:
        pass

    def is_ready(self) -> bool:
        return self._cloud.is_ready()

    def indexed_count(self) -> int:
        return self._cloud.indexed_count()

    async def answer(self, question: str, history: list[dict]) -> AgentResponse:
        result = await self._search.query(
            question, history=history, system_prompt=self.system_prompt
        )
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
        await self._cloud.index_document(file_path)
