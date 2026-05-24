"""
Eval runner — GraphRAG policy assistant.

Runs single-question and/or multi-turn conversation eval sets against the
running API, judges each answer with Gemini-as-Judge, then prints a summary
table and saves full results to JSON.

Usage:
  python -m scripts.eval_runner [OPTIONS]

Options:
  --mode     single | conversation | all   (default: all)
  --tag      label for this run, e.g. "gemini" or "openai"  (default: default)
  --output   path for JSON results file  (default: auto-generated under results/)
  --url      API base URL  (default: http://localhost:8000/api/v1)
  --delay    seconds between API calls  (default: 1.0)

Examples:
  # Run all evals against Gemini server, tag results
  python -m scripts.eval_runner --tag gemini

  # Run only conversation sets against OpenAI server
  python -m scripts.eval_runner --mode conversation --tag openai

  # Specify custom API URL
  python -m scripts.eval_runner --url http://localhost:8001/api/v1 --tag openai
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path

import httpx

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_BACKEND_DIR = Path(__file__).parent.parent
_DATA_DIR = _BACKEND_DIR / "data"
_RESULTS_DIR = _BACKEND_DIR / "results"
_SINGLE_FILE = _DATA_DIR / "eval_questions.json"
_CONV_FILE = _DATA_DIR / "eval_conversation_sets.json"


# ---------------------------------------------------------------------------
# Judge prompts
# ---------------------------------------------------------------------------

_SINGLE_JUDGE_PROMPT = """\
Bạn là chuyên gia đánh giá hệ thống hỏi đáp về nội quy công ty.

Câu hỏi: {question}
Các điểm chính cần có trong câu trả lời: {expected_key_facts}
Câu trả lời của hệ thống: {answer}

Trả về JSON theo định dạng sau:
{{
  "correctness": <1-5>,
  "groundedness": <1-5>,
  "completeness": <1-5>,
  "reasoning": "<giải thích ngắn bằng tiếng Việt>"
}}

Tiêu chí:
- correctness (1-5): Thông tin có đúng với các điểm chính không? (5 = hoàn toàn đúng)
- groundedness (1-5): Câu trả lời có dựa trên tài liệu, không bịa đặt? (5 = không bịa đặt)
- completeness (1-5): Có đầy đủ các điểm chính không? (5 = đầy đủ)
"""

_CONV_JUDGE_PROMPT = """\
Bạn là chuyên gia đánh giá hệ thống hỏi đáp nhiều lượt về nội quy công ty.

--- Lịch sử hội thoại ---
{history_text}
--- Kết thúc lịch sử ---

Câu hỏi hiện tại (lượt {turn}): {question}
Phụ thuộc ngữ cảnh từ lượt trước: {context_dependency}
Các điểm chính cần có: {expected_key_facts}
Câu trả lời của hệ thống: {answer}

Trả về JSON theo định dạng sau:
{{
  "correctness": <1-5>,
  "groundedness": <1-5>,
  "completeness": <1-5>,
  "context_retention": <1-5 hoặc null>,
  "reasoning": "<giải thích ngắn bằng tiếng Việt>"
}}

Tiêu chí:
- correctness (1-5): Thông tin có đúng không? (5 = hoàn toàn đúng)
- groundedness (1-5): Có bịa đặt thông tin không? (5 = không bịa đặt)
- completeness (1-5): Có đầy đủ các điểm chính không? (5 = đầy đủ)
- context_retention: Hệ thống có nhớ và dùng đúng ngữ cảnh từ lượt trước không?
  5 = nhớ hoàn toàn và dùng đúng
  3 = nhớ một phần, có sai sót nhỏ
  1 = quên hoặc mâu thuẫn với thông tin lượt trước
  null = lượt 1, không có context_dependency
