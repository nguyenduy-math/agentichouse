"""
Per-domain RAGAS evaluation for new-rag-2026.

After each chat request, calls GET /api/v1/chat/{session_id}/agent_trace to get
each domain agent's individual answer, then evaluates those answers with RAGAS
independently. This reveals which domain agent is weakest and guides targeted
improvement — e.g. if context_recall is low for the 'benefits' domain, you know
to add more benefits documents to the index.

Note on retrieved_contexts: The /agent_trace endpoint exposes each domain agent's
answer text but not the per-domain source chunks (only sources_count). The overall
response sources from POST /chat are used as the retrieved_contexts for all domain
samples. This is an approximation; faithfulness and recall scores should be read as
system-level lower bounds for each domain rather than exact per-domain scores.

Usage:
  python eval_per_domain.py                                 # OpenAI judge (default)
  python eval_per_domain.py --judge-provider gemini         # Gemini judge
  python eval_per_domain.py --dry-run                       # collect only, skip RAGAS
  python eval_per_domain.py --domain hr                     # evaluate one domain only
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

QUESTIONS_FILE = Path(__file__).parent / "eval_sets/eval_questions.json"
AGENT_TRACE_ENDPOINT = NEW_RAG_API_URL + "/api/v1/chat/{session_id}/agent_trace"


async def query_and_trace(
    client: httpx.AsyncClient, question: str, reference: str
) -> list[dict]:
    """
    POST /session → POST /chat → GET /agent_trace.
    Returns one row dict per domain agent that responded.
    """
    # 1. Create session
    session_resp = await client.post(SESSION_ENDPOINT, timeout=10.0)
    session_resp.raise_for_status()
    session_id = session_resp.json()["session_id"]

    # 2. POST /chat
    payload = {"session_id": session_id, "message": question, "mode": "auto"}
    chat_resp = await client.post(CHAT_ENDPOINT, json=payload, timeout=60.0)
    chat_resp.raise_for_status()
    chat_data = chat_resp.json()

    overall_contexts = [s["text"] for s in chat_data.get("sources", []) if s.get("text")]
    query_type = chat_data.get("query_type", "")

    # 3. GET /agent_trace
    trace_url = AGENT_TRACE_ENDPOINT.format(session_id=session_id)
    trace_resp = await client.get(trace_url, timeout=10.0)
    trace_resp.raise_for_status()
    trace_data = trace_resp.json()

    agent_results = trace_data.get("agent_results", [])
    if not agent_results:
        # No domain agents fired — use final answer as a single row
        return [
            {
                "domain_key": "unknown",
                "domain_name_vi": "Không xác định",
                "question": question,
                "query_type": query_type,
                "user_input": question,
                "response": chat_data.get("reply", ""),
                "retrieved_contexts": overall_contexts if overall_contexts else [""],
                "reference": reference,
            }
        ]

    rows = []
    for agent in agent_results:
        rows.append(
            {
                "domain_key": agent.get("domain_key", ""),
                "domain_name_vi": agent.get("domain_name_vi", ""),
                "question": question,
                "query_type": query_type,
                # RAGAS fields
                "user_input": question,
                "response": agent.get("answer", ""),
                # Use overall contexts as approximation (see module docstring)
                "retrieved_contexts": overall_contexts if overall_contexts else [""],
                "reference": reference,
            }
        )

    return rows


async def collect_responses(
    questions: list[dict], domain_filter: str | None = None
) -> list[dict]:
    all_rows: list[dict] = []

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
                rows = await query_and_trace(
                    client, q["question"], q["expected_answer_summary"]
                )
                # Attach question metadata to each domain row
                for r in rows:
                    r["question_id"] = q.get("id", "")
                    r["question_domain"] = q.get("domain", "")
                    r["difficulty"] = q.get("difficulty", "")

                if domain_filter:
                    rows = [r for r in rows if r["domain_key"] == domain_filter]

                domain_summary = ", ".join(r["domain_key"] for r in rows)
                print(f"    agent domains: [{domain_summary}], contexts={len(rows[0]['retrieved_contexts']) if rows else 0}")
                all_rows.extend(rows)
            except Exception as exc:
                print(f"    WARNING: failed ({exc}), skipping")

    return all_rows


def build_dataset(rows: list[dict]) -> EvaluationDataset:
    samples = [
        SingleTurnSample(
            user_input=r["user_input"],
            response=r["response"],
            retrieved_contexts=r["retrieved_contexts"],
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
    out_path = RESULTS_DIR / f"eval_per_domain_{timestamp}.csv"

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

    print(f"=== RAGAS Per-Domain Summary (new-rag-2026 / {provider}:{model}) ===")
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

    # Per-domain breakdown — core output of this script
    if "domain_key" in base.columns and base["domain_key"].nunique() > 0:
        print("\n=== Per-Domain Agent Scores ===")
        print("(Lower scores = weaker domain agent — prioritise those for improvement)")
        header = (
            f"{'domain_key':<16} {'domain_name_vi':<20} {'samples':>7}"
            + "".join(f"  {m:<22}" for m in metric_cols)
        )
        print(header)
        print("-" * len(header))
        for domain_key, grp in base.groupby("domain_key"):
            domain_name = grp["domain_name_vi"].iloc[0] if "domain_name_vi" in grp.columns else ""
            line = f"{str(domain_key):<16} {str(domain_name):<20} {len(grp):>7}"
            for m in metric_cols:
                line += f"  {grp[m].mean():<22.4f}"
            print(line)
        print("=" * len(header))

        # Highlight weakest domain by answer_correctness
        if "answer_correctness" in base.columns:
            domain_scores = (
                base.groupby("domain_key")["answer_correctness"]
                .mean()
                .sort_values()
            )
            weakest = domain_scores.index[0]
            weakest_score = domain_scores.iloc[0]
            print(
                f"\n>>> Weakest domain by answer_correctness: "
                f"{weakest!r} ({weakest_score:.4f})"
            )
            print(
                f"    Action: add more documents to the '{weakest}' index "
                f"or tune the '{weakest}' agent prompt.\n"
            )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Per-domain RAGAS evaluation for new-rag-2026"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Collect domain agent responses only; skip RAGAS scoring",
    )
    parser.add_argument(
        "--domain",
        default=None,
        help="Evaluate only a single domain key, e.g. hr, benefits, it",
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

    if args.domain:
        # Pre-filter questions to those touching the requested domain
        questions = [
            q for q in questions if args.domain in q.get("domain", "")
        ]
        if not questions:
            print(f"WARNING: No questions found with domain containing {args.domain!r}.")

    print(
        f"Loaded {len(questions)} question(s) from {QUESTIONS_FILE.name}"
        + (f" (domain filter: {args.domain})" if args.domain else "")
        + "\n"
    )

    print("Step 1/3: Querying new-rag-2026 and fetching agent traces...")
    rows = asyncio.run(collect_responses(questions, domain_filter=args.domain))
    if not rows:
        print("ERROR: No domain agent rows collected. Check backend logs.")
        sys.exit(1)
    print(
        f"Collected {len(rows)} domain-agent sample(s) across "
        f"{len(questions)} question(s).\n"
    )

    print("Step 2/3: Building RAGAS dataset...")
    dataset = build_dataset(rows)

    if args.dry_run:
        print("--dry-run: skipping RAGAS scoring. Domain samples preview:")
        for r in rows[:5]:
            print(f"  domain={r['domain_key']}  Q: {r['user_input'][:50]}")
            print(f"  A: {r['response'][:80].replace(chr(10), ' ')}...\n")
        save_and_print(rows, ragas_df=None, provider=provider, model=model)
        return

    print(f"Step 3/3: Running RAGAS evaluation (judge: {provider}:{model})...\n")
    llm, embeddings = build_judge(provider, model)
    df = run_ragas(dataset, llm, embeddings)
    save_and_print(rows, ragas_df=df, provider=provider, model=model)


if __name__ == "__main__":
    main()
