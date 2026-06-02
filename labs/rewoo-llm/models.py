from dataclasses import dataclass, field


@dataclass
class Step:
    var: str        # e.g. "#E1"
    tool: str       # e.g. "search"
    args: list[str] = field(default_factory=list)  # may contain "#En" references


@dataclass
class Plan:
    steps: list[Step] = field(default_factory=list)


@dataclass
class Evidence:
    var: str    # e.g. "#E1"
    value: str  # result of the tool call
