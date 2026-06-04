# Tree of Thoughts: 3-Day Hanoi → Da Nang Trip Planner

**Implementation Plan — No code yet. This document contains everything needed to build the agent.**

---

## 1. Overview

### What is Tree of Thoughts (ToT)?

Tree of Thoughts is a reasoning framework that extends Chain-of-Thought (CoT) prompting by exploring **multiple reasoning branches simultaneously** at each decision point, evaluating each branch with a scoring call, and pruning branches that are low-quality or violate hard constraints. The agent only commits to a path once the full tree has been explored.

| Framework   | Reasoning shape     | Backtracking | Evaluation       | Best for                             |
|-------------|---------------------|--------------|------------------|--------------------------------------|
| CoT         | Single linear chain | No           | None (implicit)  | Simple step-by-step tasks            |
| ReAct       | Interleaved think/act loop | No    | None (implicit)  | Tasks needing tool calls + reasoning |
| ReWOO       | Plan-then-execute (offline) | No  | None             | Parallelisable multi-tool tasks      |
| **ToT**     | **Branching tree**  | **Yes**      | **Explicit LLM score** | **Combinatorial decisions with constraints** |

### Why Chain-of-Thought falls short here

CoT would pick the first plausible transport, the first hotel it finds, and the first activity set — and call it done. It cannot compare "fly + hostel + free beaches" against "train + mid-range + food tour" to find which scores higher while staying under $300.

### Why ReAct falls short here

ReAct operates as a single thread: observe → think → act → observe. It backtracks only when it hits an error, not proactively. It has no mechanism to simultaneously hold multiple partial plans and compare them.

### Why trip planning is a perfect ToT fit

1. **Combinatorial structure** — transport × accommodation × activities creates a tree of independent choices.
2. **Hard budget constraint** — $300 is a binary filter: a branch either passes or is dead.
3. **Quality trade-offs** — cheap transport + premium hotel might score better than expensive transport + hostel; only explicit scoring reveals this.
4. **Natural depth levels** — the decision hierarchy (transport → hotel → activities) maps directly onto tree depth, making expansion logic clean and predictable.

---

## 2. Architecture

### Tree structure

```
                         [Root]
                    "3-day HAN→DAD, $300"
                   /         |          \
              [Fly]        [Train]       [Bus]
           score=0.85    score=0.65   score=0.38
           cost=$110       cost=$50      cost=$30
              /    \          |    \        \
          [H1]    [H2]      [H1]  [H2]    PRUNED
        score=0.72 0.88  score=0.75 0.82    (low quality score)
        cost=$97  $181    cost=$95  $185
          /  \      \        |        |
        [A1] [A2]  PRUNED  [A1]    [A1]
        0.80  0.91  (>$300) 0.78    0.85
        $217  $338          $157    $247
              OVER
             BUDGET
```

Legend:
- `H1` = hostel (~$14–18/night), `H2` = mid-range hotel (~$42–48/night)
- `A1` = budget activities (free beach + street food), `A2` = premium activities (Ba Na Hills + restaurant)
- Nodes show score (from scorer LLM call) and cumulative cost at that point

### BFS traversal order

```
Level 0: Root
Level 1: Fly, Train, Bus                    ← Bus pruned here (score < 0.4)
Level 2: Fly/H1, Fly/H2, Train/H1, Train/H2
Level 3: Fly/H1/A1, Fly/H1/A2,             ← Fly/H2/A2 pruned (cost > $300)
          Fly/H2/A1,
          Train/H1/A1, Train/H2/A1
Selector: picks highest-scoring leaf among complete nodes
```

---

## 3. Core Algorithm

```python
# Pseudocode — BFS Tree of Thoughts

PRUNE_THRESHOLD = 0.4   # score below this → prune
BUDGET = 300.0          # hard USD cap

def tree_of_thoughts(query: str) -> str:
    root = ThoughtNode(id="root", thought=query, depth=0, score=1.0, cost_so_far=0.0)
    frontier = [root]
    complete_nodes = []

    while frontier:
        node = frontier.pop(0)                    # BFS: pop from front

        if node.depth == MAX_DEPTH:               # leaf node
            complete_nodes.append(node)
            continue

        children = expand(node)                   # LLM + tools → 2–3 child options

        for child in children:
            child.score = evaluate(child)         # score_branch() LLM call

            # Dual pruning: quality AND budget
            if child.score < PRUNE_THRESHOLD:
                child.is_pruned = True
                log(f"PRUNED (score={child.score:.2f}): {child.thought}")
                continue

            if child.cost_so_far > BUDGET:
                child.is_pruned = True
                log(f"PRUNED (cost=${child.cost_so_far:.0f} > $300): {child.thought}")
                continue

            frontier.append(child)

    best = select_best(complete_nodes)            # highest score among leaves
    return solve(best)                            # final LLM call → itinerary
```

