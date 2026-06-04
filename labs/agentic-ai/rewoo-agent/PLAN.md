# ReWOO Agent — Implementation Plan

## 1. Overview

**ReWOO** (Reasoning WithOut Observation) is an LLM agent architecture that separates _planning_ from _execution_. Unlike ReAct-style agents that interleave reasoning and tool calls in a loop, ReWOO:

1. Makes **one LLM call** to produce a complete plan upfront.
2. **Executes** all tool calls (workers) without touching the LLM again.
3. Makes **one final LLM call** to synthesize the results into an answer.

This means only 2 LLM calls total, regardless of how many tool steps the plan has. Tool calls that don't depend on each other can run in parallel.

**Why this example works well:** The query _"What is the weather in the capital of France, and convert 100 EUR to USD?"_ requires three tool steps with a mix of dependencies and independence:

- `#E1` = look up capital of France (prerequisite for weather)
- `#E2` = get weather for `#E1` (depends on `#E1`)
- `#E3` = currency conversion (fully independent — runs in parallel with `#E2`)

This cleanly illustrates dependency resolution and parallel execution.

---

## 2. Architecture

```
User Query
    │
    ▼
┌─────────┐   one LLM call   ┌──────────────────────────┐
│ Planner │ ───────────────▶ │ Plan (list of Steps)     │
└─────────┘                  │  #E1 = search[...]        │
                             │  #E2 = get_weather[#E1]   │
                             │  #E3 = convert_currency[…]│
                             └────────────┬─────────────┘
                                          │
                    ┌─────────────────────▼──────────────────────┐
                    │              Worker                         │
                    │  resolve deps → run independent steps       │
                    │  in parallel via asyncio.gather             │
                    │                                             │
                    │  #E1 ──▶ search("capital of France")        │
                    │            └──▶ "Paris"                     │
                    │  #E2 ──▶ get_weather("Paris")  (after #E1) │
                    │            └──▶ "Cloudy, 18°C"              │
                    │  #E3 ──▶ convert_currency(100, EUR, USD)   │
                    │            └──▶ "108.50 USD"  (parallel)   │
                    └────────────────────┬───────────────────────┘
                                         │  {#E1, #E2, #E3} values
                                         ▼
                              ┌──────────────────┐
                              │     Solver        │  one LLM call
                              │  question + all   │ ───────────▶ Final Answer
                              │  #E values        │
                              └──────────────────┘
```

---

## 3. Project Structure

```
rewoo-llm/
├── main.py              # Entry point — wires Planner → Worker → Solver
├── planner.py           # LLM call → structured Plan object
├── worker.py            # Resolves #E refs, runs tools, parallelises
├── solver.py            # LLM call → final natural-language answer
├── models.py            # Dataclasses: Step, Plan, WorkerResult
├── tools/
│   ├── __init__.py      # Tool registry dict
│   ├── search.py        # Mock search tool
│   ├── weather.py       # Mock weather tool
│   └── currency.py      # Real HTTP call to frankfurter.app
├── .env.example         # Environment variable template
└── requirements.txt     # Python dependencies
```

---

## 4. Data Models (`models.py`)

Use Python `dataclasses` (no external dependency).

```python
from dataclasses import dataclass, field

@dataclass
class Step:
    result_var: str          # e.g. "#E1"
    tool: str                # e.g. "search"
    args: list[str]          # e.g. ["capital of France"]
                             # args may contain "#E1", "#E2" references

@dataclass
class Plan:
    steps: list[Step] = field(default_factory=list)

@dataclass
class WorkerResult:
    var: str                 # e.g. "#E1"
    value: str               # e.g. "Paris"
```

**Key invariant:** `args` are always strings. When an arg is a `#E` reference, the worker substitutes it at runtime. Args that are numeric (e.g. `100`) are still stored as strings and cast by the tool if needed.

---

## 5. Planner Design (`planner.py`)

### System prompt

```
You are a planning agent. Given a question and a list of available tools,
produce a step-by-step plan. Each step assigns a result to a variable #E<n>.
Variables from earlier steps may be referenced in later step arguments.

Available tools:
- search(query: str) -> str
- get_weather(city: str) -> str
- convert_currency(amount: str, from_currency: str, to_currency: str) -> str

Output format — output ONLY the plan, nothing else:

Plan:
#E1 = tool_name[arg1, arg2, ...]
#E2 = tool_name[#E1, arg2, ...]
...
```

