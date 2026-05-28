"""
Đánh giá RAGAS single-turn cho policy-assistant-cloud (judge: OpenAI).

Yêu cầu:
  - Backend policy-assistant-cloud đang chạy (mặc định http://127.0.0.1:8000)
  - File .env chứa OPENAI_API_KEY (và tuỳ chọn POLICY_API_URL, OPENAI_JUDGE_MODEL)

Sử dụng:
  pip install -r requirements.txt
  cp .env.example .env          # điền OPENAI_API_KEY
  python policy_eval.py             # chạy đầy đủ
  python policy_eval.py --dry-run   # chỉ thu thập câu trả lời, không gọi OpenAI
  python policy_eval.py --model gpt-4o   # đổi judge model
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

logging.basicConfig(level=logging.WARNING, format="%(levelname)s [%(name)s] %(message)s")
logging.getLogger("ragas").setLevel(logging.WARNING)

load_dotenv()

OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
POLICY_API_URL = os.getenv("POLICY_API_URL", "http://127.0.0.1:8000")
CHAT_ENDPOINT = f"{POLICY_API_URL}/chat"
HEALTH_ENDPOINT = f"{POLICY_API_URL}/health"

QUESTIONS_FILE = Path(__file__).parent / "eval_questions.json"
RESULTS_DIR = Path(__file__).parent / "results"

METRICS = [
    faithfulness,
    answer_relevancy,
    context_precision,
    context_recall,
    answer_correctness,
]


async def query_policy(client: httpx.AsyncClient, question: str) -> tuple[str, list[str]]:
    """Gửi một câu hỏi tới backend; trả (answer, retrieved_contexts)."""
    payload = {"message": question, "history": []}
    response = await client.post(CHAT_ENDPOINT, json=payload, timeout=120.0)
    response.raise_for_status()
    data = response.json()
    answer = data.get("answer", "")
    contexts = data.get("retrieved_contexts", []) or []
    return answer, contexts


async def collect_responses(questions: list[dict]) -> list[tuple[dict, str, list[str]]]:
    results = []
    async with httpx.AsyncClient() as client:
        try:
            health = await client.get(HEALTH_ENDPOINT, timeout=5.0)
            health.raise_for_status()
            indexed = health.json().get("indexed_count", 0)
            if indexed == 0:
                print(
                    "WARNING: Backend báo chưa có tài liệu nào được nạp (indexed_count=0).\n"
                    "Hãy upload PDF qua POST /ingest/upload trước khi chạy eval."
                )
        except Exception as exc:
            print(f"ERROR: Không kết nối được backend tại {POLICY_API_URL}: {exc}")
            print("Khởi động backend trước: uvicorn app.main:app --port 8000 --reload")
            sys.exit(1)

        for i, q in enumerate(questions, 1):
            print(f"  [{i}/{len(questions)}] {q['id']}: {q['question'][:60]}...")
            try:
                answer, contexts = await query_policy(client, q["question"])
                results.append((q, answer, contexts))
            except Exception as exc:
                print(f"    WARNING: thất bại ({exc}), bỏ qua")

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


def audit_failures(df: pd.DataFrame, metric_cols: list[str]) -> None:
    nan_mask = df[metric_cols].isna()
    if not nan_mask.any().any():
        return

    print("\n=== CẢNH BÁO: Các ô metric bị thiếu (RAGAS lỗi mức từng câu) ===")
    for metric in metric_cols:
        failed_idx = nan_mask.index[nan_mask[metric]].tolist()
        if not failed_idx:
            continue
        print(f"  {metric}: {len(failed_idx)}/{len(df)} câu lỗi (rows: {failed_idx})")
        for i in failed_idx:
            q = df.loc[i, "user_input"]
            preview = (q[:70] + "...") if len(q) > 70 else q
            print(f"      row {i}: {preview}")
    print(
        "Cuộn lên xem traceback chi tiết (ragas.executor ghi ở mức WARNING).\n"
        "Nguyên nhân phổ biến: OpenAI rate-limit sau retry, lỗi parse JSON, "
        "context vượt cửa sổ model.\n"
    )


def save_and_print(df: pd.DataFrame) -> None:
    RESULTS_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = RESULTS_DIR / f"policy_eval_{timestamp}.csv"
    df.to_csv(out_path, index=False)
    print(f"\nĐã lưu kết quả vào: {out_path}\n")

    skip_cols = {"user_input", "response", "retrieved_contexts", "reference"}
    metric_cols = [c for c in df.columns if c not in skip_cols]

    print("=== Tổng kết RAGAS (policy-assistant-cloud / judge OpenAI) ===")
    print(f"{'Metric':<28} {'Score':>8}  {'Coverage':>10}")
    print("-" * 52)
    for metric in metric_cols:
        score = df[metric].mean()
        n = int(df[metric].notna().sum())
        total = len(df)
        coverage = f"{n}/{total}"
        flag = "  (một phần)" if n < total else ""
        print(f"{metric:<28} {score:>8.4f}  {coverage:>10}{flag}")
    print("=" * 52)

    audit_failures(df, metric_cols)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Đánh giá RAGAS cho policy-assistant-cloud")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Chỉ thu thập câu trả lời; bỏ qua bước chấm RAGAS (không gọi OpenAI)",
    )
    parser.add_argument(
        "--model",
        default=os.getenv("OPENAI_JUDGE_MODEL", "gpt-4o-mini"),
        help="Model OpenAI dùng làm judge (mặc định: gpt-4o-mini)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    with open(QUESTIONS_FILE, encoding="utf-8") as f:
        data = json.load(f)
    questions = data["questions"]
    print(f"Đã nạp {len(questions)} câu hỏi từ {QUESTIONS_FILE.name}\n")

    print("Bước 1/3: Gọi backend policy-assistant-cloud...")
    results = asyncio.run(collect_responses(questions))
    print(f"Đã thu được {len(results)} câu trả lời.\n")

    if not results:
        print("ERROR: Không có câu trả lời nào — tất cả request thất bại. Kiểm tra log backend.")
        sys.exit(1)

    print("Bước 2/3: Dựng RAGAS dataset...")
    dataset = build_dataset(results)

    if args.dry_run:
        print("--dry-run: bỏ qua bước chấm RAGAS. Dataset hiện có:")
        for s in dataset.samples:
            preview = s.response[:80].replace("\n", " ")
            ctx_n = len(s.retrieved_contexts) if s.retrieved_contexts else 0
            print(f"  Q: {s.user_input[:60]}")
            print(f"  A ({ctx_n} ctx): {preview}...\n")
        return

    print(f"Bước 3/3: Chấm RAGAS (judge: {args.model})...\n")
    llm, embeddings = build_judge(args.model)
    df = run_ragas(dataset, llm, embeddings)
    save_and_print(df)


if __name__ == "__main__":
    main()
