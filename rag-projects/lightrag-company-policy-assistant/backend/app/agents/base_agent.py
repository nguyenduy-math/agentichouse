"""BaseAgent ABC — common interface for all domain specialist agents."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from app.schemas import AgentHealth, Citation, EngineType


class AgentResponse:
    def __init__(
        self,
        domain: str,
        answer: str,
        citations: list[Citation] | None = None,
        entities: list[str] | None = None,
    ) -> None:
        self.domain = domain
        self.answer = answer
        self.citations: list[Citation] = citations or []
        self.entities: list[str] = entities or []


class BaseAgent(ABC):
    """Each domain agent owns a retrieval engine and a domain-tuned system prompt."""

    domain: str
    engine_type: EngineType
    system_prompt: str

    @abstractmethod
    async def initialize(self) -> None:
        """Start up the underlying retrieval engine."""

    @abstractmethod
    async def shutdown(self) -> None:
        """Finalize and clean up the retrieval engine."""

    @abstractmethod
    async def answer(self, question: str, history: list[dict]) -> AgentResponse:
        """Answer a question using this agent's retrieval engine."""

    @abstractmethod
    async def index_document(self, file_path: Path) -> None:
        """Index a single document into this agent's knowledge base."""

    @abstractmethod
    def is_ready(self) -> bool:
        """Return True if at least one document has been indexed."""

    @abstractmethod
    def indexed_count(self) -> int:
        """Return the number of indexed documents."""

    def reset_doc_count(self) -> None:
        """Reset the indexed-document counter. Override in agents that track it."""

    def health(self) -> AgentHealth:
        return AgentHealth(
            ready=self.is_ready(),
            engine_type=self.engine_type,
            indexed_docs=self.indexed_count(),
        )
