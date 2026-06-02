import os
import re
import anthropic

from models import Step, Plan

PLANNER_SYSTEM = """You are a planning agent. Given a task, output a step-by-step plan
using available tools. Use #E1, #E2, ... to name evidence variables.
Reference earlier variables by name in later steps.

Available tools:
- search(query)                          — web search, returns text snippets
- summarize_top3(results1, results2)     — LLM: pick top 3 AI stories from two sources
- draft_email(briefing, language)        — LLM: write a professional email

Output format (strictly):
Plan:
#E1 = tool_name[arg1, arg2, ...]
#E2 = tool_name[arg1, ...]
...

Rules:
- Use #En references to pass outputs between steps
- Independent steps (no shared dependencies) can be listed in any order — the worker will parallelize them
- No explanation, only the Plan block"""

PLANNER_USER = "Task: {query}"

STEP_PATTERN = re.compile(r"(#E\d+)\s*=\s*(\w+)\[([^\]]*)\]")


def parse_plan(plan_text: str) -> Plan:
    """Parse LLM plan output into a Plan object."""
    steps = []
    for match in STEP_PATTERN.finditer(plan_text):
        var, tool, raw_args = match.groups()
        args = [a.strip().strip("\"'") for a in raw_args.split(",") if a.strip()]
        steps.append(Step(var=var, tool=tool, args=args))
    return Plan(steps=steps)


def build_dependency_graph(plan: Plan) -> dict[str, set[str]]:
    """Returns {var: set of vars it depends on}."""
    deps: dict[str, set[str]] = {}
    for step in plan.steps:
        step_deps: set[str] = set()
        for arg in step.args:
            if re.match(r"#E\d+", arg):
                step_deps.add(arg)
        deps[step.var] = step_deps
    return deps


def generate_plan(query: str) -> Plan:
    """Call the LLM to generate a ReWOO plan for the given query."""
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=512,
        system=PLANNER_SYSTEM,
        messages=[{"role": "user", "content": PLANNER_USER.format(query=query)}],
    )
    plan_text = message.content[0].text
    return parse_plan(plan_text)
