"""
RAGAS evaluation for new-rag-2026 — single-turn.

Supports three judge providers: openai, gemini, siliconflow.
Embeddings always use OpenAI (Gemini/SiliconFlow embeddings are not RAGAS-compatible).

Prerequisites:
  - new-rag-2026 backend running (default: http://localhost:8000)
  - eval/.env with at minimum OPENAI_API_KEY (for embeddings) and the
    chosen judge provider's key

Usage:
  pip install -r requirements.txt
  cp .env.example .env              # fill in API keys
  python eval_single.py                                     # OpenAI judge (default)
  python eval_single.py --judge-provider gemini             # Gemini judge
  python eval_single.py --judge-provider siliconflow        # SiliconFlow judge
  python eval_single.py --dry-run                           # collect responses, skip RAGAS
  python eval_single.py --judge-model gpt-4o                # override model
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

import httpx
import pandas as pd
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from ragas import EvaluationDataset, RunConfig, SingleTurnSample, evaluate
from ragas.embeddings import LangchainEmbeddingsWrapper
from ragas.llms import LangchainLLMWrapper
from ragas.metrics import (
    answer_correctness,
    answer_relevancy,
    context_precision,
    context_recall,
    faithfulness,
)

logging.basicConfig(
    level=logging.WARNING,
    format="%(levelname)s [%(name)s] %(message)s",
)
logging.getLogger("ragas").setLevel(logging.WARNING)

load_dotenv()

NEW_RAG_API_URL = os.getenv("NEW_RAG_API_URL", "http://localhost:8000")
SESSION_ENDPOINT = f"{NEW_RAG_API_URL}/api/v1/session"
CHAT_ENDPOINT = f"{NEW_RAG_API_URL}/api/v1/chat"

QUESTIONS_FILE = Path(__file__).parent / "eval_sets/eval_questions.json"
RESULTS_DIR = Path(__file__).parent / "results"

METRICS = [
    faithfulness,
    answer_relevancy,
    context_precision,
    context_recall,
    answer_correctness,
]

DEFAULT_MODEL: dict[str, str] = {
    "openai": "gpt-4o-mini",
    "gemini": "gemini-2.0-flash",
    "siliconflow": "deepseek-ai/DeepSeek-V3",
}

SKIP_COLS = {"user_input", "response", "retrieved_contexts", "reference"}


def build_judge(
    provider: str, model: str
) -> tuple[LangchainLLMWrapper, LangchainEmbeddingsWrapper]:
    """
    Build RAGAS judge LLM + embeddings wrapper for the given provider.
    Embeddings always use OpenAI text-embedding-3-small regardless of provider,
    because Gemini and SiliconFlow embedding APIs are not compatible with RAGAS.
    """
    openai_api_key = os.environ.get("OPENAI_API_KEY", "")

    if provider == "openai":
        llm = LangchainLLMWrapper(
            ChatOpenAI(model=model, api_key=openai_api_key, temperature=0)
        )
        embeddings = LangchainEmbeddingsWrapper(
            OpenAIEmbeddings(model="text-embedding-3-small", api_key=openai_api_key)
        )
    elif provider == "gemini":
        gemini_api_key = os.environ.get("GEMINI_API_KEY", "")
        if not gemini_api_key:
            print("ERROR: GEMINI_API_KEY not set in .env")
            sys.exit(1)
        llm = LangchainLLMWrapper(
            ChatOpenAI(
                model=model,
                api_key=gemini_api_key,
                base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
                temperature=0,
            )
        )
        # Gemini embeddings not compatible with RAGAS — fall back to OpenAI
        embeddings = LangchainEmbeddingsWrapper(
            OpenAIEmbeddings(model="text-embedding-3-small", api_key=openai_api_key)
        )
    elif provider == "siliconflow":
        sf_api_key = os.environ.get("SILICONFLOW_API_KEY", "")
        if not sf_api_key:
            print("ERROR: SILICONFLOW_API_KEY not set in .env")
            sys.exit(1)
        llm = LangchainLLMWrapper(
            ChatOpenAI(
                model=model,
                api_key=sf_api_key,
                base_url="https://api.siliconflow.cn/v1",
                temperature=0,
            )
        )
        embeddings = LangchainEmbeddingsWrapper(
            OpenAIEmbeddings(model="text-embedding-3-small", api_key=openai_api_key)
        )
    else:
        raise ValueError(
            f"Unknown judge provider: {provider!r}. Choose: openai, gemini, siliconflow"
        )

    return llm, embeddings


async def query_new_rag(
    client: httpx.AsyncClient, question: str
) -> tuple[str, list[str], list[str], int, str]:
    """
    POST /session → POST /chat.
    Returns (answer, contexts, domain_keys, agent_count, query_type).
    """
    session_resp = await client.post(SESSION_ENDPOINT, timeout=10.0)
    session_resp.raise_for_status()
    session_id = session_resp.json()["session_id"]

    payload = {"session_id": session_id, "message": question, "mode": "auto"}
    response = await client.post(CHAT_ENDPOINT, json=payload, timeout=60.0)
    response.raise_for_status()
    data = response.json()

    answer = data.get("reply", "")
    contexts = [s["text"] for s in data.get("sources", []) if s.get("text")]
    domain_keys = data.get("domain_keys", [])
    agent_count = data.get("agent_count", 1)
    query_type = data.get("query_type", "")
    return answer, contexts, domain_keys, agent_count, query_type


async def collect_responses(
    questions: list[dict],
) -> list[tuple[dict, str, list[str], list[str], int, str]]:
    results: list[tuple[dict, str, list[str], list[str], int, str]] = []

    async with httpx.AsyncClient() as client:
        try:
            health = await client.get(f"{NEW_RAG_API_URL}/health", timeout=5.0)
            health.raise_for_status()
        except Exception as exc:
            print(f"ERROR: Cannot reach new-rag-2026 at {NEW_RAG_API_URL}: {exc}")
            print("Start the backend first: uvicorn app.main:app --port 8000 --reload")
            sys.exit(1)

        for i, q in enumerate(questions, 1):
            print(f"  [{i}/{len(questions)}] {q['id']}: {q['question'][:60]}...")
            try:
                answer, contexts, domain_keys, agent_count, query_type = (
                    await query_new_rag(client, q["question"])
                )
                print(
                    f"    domains={domain_keys}, agents={agent_count}, "
                    f"type={query_type}, chunks={len(contexts)}"
                )
                results.append((q, answer, contexts, domain_keys, agent_count, query_type))
            except Exception as exc:
                print(f"    WARNING: failed ({exc}), skipping")

    return results


def build_dataset(
    results: list[tuple[dict, str, list[str], list[str], int, str]],
) -> EvaluationDataset:
    samples = [
        SingleTurnSample(
            user_input=q["question"],
            response=answer,
            retrieved_contexts=contexts if contexts else [""],
            reference=q["expected_answer_summary"],
        )
        for q, answer, contexts, domain_keys, agent_count, query_type in results
    ]
    return EvaluationDataset(samples=samples)


def run_ragas(
    dataset: EvaluationDataset,
    llm: LangchainLLMWrapper,
    embeddings: LangchainEmbeddingsWrapper,
) -> pd.DataFrame:
    run_config = RunConfig(max_retries=3, max_wait=60, timeout=120)
    result = evaluate(
        dataset=dataset,
        metrics=METRICS,
        llm=llm,
        embeddings=embeddings,
        run_config=run_config,
    )
    return result.to_pandas()


def audit_failures(df: pd.DataFrame, metric_cols: list[str]) -> None:
    """Print a detailed report of any NaN metric cells (per-sample RAGAS failures)."""
    nan_mask = df[metric_cols].isna()
    if not nan_mask.any().any():
        return

    print("\n=== WARNING: Missing metric cells (RAGAS per-sample failures) ===")
    for metric in metric_cols:
        failed_idx = nan_mask.index[nan_mask[metric]].tolist()
        if not failed_idx:
            continue
        print(f"  {metric}: {len(failed_idx)}/{len(df)} failed (rows: {failed_idx})")
        for i in failed_idx:
            q = df.loc[i, "user_input"]
            preview = (q[:70] + "...") if len(q) > 70 else q
            print(f"      row {i}: {preview}")
    print(
        "Common causes: rate-limit after retries, judge JSON-parse error, "
        "context exceeds model window.\n"
    )


def save_and_print(
    results: list[tuple[dict, str, list[str], list[str], int, str]],
    ragas_df: pd.DataFrame | None,
    provider: str,
    model: str,
) -> None:
    RESULTS_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = RESULTS_DIR / f"eval_single_{timestamp}.csv"

    base_rows = []
    for q, answer, contexts, domain_keys, agent_count, query_type in results:
        base_rows.append(
            {
                "id": q.get("id", ""),
                "domain": q.get("domain", ""),
                "difficulty": q.get("difficulty", ""),
                "query_type": query_type or q.get("query_type", ""),
                "domain_keys": ",".join(domain_keys),
                "agent_count": agent_count,
                "user_input": q["question"],
                "response": answer,
                "retrieved_contexts": contexts,
                "reference": q["expected_answer_summary"],
            }
        )
    base = pd.DataFrame(base_rows)

    if ragas_df is not None:
        metric_cols = [c for c in ragas_df.columns if c not in SKIP_COLS]
        base = pd.concat(
            [base.reset_index(drop=True), ragas_df[metric_cols].reset_index(drop=True)],
            axis=1,
        )

    base.to_csv(out_path, index=False)
    print(f"\nResults saved to: {out_path}\n")

    if ragas_df is None:
        return

    metric_cols = [c for c in ragas_df.columns if c not in SKIP_COLS]

    print(f"=== RAGAS Evaluation Summary (new-rag-2026 / {provider}:{model}) ===")
    print(f"{'Metric':<28} {'Score':>8}  {'Coverage':>10}")
    print("-" * 52)
    for metric in metric_cols:
        score = base[metric].mean()
        n = int(base[metric].notna().sum())
        total = len(base)
        coverage = f"{n}/{total}"
        flag = "  (partial)" if n < total else ""
        print(f"{metric:<28} {score:>8.4f}  {coverage:>10}{flag}")
    print("=" * 52)

    audit_failures(base, metric_cols)

    # Per-domain breakdown when multiple domains appear in results
    if "domain" in base.columns and base["domain"].nunique() > 1:
        per_cols = [c for c in ["answer_correctness", "faithfulness"] if c in base.columns]
        if per_cols:
            print("\n=== Per-Domain Breakdown ===")
            header = f"{'domain':<20} {'n':>4}" + "".join(
                f"  {m:<22}" for m in per_cols
            )
            print(header)
            print("-" * len(header))
            for domain, grp in base.groupby("domain"):
                line = f"{str(domain):<20} {len(grp):>4}"
                for m in per_cols:
                    score_val = grp[m].mean()
                    line += f"  {score_val:<22.4f}"
                print(line)
            print("=" * len(header))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Single-turn RAGAS evaluation for new-rag-2026"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Collect RAG responses only; skip RAGAS scoring (no judge LLM calls)",
    )
    parser.add_argument(
        "--judge-provider",
        default=os.getenv("JUDGE_PROVIDER", "openai"),
        choices=["openai", "gemini", "siliconflow"],
        help="LLM provider for RAGAS judge (default: openai)",
    )
    parser.add_argument(
        "--judge-model",
        default=None,
        help="Model name for RAGAS judge. Defaults per provider: "
        "openai=gpt-4o-mini, gemini=gemini-2.0-flash, siliconflow=deepseek-ai/DeepSeek-V3",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    provider = args.judge_provider
    model = args.judge_model or os.getenv(
        f"{provider.upper()}_JUDGE_MODEL", DEFAULT_MODEL[provider]
    )

    with open(QUESTIONS_FILE, encoding="utf-8") as f:
        data = json.load(f)
    questions = data["questions"]
    print(f"Loaded {len(questions)} questions from {QUESTIONS_FILE.name}\n")

    print("Step 1/3: Querying new-rag-2026...")
    results = asyncio.run(collect_responses(questions))
    print(f"Collected {len(results)} responses.\n")

    if not results:
        print("ERROR: No responses collected — all queries failed. Check backend logs.")
        sys.exit(1)

    print("Step 2/3: Building RAGAS dataset...")
    dataset = build_dataset(results)

    if args.dry_run:
        print("--dry-run: skipping RAGAS scoring. Dataset preview:")
        for s in dataset.samples:
            preview = s.response[:80].replace("\n", " ")
            print(f"  Q: {s.user_input[:60]}")
            print(f"  A: {preview}...\n")
        save_and_print(results, ragas_df=None, provider=provider, model=model)
        return

    print(f"Step 3/3: Running RAGAS evaluation (judge: {provider}:{model})...\n")
    llm, embeddings = build_judge(provider, model)
    df = run_ragas(dataset, llm, embeddings)
    save_and_print(results, ragas_df=df, provider=provider, model=model)


if __name__ == "__main__":
    main()