### User prompt

```
Question: {question}
```

### Expected LLM output for our example

```
Plan:
#E1 = search[capital of France]
#E2 = get_weather[#E1]
#E3 = convert_currency[100, EUR, USD]
```

### Parsing logic

Parse the LLM output line by line. For each line matching `#E\d+ = \w+\[.*\]`:

```python
import re

LINE_RE = re.compile(r"(#E\d+)\s*=\s*(\w+)\[([^\]]*)\]")

def parse_plan(text: str) -> Plan:
    steps = []
    for line in text.splitlines():
        m = LINE_RE.match(line.strip())
        if m:
            var, tool, args_str = m.group(1), m.group(2), m.group(3)
            args = [a.strip() for a in args_str.split(",") if a.strip()]
            steps.append(Step(result_var=var, tool=tool, args=args))
    return Plan(steps=steps)
```

### LLM call

```python
import anthropic, os

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

def make_plan(question: str) -> Plan:
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=512,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": f"Question: {question}"}],
    )
    raw = response.content[0].text
    return parse_plan(raw)
```

---

## 6. Worker Design (`worker.py`)

### Dependency resolution

The plan is already ordered (planner outputs steps in dependency order). Worker uses a **sequential scan with substitution**: iterate steps in order, and before running each step, replace any `#E` references in `args` with the already-resolved value from a `results: dict[str, str]`.

No need for a full topological sort — the LLM outputs steps in valid execution order. However, **independent steps** (those whose args contain no unresolved `#E` refs at the current moment) can be batched and run in parallel.

### Parallelisation algorithm

```
resolved = {}
pending = list(plan.steps)

while pending:
    # find all steps whose args are fully resolved
    ready = [s for s in pending if all_args_resolved(s, resolved)]
    
    # run them in parallel
    results = asyncio.gather(*[run_step(s, resolved) for s in ready])
    
    for step, result in zip(ready, results):
        resolved[step.result_var] = result
    
    pending = [s for s in pending if s not in ready]
```

`all_args_resolved(step, resolved)` returns `True` if every arg that starts with `#` is already a key in `resolved`.

### Step execution

```python
async def run_step(step: Step, resolved: dict[str, str]) -> str:
    # substitute #E references
    args = [resolved.get(a, a) for a in step.args]
    # look up tool function
    tool_fn = TOOLS[step.tool]          # from tools/__init__.py
    # tools are sync; run in thread pool to not block event loop
    return await asyncio.to_thread(tool_fn, *args)
```

### Return value

`execute_plan(plan) -> list[WorkerResult]` — returns results in `#E1, #E2, ...` order.

---

## 7. Solver Design (`solver.py`)

### System prompt

```
You are a helpful assistant. You will be given a question and a set of
evidence collected by tools. Use the evidence to answer the question
concisely and accurately.
```

### User prompt

```
Question: {question}

Evidence:
#E1 = {value of #E1}
#E2 = {value of #E2}
#E3 = {value of #E3}

Answer the question using the evidence above.
```

### LLM call

```python
def solve(question: str, results: list[WorkerResult]) -> str:
    evidence = "\n".join(f"{r.var} = {r.value}" for r in results)
    user_msg = f"Question: {question}\n\nEvidence:\n{evidence}\n\nAnswer the question using the evidence above."
    
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=256,
        system=SOLVER_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_msg}],
    )
    return response.content[0].text.strip()
```

---

## 8. Tool Implementations

### `tools/__init__.py` — Tool registry

```python
from .search import search
from .weather import get_weather
from .currency import convert_currency

TOOLS: dict[str, callable] = {
    "search": search,
    "get_weather": get_weather,
    "convert_currency": convert_currency,
}
```

### `tools/search.py` — Mock search

```python
def search(query: str) -> str:
    """Mock search. Returns hardcoded answers for known queries."""
    query_lower = query.lower()
    if "capital" in query_lower and "france" in query_lower:
        return "Paris"
    return f"[mock result for: {query}]"
```

### `tools/weather.py` — Mock weather

```python
def get_weather(city: str) -> str:
    """Mock weather lookup."""
    mock_data = {
        "paris": "Cloudy, 18°C",
        "london": "Rainy, 12°C",
        "new york": "Sunny, 24°C",
    }
    return mock_data.get(city.lower(), f"Weather data unavailable for {city}")
```

