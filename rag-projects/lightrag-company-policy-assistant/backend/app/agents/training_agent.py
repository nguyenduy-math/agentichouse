"""TrainingAgent — LightRAG-backed agent cho chính sách đào tạo & phát triển.

Phù hợp nhất cho các câu hỏi quan hệ: lộ trình sự nghiệp, chương trình đào tạo
kết nối với vai trò và phòng ban nào, điều kiện tham gia, ngân sách học bổng —
nơi các thực thể (kỹ năng, chương trình, vai trò, phòng ban) liên kết với nhau.
"""

from __future__ import annotations

from pathlib import Path

from app.agents.base_agent import AgentResponse, BaseAgent
from app.config import settings
from app.ingestion import extract_text
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

TRAINING_SYSTEM_PROMPT = """\
Bạn là chuyên gia tư vấn đào tạo và phát triển nhân sự của công ty. \
Hãy trả lời bằng tiếng Việt, giải thích lộ trình sự nghiệp, các chương trình đào tạo phù hợp \
với từng vai trò và phòng ban, điều kiện tham gia và ngân sách học bổng. \
Chỉ sử dụng thông tin từ tài liệu được cung cấp. \
Nếu câu hỏi vượt ngoài phạm vi tài liệu, hướng dẫn liên hệ phòng Nhân sự hoặc Trưởng phòng.
"""


class TrainingAgent(BaseAgent):
    domain = "TRAINING"
    engine_type = "lightrag"
    system_prompt = TRAINING_SYSTEM_PROMPT

    def __init__(self) -> None:
        working_dir = str(Path(settings.lightrag_base_dir) / "training")
        self._engine = LightRAGService(
            working_dir=working_dir,
            entity_types=TRAINING_ENTITY_TYPES,
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
        return AgentResponse(domain=self.domain, answer=answer)

    async def index_document(self, file_path: Path) -> None:
        text = extract_text(file_path).strip()
        if text:
            await self._engine.insert([text], [str(file_path)])
            self._doc_count += 1
