from dataclasses import dataclass, field

MAX_DEPTH = 3


@dataclass
class ThoughtNode:
    id: str
    parent_id: str | None
    thought: str
    depth: int
    score: float
    cost_so_far: float
    children: list["ThoughtNode"] = field(default_factory=list)
    is_pruned: bool = False
    is_complete: bool = False  # True when depth == MAX_DEPTH
