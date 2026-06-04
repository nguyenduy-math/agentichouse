from llm_client import call_llm
from node import ThoughtNode
from prompts import SOLVER_PROMPT
from tot_engine import reconstruct_path


def solve(best_node: ThoughtNode, all_nodes: dict[str, ThoughtNode]) -> str:
    """Generate the final itinerary from the winning leaf node."""
    path = reconstruct_path(best_node, all_nodes)
    # path[0] = root, path[1] = transport, path[2] = hotel, path[3] = activities
    transport_thought = path[1].thought if len(path) > 1 else "N/A"
    hotel_thought = path[2].thought if len(path) > 2 else "N/A"
    activities_thought = path[3].thought if len(path) > 3 else "N/A"

    print(f"\n{'─' * 42}")
    print("[Solver] Generating final itinerary for winning path...")
    print(f"  Transport : {transport_thought}")
    print(f"  Hotel     : {hotel_thought}")
    print(f"  Activities: {activities_thought}")
    print(f"  Total     : ${best_node.cost_so_far:.0f} / $300 budget")

    prompt = SOLVER_PROMPT.format(
        transport_thought=transport_thought,
        hotel_thought=hotel_thought,
        activities_thought=activities_thought,
        total_cost=best_node.cost_so_far,
    )

    return call_llm(prompt, mode="solve", max_tokens=2048)