### expand(node) — depth-specific logic

```python
def expand(node: ThoughtNode) -> list[ThoughtNode]:
    if node.depth == 0:                           # Root → Transport options
        raw = search_flights("Hanoi", "Da Nang", date)
        return llm_propose_transport_branches(node, raw)

    elif node.depth == 1:                         # Transport → Hotel options
        budget_hint = 50 if node.cost_so_far < 150 else 20
        raw = search_hotels("Da Nang", budget_hint)
        return llm_propose_hotel_branches(node, raw)

    elif node.depth == 2:                         # Hotel → Activity options
        remaining = BUDGET - node.cost_so_far
        raw = search_activities("Da Nang", remaining)
        return llm_propose_activity_branches(node, raw)
```

### evaluate(node) → float

```python
def evaluate(node: ThoughtNode) -> float:
    description = build_path_description(node)    # walk up to root, collect thoughts
    return score_branch(description)              # Claude Haiku call → 0.0–1.0
```

### select_best(nodes) → ThoughtNode

```python
def select_best(nodes: list[ThoughtNode]) -> ThoughtNode:
    eligible = [n for n in nodes if not n.is_pruned and n.is_complete]
    return max(eligible, key=lambda n: n.score)
```

---

## 4. Project Structure

```
reasoning-agent-llm/
├── main.py                    # Entry point: parse args, run ToT, print result
├── tot_engine.py              # Core: expand(), evaluate(), bfs(), select_best()
├── node.py                    # ThoughtNode dataclass
├── models.py                  # Pydantic models for tool outputs + shared types
├── prompts.py                 # All prompt templates (expander + scorer + solver)
├── tools/
│   ├── __init__.py            # re-exports all tool functions
│   ├── flights.py             # mock search_flights()
│   ├── hotels.py              # mock search_hotels()
│   ├── activities.py          # mock search_activities()
│   ├── cost_estimator.py      # estimate_total_cost() — pure math, no LLM
│   └── scorer.py              # score_branch() — Claude Haiku call
├── .env.example
└── requirements.txt
```

**File responsibilities (one sentence each):**

- `main.py` — wires everything together; defines the query string, calls `bfs()`, prints the final itinerary.
- `tot_engine.py` — owns the BFS loop, calls expanders and evaluator, returns the winning node path.
- `node.py` — pure data: the `ThoughtNode` dataclass, no logic.
- `models.py` — Pydantic models for structured tool responses; keeps tool output parsing out of business logic.
- `prompts.py` — single source of truth for all LLM prompts; nothing else builds prompt strings.
- `tools/flights.py` — returns hardcoded mock flight data (real API swap-in point).
- `tools/hotels.py` — returns hardcoded mock hotel data keyed by budget tier.
- `tools/activities.py` — returns hardcoded mock activity data with per-item costs.
- `tools/cost_estimator.py` — sums transport + hotel_per_night×3 + activities; zero LLM calls.
- `tools/scorer.py` — the only tool that calls the LLM (Claude Haiku); returns a float.

---

## 5. Data Models

### `node.py`

```python
from dataclasses import dataclass, field

@dataclass
class ThoughtNode:
    id: str                          # e.g. "fly", "fly-hostel", "fly-hostel-beach"
    parent_id: str | None            # None for root
    thought: str                     # Human-readable description of this choice
                                     # e.g. "Fly VietJet: $55 one-way, 1hr flight"
    depth: int                       # 0=root, 1=transport, 2=hotel, 3=activities
    score: float                     # 0.0–1.0 from score_branch(); 1.0 for root
    cost_so_far: float               # cumulative USD at this node
    children: list["ThoughtNode"] = field(default_factory=list)
    is_pruned: bool = False
    is_complete: bool = False        # True when depth == MAX_DEPTH (3)

MAX_DEPTH = 3
```