### `tools/currency.py` — Real HTTP call

Uses the free [Frankfurter API](https://www.frankfurter.app/) — no API key required.

```python
import httpx

def convert_currency(amount: str, from_currency: str, to_currency: str) -> str:
    """Convert currency using live rates from frankfurter.app."""
    url = "https://api.frankfurter.app/latest"
    params = {"from": from_currency.strip(), "to": to_currency.strip()}
    
    response = httpx.get(url, params=params, timeout=10)
    response.raise_for_status()
    
    data = response.json()
    rate = data["rates"][to_currency.strip().upper()]
    converted = float(amount) * rate
    
    return f"{converted:.2f} {to_currency.strip().upper()}"
```

**Error handling:** Wrap in try/except; return an error string rather than raising, so the solver can still produce a partial answer.

---

## 9. LLM Provider

- **Model:** `claude-haiku-4-5-20251001` (fast, cheap, sufficient for planning/solving)
- **SDK:** `anthropic` Python SDK (sync client; async not needed since only 2 calls)
- **Config:** `ANTHROPIC_API_KEY` loaded via `python-dotenv` from `.env`

Load env at startup in `main.py`:

```python
from dotenv import load_dotenv
load_dotenv()
```

---

## 10. Implementation Order

Build in this order to enable incremental testing at each step:

1. **`models.py`** — dataclasses only, no deps. Verify with a quick `python -c "from models import Step"`.
2. **`tools/search.py`** and **`tools/weather.py`** — pure mock functions, no deps.
3. **`tools/currency.py`** — real HTTP; test standalone with `python -c "from tools.currency import convert_currency; print(convert_currency('100','EUR','USD'))"`.
4. **`tools/__init__.py`** — assemble the registry dict.
5. **`planner.py`** — implement `parse_plan` first and unit-test it against a hardcoded string, then wire in the LLM call.
6. **`worker.py`** — implement `execute_plan` with the parallelisation loop; test by passing a hand-crafted `Plan` object.
7. **`solver.py`** — straightforward LLM call; test with hand-crafted `WorkerResult` list.
8. **`main.py`** — wire everything together, add console output, load `.env`.
9. **End-to-end test** — run `python main.py` and verify output matches expected.

---

## 11. `main.py` Wiring

```python
import asyncio
from dotenv import load_dotenv
from planner import make_plan
from worker import execute_plan
from solver import solve

load_dotenv()

QUESTION = "What is the weather in the capital of France, and convert 100 EUR to USD?"

async def main():
    print(f"Question: {QUESTION}\n")

    print("── Planner ──────────────────────────────")
    plan = make_plan(QUESTION)
    for step in plan.steps:
        print(f"  {step.result_var} = {step.tool}({step.args})")

    print("\n── Worker ───────────────────────────────")
    results = await execute_plan(plan)
    for r in results:
        print(f"  {r.var} = {r.value}")

    print("\n── Solver ───────────────────────────────")
    answer = solve(QUESTION, results)
    print(f"\nFinal Answer:\n{answer}")

asyncio.run(main())
```

---

## 12. Expected Console Output

```
Question: What is the weather in the capital of France, and convert 100 EUR to USD?

── Planner ──────────────────────────────
  #E1 = search(['capital of France'])
  #E2 = get_weather(['#E1'])
  #E3 = convert_currency(['100', 'EUR', 'USD'])

── Worker ───────────────────────────────
  #E1 = Paris
  #E2 = Cloudy, 18°C
  #E3 = 108.50 USD

── Solver ───────────────────────────────

Final Answer:
The weather in Paris, the capital of France, is currently cloudy with a
temperature of 18°C. Additionally, 100 EUR is equivalent to approximately
108.50 USD at the current exchange rate.
```

> **Note:** `#E1` and `#E2` run sequentially (weather depends on the city name). `#E3` runs in parallel with `#E2` since it has no dependencies. The exact USD amount will vary with live exchange rates.

---

## 13. Environment & Dependencies

### `.env.example`

```
ANTHROPIC_API_KEY=your_key_here
```

### `requirements.txt`

```
anthropic
httpx
python-dotenv
```

Install with:

```bash
pip install -r requirements.txt
```

Python 3.11+ recommended (uses `asyncio.to_thread`, walrus operator, `dataclasses`).
