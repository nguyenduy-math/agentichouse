import os
from dotenv import load_dotenv

load_dotenv()

from tot_engine import bfs
from solver import solve


def main():
    query = "3-day Hanoi to Da Nang trip, $300 budget"
    best_node, all_nodes = bfs(query)
    itinerary = solve(best_node, all_nodes)

    print("\n" + "=" * 50)
    print("=== 3-DAY DA NANG TRIP PLAN ===")
    print("=" * 50)
    print(itinerary)


if __name__ == "__main__":
    main()
