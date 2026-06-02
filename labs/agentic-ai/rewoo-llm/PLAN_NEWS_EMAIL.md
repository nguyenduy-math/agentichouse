# ReWOO Example 3: AI News Briefing → Vietnamese Email

**Planning document only — no implementation yet.**

---

## 1. Overview

This example demonstrates ReWOO's full agentic pipeline: the system performs parallel web research, synthesizes multi-source findings with an LLM, and produces a real, human-ready deliverable — a professional email — without any manual intervention.

Three capabilities are highlighted:

- **Parallel web search** — two independent `search` calls run concurrently via `asyncio.gather()`, cutting wall time roughly in half versus sequential execution.
- **Multi-source LLM synthesis** — `summarize_top3` merges two raw search result blobs and uses Claude Haiku to extract and rank the three most significant stories. This is the "reasoning" step that transforms noisy web text into structured facts.
- **Language-specific content generation** — `draft_email` takes the structured briefing and produces a polished Vietnamese team email complete with subject line, greeting, bullet points, and closing. The output is a real deliverable, not just an intermediate data structure.

This is the most "agentic" example in the series. Examples 1 and 2 answer questions; Example 3 produces an artifact someone can immediately send.

---

## 2. Architecture

```
Query: "Find the top 3 AI news stories today, summarize each in one sentence,
        then draft a Vietnamese email briefing for my team."
  │
  ├─→ search("top AI news today")        → #E1  ─┐
  │                                               │  parallel (asyncio.gather)
  └─→ search("AI breakthroughs this week") → #E2  ─┘
                          │
                          ▼
             summarize_top3(#E1, #E2)    → #E3   (LLM: Claude Haiku)
                          │
                          ▼
          draft_email(#E3, "Vietnamese") → #E4   (LLM: Claude Haiku)
                          │
                          ▼
                        Solver           → final answer (presents #E4)
```

**Dependency summary:**

| Step | Depends on | Execution |
|------|-----------|-----------|
| #E1  | —         | parallel group A |
| #E2  | —         | parallel group A |
| #E3  | #E1, #E2  | sequential, after group A |
| #E4  | #E3       | sequential, after #E3 |

---

## 3. Project Structure

Only new files are added. Existing files (`models.py`, `planner.py`, `worker.py`, `solver.py`, etc.) are extended, not replaced.

```
rewoo-llm/
├── tools/
│   ├── web_search.py        # NEW — DuckDuckGo search tool
│   ├── summarizer.py        # NEW — summarize_top3 via Claude Haiku
│   └── email_drafter.py     # NEW — draft_email via Claude Haiku
├── examples/
│   └── run_news_email.py    # NEW — entry point for this example
├── models.py                # unchanged
├── planner.py               # extend TOOL_REGISTRY
├── worker.py                # extend TOOL_REGISTRY
├── solver.py                # unchanged
├── requirements.txt         # append: duckduckgo-search
└── .env.example             # unchanged (ANTHROPIC_API_KEY already present)
```

---

## 4. Data Models

`models.py` requires **no changes**. The existing `Step`, `Plan`, and `Evidence` models handle this example as-is:

- `Step.tool` → `"search"`, `"summarize_top3"`, or `"draft_email"`
- `Step.args` → list of strings or `#E` references
- `Evidence.value` → raw string output of each tool call

The only new wire-up is registering three new callables in `TOOL_REGISTRY`.

---

## 5. Tool Specifications

### 5.1 `search(query: str) -> str`

**File:** `tools/web_search.py`

Uses the `duckduckgo-search` package — no API key required.

```python
from duckduckgo_search import DDGS
import time

def search(query: str) -> str:
    """Search DuckDuckGo and return top 5 result snippets as a single string."""
    for attempt in range(2):
        try:
            results = DDGS().text(query, max_results=5)
            if not results:
                return f"[No results found for: {query}]"
            parts = []
            for r in results:
                title = r.get("title", "")
                body  = r.get("body", "")
                parts.append(f"- {title}: {body}")
            return "\n".join(parts)
        except Exception as e:
            if attempt == 0:
                time.sleep(2)   # rate-limit back-off
                continue
            return f"[Search error: {e}]"
```