**Key invariants:**
- `cost_so_far` at depth 1 = round-trip transport cost (×2 if flying/bus)
- `cost_so_far` at depth 2 = transport + hotel_per_night × 3
- `cost_so_far` at depth 3 = transport + hotel + activities total
- A node is **never** added to `frontier` if `is_pruned=True`

### `models.py`

```python
from pydantic import BaseModel

class FlightOption(BaseModel):
    airline: str            # e.g. "VietJet"
    price_one_way: float    # USD
    duration_hours: float   # e.g. 1.0

class HotelOption(BaseModel):
    name: str               # e.g. "Blooming Boutique"
    price_per_night: float  # USD
    tier: str               # "budget" | "mid-range"

class ActivityOption(BaseModel):
    name: str               # e.g. "Ba Na Hills"
    cost: float             # USD, 0.0 for free
    category: str           # "attraction" | "food" | "beach"

class BranchPath(BaseModel):
    """Full path from root to a node, used by scorer and solver."""
    transport: str          # e.g. "VietJet $55 one-way"
    hotel: str              # e.g. "Blooming Boutique $42/night"
    activities: str | None  # None if depth < 3
    total_cost: float
    depth: int
```

---

## 6. Expander Design

The expander runs at each depth transition. It calls the relevant mock tool, then asks the LLM to parse the raw text into 2–3 structured branch options.

### Depth 0 → 1: Transport Expander

**Tool call:** `search_flights("Hanoi", "Da Nang", date)`

**Prompt template** (in `prompts.py` as `TRANSPORT_EXPANDER_PROMPT`):

```
You are helping plan a 3-day trip from Hanoi to Da Nang with a total budget of $300 USD.

Available flight options:
{flight_data}

Generate 2–3 transport branch options. For each option, provide:
1. A one-sentence description (airline, price one-way, travel time)
2. The round-trip cost in USD

Consider: budget airlines, trains (~$25 one-way, 16hr), and overnight buses (~$15 one-way, 18hr) as alternatives even if not in the flight data.

Return as a JSON array:
[
  {{"id": "fly-vietjet", "thought": "Fly VietJet: $55 one-way, 1hr. Round-trip $110.", "cost": 110.0}},
  ...
]
```

**Post-processing:** parse JSON, create one `ThoughtNode` per item with `depth=1`, `cost_so_far=item["cost"]`.

---

### Depth 1 → 2: Hotel Expander

**Tool call:** `search_hotels("Da Nang", budget_per_night)` — called twice:
- `budget_per_night=20` for budget tier
- `budget_per_night=50` for mid-range tier

**Prompt template** (`HOTEL_EXPANDER_PROMPT`):

```
You are planning accommodation in Da Nang for 3 nights.
Transport already chosen: {transport_description} (spent ${transport_cost} so far, ${remaining} remaining of $300 budget).

Available hotels:
{hotel_data}

Generate 2 accommodation options — one budget, one mid-range — that fit within the remaining budget (remember: 3 nights total).

Return as a JSON array:
[
  {{"id": "{parent_id}-hostel", "thought": "Stay at Memory Hostel: $18/night × 3 = $54.", "nightly_cost": 18.0, "total_hotel_cost": 54.0}},
  ...
]
```

**Post-processing:** `cost_so_far = parent.cost_so_far + item["total_hotel_cost"]`

---

### Depth 2 → 3: Activities Expander

**Tool call:** `search_activities("Da Nang", budget)` where `budget = BUDGET - node.cost_so_far`

**Prompt template** (`ACTIVITIES_EXPANDER_PROMPT`):

```
You are planning activities in Da Nang for 3 days.
Transport + hotel already chosen: {path_so_far}
Spent so far: ${cost_so_far}. Remaining budget: ${remaining}.

Available activities:
{activity_data}

Generate 2 activity plans that each stay within the remaining budget:
- Plan 1: budget-focused (free or cheap activities, street food)
- Plan 2: experience-focused (paid attractions, sit-down meals) — only if it fits

For each plan, list the activities chosen and calculate the total activities cost.

Return as a JSON array:
[
  {{
    "id": "{parent_id}-budget-activities",
    "thought": "My Khe Beach (free) + Marble Mountains ($2) + street food ($12/day × 3). Activities total: $38.",
    "activities_cost": 38.0
  }},
  ...
]
```

**Post-processing:** `cost_so_far = parent.cost_so_far + item["activities_cost"]`. Set `is_complete=True`.

---

## 7. Evaluator (Scorer) Design

