"""
Multi-turn RAGAS evaluation for new-rag-2026.

Reads eval_conversation_sets.json (5 sets x 4 turns), runs each set as a single
session (reusing session_id across turns) so the backend's conversation history
informs each answer. Scores every turn with single-turn RAGAS metrics, using
cumulative within-set retrieved contexts so memory-grounded claims aren't
penalised as ungrounded.

Usage:
  python eval_multiturn.py                                  # all sets
  python eval_multiturn.py --set CS-001                     # one set (debugging)
  python eval_multiturn.py --dry-run                        # collect responses; skip RAGAS
  python eval_multiturn.py --judge-provider gemini          # Gemini judge
  python eval_multiturn.py --judge-model gpt-4o             # override model
"""

from __future__ import annotations

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

from eval_single import (
    CHAT_ENDPOINT,
    DEFAULT_MODEL,
    METRICS,
    NEW_RAG_API_URL,
    RESULTS_DIR,
    SESSION_ENDPOINT,
    SKIP_COLS,
    audit_failures,
    build_judge,
)

CONVERSATIONS_FILE = Path(__file__).parent / "eval_sets/eval_conversation_sets.json"


async def run_set(client: httpx.AsyncClient, set_data: dict) -> list[dict]:
    """Run all turns in a single conversation set, sharing one session_id."""
    session_resp = await client.post(SESSION_ENDPOINT, timeout=10.0)
    session_resp.raise_for_status()
    session_id = session_resp.json()["session_id"]
    print(
        f"  [{set_data['set_id']}] session {session_id[:8]}... — {set_data['title']}"
    )

    cumulative_contexts: list[str] = []
    rows: list[dict] = []

    for turn in set_data["turns"]:
        payload = {
            "session_id": session_id,
            "message": turn["question"],
            "mode": "auto",
        }
        try:
            response = await client.post(CHAT_ENDPOINT, json=payload, timeout=60.0)
            response.raise_for_status()
            data = response.json()
        except Exception as exc:
            print(f"    turn {turn['turn']}: FAILED ({exc})")
            continue

        answer = data.get("reply", "")
        contexts = [s["text"] for s in data.get("sources", []) if s.get("text")]
        domain_keys = data.get("domain_keys", [])
        query_type = data.get("query_type", "")
        is_fallback = data.get("is_fallback", False)

        # Accumulate unique contexts across turns (memory-grounded claims
        # from earlier turns should remain in context for later RAGAS checks)
        for c in contexts:
            if c not in cumulative_contexts:
                cumulative_contexts.append(c)

        preview = answer[:60].replace("\n", " ")
        print(
            f"    turn {turn['turn']}: ok "
            f"(+{len(contexts)} chunks, cum={len(cumulative_contexts)}) "
            f"domains={domain_keys} reply='{preview}...'"
        )

        rows.append(
            {
                "set_id": set_data["set_id"],
                "turn": turn["turn"],
                "context_dependency": turn.get("context_dependency") or "",
                "domain_keys": ",".join(domain_keys),
                "query_type": query_type,
                "is_fallback": is_fallback,
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
            health = await client.get(f"{NEW_RAG_API_URL}/health", timeout=5.0)
            health.raise_for_status()
        except Exception as exc:
            print(f"ERROR: Cannot reach new-rag-2026 at {NEW_RAG_API_URL}: {exc}")
            print("Start the backend first: uvicorn app.main:app --port 8000 --reload")
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


def save_and_print(
    rows: list[dict],
    ragas_df: pd.DataFrame | None,
    provider: str,
    model: str,
) -> None:
    RESULTS_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = RESULTS_DIR / f"eval_multiturn_{timestamp}.csv"

    base = pd.DataFrame(rows)

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

    print(f"=== RAGAS Per-Metric Summary (multi-turn / {provider}:{model}) ===")
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

    per_set_metrics = [m for m in ("answer_correctness", "faithfulness") if m in base.columns]
    if per_set_metrics:
        print("\n=== Per-Set Summary ===")
        header = f"{'set_id':<10} {'turns':>6}" + "".join(
            f"  {m:<22}" for m in per_set_metrics
        )
        print(header)
        print("-" * len(header))
        for set_id, group in base.groupby("set_id"):
            line = f"{set_id:<10} {len(group):>6}"
            for m in per_set_metrics:
                line += f"  {group[m].mean():<22.4f}"
            print(line)
        print("=" * len(header))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Multi-turn RAGAS evaluation for new-rag-2026"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Collect RAG responses only; skip RAGAS scoring",
    )
    parser.add_argument(
        "--set",
        dest="set_id",
        default=None,
        help="Limit evaluation to a single set_id, e.g. CS-001",
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

    with open(CONVERSATIONS_FILE, encoding="utf-8") as f:
        data = json.load(f)
    sets = data["conversation_sets"]

    if args.set_id:
        sets = [s for s in sets if s["set_id"] == args.set_id]
        if not sets:
            print(
                f"ERROR: No set with id={args.set_id!r} found in {CONVERSATIONS_FILE.name}"
            )
            sys.exit(1)

    total_turns = sum(len(s["turns"]) for s in sets)
    print(
        f"Loaded {len(sets)} conversation set(s) "
        f"({total_turns} turns total) from {CONVERSATIONS_FILE.name}\n"
    )

    print("Step 1/3: Running conversations against new-rag-2026...")
    rows = asyncio.run(collect_responses(sets))
    if not rows:
        print("ERROR: No turns collected — all requests failed. Check backend logs.")
        sys.exit(1)
    n_sets = len({r["set_id"] for r in rows})
    print(f"Collected {len(rows)} turns across {n_sets} set(s).\n")

    if args.dry_run:
        print("--dry-run: skipping RAGAS scoring.")
        save_and_print(rows, ragas_df=None, provider=provider, model=model)
        return

    print("Step 2/3: Building RAGAS dataset...")
    dataset = build_dataset(rows)

    print(f"Step 3/3: Running RAGAS evaluation (judge: {provider}:{model})...\n")
    llm, embeddings = build_judge(provider, model)
    df = run_ragas(dataset, llm, embeddings)
    save_and_print(rows, ragas_df=df, provider=provider, model=model)


if __name__ == "__main__":
    main()
