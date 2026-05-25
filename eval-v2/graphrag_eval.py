"""
RAGAS evaluation for graphrag-assistant — v2 (OpenAI judge).

Prerequisites:
  - graphrag-assistant backend running (default: http://localhost:8000)
  - eval-v2/.env with OPENAI_API_KEY and GRAPHRAG_API_URL

Usage:
  pip install -r requirements.txt
  cp .env.example .env          # fill in OPENAI_API_KEY
  python graphrag_eval.py       # full run
  python graphrag_eval.py --dry-run   # collect responses only, skip RAGAS scoring
  python graphrag_eval.py --model gpt-4o   # override judge model
"""

import argparse
import asyncio
import json
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

load_dotenv()

OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
GRAPHRAG_API_URL = os.getenv("GRAPHRAG_API_URL", "http://localhost:8000")
SESSION_ENDPOINT = f"{GRAPHRAG_API_URL}/api/v1/session"
CHAT_ENDPOINT = f"{GRAPHRAG_API_URL}/api/v1/chat"

QUESTIONS_FILE = (
    Path(__file__).parent.parent
    / "rag-projects/graphrag-assistant/eval-sets/eval_questions.json"
)
RESULTS_DIR = Path(__file__).parent / "results"

METRICS = [
    faithfulness,
    answer_relevancy,
    context_precision,
    context_recall,
    answer_correctness,
]


async def query_graphrag(client: httpx.AsyncClient, question: str) -> tuple[str, list[str]]:
    session_resp = await client.post(SESSION_ENDPOINT, timeout=10.0)
    session_resp.raise_for_status()
    session_id = session_resp.json()["session_id"]

    payload = {"session_id": session_id, "message": question}
    response = await client.post(CHAT_ENDPOINT, json=payload, timeout=60.0)
    response.raise_for_status()
    data = response.json()
    answer = data.get("reply", "")
    contexts = [s["excerpt"] for s in data.get("sources", []) if s.get("excerpt")]
    return answer, contexts


async def collect_responses(questions: list[dict]) -> list[tuple[dict, str, list[str]]]:
    results = []
    async with httpx.AsyncClient() as client:
        try:
            health = await client.get(f"{GRAPHRAG_API_URL}/health", timeout=5.0)
            health.raise_for_status()
        except Exception as exc:
            print(f"ERROR: Cannot reach graphrag-assistant at {GRAPHRAG_API_URL}: {exc}")
            print("Start the backend first: uvicorn app.main:app --port 8000 --reload")
            sys.exit(1)

        for i, q in enumerate(questions, 1):
            print(f"  [{i}/{len(questions)}] {q['id']}: {q['question'][:60]}...")
            try:
                answer, contexts = await query_graphrag(client, q["question"])
                results.append((q, answer, contexts))
            except Exception as exc:
                print(f"    WARNING: failed ({exc}), skipping")

    return results


def build_dataset(results: list[tuple[dict, str, list[str]]]) -> EvaluationDataset:
    samples = [
        SingleTurnSample(
            user_input=q["question"],
            response=answer,
            retrieved_contexts=contexts if contexts else [""],
            reference=q["expected_answer_summary"],
        )
        for q, answer, contexts in results
    ]
    return EvaluationDataset(samples=samples)


def build_judge(model: str) -> tuple[LangchainLLMWrapper, LangchainEmbeddingsWrapper]:
    llm = LangchainLLMWrapper(
        ChatOpenAI(model=model, api_key=OPENAI_API_KEY, temperature=0)
    )
    embeddings = LangchainEmbeddingsWrapper(
        OpenAIEmbeddings(model="text-embedding-3-small", api_key=OPENAI_API_KEY)
    )
    return llm, embeddings


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


def save_and_print(df: pd.DataFrame) -> None:
    RESULTS_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = RESULTS_DIR / f"graphrag_eval_{timestamp}.csv"
    df.to_csv(out_path, index=False)
    print(f"\nResults saved to: {out_path}\n")

    skip_cols = {"user_input", "response", "retrieved_contexts", "reference"}
    metric_cols = [c for c in df.columns if c not in skip_cols]
    summary = df[metric_cols].mean().round(4)

    print("=== RAGAS Evaluation Summary (graphrag-assistant v2 / OpenAI judge) ===")
    print(f"{'Metric':<30} {'Score':>8}")
    print("-" * 40)
    for metric, score in summary.items():
        print(f"{metric:<30} {score:>8.4f}")
    print("=" * 40)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="RAGAS evaluation for graphrag-assistant (v2)")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Collect RAG responses only; skip RAGAS scoring (no OpenAI calls)",
    )
    parser.add_argument(
        "--model",
        default=os.getenv("OPENAI_JUDGE_MODEL", "gpt-4o-mini"),
        help="OpenAI model used as RAGAS judge (default: gpt-4o-mini)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    with open(QUESTIONS_FILE, encoding="utf-8") as f:
        data = json.load(f)
    questions = data["questions"]
    print(f"Loaded {len(questions)} questions from {QUESTIONS_FILE.name}\n")

    print("Step 1/3: Querying graphrag-assistant...")
    results = asyncio.run(collect_responses(questions))
    print(f"Collected {len(results)} responses.\n")

    if not results:
        print("ERROR: No responses collected — all queries failed. Check backend logs.")
        sys.exit(1)

    print("Step 2/3: Building RAGAS dataset...")
    dataset = build_dataset(results)

    if args.dry_run:
        print("--dry-run: skipping RAGAS scoring. Dataset contains:")
        for s in dataset.samples:
            preview = s.response[:80].replace("\n", " ")
            print(f"  Q: {s.user_input[:60]}")
            print(f"  A: {preview}...\n")
        return

    print(f"Step 3/3: Running RAGAS evaluation (judge: {args.model})...\n")
    llm, embeddings = build_judge(args.model)
    df = run_ragas(dataset, llm, embeddings)
    save_and_print(df)


if __name__ == "__main__":
    main()
