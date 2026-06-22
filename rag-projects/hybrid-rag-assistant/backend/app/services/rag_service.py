from app.agents.domain_agent import DomainAgent
from app.agents.orchestrator_agent import OrchestratorAgent
from app.schemas import ChatResponse
from app.services.llm_service import LLMService
from app.services.session_service import SessionService


class RAGService:
    """Thin façade: rewrite query → orchestrate domain agents → persist session."""

    def __init__(
        self,
        orchestrator: OrchestratorAgent,
        llm: LLMService,
        session: SessionService,
    ) -> None:
        self._orchestrator = orchestrator
        self._llm = llm
        self._session = session

    async def query(self, session_id: str, message: str) -> ChatResponse:
        history = self._session.get_history(session_id)

        rewritten = await self._llm.rewrite_query(history, message)
        reply, domains_used, sources, is_out_of_scope = await self._orchestrator.query(
            session_id=session_id,
            rewritten_query=rewritten,
            original_message=message,
            history=history,
        )

        self._session.append_message(session_id, "user", message)
        self._session.append_message(session_id, "assistant", reply)

        return ChatResponse(
            session_id=session_id,
            reply=reply,
            rewritten_query=rewritten,
            domains_used=domains_used,
            is_out_of_scope=is_out_of_scope,
            sources=sources,
        )
