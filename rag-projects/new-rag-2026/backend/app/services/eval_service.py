"""
RAGAS evaluation service.

POST /eval/run → returns run_id immediately (202 Accepted).
Scoring runs as an asyncio background task so the HTTP response is never blocked.
"""
from __future__ import annotations

import asyncio
import uuid

import structlog

from app.services.history_store import HistoryStore

logger = structlog.get_logger()

METRIC_NAMES = [
    "faithfulness",
    "answer_relevancy",
    "context_precision",
    "context_recall",
    "answer_correctness",
]


class EvalService:
    def __init__(self, history_store: HistoryStore) -> None:
        self._store = history_store
        self._running: set[str] = set()

    async def start_run(
        self,
        turn_ids: list[str],
        judge_provider: str,
        judge_model: str,
        reference_answers: dict[str, str],
    ) -> str:
        """Persist run metadata and kick off background scoring. Returns run_id."""
        run_id = str(uuid.uuid4())
        await self._store.save_eval_run(run_id, len(turn_ids), judge_provider, judge_model)
        asyncio.create_task(
            self._run_scoring(run_id, turn_ids, judge_provider, judge_model, reference_answers)
        )
        return run_id

    async def _run_scoring(
        self,
        run_id: str,
        turn_ids: list[str],
        judge_provider: str,
        judge_model: str,
        reference_answers: dict[str, str],
    ) -> None:
        self._running.add(run_id)
        await self._store.update_run_status(run_id, "running")
        try:
            turns = await self._store.get_turns_by_ids(turn_ids)
            if not turns:
                await self._store.update_run_status(run_id, "failed", "No turns found")
                return

            # Import heavy deps inside task to avoid startup delay
            from ragas import EvaluationDataset, RunConfig, SingleTurnSample, evaluate
            from ragas.metrics import (
                answer_correctness,
                answer_relevancy,
                context_precision,
                context_recall,
                faithfulness,
            )
            from ragas.llms import LangchainLLMWrapper
            from ragas.embeddings import LangchainEmbeddingsWrapper
            from langchain_openai import OpenAIEmbeddings
            import os

            from app.services.llm_service import create_chat_model

            metrics = [
                faithfulness,
                answer_relevancy,
                context_precision,
                context_recall,
                answer_correctness,
            ]

            # Build RAGAS dataset
            samples = []
            for t in turns:
                contexts = [s.get("text", "") for s in t["sources"] if s.get("text")]
                reference = reference_answers.get(t["turn_id"], "")
                samples.append(
                    SingleTurnSample(
                        user_input=t["question"],
                        response=t["answer"],
                        retrieved_contexts=contexts if contexts else [""],
                        reference=reference,
                    )
                )
            dataset = EvaluationDataset(samples=samples)

            # Build judge
            llm_model = create_chat_model(judge_provider)
            embed_model = OpenAIEmbeddings(
                model="text-embedding-3-small",
                api_key=os.environ.get("OPENAI_API_KEY", ""),
            )
            ragas_llm = LangchainLLMWrapper(llm_model)
            ragas_emb = LangchainEmbeddingsWrapper(embed_model)

            run_config = RunConfig(max_retries=3, max_wait=60, timeout=120)

            # Run evaluation in thread pool to avoid blocking the event loop
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: evaluate(
                    dataset=dataset,
                    metrics=metrics,
                    llm=ragas_llm,
                    embeddings=ragas_emb,
                    run_config=run_config,
                ),
            )
            df = result.to_pandas()

            # Persist scores
            scores = []
            for i, t in enumerate(turns):
                row = df.iloc[i] if i < len(df) else {}
                scores.append(
                    {
                        "turn_id": t["turn_id"],
                        "faithfulness": _safe_float(row.get("faithfulness")),
                        "answer_relevancy": _safe_float(row.get("answer_relevancy")),
                        "context_precision": _safe_float(row.get("context_precision")),
                        "context_recall": _safe_float(row.get("context_recall")),
                        "answer_correctness": _safe_float(row.get("answer_correctness")),
                        "reference_answer": reference_answers.get(t["turn_id"], ""),
                    }
                )
            await self._store.save_scores(run_id, scores)
            await self._store.update_run_status(run_id, "done")
            logger.info("eval_run_done", run_id=run_id, turns=len(turns))

        except Exception as exc:
            logger.error("eval_run_failed", run_id=run_id, error=str(exc))
            await self._store.update_run_status(run_id, "failed", str(exc))
        finally:
            self._running.discard(run_id)

    def is_running(self, run_id: str) -> bool:
        return run_id in self._running


def _safe_float(val) -> float | None:
    try:
        f = float(val)
        import math
        return None if math.isnan(f) else f
    except (TypeError, ValueError):
        return None
