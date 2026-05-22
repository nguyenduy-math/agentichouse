"""ConductAgent — LightRAG-backed agent cho quy tắc ứng xử.

Phù hợp nhất cho các câu hỏi quan hệ về quy tắc nơi làm việc: hành vi bị cấm,
quy định trang phục, quy trình kỷ luật, đạo đức nghề nghiệp — nơi các thực thể
(quy tắc, vai trò, hình thức xử phạt) liên kết với nhau qua nhiều tài liệu.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.agents.base_agent import AgentResponse, BaseAgent
from app.config import settings
from app.ingestion import extract_text
from app.prompts import compose_system_prompt
from app.services.lightrag_service import LightRAGService

CONDUCT_ENTITY_TYPES = [
    "quy_tac_ung_xu",       # quy tắc ứng xử
    "hanh_vi_bi_cam",       # hành vi bị cấm
    "quy_trinh_ky_luat",    # quy trình kỷ luật
    "quy_dinh_trang_phuc",  # quy định trang phục
    "dao_duc_nghe_nghiep",  # đạo đức nghề nghiệp
    "hinh_thuc_xu_phat",    # hình thức xử phạt
    "muc_vi_pham",          # mức độ vi phạm
    "vai_tro",              # vai trò / chức danh
    "phong_ban",            # phòng ban
    "thoi_han",             # thời hạn
]

CONDUCT_PERSONA = (
    "Bạn là chuyên gia tư vấn quy tắc ứng xử và đạo đức nghề nghiệp của công ty, "
    "giọng điệu chuyên nghiệp và rõ ràng. "
    "Hãy nêu rõ những gì được phép, bị cấm và hậu quả vi phạm."
)


class ConductAgent(BaseAgent):
    domain = "CONDUCT"
    engine_type = "lightrag"

    def __init__(self) -> None:
        self.system_prompt = compose_system_prompt(CONDUCT_PERSONA)
        working_dir = Path(settings.lightrag_base_dir) / "conduct"
        self._count_file = working_dir / "_doc_count.json"
        self._engine = LightRAGService(
            working_dir=str(working_dir),
            entity_types=CONDUCT_ENTITY_TYPES,
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
