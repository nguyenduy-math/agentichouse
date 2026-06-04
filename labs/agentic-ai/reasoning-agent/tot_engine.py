import json
import re

from llm_client import call_llm
from node import ThoughtNode, MAX_DEPTH
from prompts import (
    TRANSPORT_EXPANDER_PROMPT,
    HOTEL_EXPANDER_PROMPT,
    ACTIVITIES_EXPANDER_PROMPT,
)
from tools import search_flights, search_hotels, search_activities, score_branch

PRUNE_THRESHOLD = 0.4
BUDGET = 300.0
DIVIDER = "─" * 42


def _llm_call(prompt: str, max_tokens: int = 1024) -> str:
    return call_llm(prompt, mode="expand", max_tokens=max_tokens)


def _parse_json(text: str) -> list[dict]:
    """Extract and parse a JSON array from LLM output, even if there's surrounding text."""
    match = re.search(r"\[.*\]", text, re.DOTALL)
    if match:
        return json.loads(match.group())
    return json.loads(text)


def _build_path_description(node: ThoughtNode, all_nodes: dict[str, ThoughtNode]) -> str:
    """Walk from root to node, collect thought strings."""
    parts = []
    current = node
    while current and current.parent_id is not None:
        parts.append(current.thought)
        current = all_nodes.get(current.parent_id)
    parts.reverse()
    labels = ["Transport", "Hotel", "Activities"]
    described = []
    for i, part in enumerate(parts):
        label = labels[i] if i < len(labels) else f"Step {i+1}"
        described.append(f"{label}: {part}")
    return " | ".join(described) if described else node.thought


def expand(node: ThoughtNode, all_nodes: dict[str, ThoughtNode]) -> list[ThoughtNode]:
    """Generate child nodes for a given node based on its depth."""
    children = []

    if node.depth == 0:
        print(f"\n{DIVIDER}")
        print("[Expand] Depth 0→1: Transport options")
        flight_data = search_flights("Hanoi", "Da Nang", "2024-12-15")
        print(f"  Tool call: search_flights(\"Hanoi\", \"Da Nang\", \"2024-12-15\")")
        prompt = TRANSPORT_EXPANDER_PROMPT.format(flight_data=flight_data)
        raw = _llm_call(prompt)
        options = _parse_json(raw)
        print(f"  LLM proposed {len(options)} branches:")
        for opt in options:
            child = ThoughtNode(
                id=opt["id"],
                parent_id=node.id,
                thought=opt["thought"],
                depth=1,
                score=0.0,
                cost_so_far=opt["cost"],
            )
            children.append(child)
            all_nodes[child.id] = child
            print(f"    [{child.id:<16}] {child.thought}")

    elif node.depth == 1:
        print(f"\n{DIVIDER}")
        print(f"[Expand] Depth 1→2: Hotels (parent: {node.id})")
        remaining = BUDGET - node.cost_so_far
        budget_hotels = search_hotels("Da Nang", 20)
        midrange_hotels = search_hotels("Da Nang", 50)
        hotel_data = f"Budget options:\n{budget_hotels}\n\nMid-range options:\n{midrange_hotels}"
        prompt = HOTEL_EXPANDER_PROMPT.format(
            transport_description=node.thought,
            transport_cost=node.cost_so_far,
            remaining=remaining,
            hotel_data=hotel_data,
            parent_id=node.id,
        )
        raw = _llm_call(prompt)
        options = _parse_json(raw)
        print(f"  LLM proposed {len(options)} branches:")
        for opt in options:
            child = ThoughtNode(
                id=opt["id"],
                parent_id=node.id,
                thought=opt["thought"],
                depth=2,
                score=0.0,
                cost_so_far=node.cost_so_far + opt["total_hotel_cost"],
            )
            children.append(child)
            all_nodes[child.id] = child
            print(f"    [{child.id:<28}] {child.thought}")

    elif node.depth == 2:
        print(f"\n{DIVIDER}")
        remaining = BUDGET - node.cost_so_far
        print(f"[Expand] Depth 2→3: Activities (parent: {node.id}, remaining=${remaining:.0f})")
        activity_data = search_activities("Da Nang", remaining)
        path_so_far = _build_path_description(node, all_nodes)
        prompt = ACTIVITIES_EXPANDER_PROMPT.format(
            path_so_far=path_so_far,
            cost_so_far=node.cost_so_far,
            remaining=remaining,
            activity_data=activity_data,
            parent_id=node.id,
        )
        raw = _llm_call(prompt)
        options = _parse_json(raw)
        print(f"  LLM proposed {len(options)} branches:")
        for opt in options:
            total_cost = node.cost_so_far + opt["activities_cost"] + 30.0  # $10/day food baseline
            child = ThoughtNode(
                id=opt["id"],
                parent_id=node.id,
                thought=opt["thought"],
                depth=3,
                score=0.0,
                cost_so_far=total_cost,
                is_complete=True,
            )
            children.append(child)
            all_nodes[child.id] = child
            print(f"    [{child.id:<36}] {child.thought[:60]}...")

    return children