### `tools/scorer.py` — `score_branch(branch_description: str) -> float`

This is the only file that makes LLM calls outside of the expander. It uses **Claude Haiku** (fast and cheap) to rate a partial plan.

**Model:** `claude-haiku-4-5-20251001`

**Prompt template** (`SCORER_PROMPT` in `prompts.py`):

```
Rate the following partial travel plan from 0.0 to 1.0.

Scoring criteria:
- Comfort: Is transport and accommodation reasonably comfortable? (weight: 30%)
- Experience quality: Do the activities/choices make for a memorable trip? (weight: 40%)
- Value for money: Is the plan a good use of the available budget? (weight: 30%)

Score 1.0 = excellent on all criteria. Score 0.0 = poor on all criteria.

Partial travel plan:
{branch_description}

Respond with ONLY a single float between 0.0 and 1.0. No explanation.
```

**branch_description** is built by walking from the node back to root and concatenating `thought` strings:
```
"Transport: Fly VietJet $55 one-way (round-trip $110) | Hotel: Blooming Boutique $42/night × 3 ($126) | Activities: TBD"
```

**Pruning threshold:** `0.4`

**Rationale for Haiku:** scoring is called once per node (potentially 8–12 times per run). Haiku is 10–20× cheaper than Sonnet and more than capable of rating a 2-sentence travel plan. The expander and solver use Sonnet for richer generation.

---

## 8. Budget Constraint

The budget check is a **hard gate** applied in the BFS loop, independent of and in addition to the score threshold.

```python
# In tot_engine.py, inside the BFS loop:
for child in children:
    child.score = evaluate(child)           # always evaluate first (for logging)

    if child.score < PRUNE_THRESHOLD:
        child.is_pruned = True
        print(f"  → PRUNED (score={child.score:.2f} < {PRUNE_THRESHOLD})")
        continue

    if child.cost_so_far > BUDGET:
        child.is_pruned = True
        print(f"  → PRUNED (${child.cost_so_far:.0f} exceeds ${BUDGET:.0f} budget)")
        continue

    frontier.append(child)
```

**Why evaluate before the budget check?** It lets us log the score even for over-budget nodes, which is useful for debugging and makes the output more informative.

**Edge case — root node:** The root has `cost_so_far=0.0` and `score=1.0`; it is never evaluated or pruned.

---

## 9. Selector

After the BFS loop completes, `complete_nodes` holds all leaf nodes (depth=3) that were never pruned.

```python
def select_best(complete_nodes: list[ThoughtNode]) -> ThoughtNode:
    eligible = [n for n in complete_nodes if not n.is_pruned and n.is_complete]

    if not eligible:
        raise ValueError("All branches were pruned. Relax budget or prune threshold.")

    best = max(eligible, key=lambda n: n.score)

    print(f"\n[Select] Best complete path: {best.id}")
    print(f"         Score: {best.score:.2f} | Total cost: ${best.cost_so_far:.0f}")

    return best
```

**Tie-breaking:** if two nodes share the highest score (unlikely with floats), `max()` picks the first one encountered — which in BFS is the one expanded earliest (i.e. from the higher-scoring transport branch).

---

## 10. Solver

The solver takes the winning leaf's **full path** (reconstructed by walking parent links) and makes one final LLM call to write a polished, day-by-day itinerary.

### Path reconstruction

```python
def reconstruct_path(node: ThoughtNode, all_nodes: dict[str, ThoughtNode]) -> list[ThoughtNode]:
    path = []
    current = node
    while current is not None:
        path.append(current)
        current = all_nodes.get(current.parent_id)
    return list(reversed(path))   # root → leaf order
```

### Solver prompt template (`SOLVER_PROMPT` in `prompts.py`)

```
You are a travel planner. Write a detailed 3-day itinerary for a trip from Hanoi to Da Nang
based on the following chosen plan:

Transport: {transport_thought}
Accommodation: {hotel_thought}
Activities: {activities_thought}
Total estimated cost: ${total_cost} (budget: $300)

Write the itinerary in this format:

## Day 1 — Arrival & First Impressions
[Morning / Afternoon / Evening breakdown with specific times, place names, tips]

## Day 2 — [Theme]
[...]

## Day 3 — [Theme & Departure]
[...]

## Cost Breakdown
| Item | Cost |
|------|------|
| Flights (return) | $X |
| Accommodation (3 nights) | $X |
| Activities | $X |
| Food estimate | $X |
| **Total** | **$X** |

## Practical Tips
[3–5 bullet points: booking advice, local transport, weather, etc.]
```

