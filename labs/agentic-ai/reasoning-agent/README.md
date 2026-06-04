# Tree of Thoughts Trip Planner

An LLM agent that plans a 3-day trip from Hanoi to Da Nang under $300 using the **Tree of Thoughts** reasoning framework — exploring multiple plan branches simultaneously, scoring each, and pruning dead ends before committing to a final itinerary.

---

## What is Tree of Thoughts?

Tree of Thoughts (ToT) extends standard prompting by exploring **multiple reasoning branches in parallel** at each decision point. An LLM evaluates each branch with an explicit score, and low-quality or constraint-violating branches are pruned before the search goes deeper. The agent only commits to a path once the full tree has been explored.

This is fundamentally different from linear frameworks:

| Framework | Reasoning shape | Backtracking | Evaluation | Best for |
|-----------|----------------|--------------|------------|----------|
| CoT | Single linear chain | No | None (implicit) | Simple step-by-step tasks |
| ReAct | Interleaved think/act loop | No | None (implicit) | Tasks needing tool calls + reasoning |
| ReWOO | Plan-then-execute (offline) | No | None | Parallelisable multi-tool tasks |
| **ToT** | **Branching tree** | **Yes** | **Explicit LLM score** | **Combinatorial decisions with constraints** |

---

## The Example

**Query:** `"Plan a 3-day trip from Hanoi to Da Nang under $300"`

This is a near-perfect fit for ToT because:

1. **Combinatorial structure** — transport × accommodation × activities creates a tree of independent choices that compound into very different total costs and experiences.
2. **Hard budget constraint** — $300 is a binary filter: a branch either passes or is dead. There's no point writing a full itinerary for an over-budget plan.
3. **Quality trade-offs** — cheap transport + premium hotel might score better than expensive transport + hostel; only explicit scoring reveals this.
4. **Natural depth levels** — the decision hierarchy (transport → hotel → activities) maps cleanly onto tree depth, making expansion logic predictable.

---

## How It Works

The algorithm runs BFS across 3 depth levels, pruning branches that score below `0.4` or exceed the $300 budget.

### The 3 Phases

**Phase 1 — Expand:** At each depth, call a mock tool (flights/hotels/activities) and ask Claude Sonnet to propose 2–3 structured options as child nodes.

**Phase 2 — Evaluate:** Score each child node with a single Claude Haiku call (fast and cheap). Prune immediately if score < 0.4 or cumulative cost > $300.

**Phase 3 — Select + Solve:** Pick the highest-scoring leaf node, reconstruct its full path, and ask Claude Sonnet to write a polished day-by-day itinerary.

### Tree Diagram

```
                         [Root]
                    "3-day HAN→DAD, $300"
                   /         |          \
              [Fly]        [Train]       [Bus]
           score=0.85    score=0.65   score=0.38
           cost=$110       cost=$50      cost=$30
              /    \          |    \        \
          [H1]    [H2]      [H1]  [H2]    PRUNED
        score=0.72 0.88  score=0.75 0.82    (score < 0.4)
        cost=$164 $236    cost=$104 $176
          /  \      \        |        |
        [A1] [A2]  PRUNED  [A1]    [A1]
        0.74  0.86  ($331   0.70    0.84
        $196  $249  >$300)  $136    $261
                   OVER
                  BUDGET
```

Legend: `H1` = hostel (~$14–18/night), `H2` = boutique hotel (~$42–48/night), `A1` = budget activities, `A2` = premium activities (Ba Na Hills + restaurants).

**Bus branch** is pruned at depth 1 (score 0.38 < threshold 0.40). **Fly + Boutique + Premium** is pruned at depth 3 (total $331 > $300). The winning path is **Fly VietJet + Memory Hostel + Ba Na Hills** at $249 and score 0.86.

---

## Project Structure

