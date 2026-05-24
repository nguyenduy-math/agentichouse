"""
RAGAS evaluation for graphrag-assistant.

Prerequisites:
  - graphrag-assistant backend running (default: http://localhost:8000)
  - eval/.env file with GOOGLE_API_KEY and GRAPHRAG_API_URL

Usage:
  pip install -r requirements.txt
  cp .env.example .env  # fill in GOOGLE_API_KEY
  python graphrag_eval.py
"""

import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import httpx
import pandas as pd
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings
from ragas import EvaluationDataset, SingleTurnSample, evaluate
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

GOOGLE_API_KEY = os.environ["GOOGLE_API_KEY"]
GRAPHRAG_API_URL = os.getenv("GRAPHRAG_API_URL", "http://localhost:8000")
CHAT_ENDPOINT = f"{GRAPHRAG_API_URL}/api/v1/chat"

QUESTIONS_FILE = (
    Path(__file__).parent.parent
    / "rag-projects/graphrag-assistant/backend/data/eval_questions.json"
)
RESULTS_DIR = Path(__file__).parent / "results"


async def query_graphrag(client: httpx.AsyncClient, question_id: str, question: str) -> tuple[str, list[str]]:
    payload = {"session_id": f"ragas-eval-{question_id}", "message": question}
    response = await client.post(CHAT_ENDPOINT, json=payload, timeout=30.0)
    response.raise_for_status()
    data = response.json()
    answer = data.get("reply", "")
    contexts = [s["excerpt"] for s in data.get("sources", []) if s.get("excerpt")]
    return answer, contexts


async def collect_responses(questions: list[dict]) -> list[tuple[dict, str, list[str]]]:
    results = []
    async with httpx.AsyncClient() as client:
        # verify backend is reachable
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
                answer, contexts = await query_graphrag(client, q["id"], q["question"])
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


def run_ragas(dataset: EvaluationDataset) -> pd.DataFrame:
    llm = LangchainLLMWrapper(
        ChatGoogleGenerativeAI(model="gemini-2.5-flash", google_api_key=GOOGLE_API_KEY)
    )
    embeddings = LangchainEmbeddingsWrapper(
        GoogleGenerativeAIEmbeddings(
            model="models/text-embedding-004", google_api_key=GOOGLE_API_KEY
        )
    )

    result = evaluate(
        dataset=dataset,
        metrics=[
            faithfulness,
            answer_relevancy,
            context_precision,
            context_recall,
            answer_correctness,
        ],
        llm=llm,
        embeddings=embeddings,
    )
    return result.to_pandas()


def save_and_print(df: pd.DataFrame) -> None:
    RESULTS_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = RESULTS_DIR / f"graphrag_eval_{timestamp}.csv"
    df.to_csv(out_path, index=False)
    print(f"\nResults saved to: {out_path}\n")

    metric_cols = [c for c in df.columns if c not in ("user_input", "response", "retrieved_contexts", "reference")]
    summary = df[metric_cols].mean().round(4)
    print("=== RAGAS Evaluation Summary (graphrag-assistant) ===")
    print(f"{'Metric':<25} {'Score':>8}")
    print("-" * 35)
    for metric, score in summary.items():
        print(f"{metric:<25} {score:>8.4f}")
    print("=" * 35)


def main() -> None:
    with open(QUESTIONS_FILE, encoding="utf-8") as f:
        data = json.load(f)
    questions = data["questions"]
    print(f"Loaded {len(questions)} questions from {QUESTIONS_FILE.name}\n")

    print("Step 1/3: Querying graphrag-assistant...")
    results = asyncio.run(collect_responses(questions))
    print(f"Collected {len(results)} responses.\n")

    print("Step 2/3: Building RAGAS dataset...")
    dataset = build_dataset(results)

    print("Step 3/3: Running RAGAS evaluation (this calls Gemini as judge)...\n")
    df = run_ragas(dataset)

    save_and_print(df)


if __name__ == "__main__":
    main()