def evaluate(node: ThoughtNode, all_nodes: dict[str, ThoughtNode]) -> float:
    """Score a node using Claude Haiku."""
    description = _build_path_description(node, all_nodes)
    return score_branch(description)


def bfs(query: str) -> tuple[ThoughtNode, dict[str, ThoughtNode]]:
    """Run BFS Tree of Thoughts search. Returns (best_leaf, all_nodes)."""
    print(f"\n[ToT] Starting tree search for: {query}")
    print(f"[ToT] PRUNE_THRESHOLD={PRUNE_THRESHOLD} | BUDGET=${BUDGET:.0f} | MAX_DEPTH={MAX_DEPTH}")

    root = ThoughtNode(id="root", parent_id=None, thought=query, depth=0, score=1.0, cost_so_far=0.0)
    all_nodes: dict[str, ThoughtNode] = {"root": root}
    frontier = [root]
    complete_nodes: list[ThoughtNode] = []

    while frontier:
        node = frontier.pop(0)

        if node.depth == MAX_DEPTH:
            complete_nodes.append(node)
            continue

        children = expand(node, all_nodes)

        print(f"\n[Evaluate] Scoring {len(children)} branches...")
        for child in children:
            child.score = evaluate(child, all_nodes)
            budget_ok = child.cost_so_far <= BUDGET
            score_ok = child.score >= PRUNE_THRESHOLD

            status = "✓" if (score_ok and budget_ok) else "✗"
            reason = ""
            if not score_ok:
                reason = f"  PRUNED (score={child.score:.2f} < {PRUNE_THRESHOLD})"
            elif not budget_ok:
                reason = f"  PRUNED (${child.cost_so_far:.0f} exceeds ${BUDGET:.0f} budget)"

            print(f"    {child.id:<36} score={child.score:.2f} {status}  cost=${child.cost_so_far:.0f}{reason}")

            if not score_ok or not budget_ok:
                child.is_pruned = True
                continue

            frontier.append(child)

    return select_best(complete_nodes), all_nodes


def select_best(complete_nodes: list[ThoughtNode]) -> ThoughtNode:
    """Pick the highest-scoring non-pruned leaf node."""
    print(f"\n{DIVIDER}")
    eligible = [n for n in complete_nodes if not n.is_pruned and n.is_complete]

    if not eligible:
        raise ValueError(
            "All branches were pruned. Consider relaxing the budget or lowering PRUNE_THRESHOLD."
        )

    print(f"[Select] Complete nodes (depth=3, not pruned): {len(eligible)}")
    for n in sorted(eligible, key=lambda x: x.score, reverse=True):
        print(f"    {n.id:<40} score={n.score:.2f}  cost=${n.cost_so_far:.0f}")

    best = max(eligible, key=lambda n: n.score)
    print(f"\n  ★ Best: {best.id}  (score={best.score:.2f}, cost=${best.cost_so_far:.0f})")
    return best


def reconstruct_path(node: ThoughtNode, all_nodes: dict[str, ThoughtNode]) -> list[ThoughtNode]:
    """Walk from leaf back to root, return path root→leaf."""
    path = []
    current = node
    while current is not None:
        path.append(current)
        current = all_nodes.get(current.parent_id) if current.parent_id else None
    return list(reversed(path))