**Error handling:**
- Rate limit → sleep 2 s, retry once.
- No results → return descriptive placeholder so downstream LLM steps degrade gracefully.
- Any other exception on second attempt → return error string (never raise; keeps the pipeline running).

---

### 5.2 `summarize_top3(results1: str, results2: str) -> str`

**File:** `tools/summarizer.py`

Merges the two search result strings and calls Claude Haiku to extract the three most significant AI stories.

```python
import anthropic

_client = anthropic.Anthropic()

SYSTEM_PROMPT = (
    "You are a tech journalist. Given news search results, identify the "
    "3 most significant AI stories. For each story return: Title, "
    "One-sentence summary. Format as a numbered list."
)

def summarize_top3(results1: str, results2: str) -> str:
    """Identify the 3 most significant AI stories from combined search results."""
    combined = f"=== Source 1 ===\n{results1}\n\n=== Source 2 ===\n{results2}"
    message = _client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=512,
        messages=[
            {"role": "user", "content": combined}
        ],
        system=SYSTEM_PROMPT,
    )
    return message.content[0].text
```

**Expected output format:**
```
1. GPT-5 Launch: OpenAI released GPT-5, claiming a 30% improvement in reasoning benchmarks over GPT-4o.
2. Claude 4 Release: Anthropic unveiled Claude 4 with enhanced coding and multilingual capabilities.
3. Meta LLaMA 4: Meta open-sourced LLaMA 4, enabling on-device fine-tuning for the first time.
```

---

### 5.3 `draft_email(briefing: str, language: str) -> str`

**File:** `tools/email_drafter.py`

Takes the structured briefing from `summarize_top3` and writes a complete professional email.

```python
import anthropic

_client = anthropic.Anthropic()

SYSTEM_PROMPT = (
    "You are a professional assistant. Draft a team briefing email in "
    "{language} based on these AI news stories. Include: Subject line, "
    "Greeting, 3 bullet points (one per story), Professional closing. "
    "Be concise and engaging."
)

def draft_email(briefing: str, language: str = "Vietnamese") -> str:
    """Draft a professional team email in the specified language."""
    message = _client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        messages=[
            {"role": "user", "content": briefing}
        ],
        system=SYSTEM_PROMPT.format(language=language),
    )
    return message.content[0].text
```

**Expected output format (Vietnamese):**
```
Chủ đề: Tin tức AI nổi bật tuần này

Kính gửi team,

Dưới đây là 3 tin tức AI đáng chú ý nhất:

• GPT-5 ra mắt: OpenAI phát hành GPT-5 với cải tiến 30% về khả năng suy luận.
• Claude 4: Anthropic ra mắt Claude 4 với năng lực lập trình và đa ngôn ngữ được nâng cao.
• LLaMA 4 mã nguồn mở: Meta công bố LLaMA 4 hỗ trợ fine-tuning trực tiếp trên thiết bị.

Trân trọng,
[Tên]
```

---

## 6. Planner

### Prompt Template

```python
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
- Independent steps (no shared dependencies) can be listed without ordering — the worker will parallelize them
- No explanation, only the Plan block
"""

PLANNER_USER = "Task: {query}"
```

### Expected Planner Output

```
Plan:
#E1 = search["top AI news today"]
#E2 = search["AI breakthroughs this week"]
#E3 = summarize_top3[#E1, #E2]
#E4 = draft_email[#E3, Vietnamese]
```

### Parsing Logic

