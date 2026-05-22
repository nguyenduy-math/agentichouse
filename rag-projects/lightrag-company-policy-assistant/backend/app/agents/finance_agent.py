"""FinanceAgent — LightRAG-backed agent cho chính sách tài chính.

Phù hợp nhất cho các câu hỏi quan hệ về hạn mức chi phí, quy trình hoàn ứng, chính sách
chi tiêu công tác, khoán phụ cấp, quy định phê duyệt ngân sách — nơi các thực thể
(hạn mức, danh mục, người phê duyệt) liên kết với nhau qua nhiều tài liệu.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.agents.base_agent import AgentResponse, BaseAgent
from app.config import settings
from app.ingestion import extract_text
from app.prompts import compose_system_prompt
from app.services.lightrag_service import LightRAGService

FINANCE_ENTITY_TYPES = [
    "han_muc_chi_phi",      # hạn mức chi phí
    "loai_chi_phi",         # loại chi phí / danh mục
    "quy_trinh_phe_duyet",  # quy trình phê duyệt
    "danh_muc_hoan_ung",    # danh mục được hoàn ứng
    "muc_chi_tieu",         # mức chi tiêu công tác
    "thoi_han_nop",         # thời hạn nộp hồ sơ
    "nguoi_phe_duyet",      # người phê duyệt / cấp ủy quyền
    "don_vi_tien_te",       # đơn vị tiền tệ / số tiền
    "phong_ban",            # phòng ban
    "chinh_sach_tai_chinh", # chính sách tài chính cấp cao
]

FINANCE_PERSONA = (
    "Bạn là chuyên gia tư vấn chính sách tài chính và kế toán của công ty. "
    "Hãy nêu rõ mức trần chi phí, danh mục được phép hoàn ứng, quy trình phê duyệt "
    "và thời hạn nộp hồ sơ."
)


class FinanceAgent(BaseAgent):
    domain = "FINANCE"
    engine_type = "lightrag"

    def __init__(self) -> None:
        self.system_prompt = compose_system_prompt(FINANCE_PERSONA)
        working_dir = Path(settings.lightrag_base_dir) / "finance"
        self._count_file = working_dir / "_doc_count.json"
        self._engine = LightRAGService(
            working_dir=str(working_dir),
            entity_types=FINANCE_ENTITY_TYPES,
        )
        self._doc_count = 0

    async def initialize(self) -> None:
        await self._engine.initialize()
        try:
            self._doc_count = json.loads(self._count_file.read_text())
        except Exception:
            self._doc_count = 0

    async def shutdown(self) -> None:
        await self._engine.shutdown()

    def is_ready(self) -> bool:
        return self._engine.is_ready()

    def indexed_count(self) -> int:
        return self._doc_count

    def reset_doc_count(self) -> None:
        self._doc_count = 0
        self._count_file.unlink(missing_ok=True)

    async def answer(self, question: str, history: list[dict]) -> AgentResponse:
        answer = await self._engine.query(
            question, mode="hybrid", history=history, user_prompt=self.system_prompt
        )
        entities = await self._engine.retrieve_entities(question, mode="hybrid")
        return AgentResponse(domain=self.domain, answer=answer, entities=entities)

    async def index_document(self, file_path: Path) -> None:
        text = extract_text(file_path).strip()
        if text:
            await self._engine.insert([text], [str(file_path)])
            self._doc_count += 1
            self._count_file.write_text(json.dumps(self._doc_count))
