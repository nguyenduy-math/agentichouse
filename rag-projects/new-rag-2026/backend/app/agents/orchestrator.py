"""
OrchestratorAgent — classifies questions, routes to domain agents, synthesizes.

Flow:
  1. Rewrite query for standalone retrieval (Layer 1)
  2. Classify question → list of domain keys (LLM call)
  3. Determine search mode (LOCAL for single-domain, GLOBAL for cross-domain)
  4. Retrieve context from GraphRAG (with full 8-layer retrieval pipeline)
  5a. Single domain → direct DomainAgent call
  5b. Multi-domain → asyncio.gather fan-out → _synthesize()
  6. Two-level answer verification (Layers 1 + 2)

All major steps decorated with @traceable for LangSmith observability.
RunnableConfig is propagated through all LangChain calls.
"""
from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage
from langchain_core.runnables.config import RunnableConfig
from langsmith import traceable

from app.agents.base_agent import AgentResult, BaseDomainAgent
from app.domains import DOMAIN_MAP, DOMAINS
from app.prompts.orchestrator_prompts import (
    CLASSIFICATION_PROMPT,
    QUERY_REWRITE_PROMPT,
    SYNTHESIS_PROMPT,
)
from app.prompts.synthesis_prompts import build_graph_context
from app.services.graphrag_service import GraphRAGService, SearchMode
from app.services.neo4j_store import Neo4jStore
from app.services.rerank_service import RerankService
from app.services.verification_service import FALLBACK_ANSWER, VerificationService

logger = logging.getLogger(__name__)


def _step_config(base_config: RunnableConfig | None, call_type: str) -> RunnableConfig | None:
    """
    Return a shallow copy of base_config with call_type injected into metadata.

    SessionTokenCallback reads metadata["call_type"] in on_llm_start to
    associate each LLM call with the correct pipeline step.
    """
    if base_config is None:
        return None
    meta = dict(base_config.get("metadata") or {})
    meta["call_type"] = call_type
    return {**base_config, "metadata": meta}


@dataclass
class OrchestratorResult:
    final_answer: str
    domain_keys: list[str]
    agent_results: list[AgentResult] = field(default_factory=list)
    search_mode: str = "local"
    sources: list[dict] = field(default_factory=list)
    rewritten_query: str | None = None
    verification: dict[str, Any] | None = None


