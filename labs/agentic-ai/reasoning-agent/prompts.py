TRANSPORT_EXPANDER_PROMPT = """You are helping plan a 3-day trip from Hanoi to Da Nang with a total budget of $300 USD.

Available transport options:
{flight_data}

Generate exactly 3 transport branch options (fly, train, bus). For each option, provide:
1. A one-sentence description (carrier, price one-way, travel time)
2. The round-trip cost in USD

Return ONLY a valid JSON array with no extra text:
[
  {{"id": "fly-vietjet", "thought": "Fly VietJet: $55 one-way, 1hr 10min. Round-trip $110.", "cost": 110.0}},
  {{"id": "train", "thought": "Overnight train: $25 one-way, 16hr. Round-trip $50.", "cost": 50.0}},
  {{"id": "bus", "thought": "Sleeper bus: $15 one-way, 18hr. Round-trip $30.", "cost": 30.0}}
]"""

HOTEL_EXPANDER_PROMPT = """You are planning accommodation in Da Nang for 3 nights.
Transport already chosen: {transport_description} (spent ${transport_cost:.0f} so far, ${remaining:.0f} remaining of $300 budget).

Available hotels:
{hotel_data}

Generate exactly 2 accommodation options — one budget (~$14-18/night), one mid-range (~$42-48/night).
Only include options that leave enough budget for activities.

Return ONLY a valid JSON array with no extra text:
[
  {{"id": "{parent_id}-hostel", "thought": "Stay at Memory Hostel: $18/night x 3 = $54.", "nightly_cost": 18.0, "total_hotel_cost": 54.0}},
  {{"id": "{parent_id}-boutique", "thought": "Stay at Blooming Boutique Hotel: $42/night x 3 = $126.", "nightly_cost": 42.0, "total_hotel_cost": 126.0}}
]"""

ACTIVITIES_EXPANDER_PROMPT = """You are planning activities in Da Nang for 3 days.
Transport + hotel already chosen: {path_so_far}
Spent so far: ${cost_so_far:.0f}. Remaining budget: ${remaining:.0f}.

Available activities:
{activity_data}

Generate 2 activity plans that each stay within the remaining budget:
- Plan 1: budget-focused (free or cheap activities, street food)
- Plan 2: experience-focused (paid attractions + meals) — only include if it fits within remaining budget

For each plan, list the activities and calculate the total activities cost (3 days of food is already covered by $10/day baseline, only add extra costs for upgrades).

Return ONLY a valid JSON array with no extra text:
[
  {{
    "id": "{parent_id}-budget",
    "thought": "My Khe Beach (free) + Marble Mountains ($2) + street food ($30 for 3 days). Activities total: $32.",
    "activities_cost": 32.0
  }},
  {{
    "id": "{parent_id}-premium",
    "thought": "Ba Na Hills ($35) + Hoi An day trip ($10) + restaurants ($40). Activities total: $85.",
    "activities_cost": 85.0
  }}
]"""

SCORER_PROMPT = """Rate the following partial travel plan from 0.0 to 1.0.

Scoring criteria:
- Comfort: Is transport and accommodation reasonably comfortable? (weight: 30%)
- Experience quality: Do the activities/choices make for a memorable trip? (weight: 40%)
- Value for money: Is the plan a good use of the available budget? (weight: 30%)

Score 1.0 = excellent on all criteria. Score 0.0 = poor on all criteria.

Partial travel plan:
{branch_description}

Respond with ONLY a single float between 0.0 and 1.0. No explanation."""

SOLVER_PROMPT = """You are a travel planner. Write a detailed 3-day itinerary for a trip from Hanoi to Da Nang based on the following chosen plan:

Transport: {transport_thought}
Accommodation: {hotel_thought}
Activities: {activities_thought}
Total estimated cost: ${total_cost:.0f} (budget: $300)

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
[3-5 bullet points: booking advice, local transport, weather, etc.]"""
