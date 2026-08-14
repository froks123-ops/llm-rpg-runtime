"""Central randomness helpers.

Runtime calls use ``random.SystemRandom`` by default. Supplying a seed switches to a
reproducible PRNG for tests, replays and deterministic simulations.
"""

from __future__ import annotations

from dataclasses import dataclass
import random
import re
from typing import Sequence, TypeVar

T = TypeVar("T")
_DICE_RE = re.compile(r"^\s*(?P<count>\d*)d(?P<sides>\d+)\s*(?P<mod>[+-]\s*\d+)?\s*$", re.I)


@dataclass(frozen=True)
class Roll:
    low: int
    high: int
    value: int
    seed: int | None = None


@dataclass(frozen=True)
class DiceRoll:
    notation: str
    rolls: tuple[int, ...]
    kept: tuple[int, ...]
    dropped: tuple[int, ...]
    modifier: int
    total: int
    mode: str
    seed: int | None = None


def _gen(seed: int | None = None) -> random.Random:
    return random.Random(seed) if seed is not None else random.SystemRandom()


def randint(low: int, high: int, seed: int | None = None) -> Roll:
    if isinstance(low, bool) or isinstance(high, bool):
        raise ValueError("bounds must be integers, not booleans")
    if low > high:
        raise ValueError("low must be <= high")
    generator = _gen(seed)
    return Roll(low, high, generator.randint(low, high), seed)


def d100(seed: int | None = None) -> Roll:
    return randint(1, 100, seed)


def choice(items: Sequence[T], seed: int | None = None) -> T:
    if not items:
        raise ValueError("items cannot be empty")
    return _gen(seed).choice(list(items))


def weighted_choice(items: Sequence[T], weights: Sequence[float], seed: int | None = None) -> T:
    if len(items) != len(weights) or not items:
        raise ValueError("items and weights must have equal non-zero length")
    if any(weight < 0 for weight in weights) or sum(weights) <= 0:
        raise ValueError("weights must be non-negative and sum > 0")
    return _gen(seed).choices(list(items), weights=list(weights), k=1)[0]


def shuffle(items: Sequence[T], seed: int | None = None) -> list[T]:
    out = list(items)
    _gen(seed).shuffle(out)
    return out


def sample(items: Sequence[T], count: int, seed: int | None = None) -> list[T]:
    if count < 0 or count > len(items):
        raise ValueError("count must be between 0 and len(items)")
    return _gen(seed).sample(list(items), count)


def chance(percent: float, seed: int | None = None) -> tuple[bool, Roll]:
    if not 0 <= percent <= 100:
        raise ValueError("percent must be between 0 and 100")
    roll = d100(seed)
    return roll.value <= percent, roll


def parse_dice(notation: str) -> tuple[int, int, int]:
    match = _DICE_RE.match(notation)
    if not match:
        raise ValueError(f"unsupported dice notation: {notation!r}")
    count = int(match.group("count") or "1")
    sides = int(match.group("sides"))
    modifier = int((match.group("mod") or "0").replace(" ", ""))
    if not 1 <= count <= 100:
        raise ValueError("dice count must be between 1 and 100")
    if sides < 2:
        raise ValueError("dice sides must be >= 2")
    return count, sides, modifier


def roll_dice(notation: str, mode: str = "normal", seed: int | None = None) -> DiceRoll:
    count, sides, modifier = parse_dice(notation)
    mode = mode.lower().strip()
    if mode not in {"normal", "advantage", "disadvantage"}:
        raise ValueError("mode must be normal, advantage or disadvantage")
    if mode != "normal" and (count, sides) != (1, 20):
        raise ValueError("advantage/disadvantage only apply to 1d20")

    generator = _gen(seed)
    if mode == "normal":
        rolls = tuple(generator.randint(1, sides) for _ in range(count))
        kept = rolls
        dropped: tuple[int, ...] = ()
    else:
        rolls = (generator.randint(1, 20), generator.randint(1, 20))
        kept_value = max(rolls) if mode == "advantage" else min(rolls)
        dropped_value = min(rolls) if mode == "advantage" else max(rolls)
        kept = (kept_value,)
        dropped = (dropped_value,)

    normalized = f"{count}d{sides}" + (f"+{modifier}" if modifier > 0 else str(modifier) if modifier < 0 else "")
    return DiceRoll(
        notation=normalized,
        rolls=rolls,
        kept=kept,
        dropped=dropped,
        modifier=modifier,
        total=sum(kept) + modifier,
        mode=mode,
        seed=seed,
    )
