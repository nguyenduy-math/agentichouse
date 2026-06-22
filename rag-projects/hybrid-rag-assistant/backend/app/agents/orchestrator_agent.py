"""OrchestratorAgent — classifies query, routes to domain agents, synthesizes."""

import asyncio
import re
import structlog
from google import genai
from google.genai import types

from app.config import settings
from app.domains import DOMAINS, DOMAIN_KEYS
from app.prompts.chat_prompts import (
    CLASSIFY_PROMPT,
    REFUSAL_MESSAGE,
    SYNTHESIS_PROMPT,
    build_system_instruction,
)
from app.agents.domain_agent import DomainAgent
from app.schemas import ChunkSource, ChatResponse

log = structlog.get_logger()

_SENT_SPLIT = re.compile(r'(?<=[.!?\n])\s+')


def _best_excerpt(text: str, query: str, max_len: int = 400) -> str:
    """Return the sentence window from text most relevant to the query keywords."""
    keywords = {w for w in query.lower().split() if len(w) > 2}
    sentences = [s.strip() for s in _SENT_SPLIT.split(text) if s.strip()]
    if not sentences:
        return text[:max_len]

    scored = sorted(
        enumerate(sentences),
        key=lambda t: len(keywords & set(t[1].lower().split())),
        reverse=True,
    )
    best_idx = scored[0][0]

    # Expand outward from the best sentence until max_len is reached
    result = sentences[best_idx]
    lo, hi = best_idx - 1, best_idx + 1
    while len(result) < max_len:
        added = False
        if lo >= 0:
            candidate = sentences[lo] + " " + result
            if len(candidate) <= max_len:
                result, lo, added = candidate, lo - 1, True
        if hi < len(sentences):
            candidate = result + " " + sentences[hi]
            if len(candidate) <= max_len:
                result, hi, added = candidate, hi + 1, True
        if not added:
            break
    return result


class OrchestratorAgent:
    def __init__(
        self,
        agents: dict[str, DomainAgent],
        llm_client: genai.Client,
    ) -> None:
        self._agents = agents
        self._client = llm_client
        self._model = settings.gemini_model

    async def _classify(self, question: str) -> list[str]:
        domain_list = "\n".join(f"- {k}: {v}" for k, v in DOMAINS.items())
        prompt = CLASSIFY_PROMPT.format(domain_list=domain_list, question=question)
        resp = await self._client.aio.models.generate_content(
            model=self._model,
            contents=prompt,
            config=types.GenerateContentConfig(temperature=0.0),
        )
        raw = resp.text.strip().lower()
        keys = [k.strip() for k in raw.split(",") if k.strip() in DOMAIN_KEYS]
        if not keys:
            keys = ["general"]
        log.info("orchestrator.classify", question=question[:80], domains=keys)
        return keys

    async def _answer_domain(
        self, domain_key: str, question: str, history: list[dict]
    ) -> dict:
        agent = self._agents[domain_key]
        ranked = await agent.retrieve(question)

        # No in-scope chunks — skip LLM call; orchestrator will filter this domain out
        if not ranked:
            return {"domain_key": domain_key, "domain_label": DOMAINS[domain_key], "answer": "", "ranked": []}

        system_instruction = agent.build_context(ranked)

        contents: list[types.Content] = []
        for msg in history:
            role = "user" if msg["role"] == "user" else "model"
            contents.append(types.Content(role=role, parts=[types.Part(text=msg["content"])]))
        contents.append(types.Content(role="user", parts=[types.Part(text=question)]))

        resp = await self._client.aio.models.generate_content(
            model=self._model,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.0,
            ),
        )
        return {
            "domain_key": domain_key,
            "domain_label": DOMAINS[domain_key],
            "answer": resp.text.strip(),
            "ranked": ranked,
        }

    async def _synthesize(
        self, domain_results: list[dict], question: str, history: list[dict]
    ) -> str:
        domain_answers = "\n\n".join(
            f"### {r['domain_label']}\n{r['answer']}" for r in domain_results
        )
        prompt = SYNTHESIS_PROMPT.format(domain_answers=domain_answers, question=question)

        contents: list[types.Content] = []
        for msg in history:
            role = "user" if msg["role"] == "user" else "model"
            contents.append(types.Content(role=role, parts=[types.Part(text=msg["content"])]))
        contents.append(types.Content(role="user", parts=[types.Part(text=prompt)]))

        resp = await self._client.aio.models.generate_content(
            model=self._model,
            contents=contents,
            config=types.GenerateContentConfig(temperature=0.0),
        )
        return resp.text.strip()

    async def query(
        self,
        session_id: str,
        rewritten_query: str,
        original_message: str,
        history: list[dict],
    ) -> tuple[str, list[str], list[ChunkSource], bool]:
        """Returns (reply, domains_used, sources, is_out_of_scope)."""
        domain_keys = await self._classify(rewritten_query)

        # Fan-out: query each domain agent in parallel
        tasks = [
            self._answer_domain(dk, rewritten_query, history)
            for dk in domain_keys
            if dk in self._agents
        ]
        domain_results: list[dict] = await asyncio.gather(*tasks)

        # Drop domains that returned no in-scope chunks
        domain_results = [dr for dr in domain_results if dr["ranked"]]

        # If no domain has relevant content, refuse politely without calling LLM
        if not domain_results:
            log.info("orchestrator.out_of_scope", query=rewritten_query[:80])
            return REFUSAL_MESSAGE, [], [], True

        if len(domain_results) == 1:
            reply = domain_results[0]["answer"]
        else:
            reply = await self._synthesize(domain_results, original_message, history)

        # Collect all sources across domains
        sources: list[ChunkSource] = []
        for dr in domain_results:
            for c in dr["ranked"]:
                sources.append(
                    ChunkSource(
                        chunk_id=c["chunk_id"],
                        source_file=c["metadata"].get("source_file", ""),
                        page_number=c["metadata"].get("page_number", 0),
                        chunk_index=c["metadata"].get("chunk_index", 0),
                        excerpt=_best_excerpt(c["text"], rewritten_query),
                        rerank_score=c.get("rerank_score", 0.0),
                        domain=c["metadata"].get("domain", dr["domain_key"]),
                    )
                )

        domains_used = [dr["domain_key"] for dr in domain_results]
        return reply, domains_used, sources, False
