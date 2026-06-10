"""
Abstract base class for all domain specialist agents.

Each concrete agent defines:
  - domain_key: str -- matches a key in DOMAIN_MAP
  - _system_prompt: str -- Vietnamese system prompt for this domain

Agents use LangChain's ChatPromptTemplate | BaseChatModel chain with .ainvoke().
RunnableConfig is propagated from the chat router through all nested LangChain calls.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables.config import RunnableConfig

logger = logging.getLogger(__name__)


def _step_config(base_config: RunnableConfig | None, call_type: str) -> RunnableConfig | None:
    """Return a copy of base_config with call_type injected into metadata."""
    if base_config is None:
        return None
    meta = dict(base_config.get("metadata") or {})
    meta["call_type"] = call_type
    return {**base_config, "metadata": meta}


@dataclass
class AgentResult:
    domain_key: str
    answer: str
    search_mode: str        # "local" | "global"
    sources: list[dict] = field(default_factory=list)


class BaseDomainAgent(ABC):
    """
    Abstract base for all domain specialist agents.

    Subclasses must set class attributes:
      domain_key (str): e.g., "hr"
      _system_prompt (str): Vietnamese system prompt

    All LLM calls use .ainvoke() and propagate RunnableConfig.
    """

    domain_key: str
    _system_prompt: str

    def __init__(self, llm: BaseChatModel) -> None:
        self._llm = llm
        self._prompt = ChatPromptTemplate.from_messages([
            ("system", self._system_prompt),
            ("human", "{user_message}"),
        ])
        self._chain = self._prompt | self._llm

    @abstractmethod
    def _build_user_message(
        self,
        question: str,
        context_chunks: list[str],
        graph_context: str,
    ) -> str:
        """Build the user message for the LLM from retrieved context."""
        ...

    async def answer(
        self,
        question: str,
        context_chunks: list[str],
        graph_context: str,
        search_mode: str = "local",
        sources: list[dict] | None = None,
        config: RunnableConfig | None = None,
    ) -> AgentResult:
        """
        Generate a Vietnamese answer using the provided context.

        Args:
            question: The user's question (Vietnamese)
            context_chunks: Text excerpts from GraphRAG retrieval
            graph_context: Community summaries or graph traversal results
            search_mode: "local" or "global"
            sources: Source references from GraphRAG
            config: LangChain RunnableConfig for tracing propagation

        Returns:
            AgentResult with domain_key, answer, search_mode, sources
        """
        user_message = self._build_user_message(question, context_chunks, graph_context)

        invoke_kwargs: dict[str, Any] = {"user_message": user_message}
        step_cfg = _step_config(config, f"domain_answer_{self.domain_key}")

        try:
            if step_cfg is not None:
                response = await self._chain.ainvoke(invoke_kwargs, config=step_cfg)
            else:
                response = await self._chain.ainvoke(invoke_kwargs)

            answer_text = response.content.strip()
        except Exception as exc:
            logger.error("[%s] LLM call failed: %s", self.domain_key, exc)
            answer_text = (
                "Xin l\u1ed7i, \u0111\u00e3 x\u1ea3y ra l\u1ed7i khi x\u1eed l\u00fd c\u00e2u h\u1ecfi c\u1ee7a b\u1ea1n. "
                "Vui l\u00f2ng th\u1eed l\u1ea1i ho\u1eb7c li\u00ean h\u1ec7 b\u1ed9 ph\u1eadn h\u1ed7 tr\u1ee3."
            )

        return AgentResult(
            domain_key=self.domain_key,
            answer=answer_text,
            search_mode=search_mode,
            sources=sources or [],
        )
