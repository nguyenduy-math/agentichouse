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
