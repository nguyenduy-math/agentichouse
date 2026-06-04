from pydantic import BaseModel


class FlightOption(BaseModel):
    airline: str
    price_one_way: float
    duration_hours: float


class HotelOption(BaseModel):
    name: str
    price_per_night: float
    tier: str  # "budget" | "mid-range"


class ActivityOption(BaseModel):
    name: str
    cost: float
    category: str  # "attraction" | "food" | "beach"


class BranchPath(BaseModel):
    transport: str
    hotel: str
    activities: str | None
    total_cost: float
    depth: int
