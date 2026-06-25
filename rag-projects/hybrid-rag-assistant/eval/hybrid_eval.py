"""
RAGAS evaluation for hybrid-rag-assistant (OpenAI judge).

Two question sets:
  Set A — 17 shared questions from eval-v2 (apples-to-apples with graphrag-assistant)
  Set B — 15 hybrid-specific questions stress-testing BM25/vector/reranker/out-of-scope

Prerequisites:
  - hybrid-rag-assistant backend running (default: http://localhost:8000)
  - eval/.env with OPENAI_API_KEY

Usage:
  pip install -r requirements.txt
  cp .env.example .env          # fill in OPENAI_API_KEY
  python hybrid_eval.py                     # Set A (17 questions)
  python hybrid_eval.py --set B             # Set B (15 questions)
  python hybrid_eval.py --set all           # both sets merged
  python hybrid_eval.py --file eval-sets/hybrid_questions_sample10.json  # custom file
  python hybrid_eval.py --dry-run           # collect responses only, skip RAGAS
  python hybrid_eval.py --model gpt-4o      # override judge model
"""

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
from ragas import EvaluationDataset, RunConfig, SingleTurnSample, evaluate
from ragas.embeddings import embedding_factory
from ragas.llms import llm_factory
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

OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
HYBRID_API_URL = os.getenv("HYBRID_API_URL", "http://localhost:8000")
SESSION_ENDPOINT = f"{HYBRID_API_URL}/api/session"
CHAT_ENDPOINT = f"{HYBRID_API_URL}/api/chat"

EVAL_DIR = Path(__file__).parent / "eval-sets"
QUESTIONS_FILE_A = EVAL_DIR / "eval_questions.json"
QUESTIONS_FILE_B = EVAL_DIR / "hybrid_questions.json"
RESULTS_DIR = Path(__file__).parent / "results"

METRICS = [
    faithfulness,
    answer_relevancy,
    context_precision,
    context_recall,
    answer_correctness,
]


async def query_hybrid(
    client: httpx.AsyncClient, question: str
) -> tuple[str, list[str], list[str], bool]:
    session_resp = await client.post(SESSION_ENDPOINT, timeout=10.0)
    session_resp.raise_for_status()
    session_id = session_resp.json()["session_id"]

    payload = {"session_id": session_id, "message": question}
    response = await client.post(CHAT_ENDPOINT, json=payload, timeout=60.0)
    response.raise_for_status()
    data = response.json()

    answer = data.get("reply", "")
    contexts = [s["excerpt"] for s in data.get("sources", []) if s.get("excerpt")]
    domains_used = data.get("domains_used", [])
    is_out_of_scope = data.get("is_out_of_scope", False)
    return answer, contexts, domains_used, is_out_of_scope


async def collect_responses(
    questions: list[dict],
) -> list[tuple[dict, str, list[str], list[str], bool]]:
    results = []
    async with httpx.AsyncClient() as client:
        try:
            health = await client.get(f"{HYBRID_API_URL}/api/admin/domains", timeout=5.0)
            health.raise_for_status()
        except Exception as exc:
            print(f"ERROR: Cannot reach hybrid-rag-assistant at {HYBRID_API_URL}: {exc}")
            print("Start the backend first: uvicorn app.main:app --port 8000 --reload")
            sys.exit(1)

        for i, q in enumerate(questions, 1):
            print(f"  [{i}/{len(questions)}] {q['id']}: {q['question'][:60]}...")
            try:
                answer, contexts, domains_used, is_out_of_scope = await query_hybrid(
                    client, q["question"]
                )
                results.append((q, answer, contexts, domains_used, is_out_of_scope))
            except Exception as exc:
                print(f"    WARNING: failed ({exc}), skipping")

    return results


def build_dataset(
    results: list[tuple[dict, str, list[str], list[str], bool]],
) -> EvaluationDataset:
    samples = [
        SingleTurnSample(
            user_input=q["question"],
            response=answer,
            retrieved_contexts=contexts if contexts else [""],
            reference=q["expected_answer_summary"],
        )
        for q, answer, contexts, _domains, _oos in results
    ]
    return EvaluationDataset(samples=samples)


def build_judge(model: str):
    llm = llm_factory(model)
    embeddings = embedding_factory("text-embedding-3-small")
    return llm, embeddings


