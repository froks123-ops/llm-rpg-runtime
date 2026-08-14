from __future__ import annotations
from dataclasses import dataclass
import random
from typing import Any

@dataclass(frozen=True)
class TickResult:
    entity: str
    goal: str
    roll: int
    dc: int
    outcome: str
    progress_delta: int


def tick_goal(entity: str, goal: dict[str, Any], seed: int | None = None) -> TickResult:
    # Engine resolves probability; LLM may interpret consequences afterwards.
    g = random.Random(seed) if seed is not None else random.SystemRandom()
    roll = g.randint(1, 100)
    dc = int(goal.get('dc', 60))
    if roll >= min(100, dc + 30):
        outcome, delta = 'major_success', 2
    elif roll >= dc:
        outcome, delta = 'success', 1
    elif roll <= max(1, dc - 40):
        outcome, delta = 'major_failure', -1
    else:
        outcome, delta = 'no_progress', 0
    return TickResult(entity, str(goal.get('id', 'goal')), roll, dc, outcome, delta)
