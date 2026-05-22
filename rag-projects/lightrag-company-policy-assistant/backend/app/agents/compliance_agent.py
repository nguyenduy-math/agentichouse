"""ComplianceAgent — LightRAG-backed agent cho chính sách tuân thủ & pháp lý.

Phù hợp nhất cho các câu hỏi quan hệ về tuân thủ pháp luật lao động, quy định thuế,
bảo vệ dữ liệu cá nhân (PDPA/GDPR), phòng chống tham nhũng, báo cáo vi phạm —
nơi các thực thể (điều luật, nghĩa vụ, hình thức xử phạt) liên kết qua nhiều văn bản.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.agents.base_agent import AgentResponse, BaseAgent
from app.config import settings
from app.ingestion import extract_text
from app.prompts import compose_system_prompt
from app.services.lightrag_service import LightRAGService

COMPLIANCE_ENTITY_TYPES = [
    "quy_dinh_phap_ly",         # quy định pháp lý
    "dieu_luat",                # điều luật / điều khoản
    "nghia_vu_phap_ly",         # nghĩa vụ pháp lý
    "hanh_vi_vi_pham",          # hành vi vi phạm
    "xu_phat",                  # hình thức xử phạt
    "bao_cao_vi_pham",          # kênh báo cáo vi phạm
    "bao_mat_du_lieu",          # bảo mật dữ liệu (PDPA/GDPR)
    "phong_chong_tham_nhung",   # phòng chống tham nhũng
    "to_chuc_phap_ly",          # tổ chức / cơ quan pháp lý
    "thoi_han_phap_ly",         # thời hạn pháp lý
]

COMPLIANCE_PERSONA = (
    "Bạn là chuyên gia tư vấn tuân thủ pháp lý và quy định của công ty. "
    "Hãy nêu rõ nghĩa vụ pháp lý, hậu quả vi phạm và quy trình báo cáo; "
    "với tư vấn pháp lý chuyên sâu, hướng dẫn liên hệ phòng Pháp chế."
)


class ComplianceAgent(BaseAgent):
    domain = "COMPLIANCE"
    engine_type = "lightrag"

    def __init__(self) -> None:
        self.system_prompt = compose_system_prompt(COMPLIANCE_PERSONA)
        working_dir = Path(settings.lightrag_base_dir) / "compliance"
        self._count_file = working_dir / "_doc_count.json"
        self._engine = LightRAGService(
            working_dir=str(working_dir),
            entity_types=COMPLIANCE_ENTITY_TYPES,
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