**Model for solver:** `claude-sonnet-4-6` (richer writing quality than Haiku for the final output).

---

## 11. Mock Tool Data

All mock tools are pure functions returning hardcoded strings. This makes the tree deterministic and testable without network calls.

### `tools/flights.py`

```python
def search_flights(origin: str, destination: str, date: str) -> str:
    """Returns mock flight options as a formatted string."""
    if origin.lower() in ("hanoi", "han") and destination.lower() in ("da nang", "dad"):
        return (
            "VietJet Air (VJ): $55 one-way | 1hr 10min | departs 06:00\n"
            "Vietnam Airlines (VN): $75 one-way | 1hr 15min | departs 08:30\n"
            "Bamboo Airways (QH): $60 one-way | 1hr 10min | departs 11:45\n"
            "Note: Train (SE) is ~$25 one-way, 16hr overnight. "
            "Sleeper bus is ~$15 one-way, 18hr."
        )
    return "No flights found for this route."
```

### `tools/hotels.py`

```python
def search_hotels(city: str, budget_per_night: float) -> str:
    """Returns mock hotel options filtered by budget tier."""
    if city.lower() != "da nang":
        return "No hotels found."

    if budget_per_night <= 20:
        return (
            "An Bang Backpackers Hostel: $14/night | dorm bed | free breakfast | beach 200m\n"
            "Memory Hostel: $18/night | private room | AC | city center\n"
            "Sandy Feet Hostel: $16/night | mixed dorm | rooftop bar"
        )
    else:  # mid-range
        return (
            "Blooming Boutique Hotel: $42/night | private room | pool | 5min to beach\n"
            "Sunnyside Hotel: $48/night | private room | breakfast included | My Khe Beach\n"
            "Da Nang Boutique: $45/night | private room | rooftop pool | city view"
        )
```

### `tools/activities.py`

```python
def search_activities(city: str, budget: float) -> str:
    """Returns mock activity options with costs."""
    if city.lower() != "da nang":
        return "No activities found."

    return (
        "My Khe Beach: FREE | 3km white sand beach | best morning/evening\n"
        "Marble Mountains: $2 | caves + pagodas | half-day | 9km from center\n"
        "Ba Na Hills (cable car + theme park): $35 | full day | book in advance\n"
        "Dragon Bridge: FREE | evening light show Fri/Sat/Sun 9pm\n"
        "Street food tour (self-guided): $8–15/day | Mi Quang, Banh Mi, Com Tam\n"
        "My Son Sanctuary (day trip): $20 | UNESCO site | 70km from Da Nang\n"
        "Hoi An day trip: $10 transport + free entry to old town | 30km south\n"
        "Seafood dinner at Han Market area: $12–18 per meal"
    )
```

### `tools/cost_estimator.py`

```python
def estimate_total_cost(
    transport_one_way: float,
    hotel_per_night: float,
    nights: int,
    activities_total: float,
    food_per_day: float,
    days: int,
) -> float:
    """Pure calculation — no LLM call."""
    transport_return = transport_one_way * 2
    hotel_total = hotel_per_night * nights
    food_total = food_per_day * days
    return transport_return + hotel_total + activities_total + food_total
```

Note: `food_per_day` defaults to `$10` in the expander (street food baseline). Upgrades are included in `activities_total` when the LLM selects restaurant options.

### Deterministic tree output

With this mock data, the tree always produces:

| Path | Cost | Score (expected) |
|------|------|-----------------|
| Fly VietJet + Hostel + Budget activities | ~$196 | ~0.75 |
| Fly VietJet + Hostel + Premium activities | ~$243 | ~0.82 |
| Fly VietJet + Boutique + Budget activities | ~$284 | ~0.83 |
| Fly VietJet + Boutique + Premium activities | ~$331 | PRUNED (over budget) |
| Train + Hostel + Budget activities | ~$148 | ~0.70 |
| Train + Boutique + Budget activities | ~$236 | ~0.80 |
| Bus + * | * | PRUNED (score < 0.4) |

---

## 12. Expected Console Output

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
  Tool call: search_hotels("Da Nang", budget=20)
  Tool call: search_hotels("Da Nang", budget=50)
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
  Tool call: search_activities("Da Nang", budget=136)
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
  LLM proposed 2 branches:
    [train-hostel-budget]   Beach + Marble Mtns + street food. Total: $32.
    [train-hostel-premium]  Ba Na Hills + Hoi An + restaurants. Total: $85.

