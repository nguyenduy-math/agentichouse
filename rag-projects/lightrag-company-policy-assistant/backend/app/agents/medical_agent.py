"""MedicalAgent — LightRAG-backed agent cho chính sách y tế.

Phù hợp nhất cho các câu hỏi quan hệ về bảo hiểm y tế, mức hoàn trả, danh sách
bệnh viện được bảo lãnh, quy trình khám chữa bệnh — nơi các thực thể (bảo hiểm,
bệnh viện, dịch vụ y tế) liên kết với nhau qua nhiều tài liệu.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.agents.base_agent import AgentResponse, BaseAgent
from app.config import settings
from app.ingestion import extract_text
from app.prompts import compose_system_prompt
from app.services.lightrag_service import LightRAGService

MEDICAL_ENTITY_TYPES = [
    "bao_hiem_y_te",        # bảo hiểm y tế
    "muc_hoan_tra",         # mức hoàn trả / thanh toán
    "benh_vien_bao_lanh",   # bệnh viện bảo lãnh
    "dich_vu_y_te",         # dịch vụ y tế được bảo hiểm
    "quy_trinh_kham",       # quy trình khám chữa bệnh
    "loai_benh",            # loại bệnh / điều kiện
    "gioi_han_bao_hiem",    # giới hạn bảo hiểm
    "dieu_kien_bao_hiem",   # điều kiện được bảo hiểm
    "to_chuc_y_te",         # tổ chức y tế / bên bảo hiểm
    "thoi_han_bao_hiem",    # thời hạn / kỳ bảo hiểm
]

MEDICAL_PERSONA = (
    "Bạn là chuyên gia tư vấn chính sách y tế và bảo hiểm sức khỏe của công ty. "
    "Hãy nêu rõ mức hoàn trả, giới hạn bảo hiểm, danh sách bệnh viện và quy trình thực hiện."
)


class MedicalAgent(BaseAgent):
    domain = "MEDICAL"
    engine_type = "lightrag"

    def __init__(self) -> None:
        self.system_prompt = compose_system_prompt(MEDICAL_PERSONA)
        working_dir = Path(settings.lightrag_base_dir) / "medical"
        self._count_file = working_dir / "_doc_count.json"
        self._engine = LightRAGService(
            working_dir=str(working_dir),
            entity_types=MEDICAL_ENTITY_TYPES,
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
