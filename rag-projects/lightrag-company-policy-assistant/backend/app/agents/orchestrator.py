"""OrchestratorAgent — routes employee questions to domain specialist agents.

Flow:
  1. classify_domains()  — LLM classifies question into 1-3 domain keys
  2. single domain       — direct route, no synthesis needed
  3. cross-domain        — asyncio.gather fan-out → _synthesize() merges answers

The JSON classification pattern is lifted from graphrag-assistant's
llm_service.classify_query() (temperature=0, response_mime_type=application/json).
"""

from __future__ import annotations

import asyncio
import json
import logging

from google import genai
from google.genai import types

from app.agents.base_agent import AgentResponse, BaseAgent
from app.config import settings
from app.schemas import AgentHealth, ChatTurn, Citation

logger = logging.getLogger(__name__)

_JSON_CONFIG = types.GenerateContentConfig(
    response_mime_type="application/json",
    temperature=0.0,
)

_DOMAIN_CLASSIFY_PROMPT = """\
Phân loại câu hỏi của nhân viên vào một hoặc nhiều lĩnh vực chính sách của công ty.

Các lĩnh vực:
  HR_POLICY   — Nội quy lao động, hợp đồng, nghỉ phép, giờ làm việc, đánh giá hiệu suất
  BENEFITS    — Lương thưởng, bảo hiểm sức khỏe, hưu trí, phụ cấp, đãi ngộ
  CONDUCT     — Quy tắc ứng xử, đạo đức, quy trình kỷ luật, trang phục
  PROCEDURES  — Quy trình từng bước, phê duyệt, onboarding, đề xuất
  HANDBOOK    — Tổng quan công ty, văn hóa, sứ mệnh, thông tin chung nhân viên
  MEDICAL     — Chính sách y tế, bảo hiểm sức khỏe, danh sách bệnh viện, quy trình khám chữa bệnh
  IT_SECURITY — Chính sách CNTT, bảo mật thông tin, sử dụng thiết bị, mật khẩu, quyền truy cập
  COMPLIANCE  — Tuân thủ pháp luật, quy định lao động, bảo vệ dữ liệu, phòng chống tham nhũng
  FINANCE     — Chính sách tài chính, hạn mức chi phí, hoàn ứng, phê duyệt ngân sách
  TRAINING    — Đào tạo, phát triển nhân sự, lộ trình sự nghiệp, học bổng, chứng chỉ

Câu hỏi: "{question}"

Quy tắc:
- Trả về 1 đến 3 lĩnh vực theo thứ tự ưu tiên (liên quan nhất trước)
- Chỉ dùng đúng các tên lĩnh vực như liệt kê trên

Chỉ trả về JSON: {{"domains": ["HR_POLICY"]}}
"""

_SYNTHESIZE_PROMPT = """\
Bạn đang tổng hợp câu trả lời từ nhiều chuyên gia tư vấn chính sách công ty để trả lời một câu hỏi của nhân viên.

Câu hỏi của nhân viên: {question}

Câu trả lời từ các chuyên gia:
{answers_block}

Hướng dẫn:
- Kết hợp các câu trả lời thành một câu trả lời mạch lạc bằng tiếng Việt
- Giữ nguyên tất cả trích dẫn trang (ví dụ: "Trang 4 của benefits_guide.pdf")
- Nếu các chuyên gia có câu trả lời mâu thuẫn nhau, hãy ghi chú rõ
- Ngắn gọn, chính xác và thực tế

Câu trả lời tổng hợp:
"""

ALL_DOMAINS = [
    "HR_POLICY", "BENEFITS", "CONDUCT", "PROCEDURES", "HANDBOOK",
    "MEDICAL", "IT_SECURITY", "COMPLIANCE", "FINANCE", "TRAINING",
]


class OrchestratorResponse:
    def __init__(
        self,
        answer: str,
        domains_consulted: list[str],
        citations: list[Citation] | None = None,
        entities: list[str] | None = None,
        history: list[ChatTurn] | None = None,
    ) -> None:
        self.answer = answer
        self.domains_consulted = domains_consulted
        self.citations: list[Citation] = citations or []
        self.entities: list[str] = entities or []
        self.history: list[ChatTurn] = history or []