```python
import re

STEP_PATTERN = re.compile(
    r"(#E\d+)\s*=\s*(\w+)\[([^\]]*)\]"
)

def parse_plan(plan_text: str) -> list[dict]:
    steps = []
    for match in STEP_PATTERN.finditer(plan_text):
        var, tool, raw_args = match.groups()
        # Split on comma, strip whitespace/quotes
        args = [a.strip().strip('"\'') for a in raw_args.split(",") if a.strip()]
        steps.append({"var": var, "tool": tool, "args": args})
    return steps

def build_dependency_graph(steps: list[dict]) -> dict[str, set[str]]:
    """Returns {var: {vars it depends on}}."""
    deps = {}
    for step in steps:
        step_deps = set()
        for arg in step["args"]:
            if re.match(r"#E\d+", arg):
                step_deps.add(arg)
        deps[step["var"]] = step_deps
    return deps
```

**Dependency graph for this example:**
```python
{
    "#E1": set(),           # no deps → parallel group
    "#E2": set(),           # no deps → parallel group
    "#E3": {"#E1", "#E2"},  # waits for both
    "#E4": {"#E3"},         # waits for #E3
}
```

---

## 7. Worker — Parallel Execution Design

The worker uses `asyncio` throughout. Synchronous tool calls (DuckDuckGo search, which is blocking I/O) are offloaded with `asyncio.to_thread()`.

### Execution Algorithm

```python
import asyncio

async def execute_step(step: dict, evidence: dict, tool_registry: dict) -> str:
    """Resolve #E references in args, then call the tool."""
    resolved_args = [
        evidence.get(arg, arg)   # replace #En with its value, else pass as-is
        for arg in step["args"]
    ]
    tool_fn = tool_registry[step["tool"]]
    # Wrap sync tools to avoid blocking the event loop
    return await asyncio.to_thread(tool_fn, *resolved_args)

async def run_worker(steps: list[dict], tool_registry: dict) -> dict:
    evidence = {}
    deps = build_dependency_graph(steps)

    # Identify execution waves: steps whose deps are all satisfied
    remaining = list(steps)
    while remaining:
        # Find all steps whose dependencies are already in evidence
        ready = [s for s in remaining if deps[s["var"]].issubset(evidence.keys())]
        if not ready:
            raise RuntimeError("Circular dependency or unresolved reference")

        if len(ready) > 1:
            print(f"[Worker] Running {[s['var'] for s in ready]} in parallel...")
        else:
            print(f"[Worker] Running {ready[0]['var']}...")

        # Run the ready wave in parallel
        results = await asyncio.gather(
            *[execute_step(s, evidence, tool_registry) for s in ready]
        )
        for step, result in zip(ready, results):
            evidence[step["var"]] = result
            print(f"  → {step['var']} = {repr(result[:80])}...")

        for s in ready:
            remaining.remove(s)

    return evidence
```

### Wave execution for this example:

| Wave | Steps | Method |
|------|-------|--------|
| 1    | #E1, #E2 | `asyncio.gather(search, search)` |
| 2    | #E3      | `asyncio.to_thread(summarize_top3, e1, e2)` |
| 3    | #E4      | `asyncio.to_thread(draft_email, e3, "Vietnamese")` |

---

## 8. Solver

The solver receives the original query and the full evidence dict. For this example, `#E4` already contains the complete email — the solver's job is simply to present it cleanly.

### Solver Prompt

```python
SOLVER_SYSTEM = """You are a helpful assistant. Given a task and the evidence
collected by previous tool calls, produce the final answer.
For email drafts: present the email clearly with a separator line.
Do not add commentary beyond what was requested."""

SOLVER_USER = """Task: {query}

Evidence:
{evidence_block}

Final answer:"""
```

**Evidence block for this example:**

```
#E1 = [raw search snippets for "top AI news today"]
#E2 = [raw search snippets for "AI breakthroughs this week"]
#E3 = 1. GPT-5 Launch: ...
      2. Claude 4: ...
      3. LLaMA 4: ...
#E4 = Chủ đề: Tin tức AI nổi bật tuần này
      Kính gửi team, ...
```

The solver confirms the content of `#E4` and presents it as the final answer. No additional LLM synthesis is needed — `#E4` is already the deliverable.

---

## 9. Expected Console Output

