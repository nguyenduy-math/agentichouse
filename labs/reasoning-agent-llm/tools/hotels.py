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
    else:
        return (
            "Blooming Boutique Hotel: $42/night | private room | pool | 5min to beach\n"
            "Sunnyside Hotel: $48/night | private room | breakfast included | My Khe Beach\n"
            "Da Nang Boutique: $45/night | private room | rooftop pool | city view"
        )