class OrchestratorAgent:
    def __init__(self, agents: dict[str, BaseAgent]) -> None:
        self._agents = agents
        self._client = genai.Client(api_key=settings.gemini_api_key)
        self._model = settings.gemini_llm_model

    # ------------------------------------------------------------------
    # Domain classification
    # ------------------------------------------------------------------

    async def classify_domains(self, question: str) -> list[str]:
        prompt = _DOMAIN_CLASSIFY_PROMPT.format(question=question)
        try:
            response = await self._client.aio.models.generate_content(
                model=self._model,
                contents=prompt,
                config=_JSON_CONFIG,
            )
            data = json.loads(response.text or "{}")
            domains = data.get("domains", [])
            # Validate — only accept known domain keys
            valid = [d for d in domains if d in ALL_DOMAINS]
            return valid if valid else ["HR_POLICY"]
        except Exception as exc:
            logger.warning("Domain classification failed (%s), defaulting to all domains", exc)
            return ALL_DOMAINS

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    async def process_message(
        self,
        message: str,
        history: list[dict],
        history_turns: int,
    ) -> OrchestratorResponse:
        # Trim history to requested turns
        trimmed_history = history[-history_turns * 2:] if history_turns else history

        domains = await self.classify_domains(message)
        ready_domains = [d for d in domains if d in self._agents and self._agents[d].is_ready()]

        logger.info(
            "Orchestrator: question=%r, classified=%s, ready=%s",
            message[:80],
            domains,
            ready_domains,
        )

        if not ready_domains:
            return OrchestratorResponse(
                answer=(
                    "No documents have been indexed yet for the relevant policy domains "
                    f"({', '.join(domains)}). Please upload policy documents first."
                ),
                domains_consulted=domains,
            )

        if len(ready_domains) == 1:
            domain = ready_domains[0]
            response = await self._agents[domain].answer(message, trimmed_history)
            return OrchestratorResponse(
                answer=response.answer,
                domains_consulted=[response.domain],
                citations=response.citations,
                entities=response.entities,
            )

        # Cross-domain: fan-out in parallel
        tasks = [
            self._agents[d].answer(message, trimmed_history) for d in ready_domains
        ]
        results: list[AgentResponse] = await asyncio.gather(*tasks)  # type: ignore[assignment]

        synthesized = await self._synthesize(message, results)
        all_citations = [c for r in results for c in r.citations]
        all_entities = [e for r in results for e in r.entities]
        return OrchestratorResponse(
            answer=synthesized,
            domains_consulted=[r.domain for r in results],
            citations=all_citations,
            entities=all_entities,
        )

    # ------------------------------------------------------------------
    # Synthesis
    # ------------------------------------------------------------------

    async def _synthesize(self, question: str, responses: list[AgentResponse]) -> str:
        answers_block = "\n\n".join(
            f"[{r.domain} specialist]:\n{r.answer}" for r in responses
        )
        prompt = _SYNTHESIZE_PROMPT.format(
            question=question,
            answers_block=answers_block[:8000],
        )
        try:
            response = await self._client.aio.models.generate_content(
                model=self._model,
                contents=prompt,
                config=types.GenerateContentConfig(temperature=0.2),
            )
            return (response.text or "").strip() or responses[0].answer
        except Exception as exc:
            logger.warning("Synthesis failed (%s), using first agent answer", exc)
            return responses[0].answer

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def agent_health_map(self) -> dict[str, AgentHealth]:
        return {domain: agent.health() for domain, agent in self._agents.items()}

    async def check_neo4j(self) -> bool:
        # Delegate to any LightRAG-backed agent (they all hit the same instance)
        for agent in self._agents.values():
            if agent.engine_type == "lightrag":
                from app.services.lightrag_service import LightRAGService

                svc: LightRAGService = agent._engine  # type: ignore[attr-defined]
                return await svc.check_neo4j()
        return True  # no LightRAG agents, nothing to check
