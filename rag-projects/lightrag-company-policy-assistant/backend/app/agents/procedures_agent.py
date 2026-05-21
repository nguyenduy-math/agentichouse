"""ProceduresAgent — LightRAG-backed agent cho quy trình & thủ tục.

Phù hợp nhất cho các câu hỏi về quy trình từng bước: onboarding, offboarding,
đề xuất hoàn ứng, xin nghỉ phép, chuỗi phê duyệt — nơi các bước kết nối với
phòng ban, vai trò và hệ thống tạo thành đồ thị thực thể.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.agents.base_agent import AgentResponse, BaseAgent
from app.config import settings
from app.ingestion import extract_text
from app.prompts import compose_system_prompt
from app.services.lightrag_service import LightRAGService

PROCEDURES_ENTITY_TYPES = [
    "buoc_quy_trinh",    # process step
    "vai_tro_phe_duyet", # approval role
    "phong_ban",          # department
    "he_thong",           # system / tool
    "mau_bieu",           # form / document
    "thoi_han",           # deadline
    "dieu_kien",          # condition
    "ket_qua",            # outcome
    "to_chuc",            # organization
    "ngay_thang",         # date
]

PROCEDURES_PERSONA = (
    "Bạn là chuyên gia tư vấn quy trình và thủ tục hành chính của công ty. "
    "Hãy giải thích từng bước theo thứ tự, xác định người chịu trách nhiệm ở mỗi bước, "
    "thời hạn thực hiện và các điều kiện cần đáp ứng."
)


class ProceduresAgent(BaseAgent):
    domain = "PROCEDURES"
    engine_type = "lightrag"

    def __init__(self) -> None:
        self.system_prompt = compose_system_prompt(PROCEDURES_PERSONA)
        working_dir = Path(settings.lightrag_base_dir) / "procedures"
        self._count_file = working_dir / "_doc_count.json"
        self._engine = LightRAGService(
            working_dir=str(working_dir),
            entity_types=PROCEDURES_ENTITY_TYPES,
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
