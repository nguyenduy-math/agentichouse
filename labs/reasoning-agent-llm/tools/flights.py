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