[Evaluate] Scoring...
    train-hostel-budget   → score=0.70 ✓  total=$136 ✓
    train-hostel-premium  → score=0.78 ✓  total=$189 ✓

[Expand] Depth 2→3: Activities (parent: train-boutique, remaining=$124)
  LLM proposed 2 branches:
    [train-boutique-budget]   Beach + Marble Mtns + street food. Total: $32.
    [train-boutique-premium]  Ba Na Hills + Hoi An + restaurants. Total: $85.

[Evaluate] Scoring...
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

=== 3-DAY DA NANG TRIP PLAN ===
[Full itinerary written by solver LLM call — see Section 10 for format]
```

---

## 13. Implementation Order

Follow this sequence to avoid circular imports and allow incremental testing:

1. **`node.py`** — pure dataclass, no imports from the project. Test: instantiate a `ThoughtNode`, verify fields.

2. **`models.py`** — Pydantic models, depends only on `pydantic`. Test: parse a dict into `FlightOption`.

3. **`tools/cost_estimator.py`** — pure math, no imports. Test: `estimate_total_cost(55, 18, 3, 35, 10, 3)` → `$216`.

4. **`tools/flights.py`**, **`tools/hotels.py`**, **`tools/activities.py`** — mock tools, no imports. Test: call each, verify string output.

5. **`tools/scorer.py`** — first file that uses the Anthropic SDK. Requires `ANTHROPIC_API_KEY`. Test: call `score_branch("Fly + hostel + beach")`, verify float in [0, 1].

6. **`prompts.py`** — string constants. No logic. No test needed.

7. **`tot_engine.py`** — depends on all of the above. Implement and test `expand()` at each depth, then the full BFS loop.

8. **Solver logic** — can live in `tot_engine.py` or a separate `solver.py`. Implement after BFS is working end-to-end.

9. **`main.py`** — thin entry point. Wire together and print output.

---

## 14. Key Design Decisions

### BFS over DFS

BFS expands all nodes at depth 1 before any at depth 2, ensuring all transport options are evaluated before hotel choices are explored. This means the final comparison of leaf nodes is always apples-to-apples (all at depth 3). DFS would commit to exploring one branch deeply before others, potentially missing that a "worse" transport option leads to a better overall plan when combined with specific accommodation.

Practical advantage: BFS makes the console output read naturally top-to-bottom by depth level, matching the mental model of "first decide transport, then hotel, then activities."

### Mock tools over real APIs

Real flight/hotel APIs introduce latency, cost, API key management, and non-determinism. During development, deterministic mock data lets you run the full tree 10 times and get identical results, making it easy to verify pruning logic and scorer thresholds. The swap to real APIs requires changing only the function bodies in `tools/flights.py` etc. — the rest of the codebase is unaffected.

### Separate scorer from expander

The expander's job is to generate options (creative, generative). The scorer's job is to judge quality (evaluative, reductive). These are distinct cognitive tasks that benefit from separate prompts and potentially different models (Sonnet for generation, Haiku for scoring). Keeping them separate also means the scorer can be called independently for unit testing, and its prompt can be tuned without touching expansion logic.

### Score stored on node, not recomputed

Each node's `score` field is set once during BFS and never changes. This means the selector and solver can trust `node.score` without re-querying the LLM, keeping the total API call count predictable: `1 call per node evaluated` + `1 solver call`.

### `cost_so_far` is cumulative, not marginal

Each node stores the running total from root, not just its own incremental cost. This makes the budget check `child.cost_so_far > BUDGET` a one-liner — no need to walk up to root and sum costs.

---

## Appendix: API Call Budget

For a typical run with this tree:

| Call type | Count | Model | Est. cost |
|-----------|-------|-------|-----------|
| Transport expander | 1 | Sonnet | ~$0.002 |
| Hotel expander | 2 | Sonnet | ~$0.004 |
| Activities expander | 4 | Sonnet | ~$0.008 |
| Scorer calls | ~10 | Haiku | ~$0.001 |
| Solver | 1 | Sonnet | ~$0.005 |
| **Total** | **~18** | | **~$0.02** |

A full run costs roughly **2 cents**. Running it 50 times during development costs ~$1.
