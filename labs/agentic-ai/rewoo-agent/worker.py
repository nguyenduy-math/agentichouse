import asyncio
from typing import Callable

from models import Plan
from planner import build_dependency_graph
from tools import search, summarize_top3, draft_email

TOOL_REGISTRY: dict[str, Callable] = {
    "search": search,
    "summarize_top3": summarize_top3,
    "draft_email": draft_email,
}


async def _execute_step(step, evidence: dict[str, str]) -> str:
    """Resolve #E references in args and call the tool asynchronously."""
    resolved_args = [evidence.get(arg, arg) for arg in step.args]
    tool_fn = TOOL_REGISTRY.get(step.tool)
    if tool_fn is None:
        raise ValueError(f"Unknown tool: {step.tool}")
    return await asyncio.to_thread(tool_fn, *resolved_args)


async def run_worker(plan: Plan) -> dict[str, str]:
    """Execute the plan using wave-based parallel execution."""
    evidence: dict[str, str] = {}
    deps = build_dependency_graph(plan)
    remaining = list(plan.steps)

    while remaining:
        # Find all steps whose dependencies are already resolved
        ready = [s for s in remaining if deps[s.var].issubset(evidence.keys())]
        if not ready:
            raise RuntimeError("Circular dependency or unresolved #E reference in plan.")

        if len(ready) > 1:
            var_names = " and ".join(s.var for s in ready)
            print(f"[Worker] Running {var_names} in parallel...")
        else:
            print(f"[Worker] Running {ready[0].var}: {ready[0].tool}...")

        results = await asyncio.gather(
            *[_execute_step(s, evidence) for s in ready]
        )

        for step, result in zip(ready, results):
            evidence[step.var] = result
            preview = repr(result[:80]).rstrip("'") + "...'"
            print(f"  → {step.var} = {preview}")
            remaining.remove(step)

    return evidence
