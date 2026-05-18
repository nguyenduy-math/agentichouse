"""HandbookAgent — LightRAG-backed agent cho sổ tay nhân viên.

Phù hợp nhất cho các câu hỏi tổng quan về văn hóa công ty, sứ mệnh, giá trị,
thông tin chung cho nhân viên mới — nơi các mối quan hệ thực thể phác họa toàn
cảnh tổ chức.
"""

from __future__ import annotations

from pathlib import Path

from app.agents.base_agent import AgentResponse, BaseAgent
from app.config import settings
from app.ingestion import extract_text
from app.services.lightrag_service import LightRAGService

HANDBOOK_ENTITY_TYPES = [
    "gia_tri_cong_ty",  # company value
    "phong_ban",         # department
    "vai_tro",           # role / job title
    "chinh_sach",        # policy
    "quyen_loi",         # benefit
    "van_hoa",           # culture norm
    "co_so_vat_chat",   # facility / office
    "to_chuc",           # organization
    "ngay_thang",        # date
]

HANDBOOK_SYSTEM_PROMPT = """\
Bạn là hướng dẫn viên thân thiện của sổ tay nhân viên công ty. \
Hãy trả lời bằng tiếng Việt với giọng điệu ấm áp, chào đón và dễ hiểu. \
Giải thích văn hóa, giá trị, sứ mệnh và thông tin chung dựa chặt chẽ vào nội dung sổ tay. \
Đặc biệt hữu ích cho nhân viên mới cần hiểu tổng quan về công ty.
"""


class HandbookAgent(BaseAgent):
    domain = "HANDBOOK"
    engine_type = "lightrag"
    system_prompt = HANDBOOK_SYSTEM_PROMPT

    def __init__(self) -> None:
        working_dir = str(Path(settings.lightrag_base_dir) / "handbook")
        self._engine = LightRAGService(
            working_dir=working_dir,
            entity_types=HANDBOOK_ENTITY_TYPES,
        )
        self._doc_count = 0

    async def initialize(self) -> None:
        await self._engine.initialize()

    async def shutdown(self) -> None:
        await self._engine.shutdown()

    def is_ready(self) -> bool:
        return self._engine.is_ready()

    def indexed_count(self) -> int:
        return self._doc_count

    async def answer(self, question: str, history: list[dict]) -> AgentResponse:
        answer = await self._engine.query(
            question, mode="global", history=history, user_prompt=self.system_prompt
        )
        return AgentResponse(domain=self.domain, answer=answer)

    async def index_document(self, file_path: Path) -> None:
        text = extract_text(file_path).strip()
        if text:
            await self._engine.insert([text], [str(file_path)])
            self._doc_count += 1
