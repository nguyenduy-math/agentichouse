"""HRPolicyAgent — LightRAG-backed agent cho nội quy lao động.

Phù hợp nhất cho các câu hỏi quan hệ về hợp đồng lao động, chính sách nghỉ phép,
giờ làm việc, đánh giá hiệu suất — nơi các thực thể (vai trò, phòng ban, quyền lợi)
liên kết với nhau qua nhiều tài liệu nội quy.
"""

from __future__ import annotations

from pathlib import Path

from app.agents.base_agent import AgentResponse, BaseAgent
from app.config import settings
from app.ingestion import extract_text
from app.prompts import compose_system_prompt
from app.services.lightrag_service import LightRAGService

HR_ENTITY_TYPES = [
    "chinh_sach",       # chính sách cấp cao
    "quy_tac",          # quy tắc cụ thể
    "phong_ban",        # bộ phận / phòng ban
    "vai_tro",          # vai trò / chức danh
    "quyen_loi",        # quyền lợi / phúc lợi
    "loai_nghi_phep",   # loại nghỉ phép
    "gio_lam_viec",     # giờ làm việc
    "chi_so_hieu_suat", # chỉ số đánh giá hiệu suất
    "quy_dinh",         # quy định pháp luật
    "ngoai_le",         # trường hợp ngoại lệ
    "to_chuc",          # tổ chức
    "ngay_thang",       # ngày / thời hạn
]

# Persona only — shared grounding + citation + language are added by
# compose_system_prompt() so every agent answers under the same contract.
HR_PERSONA = (
    "Bạn là chuyên gia tư vấn nội quy lao động của công ty, "
    "giọng điệu thân thiện và chuyên nghiệp như một đồng nghiệp HR nhiệt tình. "
    "Nếu quy định khác nhau theo phòng ban hoặc vai trò, hãy nêu rõ từng trường hợp."
)


class HRPolicyAgent(BaseAgent):
    domain = "HR_POLICY"
    engine_type = "lightrag"

    def __init__(self) -> None:
        self.system_prompt = compose_system_prompt(HR_PERSONA)
        working_dir = str(Path(settings.lightrag_base_dir) / "hr_policy")
        self._engine = LightRAGService(
            working_dir=working_dir,
            entity_types=HR_ENTITY_TYPES,
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
            question, mode="hybrid", history=history, user_prompt=self.system_prompt
        )
        entities = await self._engine.retrieve_entities(question, mode="hybrid")
        return AgentResponse(domain=self.domain, answer=answer, entities=entities)

    async def index_document(self, file_path: Path) -> None:
        text = extract_text(file_path).strip()
        if text:
            await self._engine.insert([text], [str(file_path)])
            self._doc_count += 1
