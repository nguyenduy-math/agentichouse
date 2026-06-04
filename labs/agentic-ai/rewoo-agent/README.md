# ReWOO LLM — Reasoning WithOut Observation

A collection of ReWOO agent examples built with Python and Claude. ReWOO separates planning from execution — the LLM generates a full plan upfront, tools run without further LLM involvement, and a final solver produces the answer. Fewer API calls, parallel execution, lower cost.

---

## What is ReWOO?

Standard ReAct agents loop: **Think → Act → Observe → Think → Act…** — one LLM call per step, strictly sequential.

ReWOO uses three phases instead:

| Phase | Who runs it | LLM call? |
|-------|-------------|-----------|
| **Planner** | LLM generates the full plan upfront with `#E1`, `#E2`… variable references | ✅ Once |
| **Worker** | Executes each tool call, resolves `#E` variables, parallelises independent steps | ❌ No |
| **Solver** | Takes original question + all tool results → writes final answer | ✅ Once |

**Total LLM calls: 2** regardless of how many tool steps the plan has.

---

## Examples

### Example 1 — Weather + Currency (`PLAN.md`)

> "What is the weather in the capital of France, and convert 100 EUR to USD?"

```
#E1 = search["capital of France"]        ← parallel
#E2 = convert_currency[100, EUR, USD]    ← parallel
#E3 = get_weather[#E1]                   ← waits for #E1
```

Demonstrates: parallel independent steps, sequential dependency chain.

---

### Example 2 — Invoice PDF → Currency Conversion (`PLAN_DOC_CALC.md`)

> "Read the invoice PDF, extract the total amount, and convert it from JPY to VND."

```
#E1 = scan_pdf["invoice.pdf"]
#E2 = extract_total[#E1]
#E3 = convert_currency[#E2, JPY, VND]
```

Demonstrates: pure sequential chain, LLM-powered field extraction as a tool step.

---

### Example 3 — AI News → Vietnamese Email (`PLAN_NEWS_EMAIL.md`) ✅ Implemented

> "Find the top 3 AI news stories today, summarize each in one sentence, then draft a Vietnamese email briefing for my team."

```
#E1 = search["top AI news today"]           ← parallel
#E2 = search["AI breakthroughs this week"]  ← parallel
#E3 = summarize_top3[#E1, #E2]              ← waits for both
#E4 = draft_email[#E3, Vietnamese]          ← waits for #E3
```

Demonstrates: parallel web search, multi-source LLM synthesis, language-specific content generation.

---

## Project Structure

```
rewoo-llm/
├── models.py                  Step, Plan, Evidence dataclasses
├── planner.py                 LLM plan generation, parsing, dependency graph
├── worker.py                  Async wave executor — asyncio.gather() for parallel steps
├── solver.py                  Final answer generation
├── tools/
│   ├── __init__.py
│   ├── web_search.py          DuckDuckGo search (no API key needed)
│   ├── summarizer.py          summarize_top3() via Claude Haiku
│   └── email_drafter.py       draft_email() via Claude Haiku
├── examples/
│   └── run_news_email.py      Entry point for Example 3
├── PLAN.md                    Design doc — Example 1
├── PLAN_DOC_CALC.md           Design doc — Example 2
├── PLAN_NEWS_EMAIL.md         Design doc — Example 3
├── .env.example
└── requirements.txt
```

---

## Getting Started

```bash
cd rewoo-llm

# Install dependencies
pip install -r requirements.txt

# Set up API key
cp .env.example .env
# Edit .env and add: ANTHROPIC_API_KEY=your_key_here

# Run Example 3 (News → Email)
python examples/run_news_email.py
```

---

## Expected Output

```
[Planner] Generating plan...

Plan:
  #E1 = search[top AI news today]
  #E2 = search[AI breakthroughs this week]
  #E3 = summarize_top3[#E1, #E2]
  #E4 = draft_email[#E3, Vietnamese]

[Worker] Running #E1 and #E2 in parallel...
  → #E1 = '- OpenAI releases GPT-5: The new model outperforms...'
  → #E2 = '- Anthropic Claude 4: Anthropic latest model sets...'
[Worker] Running #E3: summarize_top3...
  → #E3 = '1. GPT-5 Launch: OpenAI released GPT-5, claiming a 30%...'
[Worker] Running #E4: draft_email...
  → #E4 = 'Chủ đề: Tin tức AI nổi bật tuần này...'

[Solver] Finalizing answer...

--- EMAIL DRAFT ---
Chủ đề: Tin tức AI nổi bật tuần này

Kính gửi team,

Dưới đây là 3 tin tức AI đáng chú ý nhất tuần này:

• GPT-5 ra mắt: OpenAI phát hành GPT-5 với cải tiến 30% về khả năng suy luận.
• Claude 4: Anthropic ra mắt Claude 4 với năng lực lập trình và đa ngôn ngữ được nâng cao.
• LLaMA 4 mã nguồn mở: Meta công bố LLaMA 4, hỗ trợ fine-tuning trực tiếp trên thiết bị.

Trân trọng,
[Tên của bạn]
-------------------
```

---

## How Parallel Execution Works

The worker builds a dependency graph from the plan's `#E` references, then executes steps in "waves" — all steps in a wave are independent and run simultaneously via `asyncio.gather()`.

For Example 3:

| Wave | Steps | How |
|------|-------|-----|
| 1 | `#E1`, `#E2` | `asyncio.gather()` — both searches fire at once |
| 2 | `#E3` | waits for wave 1, then runs summarizer |
| 3 | `#E4` | waits for `#E3`, then drafts email |

Synchronous tools (DuckDuckGo) are wrapped with `asyncio.to_thread()` to avoid blocking the event loop.

---

## Models Used

| Tool | Model | Why |
|------|-------|-----|
| Planner | `claude-haiku-4-5-20251001` | Cheap, fast, sufficient for plan generation |
| `summarize_top3` | `claude-haiku-4-5-20251001` | Short input/output, no heavy reasoning needed |
| `draft_email` | `claude-haiku-4-5-20251001` | Templated task, Haiku handles it well |
| Solver | `claude-haiku-4-5-20251001` | Passthrough presentation, minimal reasoning |

Estimated cost per run: **~$0.005** (under half a cent).

---

## Adding a New Tool

1. Create `tools/your_tool.py` with a plain function
2. Export it in `tools/__init__.py`
3. Register it in `worker.py`'s `TOOL_REGISTRY`
4. Add it to the `Available tools` list in `planner.py`'s `PLANNER_SYSTEM` prompt
5. Create a new `examples/run_your_example.py`

---

## Requirements

```
anthropic
httpx
python-dotenv
pymupdf
duckduckgo-search
```