"""


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------

@dataclass
class TurnScores:
    correctness: float
    groundedness: float
    completeness: float
    context_retention: float | None
    reasoning: str

    def passed(self) -> bool:
        return (
            self.correctness >= 3.5
            and self.groundedness >= 4.0
            and self.completeness >= 3.0
            and (self.context_retention is None or self.context_retention >= 3.0)
        )


@dataclass
class SingleResult:
    id: str
    category: str
    difficulty: str
    query_type: str
    question: str
    answer: str
    scores: TurnScores


@dataclass
class ConvTurnResult:
    turn: int
    question: str
    answer: str
    context_dependency: str | None
    scores: TurnScores


@dataclass
class ConvSetResult:
    set_id: str
    title: str
    session_id: str
    turns: list[ConvTurnResult] = field(default_factory=list)


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------

async def create_session(client: httpx.AsyncClient) -> str:
    r = await client.post("/session")
    r.raise_for_status()
    return r.json()["session_id"]


async def chat(client: httpx.AsyncClient, session_id: str, message: str) -> str:
    r = await client.post("/chat", json={"session_id": session_id, "message": message})
    r.raise_for_status()
    return r.json().get("reply", "")


# ---------------------------------------------------------------------------
# Judge
# ---------------------------------------------------------------------------

def _build_judge_client() -> object:
    api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY", "")
    if not api_key:
        # Try loading from backend .env
        env_file = _BACKEND_DIR / ".env"
        if env_file.exists():
            for line in env_file.read_text().splitlines():
                if line.startswith("GOOGLE_API_KEY="):
                    api_key = line.split("=", 1)[1].strip()
                    break
    if not api_key:
        print("ERROR: GOOGLE_API_KEY not set. Judge cannot run.")
        sys.exit(1)
    from google import genai
    return genai.Client(api_key=api_key, http_options={"api_version": "v1beta"})


def _call_judge(client: object, prompt: str) -> dict:
    from google.genai import types as gtypes
    resp = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=gtypes.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.0,
        ),
    )
    return json.loads(resp.text)


def judge_single(judge, question: str, expected_key_facts: list[str], answer: str) -> TurnScores:
    prompt = _SINGLE_JUDGE_PROMPT.format(
        question=question,
        expected_key_facts="\n".join(f"- {f}" for f in expected_key_facts),
        answer=answer,
    )
    raw = _call_judge(judge, prompt)
    return TurnScores(
        correctness=float(raw.get("correctness", 0)),
        groundedness=float(raw.get("groundedness", 0)),
        completeness=float(raw.get("completeness", 0)),
        context_retention=None,
        reasoning=raw.get("reasoning", ""),
    )


def judge_conv_turn(
    judge,
    turn: int,
    question: str,
    expected_key_facts: list[str],
    answer: str,
    history: list[dict],
    context_dependency: str | None,
) -> TurnScores:
    history_lines = [
        f"  Lượt {i + 1} [{h['role']}]: {h['content']}"
        for i, h in enumerate(history)
    ]
    history_text = "\n".join(history_lines) if history_lines else "(chưa có lịch sử)"
    prompt = _CONV_JUDGE_PROMPT.format(
        history_text=history_text,
        turn=turn,
        question=question,
        context_dependency=context_dependency or "Không có (lượt đầu tiên)",
        expected_key_facts="\n".join(f"- {f}" for f in expected_key_facts),
        answer=answer,
    )
    raw = _call_judge(judge, prompt)
    cr = raw.get("context_retention")
    return TurnScores(
        correctness=float(raw.get("correctness", 0)),
        groundedness=float(raw.get("groundedness", 0)),
        completeness=float(raw.get("completeness", 0)),
        context_retention=float(cr) if cr is not None else None,
        reasoning=raw.get("reasoning", ""),
    )


# ---------------------------------------------------------------------------
# Single-question eval
# ---------------------------------------------------------------------------

async def run_single_eval(
    client: httpx.AsyncClient,
    judge: object,
    questions: list[dict],
    delay: float,
) -> list[SingleResult]:
    results: list[SingleResult] = []
    total = len(questions)
    print(f"\nRunning single-question eval ({total} questions)...")

    for i, q in enumerate(questions, 1):
        qid = q["id"]
        question = q["question"]
        expected = q["expected_key_facts"]

        try:
            session_id = await create_session(client)
            answer = await chat(client, session_id, question)
            scores = judge_single(judge, question, expected, answer)

            mark = "✓" if scores.passed() else "✗"
            print(
                f"  [{i:2d}/{total}] {qid} — {q['category'][:18]:18s} "
                f"C={scores.correctness:.0f} G={scores.groundedness:.0f} "
                f"Comp={scores.completeness:.0f}  {mark}"
            )
            results.append(SingleResult(
                id=qid,
                category=q["category"],
                difficulty=q["difficulty"],
                query_type=q["query_type"],
                question=question,
                answer=answer,
                scores=scores,
            ))
        except Exception as e:
            print(f"  [{i:2d}/{total}] {qid} ERROR: {e}")
            results.append(SingleResult(
                id=qid, category=q["category"], difficulty=q["difficulty"],
                query_type=q["query_type"], question=question, answer=f"ERROR: {e}",
                scores=TurnScores(0, 0, 0, None, str(e)),
            ))

        await asyncio.sleep(delay)

    return results


# ---------------------------------------------------------------------------
# Conversation eval
# ---------------------------------------------------------------------------

async def run_conversation_eval(
    client: httpx.AsyncClient,
    judge: object,
    conv_sets: list[dict],
    delay: float,
) -> list[ConvSetResult]:
    results: list[ConvSetResult] = []
    total_sets = len(conv_sets)
    print(f"\nRunning conversation eval ({total_sets} sets)...")

    for conv in conv_sets:
        set_id = conv["set_id"]
        title = conv["title"]
        turns = conv["turns"]
        print(f"\n  [{set_id}] {title}")

        try:
            session_id = await create_session(client)
        except Exception as e:
            print(f"    Session creation failed: {e}")
            continue

        set_result = ConvSetResult(set_id=set_id, title=title, session_id=session_id)
        history: list[dict] = []

        for turn_data in turns:
            turn_num = turn_data["turn"]
            question = turn_data["question"]
            expected = turn_data["expected_key_facts"]
            context_dep = turn_data.get("context_dependency")

            try:
                answer = await chat(client, session_id, question)
                scores = judge_conv_turn(
                    judge, turn_num, question, expected, answer, history, context_dep
                )

                ret_str = f"Ret={scores.context_retention:.0f}" if scores.context_retention else "Ret=N/A"
                mark = "✓" if scores.passed() else "✗"
                print(
                    f"    Turn {turn_num}: C={scores.correctness:.0f} "
                    f"G={scores.groundedness:.0f} Comp={scores.completeness:.0f} "
                    f"{ret_str}  {mark}"
                )

                set_result.turns.append(ConvTurnResult(
                    turn=turn_num,
                    question=question,
                    answer=answer,
                    context_dependency=context_dep,
                    scores=scores,
                ))
                history.extend([
                    {"role": "user", "content": question},
                    {"role": "assistant", "content": answer},
                ])
            except Exception as e:
                print(f"    Turn {turn_num} ERROR: {e}")
                set_result.turns.append(ConvTurnResult(
                    turn=turn_num, question=question, answer=f"ERROR: {e}",
                    context_dependency=context_dep,
                    scores=TurnScores(0, 0, 0, None, str(e)),
                ))

            await asyncio.sleep(delay)

        results.append(set_result)

    return results


# ---------------------------------------------------------------------------
# Report & save
# ---------------------------------------------------------------------------

def _avg(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def print_report(
    tag: str,
    single: list[SingleResult],
    conv: list[ConvSetResult],
) -> None:
    print("\n" + "═" * 60)
    print(f"  EVAL REPORT  |  tag: {tag}  |  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("═" * 60)

    if single:
        c_vals = [r.scores.correctness for r in single]
        g_vals = [r.scores.groundedness for r in single]
        comp_vals = [r.scores.completeness for r in single]
        passed = sum(1 for r in single if r.scores.passed())
        print(f"\nSingle Questions ({len(single)}):")
        print(f"  Correctness:  {_avg(c_vals):.2f}/5.0")
        print(f"  Groundedness: {_avg(g_vals):.2f}/5.0")
        print(f"  Completeness: {_avg(comp_vals):.2f}/5.0")
        print(f"  Pass rate:    {passed}/{len(single)} ({100*passed//len(single)}%)")

    if conv:
        all_turns = [t for s in conv for t in s.turns]
        c_vals = [t.scores.correctness for t in all_turns]
        g_vals = [t.scores.groundedness for t in all_turns]
        comp_vals = [t.scores.completeness for t in all_turns]
        ret_vals = [t.scores.context_retention for t in all_turns if t.scores.context_retention]
        passed = sum(1 for t in all_turns if t.scores.passed())
        print(f"\nConversation Sets ({len(conv)} sets, {len(all_turns)} turns):")
        print(f"  Correctness:       {_avg(c_vals):.2f}/5.0")
        print(f"  Groundedness:      {_avg(g_vals):.2f}/5.0")
        print(f"  Completeness:      {_avg(comp_vals):.2f}/5.0")
        if ret_vals:
            print(f"  Context Retention: {_avg(ret_vals):.2f}/5.0 ({len(ret_vals)} turns evaluated)")
        print(f"  Pass rate:         {passed}/{len(all_turns)} ({100*passed//len(all_turns)}%)")

    print("═" * 60)


def save_results(
    tag: str,
    mode: str,
    base_url: str,
    single: list[SingleResult],
    conv: list[ConvSetResult],
    output_path: Path,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    def _scores_dict(s: TurnScores) -> dict:
        return asdict(s)

    payload = {
        "run_info": {
            "tag": tag,
            "mode": mode,
            "base_url": base_url,
            "timestamp": datetime.now().isoformat(),
        },
        "single_results": [
            {
                "id": r.id,
                "category": r.category,
                "difficulty": r.difficulty,
                "query_type": r.query_type,
                "question": r.question,
                "answer": r.answer,
                "scores": _scores_dict(r.scores),
                "passed": r.scores.passed(),
            }
            for r in single
        ],
        "conversation_results": [
            {
                "set_id": s.set_id,
                "title": s.title,
                "session_id": s.session_id,
                "turns": [
                    {
                        "turn": t.turn,
                        "question": t.question,
                        "answer": t.answer,
                        "context_dependency": t.context_dependency,
                        "scores": _scores_dict(t.scores),
                        "passed": t.scores.passed(),
                    }
                    for t in s.turns
                ],
            }
            for s in conv
        ],
    }

    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    print(f"\nResults saved → {output_path}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def main(args: argparse.Namespace) -> None:
    base_url = args.url.rstrip("/")
    delay = args.delay
    tag = args.tag

    # Health check
    try:
        async with httpx.AsyncClient(base_url=base_url, timeout=10) as hc:
            r = await hc.get("/health" if "/api/v1" not in base_url else "/../health")
    except Exception:
        # Fallback: try calling /session to see if the server is up
        pass

    judge = _build_judge_client()

    single_results: list[SingleResult] = []
    conv_results: list[ConvSetResult] = []

    async with httpx.AsyncClient(base_url=base_url, timeout=90) as client:
        if args.mode in ("single", "all"):
            if not _SINGLE_FILE.exists():
                print(f"WARN: {_SINGLE_FILE} not found — skipping single eval")
            else:
                questions = json.loads(_SINGLE_FILE.read_text())["questions"]
                single_results = await run_single_eval(client, judge, questions, delay)

        if args.mode in ("conversation", "all"):
            if not _CONV_FILE.exists():
                print(f"WARN: {_CONV_FILE} not found — skipping conversation eval")
            else:
                conv_sets = json.loads(_CONV_FILE.read_text())["conversation_sets"]
                conv_results = await run_conversation_eval(client, judge, conv_sets, delay)

    print_report(tag, single_results, conv_results)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = Path(args.output) if args.output else _RESULTS_DIR / f"eval_{ts}_{tag}.json"
    save_results(tag, args.mode, base_url, single_results, conv_results, output_path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="GraphRAG eval runner")
    parser.add_argument(
        "--mode",
        choices=["single", "conversation", "all"],
        default="all",
        help="Which eval set to run (default: all)",
    )
    parser.add_argument(
        "--tag",
        default="default",
        help="Label for this run, e.g. 'gemini' or 'openai' (default: default)",
    )
    parser.add_argument(
        "--output",
        default="",
        help="Path to save JSON results (default: results/eval_<timestamp>_<tag>.json)",
    )
    parser.add_argument(
        "--url",
        default="http://localhost:8000/api/v1",
        help="API base URL (default: http://localhost:8000/api/v1)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=1.0,
        help="Seconds between API calls to avoid rate limiting (default: 1.0)",
    )
    asyncio.run(main(parser.parse_args()))