```
reasoning-agent-llm/
├── main.py                # Entry point: runs BFS, calls solver, prints itinerary
├── tot_engine.py          # Core BFS loop: expand(), evaluate(), select_best()
├── solver.py              # Final LLM call: reconstructs path, writes itinerary
├── node.py                # ThoughtNode dataclass (id, depth, score, cost_so_far, …)
├── models.py              # Pydantic models: FlightOption, HotelOption, ActivityOption, BranchPath
├── prompts.py             # All prompt templates — single source of truth for LLM strings
├── tools/
│   ├── __init__.py        # Re-exports all tool functions
│   ├── flights.py         # mock search_flights() — swap body for real API
│   ├── hotels.py          # mock search_hotels() — swap body for real API
│   ├── activities.py      # mock search_activities() — swap body for real API
│   ├── cost_estimator.py  # estimate_total_cost() — pure math, zero LLM calls
│   └── scorer.py          # score_branch() — the only tool that calls Claude Haiku
├── .env.example
└── requirements.txt
```

---

## Getting Started

```bash
cd reasoning-agent-llm
pip install -r requirements.txt
cp .env.example .env
# edit .env and add your key:  ANTHROPIC_API_KEY=sk-ant-...
python main.py
```

---

## Expected Output

```
[ToT] Starting tree search for: 3-day Hanoi→Da Nang trip, $300 budget
[ToT] PRUNE_THRESHOLD=0.40 | BUDGET=$300 | MAX_DEPTH=3

──────────────────────────────────────────
[Expand] Depth 0→1: Transport options
  Tool call: search_flights("Hanoi", "Da Nang", "2024-12-15")
  LLM proposed 3 branches:
    [fly-vietjet]  Fly VietJet: $55 one-way, 1hr. Round-trip $110.
    [train]        Overnight train: $25 one-way, 16hr. Round-trip $50.
    [bus]          Sleeper bus: $15 one-way, 18hr. Round-trip $30.

[Evaluate] Scoring branches...
    fly-vietjet  → score=0.85 ✓  cost=$110
    train        → score=0.65 ✓  cost=$50
    bus          → score=0.38 ✗  PRUNED (score < 0.40)

──────────────────────────────────────────
[Expand] Depth 1→2: Hotels (parent: fly-vietjet)
  LLM proposed 2 branches:
    [fly-vietjet-hostel]    Memory Hostel: $18/night × 3 = $54.
    [fly-vietjet-boutique]  Blooming Boutique: $42/night × 3 = $126.

[Evaluate] Scoring branches...
    fly-vietjet-hostel    → score=0.72 ✓  cost=$164
    fly-vietjet-boutique  → score=0.88 ✓  cost=$236

[Expand] Depth 1→2: Hotels (parent: train)
  LLM proposed 2 branches:
    [train-hostel]    Memory Hostel: $18/night × 3 = $54.
    [train-boutique]  Blooming Boutique: $42/night × 3 = $126.

[Evaluate] Scoring branches...
    train-hostel    → score=0.68 ✓  cost=$104
    train-boutique  → score=0.79 ✓  cost=$176

──────────────────────────────────────────
[Expand] Depth 2→3: Activities (parent: fly-vietjet-hostel, remaining=$136)
  LLM proposed 2 branches:
    [fly-vietjet-hostel-budget]   My Khe Beach + Marble Mtns ($2) + street food ($30). Total: $32.
    [fly-vietjet-hostel-premium]  Ba Na Hills ($35) + Hoi An day trip ($10) + restaurants ($40). Total: $85.

[Evaluate] Scoring...
    fly-vietjet-hostel-budget   → score=0.74 ✓  total=$196 ✓
    fly-vietjet-hostel-premium  → score=0.86 ✓  total=$249 ✓

[Expand] Depth 2→3: Activities (parent: fly-vietjet-boutique, remaining=$64)
  LLM proposed 2 branches:
    [fly-vietjet-boutique-budget]   My Khe Beach + Marble Mtns + street food. Total: $32.
    [fly-vietjet-boutique-premium]  Ba Na Hills + restaurants. Total: $95.

[Evaluate] Scoring...
    fly-vietjet-boutique-budget   → score=0.80 ✓  total=$268 ✓
    fly-vietjet-boutique-premium  → score=0.91    total=$331 ✗  PRUNED (exceeds $300)

[Expand] Depth 2→3: Activities (parent: train-hostel, remaining=$196)
  ...
    train-hostel-budget   → score=0.70 ✓  total=$136 ✓
    train-hostel-premium  → score=0.78 ✓  total=$189 ✓

[Expand] Depth 2→3: Activities (parent: train-boutique, remaining=$124)
  ...
    train-boutique-budget   → score=0.75 ✓  total=$208 ✓
    train-boutique-premium  → score=0.84 ✓  total=$261 ✓

──────────────────────────────────────────
[Select] Complete nodes (depth=3, not pruned): 7
    fly-vietjet-hostel-budget        score=0.74  cost=$196
    fly-vietjet-hostel-premium       score=0.86  cost=$249
    fly-vietjet-boutique-budget      score=0.80  cost=$268
    train-hostel-budget              score=0.70  cost=$136
    train-hostel-premium             score=0.78  cost=$189
    train-boutique-budget            score=0.75  cost=$208
    train-boutique-premium           score=0.84  cost=$261

  ★ Best: fly-vietjet-hostel-premium  (score=0.86, cost=$249)

──────────────────────────────────────────
[Solver] Generating final itinerary for winning path...
  Transport : Fly VietJet: $55 one-way, 1hr. Round-trip $110.
  Hotel     : Memory Hostel: $18/night × 3 = $54.
  Activities: Ba Na Hills ($35) + Hoi An day trip ($10) + restaurants ($40).
  Total     : $249 / $300 budget

==================================================
=== 3-DAY DA NANG TRIP PLAN ===
==================================================
[Full itinerary written by Claude Sonnet]
```