class OrchestratorAgent:
    """
    Routes questions to domain specialist agents and synthesizes multi-domain answers.

    Thread safety: all state is per-invocation (no shared mutable state).
    asyncio.Lock() is used in Neo4jStore and GraphRAGService, not here.
    """

    def __init__(
        self,
        llm: BaseChatModel,
        graphrag: GraphRAGService,
        neo4j_store: Neo4jStore,
        agents: dict[str, BaseDomainAgent],
        rerank_service: RerankService,
        verification_service: VerificationService,
        graph_hop_depth: int = 2,
        enable_rerank: bool = True,
        rerank_pool_size: int = 25,
        max_chunks: int = 8,
    ) -> None:
        self._llm = llm
        self._graphrag = graphrag
        self._neo4j = neo4j_store
        self._agents = agents
        self._rerank = rerank_service
        self._verifier = verification_service
        self._graph_hop_depth = graph_hop_depth
        self._enable_rerank = enable_rerank
        self._rerank_pool_size = rerank_pool_size
        self._max_chunks = max_chunks

    @traceable(name="orchestrator_run", run_type="chain")
    async def run(
        self,
        question: str,
        session_history: str = "",
        config: RunnableConfig | None = None,
    ) -> OrchestratorResult:
        """
        Main entry point. Full 8-layer retrieval pipeline + multi-agent routing.

        Args:
            question: User's original question (Vietnamese)
            session_history: Formatted conversation history for context
            config: LangChain RunnableConfig for LangSmith tracing propagation

        Returns:
            OrchestratorResult with final_answer, domain_keys, agent_results, sources
        """
        # Layer 1: Query rewriting
        rewritten = await self._rewrite_query(question, session_history, config)
        logger.info("Rewritten query: %s", rewritten)

        # Classify → domain keys
        domain_keys = await self._classify(question, session_history, config)
        logger.info("Classified domains: %s", domain_keys)

        # Determine search mode
        search_mode = SearchMode.GLOBAL if len(domain_keys) > 1 else SearchMode.LOCAL

        # GraphRAG primary retrieval
        graphrag_result = await self._graphrag.search(rewritten, search_mode)
        graphrag_reply = graphrag_result.get("reply", "")
        raw_sources = graphrag_result.get("sources", [])

        # Build context chunks from GraphRAG sources
        context_chunks = [
            s.get("text", s.get("summary", ""))
            for s in raw_sources
            if s.get("text") or s.get("summary")
        ]

        # Layers 2-7: Enhanced retrieval via Neo4j (if graphrag returned sources)
        final_chunks, final_sources, graph_context_str = await self._enhanced_retrieval(
            rewritten, context_chunks, raw_sources
        )

        # Layer 5 fallback: use GraphRAG reply as graph_context if Neo4j returns nothing
        if not graph_context_str and graphrag_reply:
            graph_context_str = graphrag_reply

        # Route to domain agent(s)
        if len(domain_keys) == 1:
            result = await self._single_domain_route(
                question=question,
                rewritten=rewritten,
                domain_key=domain_keys[0],
                context_chunks=final_chunks,
                graph_context=graph_context_str,
                search_mode=search_mode.value,
                sources=final_sources,
                config=config,
            )
            final_answer = result.answer
            agent_results = [result]
        else:
            agent_results, final_answer = await self._multi_domain_route(
                question=question,
                rewritten=rewritten,
                domain_keys=domain_keys,
                context_chunks=final_chunks,
                graph_context=graph_context_str,
                search_mode=search_mode.value,
                sources=final_sources,
                config=config,
            )

        # Level 2: Final verification
        combined_context = "\n\n".join(final_chunks[:5])
        final_verification = await self._verifier.verify(
            question=question,
            context=combined_context,
            answer=final_answer,
            domain="final_synthesis",
            config=_step_config(config, "verify_final"),
        )
        if self._verifier.should_fallback(final_verification):
            logger.warning("Final verification failed — using fallback answer.")
            final_answer = FALLBACK_ANSWER

        return OrchestratorResult(
            final_answer=final_answer,
            domain_keys=domain_keys,
            agent_results=agent_results,
            search_mode=search_mode.value,
            sources=final_sources,
            rewritten_query=rewritten if rewritten != question else None,
            verification=final_verification,
        )

    async def _rewrite_query(
        self,
        question: str,
        session_history: str,
        config: RunnableConfig | None,
    ) -> str:
        """Layer 1: Rewrite follow-up questions to standalone retrieval queries."""
        if not session_history or session_history.strip() == "(không có lịch sử)":
            return question  # First turn — no rewrite needed

        prompt = QUERY_REWRITE_PROMPT.format(
            history_text=session_history,
            question=question,
        )
        try:
            if config:
                response = await self._llm.ainvoke(
                    [HumanMessage(content=prompt)],
                    config=_step_config(config, "query_rewrite"),
                )
            else:
                response = await self._llm.ainvoke([HumanMessage(content=prompt)])
            rewritten = response.content.strip()
            return rewritten if rewritten else question
        except Exception as exc:
            logger.warning("Query rewrite failed: %s. Using original.", exc)
            return question

    @traceable(name="orchestrator_classify", run_type="chain")
    async def _classify(
        self,
        question: str,
        session_history: str,
        config: RunnableConfig | None,
    ) -> list[str]:
        """
        Call the LLM with the classification prompt.
        Returns a list of domain keys (subset of DOMAIN_MAP keys).
        Falls back to ["general"] on parse error.
        """
        domain_list = "\n".join(
            f"- {d.key}: {d.description_vi}" for d in DOMAINS
        )
        prompt = CLASSIFICATION_PROMPT.format(
            domain_list=domain_list,
            session_history=session_history or "(không có lịch sử)",
            question=question,
        )
        try:
            if config:
                response = await self._llm.ainvoke(
                    [HumanMessage(content=prompt)],
                    config=_step_config(config, "classify"),
                )
            else:
                response = await self._llm.ainvoke([HumanMessage(content=prompt)])
            raw = response.content.strip()

            # Try strict JSON parse
            keys = json.loads(raw)
            if isinstance(keys, list):
                valid = [k for k in keys if k in DOMAIN_MAP]
                return valid if valid else ["general"]
        except (json.JSONDecodeError, ValueError, Exception) as exc:
            logger.warning("Classification parse error: %s. Raw: %s", exc, raw if 'raw' in dir() else "")

        # Fallback: scan for domain keys in the raw response
        try:
            found = [k for k in DOMAIN_MAP if k in raw.lower()]
            return found if found else ["general"]
        except Exception:
            return ["general"]

    async def _enhanced_retrieval(
        self,
        rewritten_query: str,
        context_chunks: list[str],
        raw_sources: list[dict],
    ) -> tuple[list[str], list[dict], str]:
        """
        Layers 3-7: Type-aware entity seeding, reranking, graph traversal.

        Returns: (final_chunks, final_sources, graph_context_str)
        """
        if not self._neo4j.is_connected:
            return context_chunks[:self._max_chunks], raw_sources, ""

        try:
            # Layer 3: Collect seed entities from sources
            seed_pool: list[str] = []
            for src in raw_sources:
                names = src.get("entity_names", [])
                if isinstance(names, list):
                    seed_pool.extend(names)
            seed_pool = list(dict.fromkeys(seed_pool))[:20]  # dedup, cap at 20

            # Enrich candidates with entity-augmented chunks
            all_chunks = [{"text": c, "score": 0.5} for c in context_chunks]
            if seed_pool:
                specific_seeds = await self._neo4j.get_specific_entity_names(seed_pool)
                if specific_seeds:
                    entity_chunks = await self._neo4j.get_chunks_by_entity_names(
                        specific_seeds, k=5, min_entity_hits=1
                    )
                else:
                    entity_chunks = await self._neo4j.get_chunks_by_entity_names(
                        seed_pool, k=5, min_entity_hits=2
                    )
                # Merge without duplicates
                seen_texts = {c["text"] for c in all_chunks}
                for ec in entity_chunks:
                    if ec.get("text") and ec["text"] not in seen_texts:
                        all_chunks.append(ec)
                        seen_texts.add(ec["text"])

            # Layer 4: Cohere reranking (25 → max_chunks)
            if self._enable_rerank and self._rerank.is_available:
                reranked = await self._rerank.rerank(
                    query=rewritten_query,
                    documents=all_chunks,
                    text_key="text",
                )
                winning_chunks = reranked[: self._max_chunks]
            else:
                winning_chunks = all_chunks[: self._max_chunks]

            # Layer 5: Recompute seed entities from winning chunks only
            win_seed_names: list[str] = []
            for chunk in winning_chunks:
                names = chunk.get("entity_names", [])
                if isinstance(names, list):
                    win_seed_names.extend(names)
            win_seed_names = list(dict.fromkeys(win_seed_names))[:20]

            # Layer 6: 2-hop graph neighborhood traversal
            graph_context_str = ""
            if win_seed_names:
                neighborhood = await self._neo4j.get_entity_neighborhood(
                    entity_names=win_seed_names,
                    depth=self._graph_hop_depth,
                )
                triples = neighborhood.get("triples", [])

                # Layer 7: Seed-entity triple filtering
                # Only keep triples where BOTH endpoints are seed entities
                seed_set = set(win_seed_names)
                filtered_triples = [
                    t for t in triples
                    if t.get("source") in seed_set and t.get("target") in seed_set
                ]
                neighborhood["triples"] = filtered_triples

                graph_context_str = build_graph_context(neighborhood)

            final_texts = [c.get("text", "") for c in winning_chunks if c.get("text")]
            return final_texts, raw_sources, graph_context_str

        except Exception as exc:
            logger.warning("Enhanced retrieval failed: %s. Using raw sources.", exc)
            return context_chunks[:self._max_chunks], raw_sources, ""

    async def _single_domain_route(
        self,
        question: str,
        rewritten: str,
        domain_key: str,
        context_chunks: list[str],
        graph_context: str,
        search_mode: str,
        sources: list[dict],
        config: RunnableConfig | None,
    ) -> AgentResult:
        """Route to a single domain agent and apply Level 1 verification."""
        agent = self._agents.get(domain_key) or self._agents.get("general")
        if agent is None:
            logger.error("No agent found for domain '%s' and no general fallback.", domain_key)
            from app.agents.base_agent import AgentResult as AR
            return AR(domain_key=domain_key, answer=FALLBACK_ANSWER, search_mode=search_mode)

        result = await agent.answer(
            question=question,
            context_chunks=context_chunks,
            graph_context=graph_context,
            search_mode=search_mode,
            sources=sources,
            config=config,
        )

        # Level 1 verification
        context_str = "\n\n".join(context_chunks[:5])
        verification = await self._verifier.verify(
            question=question,
            context=context_str,
            answer=result.answer,
            domain=domain_key,
            config=_step_config(config, "verify_domain"),
        )
        if self._verifier.should_fallback(verification):
            logger.warning("Domain verification failed for '%s'.", domain_key)
            result.answer = FALLBACK_ANSWER

        return result

    async def _multi_domain_route(
        self,
        question: str,
        rewritten: str,
        domain_keys: list[str],
        context_chunks: list[str],
        graph_context: str,
        search_mode: str,
        sources: list[dict],
        config: RunnableConfig | None,
    ) -> tuple[list[AgentResult], str]:
        """Fan-out to multiple domain agents in parallel, then synthesize."""
        tasks = []
        for key in domain_keys:
            agent = self._agents.get(key) or self._agents.get("general")
            if agent:
                tasks.append(
                    agent.answer(
                        question=question,
                        context_chunks=context_chunks,
                        graph_context=graph_context,
                        search_mode=search_mode,
                        sources=sources,
                        config=config,
                    )
                )

        agent_results: list[AgentResult] = list(await asyncio.gather(*tasks))

        # Level 1 verification per domain agent
        context_str = "\n\n".join(context_chunks[:5])
        for result in agent_results:
            verification = await self._verifier.verify(
                question=question,
                context=context_str,
                answer=result.answer,
                domain=result.domain_key,
                config=_step_config(config, "verify_domain"),
            )
            if self._verifier.should_fallback(verification):
                logger.warning("Domain verification failed for '%s'.", result.domain_key)
                result.answer = FALLBACK_ANSWER

        final_answer = await self._synthesize(question, agent_results, config)
        return agent_results, final_answer

    @traceable(name="orchestrator_synthesize", run_type="chain")
    async def _synthesize(
        self,
        question: str,
        agent_results: list[AgentResult],
        config: RunnableConfig | None = None,
    ) -> str:
        """Merge multiple domain agent answers into one coherent Vietnamese response."""
        parts = []
        for r in agent_results:
            domain = DOMAIN_MAP.get(r.domain_key)
            name = domain.name_vi if domain else r.domain_key
            parts.append(f"## {name}\n{r.answer}")
        combined = "\n\n".join(parts)

        prompt = SYNTHESIS_PROMPT.format(
            question=question,
            combined_answers=combined,
        )
        try:
            if config:
                response = await self._llm.ainvoke(
                    [HumanMessage(content=prompt)],
                    config=_step_config(config, "synthesize"),
                )
            else:
                response = await self._llm.ainvoke([HumanMessage(content=prompt)])
            return response.content.strip()
        except Exception as exc:
            logger.error("Synthesis failed: %s", exc)
            # Fall back to concatenated answers
            return combined