```
[Planner] Generating plan...

Plan:
  #E1 = search["top AI news today"]
  #E2 = search["AI breakthroughs this week"]
  #E3 = summarize_top3[#E1, #E2]
  #E4 = draft_email[#E3, Vietnamese]

[Worker] Running #E1 and #E2 in parallel...
  → #E1 = "- OpenAI releases GPT-5: The new model outperforms GPT-4o on reasoning..."
  → #E2 = "- Anthropic Claude 4: Anthropic's latest model sets new benchmarks..."
[Worker] Running #E3...
  → #E3 = "1. GPT-5 Launch: OpenAI released GPT-5, claiming a 30% improvement..."
[Worker] Running #E4...
  → #E4 = "Chủ đề: Tin tức AI nổi bật tuần này\n\nKính gửi team,..."

[Solver] Finalizing answer...

--- EMAIL DRAFT ---
Chủ đề: Tin tức AI nổi bật tuần này

Kính gửi team,

Dưới đây là 3 tin tức AI đáng chú ý nhất tuần này:

• GPT-5 ra mắt: OpenAI phát hành GPT-5 với cải tiến 30% về khả năng suy luận so với GPT-4o.
• Claude 4: Anthropic ra mắt Claude 4 với năng lực lập trình và đa ngôn ngữ được nâng cao đáng kể.
• LLaMA 4 mã nguồn mở: Meta công bố LLaMA 4, lần đầu tiên hỗ trợ fine-tuning trực tiếp trên thiết bị.

Trân trọng,
[Tên của bạn]
-------------------
```

---

## 10. Key Design Decisions

### Why does `summarize_top3` take both #E1 and #E2 as arguments?

ReWOO's strength is that the planner can express multi-source merging explicitly in the plan. Passing both search results as separate arguments to `summarize_top3` means:

1. The dependency graph is unambiguous — #E3 provably waits for both #E1 and #E2.
2. The tool itself controls how sources are merged, keeping the worker generic.
3. If either search returns sparse results, the LLM still has the other source to draw from — graceful degradation built into the data flow.

An alternative would be a single `search_and_summarize(q1, q2)` mega-tool, but that forfeits parallelism and makes the tool non-reusable.

### Why is `draft_email` a tool rather than handled by the Solver?

The Solver is intended to be a thin presentation layer — it synthesizes evidence into a final answer. Putting email drafting in the Solver would:

- Couple language selection to the solver prompt (fragile).
- Make the pipeline non-reusable: a different entry point couldn't call `draft_email` independently.
- Blur the line between "what the plan computed" and "how we present it."

By making `draft_email` an explicit tool step (#E4), the Solver merely confirms and displays a pre-computed artifact. This also means the email can be logged, cached, or reused as `#E4` by a hypothetical future step (e.g., `send_email[#E4, recipients]`).

---

## 11. Implementation Order

1. **`models.py`** — confirm no changes needed; verify `Step`, `Plan`, `Evidence` types cover multi-arg tools.
2. **`tools/web_search.py`** — implement `search()` with DuckDuckGo, rate-limit retry, graceful empty-result handling.
3. **`tools/summarizer.py`** — implement `summarize_top3()` with Claude Haiku; test with mocked search strings.
4. **`tools/email_drafter.py`** — implement `draft_email()` with Claude Haiku; test independently with a hardcoded briefing.
5. **`worker.py`** — extend with `asyncio`-based wave executor and `asyncio.to_thread()` wrapper; register new tools in `TOOL_REGISTRY`.
6. **`planner.py`** — add planner prompt, `parse_plan()`, and `build_dependency_graph()`; register new tools in tool description block.
7. **`solver.py`** — verify solver prompt handles email passthrough cleanly; add `--- EMAIL DRAFT ---` formatting for email outputs.
8. **`examples/run_news_email.py`** — wire planner → worker → solver; add `asyncio.run()` entry point; print formatted output.
9. **Manual test** — run end-to-end; verify parallel execution from console timestamps; inspect Vietnamese email quality.
10. **Edge case test** — mock DuckDuckGo returning empty results; confirm pipeline completes with degraded-but-valid email.
