"""ITSecurityAgent — LightRAG-backed agent cho chính sách CNTT & bảo mật.

Phù hợp nhất cho các câu hỏi quan hệ về quy định sử dụng thiết bị, chính sách mật khẩu,
bảo mật dữ liệu, quyền truy cập hệ thống — nơi các thực thể (hệ thống, vai trò,
chính sách bảo mật) liên kết với nhau qua nhiều tài liệu.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.agents.base_agent import AgentResponse, BaseAgent
from app.config import settings
from app.ingestion import extract_text
from app.prompts import compose_system_prompt
from app.services.lightrag_service import LightRAGService

IT_SECURITY_ENTITY_TYPES = [
    "chinh_sach_bao_mat",   # chính sách bảo mật
    "quy_dinh_thiet_bi",    # quy định sử dụng thiết bị
    "chinh_sach_mat_khau",  # chính sách mật khẩu
    "quyen_truy_cap",       # quyền truy cập hệ thống
    "su_co_bao_mat",        # sự cố bảo mật / incident
    "du_lieu_nhay_cam",     # dữ liệu nhạy cảm
    "he_thong_cntt",        # hệ thống CNTT
    "hanh_vi_bi_cam",       # hành vi bị cấm
    "vai_tro_cntt",         # vai trò IT / chức danh
    "quy_trinh_xu_ly",      # quy trình xử lý sự cố
]

IT_SECURITY_PERSONA = (
    "Bạn là chuyên gia tư vấn chính sách CNTT và bảo mật thông tin của công ty. "
    "Hãy nêu rõ các quy tắc được phép và bị cấm, hướng dẫn sử dụng thiết bị và bảo mật dữ liệu."
)


class ITSecurityAgent(BaseAgent):
    domain = "IT_SECURITY"
    engine_type = "lightrag"

    def __init__(self) -> None:
        self.system_prompt = compose_system_prompt(IT_SECURITY_PERSONA)
        working_dir = Path(settings.lightrag_base_dir) / "it_security"
        self._count_file = working_dir / "_doc_count.json"
        self._engine = LightRAGService(
            working_dir=str(working_dir),
            entity_types=IT_SECURITY_ENTITY_TYPES,
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
