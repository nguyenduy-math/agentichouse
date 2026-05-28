"""
Đánh giá RAGAS multi-turn cho policy-assistant-cloud.

Đọc eval_conversation_sets.json (mỗi set vài lượt), chạy từng set thành một chuỗi
hội thoại — lượt sau gửi kèm history của các lượt trước (backend stateless, history
do client giữ và truyền vào). Mỗi lượt chấm bằng SingleTurnSample của RAGAS với
retrieved_contexts tích luỹ trong set, để các phát biểu dựa vào ngữ cảnh hội thoại
không bị phạt là "ungrounded".

Sử dụng:
  python policy_eval_multiturn.py              # toàn bộ set
  python policy_eval_multiturn.py --set CS-001 # 1 set (debug)
  python policy_eval_multiturn.py --dry-run    # chỉ thu thập, không chấm
  python policy_eval_multiturn.py --model gpt-4o
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
from ragas import EvaluationDataset, RunConfig, SingleTurnSample, evaluate

from policy_eval import (
    CHAT_ENDPOINT,
    HEALTH_ENDPOINT,
    METRICS,
    POLICY_API_URL,
    RESULTS_DIR,
    audit_failures,
    build_judge,
)

CONVERSATIONS_FILE = Path(__file__).parent / "eval_conversation_sets.json"
SKIP_COLS = {"user_input", "response", "retrieved_contexts", "reference"}


async def run_set(client: httpx.AsyncClient, set_data: dict) -> list[dict]:
    print(f"  [{set_data['set_id']}] — {set_data['title']}")
    history: list[dict] = []
    cumulative_contexts: list[str] = []
    rows: list[dict] = []

    for turn in set_data["turns"]:
        payload = {"message": turn["question"], "history": list(history)}
        try:
            response = await client.post(CHAT_ENDPOINT, json=payload, timeout=120.0)
            response.raise_for_status()
            data = response.json()
        except Exception as exc:
            print(f"    lượt {turn['turn']}: THẤT BẠI ({exc})")
            continue

        answer = data.get("answer", "")
        contexts = data.get("retrieved_contexts", []) or []
        for c in contexts:
            if c not in cumulative_contexts:
                cumulative_contexts.append(c)

        # Cập nhật history cho lượt kế tiếp
        history.append({"role": "user", "content": turn["question"]})
        history.append({"role": "assistant", "content": answer})

        preview = answer[:60].replace("\n", " ")
        print(
            f"    lượt {turn['turn']}: ok "
            f"({len(contexts)} ctx mới, cum={len(cumulative_contexts)}) "
            f"reply='{preview}...'"
        )

        rows.append(
            {
                "set_id": set_data["set_id"],
                "turn": turn["turn"],
                "context_dependency": turn.get("context_dependency") or "",
                "user_input": turn["question"],
                "response": answer,
                "retrieved_contexts": list(cumulative_contexts),
                "reference": turn["expected_answer_summary"],
            }
        )

    return rows


async def collect_responses(sets: list[dict]) -> list[dict]:
    rows: list[dict] = []
    async with httpx.AsyncClient() as client:
        try:
            health = await client.get(HEALTH_ENDPOINT, timeout=5.0)
            health.raise_for_status()
        except Exception as exc:
            print(f"ERROR: Không kết nối được backend tại {POLICY_API_URL}: {exc}")
            print("Khởi động backend trước: uvicorn app.main:app --port 8000 --reload")
            sys.exit(1)

        for s in sets:
            rows.extend(await run_set(client, s))

    return rows


def build_dataset(rows: list[dict]) -> EvaluationDataset:
    samples = [
        SingleTurnSample(
            user_input=r["user_input"],
            response=r["response"],
            retrieved_contexts=r["retrieved_contexts"] if r["retrieved_contexts"] else [""],
            reference=r["reference"],
        )
        for r in rows
    ]
    return EvaluationDataset(samples=samples)


def run_ragas(dataset: EvaluationDataset, llm, embeddings) -> pd.DataFrame:
    run_config = RunConfig(max_retries=3, max_wait=60, timeout=120)
    result = evaluate(
        dataset=dataset,
        metrics=METRICS,
        llm=llm,
        embeddings=embeddings,
        run_config=run_config,
    )
    return result.to_pandas()


def save_and_print(rows: list[dict], ragas_df: pd.DataFrame | None) -> None:
    RESULTS_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = RESULTS_DIR / f"policy_eval_multiturn_{timestamp}.csv"

    base = pd.DataFrame(rows)
    if ragas_df is not None:
        metric_cols = [c for c in ragas_df.columns if c not in SKIP_COLS]
        base = pd.concat(
            [base.reset_index(drop=True), ragas_df[metric_cols].reset_index(drop=True)],
            axis=1,
        )

    base.to_csv(out_path, index=False)
    print(f"\nĐã lưu kết quả vào: {out_path}\n")

    if ragas_df is None:
        return

    metric_cols = [c for c in ragas_df.columns if c not in SKIP_COLS]

    print("=== Tổng kết RAGAS theo metric (multi-turn) ===")
    print(f"{'Metric':<28} {'Score':>8}  {'Coverage':>10}")
    print("-" * 52)
    for metric in metric_cols:
        score = base[metric].mean()
        n = int(base[metric].notna().sum())
        total = len(base)
        coverage = f"{n}/{total}"
        flag = "  (một phần)" if n < total else ""
        print(f"{metric:<28} {score:>8.4f}  {coverage:>10}{flag}")
    print("=" * 52)

    audit_failures(base, metric_cols)

    per_set_metrics = [m for m in ("answer_correctness", "faithfulness") if m in base.columns]
    if per_set_metrics:
        print("\n=== Tổng kết theo set ===")
        header = f"{'set_id':<10} {'turns':>6}" + "".join(f" {m:>10}" for m in per_set_metrics)
        print(header)
        print("-" * len(header))
        for set_id, group in base.groupby("set_id"):
            line = f"{set_id:<10} {len(group):>6}"
            for m in per_set_metrics:
                line += f" {group[m].mean():>10.4f}"
            print(line)
        print("=" * len(header))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Đánh giá RAGAS multi-turn cho policy-assistant-cloud")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Chỉ thu thập câu trả lời, bỏ qua chấm RAGAS",
    )
    parser.add_argument(
        "--set", dest="set_id", default=None,
        help="Chỉ chạy 1 set theo set_id (vd: CS-001)",
    )
    parser.add_argument(
        "--model",
        default=os.getenv("OPENAI_JUDGE_MODEL", "gpt-4o-mini"),
        help="Model OpenAI làm judge (mặc định: gpt-4o-mini)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    with open(CONVERSATIONS_FILE, encoding="utf-8") as f:
        data = json.load(f)
    sets = data["conversation_sets"]

    if args.set_id:
        sets = [s for s in sets if s["set_id"] == args.set_id]
        if not sets:
            print(f"ERROR: Không có set nào có id={args.set_id!r} trong {CONVERSATIONS_FILE.name}")
            sys.exit(1)

    total_turns = sum(len(s["turns"]) for s in sets)
    print(
        f"Đã nạp {len(sets)} conversation set ({total_turns} lượt) "
        f"từ {CONVERSATIONS_FILE.name}\n"
    )

    print("Bước 1/3: Chạy hội thoại trên backend...")
    rows = asyncio.run(collect_responses(sets))
    if not rows:
        print("ERROR: Không thu được lượt nào — tất cả request thất bại. Kiểm tra log backend.")
        sys.exit(1)
    n_sets = len({r["set_id"] for r in rows})
    print(f"Đã thu {len(rows)} lượt trên {n_sets} set.\n")

    if args.dry_run:
        print("--dry-run: bỏ qua chấm RAGAS.")
        save_and_print(rows, ragas_df=None)
        return

    print("Bước 2/3: Dựng RAGAS dataset...")
    dataset = build_dataset(rows)

    print(f"Bước 3/3: Chấm RAGAS (judge: {args.model})...\n")
    llm, embeddings = build_judge(args.model)
    df = run_ragas(dataset, llm, embeddings)
    save_and_print(rows, ragas_df=df)


if __name__ == "__main__":
    main()
