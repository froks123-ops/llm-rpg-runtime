from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .rng import d100


@dataclass(frozen=True)
class TickResult:
    entity: str
    goal: str
    roll: int | None
    effective_roll: int | None
    dc: int
    outcome: str
    progress_delta: int


def tick_goal(entity: str, goal: dict[str, Any], seed: int | None = None) -> TickResult:
    """Resolve one off-screen goal tick mechanically.

    The caller decides *when* a heartbeat is warranted. The engine only resolves the
    uncertainty after that decision. Inactive goals are skipped without consuming RNG.
    """

    status = str(goal.get("status", "active"))
    dc = int(goal.get("dc", 60))
    if not 1 <= dc <= 100:
        raise ValueError("goal dc must be between 1 and 100")
    if status != "active":
        return TickResult(entity, str(goal.get("id", "goal")), None, None, dc, "skipped", 0)

    modifier = int(goal.get("modifier", 0))
    raw = d100(seed).value
    effective = max(1, min(100, raw + modifier))
    if effective >= min(100, dc + 30):
        outcome, delta = "major_success", 2
    elif effective >= dc:
        outcome, delta = "success", 1
    elif effective <= max(1, dc - 40):
        outcome, delta = "major_failure", -1
    else:
        outcome, delta = "no_progress", 0
    return TickResult(
        entity,
        str(goal.get("id", "goal")),
        raw,
        effective,
        dc,
        outcome,
        delta,
    )
