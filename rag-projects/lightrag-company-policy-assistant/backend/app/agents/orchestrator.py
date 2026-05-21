"""OrchestratorAgent — routes employee questions to domain specialist agents.

Flow:
  1. classify_domains()  — LLM classifies question (+ recent history) into domain keys
  2. single domain       — direct route, no synthesis needed
  3. cross-domain        — asyncio.gather fan-out → _synthesize() merges answers

Classification uses a Gemini response_schema (DomainClassification) so the model can
only emit valid domain keys — no manual validate-and-default dance (audit ref: B2).
Prompts live in app.prompts; the domain set comes from app.domains.
"""

from __future__ import annotations

import asyncio
import json
import logging

from google import genai
from google.genai import types

from app import prompts
from app.agents.base_agent import AgentResponse, BaseAgent
from app.config import settings
from app.context_budget import estimate_tokens, fit_sections, log_prompt_size
from app.domains import is_valid_domain
from app.schemas import AgentHealth, ChatTurn, Citation, DomainClassification

logger = logging.getLogger(__name__)

# Safe fallback when classification fails: a small, broadly-useful set rather than
# fanning out to all 10 agents (which spikes cost/latency exactly when failing).
# Audit ref: A5.
_FALLBACK_DOMAINS = ["HR_POLICY", "HANDBOOK"]

_CLASSIFY_CONFIG = types.GenerateContentConfig(
    response_mime_type="application/json",
    response_schema=DomainClassification,
    temperature=0.0,
)


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


def _trim_history(history: list[dict], turns: int) -> list[dict]:
    """Keep the last ``turns`` user/assistant exchanges.

    Counts from the Nth-last *user* message rather than assuming strict
    user/assistant alternation, so a malformed history can't skew the window.
    Audit ref: D4.
    """
    if not turns or not history:
        return history if not turns else []
    user_seen = 0
    start = 0
    for i in range(len(history) - 1, -1, -1):
        if history[i].get("role") != "assistant":
            user_seen += 1
            if user_seen == turns:
                start = i
                break
    return history[start:]


class OrchestratorAgent:
    def __init__(self, agents: dict[str, BaseAgent]) -> None:
        self._agents = agents
        self._client = genai.Client(api_key=settings.gemini_api_key)
        self._model = settings.gemini_llm_model

    # ------------------------------------------------------------------
    # Domain classification
    # ------------------------------------------------------------------

    async def classify_domains(self, question: str, history: list[dict] | None = None) -> list[str]:
        history_block = prompts.format_history(history, settings.classify_history_turns)
        prompt = prompts.build_classification_prompt(question, history_block)
        log_prompt_size("classify", prompt)
        try:
            response = await self._client.aio.models.generate_content(
                model=self._model,
                contents=prompt,
                config=_CLASSIFY_CONFIG,
            )
            data = json.loads(response.text or "{}")
            domains = data.get("domains", [])
            # Schema already constrains values, but validate defensively.
            valid = [d for d in domains if is_valid_domain(d)]
            return valid  # may be empty — caller handles "no domain matched"
        except Exception as exc:
            logger.warning(
                "Domain classification failed (%s), using safe fallback %s",
                exc, _FALLBACK_DOMAINS,
            )
            return list(_FALLBACK_DOMAINS)

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    async def process_message(
        self,
        message: str,
        history: list[dict],
        history_turns: int,
    ) -> OrchestratorResponse:
        trimmed_history = _trim_history(history, history_turns)

        domains = await self.classify_domains(message, trimmed_history)

        # No policy domain matched (greeting, thanks, off-topic).
        if not domains:
            return OrchestratorResponse(
                answer=prompts.NO_POLICY_DOMAIN_RESPONSE,
                domains_consulted=[],
            )

        ready_domains = [d for d in domains if d in self._agents and self._agents[d].is_ready()]

        logger.info(
            "Orchestrator: question=%r, classified=%s, ready=%s",
            message[:80], domains, ready_domains,
        )

        if not ready_domains:
            return OrchestratorResponse(
                answer=prompts.no_documents_response(domains),
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
        tasks = [self._agents[d].answer(message, trimmed_history) for d in ready_domains]
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
        # Rank by answer length as a cheap relevance proxy, cap the number of
        # contributing answers, then fit them to the token budget by dropping whole
        # answers rather than slicing one mid-citation. Audit refs: C1, C3.
        ranked = sorted(responses, key=lambda r: estimate_tokens(r.answer), reverse=True)
        capped = ranked[: settings.max_docs_per_synthesis]
        sections = [f"[Chuyên gia {r.domain}]:\n{r.answer}" for r in capped]
        answers_block = fit_sections(
            sections, settings.synthesis_input_budget_tokens, label="specialist answers"
        )
        prompt = prompts.build_synthesis_prompt(question, answers_block)
        log_prompt_size("synthesize", prompt)
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

    def agent_items(self) -> list[tuple[str, BaseAgent]]:
        return list(self._agents.items())

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