def run_ragas(
    dataset: EvaluationDataset,
    llm,
    embeddings,
) -> pd.DataFrame:
    run_config = RunConfig(max_retries=5, max_wait=120, timeout=180, max_workers=2)
    result = evaluate(
        dataset=dataset,
        metrics=METRICS,
        llm=llm,
        embeddings=embeddings,
        run_config=run_config,
    )
    return result.to_pandas()


def audit_failures(df: pd.DataFrame, metric_cols: list[str]) -> None:
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
        "Common causes: OpenAI rate-limit after retries, judge JSON-parse error, "
        "context exceeds model window.\n"
    )


def save_and_print(
    df: pd.DataFrame,
    results: list[tuple[dict, str, list[str], list[str], bool]],
    set_label: str,
) -> None:
    RESULTS_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = RESULTS_DIR / f"hybrid_eval_{set_label}_{timestamp}.csv"

    # Attach extra hybrid-specific columns (not fed to RAGAS)
    skip_cols = {"user_input", "response", "retrieved_contexts", "reference"}
    metric_cols = [c for c in df.columns if c not in skip_cols]

    df = df.copy()
    df.insert(0, "question_id", [r[0]["id"] for r in results])
    df.insert(1, "retrieval_challenge", [r[0].get("retrieval_challenge", "") for r in results])
    df.insert(2, "domains_used", [",".join(r[3]) for r in results])
    df.insert(3, "is_out_of_scope", [r[4] for r in results])

    df.to_csv(out_path, index=False)
    print(f"\nResults saved to: {out_path}\n")

    print(f"=== RAGAS Evaluation Summary (hybrid-rag-assistant / Set {set_label} / OpenAI judge) ===")
    print(f"{'Metric':<28} {'Score':>8}  {'Coverage':>10}")
    print("-" * 52)
    for metric in metric_cols:
        score = df[metric].mean()
        n = int(df[metric].notna().sum())
        total = len(df)
        coverage = f"{n}/{total}"
        flag = "  (partial)" if n < total else ""
        print(f"{metric:<28} {score:>8.4f}  {coverage:>10}{flag}")
    print("=" * 52)

    # Extra breakdown by retrieval_challenge (Set B)
    if "retrieval_challenge" in df.columns and df["retrieval_challenge"].nunique() > 1:
        print("\n=== Per-Challenge Breakdown ===")
        for challenge, group in df.groupby("retrieval_challenge"):
            scores = "  ".join(
                f"{m}={group[m].mean():.3f}" for m in metric_cols if m in group
            )
            print(f"  {challenge:<22} n={len(group)}  {scores}")
        print()

    audit_failures(df, metric_cols)


def load_questions(set_flag: str, custom_file: str | None = None) -> tuple[list[dict], str]:
    if custom_file:
        path = Path(custom_file)
        if not path.is_absolute():
            path = Path(__file__).parent / custom_file
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data["questions"], path.stem

    if set_flag == "A":
        with open(QUESTIONS_FILE_A, encoding="utf-8") as f:
            data = json.load(f)
        return data["questions"], "A"

    if set_flag == "B":
        with open(QUESTIONS_FILE_B, encoding="utf-8") as f:
            data = json.load(f)
        return data["questions"], "B"

    # "all" — merge both
    with open(QUESTIONS_FILE_A, encoding="utf-8") as f:
        questions_a = json.load(f)["questions"]
    with open(QUESTIONS_FILE_B, encoding="utf-8") as f:
        questions_b = json.load(f)["questions"]
    return questions_a + questions_b, "all"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="RAGAS evaluation for hybrid-rag-assistant")
    parser.add_argument(
        "--set",
        choices=["A", "B", "all"],
        default="A",
        help="Question set to evaluate: A (17 shared), B (15 hybrid-specific), all (both merged)",
    )
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
    parser.add_argument(
        "--file",
        default=None,
        help="Path to a custom question JSON file (relative to eval/ or absolute). Overrides --set.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    questions, set_label = load_questions(args.set, args.file)
    print(f"Loaded {len(questions)} questions (Set {set_label})\n")

    print("Step 1/3: Querying hybrid-rag-assistant...")
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
    save_and_print(df, results, set_label)


if __name__ == "__main__":
    main()
