"""TrainingAgent — LightRAG-backed agent cho chính sách đào tạo & phát triển.

Phù hợp nhất cho các câu hỏi quan hệ: lộ trình sự nghiệp, chương trình đào tạo
kết nối với vai trò và phòng ban nào, điều kiện tham gia, ngân sách học bổng —
nơi các thực thể (kỹ năng, chương trình, vai trò, phòng ban) liên kết với nhau.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.agents.base_agent import AgentResponse, BaseAgent
from app.config import settings
from app.ingestion import extract_text
from app.prompts import compose_system_prompt
from app.services.lightrag_service import LightRAGService

TRAINING_ENTITY_TYPES = [
    "chuong_trinh_dao_tao",   # training program
    "lo_trinh_su_nghiep",     # career path
    "ky_nang",                 # skill / competency
    "vai_tro",                 # role / job title
    "phong_ban",               # department
    "dieu_kien",               # eligibility condition
    "ngan_sach",               # budget / scholarship
    "nha_cung_cap_dao_tao",   # training provider
    "chung_chi",               # certificate / credential
    "to_chuc",                 # organization
    "ngay_thang",              # date / deadline
]

TRAINING_PERSONA = (
    "Bạn là chuyên gia tư vấn đào tạo và phát triển nhân sự của công ty. "
    "Hãy giải thích lộ trình sự nghiệp, các chương trình đào tạo phù hợp với từng vai trò "
    "và phòng ban, điều kiện tham gia và ngân sách học bổng."
)


class TrainingAgent(BaseAgent):
    domain = "TRAINING"
    engine_type = "lightrag"

    def __init__(self) -> None:
        self.system_prompt = compose_system_prompt(TRAINING_PERSONA)
        working_dir = Path(settings.lightrag_base_dir) / "training"
        self._count_file = working_dir / "_doc_count.json"
        self._engine = LightRAGService(
            working_dir=str(working_dir),
            entity_types=TRAINING_ENTITY_TYPES,
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