---

## Models Used

| Role | Model | Why |
|------|-------|-----|
| Expander (generate options) | `claude-sonnet-4-6` | Richer generation for proposing structured branches |
| Scorer (evaluate branches) | `claude-haiku-4-5-20251001` | Called ~10× per run — fast and 10–20× cheaper than Sonnet |
| Solver (write itinerary) | `claude-sonnet-4-6` | Best writing quality for the final output |

**Estimated cost per run: ~$0.02** (~18 total API calls: 7 expander, ~10 scorer, 1 solver).

---

## Customisation

**Change the budget** — edit `BUDGET` at the top of `tot_engine.py`:
```python
BUDGET = 500.0   # e.g. raise to $500 for more options
```

**Change the pruning threshold** — edit `PRUNE_THRESHOLD` in `tot_engine.py`:
```python
PRUNE_THRESHOLD = 0.5   # stricter pruning, fewer branches explored
```

**Swap in real APIs** — only the function body in each tool file needs to change. The rest of the codebase is unaffected:
```python
# tools/flights.py
def search_flights(origin: str, destination: str, date: str) -> str:
    # Replace this mock with a real Skyscanner / Amadeus API call
    response = skyscanner_client.search(origin, destination, date)
    return format_response(response)
```

**Change the destination** — update the mock data strings in `tools/flights.py`, `tools/hotels.py`, and `tools/activities.py` to reflect your route and city.

---

## Architecture Notes

**BFS over DFS** — BFS expands all transport options before exploring any hotels. This ensures the final leaf comparison is always apples-to-apples (all at depth 3). DFS could miss that a "worse" transport option leads to a better overall plan when paired with specific accommodation.

**Mock tools** — Real APIs add latency, cost, key management, and non-determinism. Mock data makes the full tree run in seconds with identical results every time, which is essential for verifying pruning logic and tuning scorer thresholds. The abstraction boundary means swapping to real APIs requires changing only the function bodies.

**Scorer separate from expander** — Expansion is generative (propose options); scoring is evaluative (judge quality). Separating them allows different models for each task (Sonnet for generation, Haiku for scoring), independent prompt tuning, and unit-testable scorer calls without triggering the full expansion chain.

**Score stored on node, not recomputed** — Each node's `score` is set once during BFS and never changes. This keeps total API call count predictable: one Haiku call per node evaluated, plus one Sonnet call at the end for the solver.
