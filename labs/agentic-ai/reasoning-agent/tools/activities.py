def search_activities(city: str, budget: float) -> str:
    """Returns mock activity options with costs."""
    if city.lower() != "da nang":
        return "No activities found."

    return (
        "My Khe Beach: FREE | 3km white sand beach | best morning/evening\n"
        "Marble Mountains: $2 | caves + pagodas | half-day | 9km from center\n"
        "Ba Na Hills (cable car + theme park): $35 | full day | book in advance\n"
        "Dragon Bridge: FREE | evening light show Fri/Sat/Sun 9pm\n"
        "Street food tour (self-guided): $8-15/day | Mi Quang, Banh Mi, Com Tam\n"
        "My Son Sanctuary (day trip): $20 | UNESCO site | 70km from Da Nang\n"
        "Hoi An day trip: $10 transport + free entry to old town | 30km south\n"
        "Seafood dinner at Han Market area: $12-18 per meal"
    )
