import asyncio
import os
import sys

# Allow imports from the project root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from planner import generate_plan
from worker import run_worker
from solver import solve

QUERY = (
    "Find the top 3 AI news stories today, summarize each in one sentence, "
    "then draft a Vietnamese email briefing for my team."
)


async def main():
    # ── Planner ──────────────────────────────────────────────
    print("[Planner] Generating plan...\n")
    plan = generate_plan(QUERY)

    print("Plan:")
    for step in plan.steps:
        args_str = ", ".join(step.args)
        print(f"  {step.var} = {step.tool}[{args_str}]")
    print()

    # ── Worker ───────────────────────────────────────────────
    evidence = await run_worker(plan)

    # ── Solver ───────────────────────────────────────────────
    answer = solve(QUERY, evidence)

    print("\n--- EMAIL DRAFT ---")
    print(answer)
    print("-------------------")


if __name__ == "__main__":
    asyncio.run(main())
