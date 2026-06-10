"""
Two-level Vietnamese answer verification service.

Checks whether a generated answer is grounded in the retrieved context.
Falls back to FALLBACK_ANSWER when confidence < threshold or answer is not grounded.

Level 1: Domain agent verifies own answer before returning to orchestrator.
Level 2: Orchestrator verifies final synthesized answer.

Decorated with @traceable for LangSmith observability (Layer 8 of pipeline).
"""
from __future__ import annotations

import json
import logging
import os

from langchain_core.runnables.config import RunnableConfig
from langsmith import traceable
from langchain_core.messages import HumanMessage

logger = logging.getLogger(__name__)

FALLBACK_ANSWER = (
    "Xin lỗi, tôi không tìm thấy đủ thông tin trong tài liệu nội bộ để trả lời câu hỏi này một cách chính xác. "
    "Vui lòng liên hệ trực tiếp với bộ phận liên quan hoặc kiểm tra tài liệu chính sách mới nhất."
)

VERIFICATION_PROMPT = """\
Câu hỏi: {question}

Ngữ cảnh được sử dụng để tạo câu trả lời:
{context}

Câu trả lời được tạo ra:
{answer}

Hãy đánh giá câu trả lời theo hai tiêu chí:
1. is_grounded: Mọi thông tin trong câu trả lời có được hỗ trợ trực tiếp bởi ngữ cảnh không? (true/false)
2. confidence: Mức độ tin cậy từ 1 đến 5, trong đó:
   1 = Câu trả lời phần lớn không có căn cứ
   3 = Câu trả lời một phần có căn cứ nhưng có các điểm không chắc chắn
   5 = Câu trả lời hoàn toàn có căn cứ và rõ ràng

Trả về JSON: {{"is_grounded": bool, "confidence": int, "issues": ["..."]}}"""


class VerificationService:
    """
    Vietnamese grounding check service.

    Uses the configured LLM to verify that generated answers are
    supported by the retrieved context.
    """

    def __init__(self, llm) -> None:
        self._llm = llm
        self._confidence_threshold = int(
            os.environ.get("VERIFICATION_CONFIDENCE_THRESHOLD", "3")
        )
        self._enabled = os.environ.get("ENABLE_ANSWER_VERIFICATION", "true").lower() == "true"

    @traceable(
        name="answer_verification",
        run_type="llm",
        metadata={"type": "grounding_check"},
    )
    async def verify(
        self,
        question: str,
        context: str,
        answer: str,
        domain: str | None = None,
        config: RunnableConfig | None = None,
    ) -> dict:
        """
        Verify that the answer is grounded in the context.

        Args:
            question: The original user question
            context: Retrieved context used to generate the answer
            answer: The generated answer to verify
            domain: Domain label for tracing
            config: LangChain RunnableConfig for callback propagation

        Returns:
            dict with keys: is_grounded (bool), confidence (int 1-5), issues (list[str])
        """
        if not self._enabled:
            return {"is_grounded": True, "confidence": 5, "issues": []}

        prompt = VERIFICATION_PROMPT.format(
            question=question,
            context=context[:4000],
            answer=answer,
        )

        try:
            if config is not None:
                response = await self._llm.ainvoke(
                    [HumanMessage(content=prompt)], config=config
                )
            else:
                response = await self._llm.ainvoke([HumanMessage(content=prompt)])
            content = response.content

            if "```" in content:
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]

            data = json.loads(content.strip())
            return {
                "is_grounded": bool(data.get("is_grounded", True)),
                "confidence": max(1, min(5, int(data.get("confidence", 3)))),
                "issues": data.get("issues", []),
            }
        except Exception as exc:
            logger.warning("Verification failed: %s. Assuming grounded.", exc)
            return {"is_grounded": True, "confidence": 5, "issues": []}

    def should_fallback(self, verification: dict) -> bool:
        """
        Return True if the answer should be replaced with FALLBACK_ANSWER.

        Triggers fallback when:
          - is_grounded is False, OR
          - confidence < threshold (default: 3)
        """
        return (
            not verification.get("is_grounded", True)
            or verification.get("confidence", 5) < self._confidence_threshold
        )
