from __future__ import annotations
import random
from dataclasses import dataclass
from typing import Sequence, TypeVar

T = TypeVar('T')

@dataclass(frozen=True)
class Roll:
    low: int
    high: int
    value: int
    seed: int | None = None


def _gen(seed: int | None = None) -> random.Random:
    return random.Random(seed) if seed is not None else random.SystemRandom()


def randint(low: int, high: int, seed: int | None = None) -> Roll:
    if low > high:
        raise ValueError('low must be <= high')
    g = _gen(seed)
    return Roll(low, high, g.randint(low, high), seed)


def d100(seed: int | None = None) -> Roll:
    return randint(1, 100, seed)


def choice(items: Sequence[T], seed: int | None = None) -> T:
    if not items:
        raise ValueError('items cannot be empty')
    return _gen(seed).choice(list(items))


def weighted_choice(items: Sequence[T], weights: Sequence[float], seed: int | None = None) -> T:
    if len(items) != len(weights) or not items:
        raise ValueError('items and weights must have equal non-zero length')
    if any(w < 0 for w in weights) or sum(weights) <= 0:
        raise ValueError('weights must be non-negative and sum > 0')
    return _gen(seed).choices(list(items), weights=list(weights), k=1)[0]


def shuffle(items: Sequence[T], seed: int | None = None) -> list[T]:
    out = list(items)
    _gen(seed).shuffle(out)
    return out
