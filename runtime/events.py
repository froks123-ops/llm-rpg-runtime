"""Immutable append-only event records and activity projection."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping
import copy
import uuid


@dataclass(frozen=True)
class EventAppendResult:
    events: list[dict[str, Any]]
    event: dict[str, Any]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def next_sequence(events: Iterable[Mapping[str, Any]]) -> int:
    highest = 0
    for event in events:
        seq = event.get("seq", 0)
        if isinstance(seq, int) and not isinstance(seq, bool):
            highest = max(highest, seq)
    return highest + 1


def validate_event_order(events: Iterable[Mapping[str, Any]]) -> list[str]:
    errors: list[str] = []
    seen_ids: set[str] = set()
    previous_seq = 0
    for index, event in enumerate(events):
        event_id = event.get("id")
        seq = event.get("seq")
        if not isinstance(event_id, str) or not event_id:
            errors.append(f"event[{index}] has no valid id")
        elif event_id in seen_ids:
            errors.append(f"duplicate event id: {event_id}")
        else:
            seen_ids.add(event_id)
        if not isinstance(seq, int) or isinstance(seq, bool) or seq <= 0:
            errors.append(f"event[{index}] has invalid seq")
        elif seq <= previous_seq:
            errors.append(f"event[{index}] seq is not strictly increasing")
        else:
            previous_seq = seq
    return errors


def make_event(
    *,
    seq: int,
    kind: str,
    source: Mapping[str, Any],
    summary: str,
    mutations: list[Mapping[str, Any]] | None = None,
    fact_ids: list[str] | None = None,
    event_ids: list[str] | None = None,
    actor: str | None = None,
    targets: list[str] | None = None,
    event_id: str | None = None,
    timestamp: str | None = None,
    status: str = "active",
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if seq < 1:
        raise ValueError("seq must be >= 1")
    if not kind.strip():
        raise ValueError("kind cannot be empty")
    return {
        "id": event_id or f"evt:{uuid.uuid4()}",
        "seq": seq,
        "timestamp": timestamp or utc_now(),
        "kind": kind,
        "status": status,
        "source": dict(source),
        "actor": actor,
        "targets": list(targets or []),
        "dependencies": {
            "fact_ids": list(fact_ids or []),
            "event_ids": list(event_ids or []),
        },
        "mutations": [dict(mutation) for mutation in (mutations or [])],
        "metadata": dict(metadata or {}),
        "summary": summary,
    }


def append_event(
    events: Iterable[Mapping[str, Any]],
    **event_kwargs: Any,
) -> EventAppendResult:
    out = [copy.deepcopy(dict(event)) for event in events]
    event = make_event(seq=next_sequence(out), **event_kwargs)
    out.append(event)
    errors = validate_event_order(out)
    if errors:
        raise ValueError("; ".join(errors))
    return EventAppendResult(out, event)


def dependent_event_ids(
    events: Iterable[Mapping[str, Any]],
    invalid_fact_ids: set[str],
    invalid_event_ids: set[str] | None = None,
) -> tuple[str, ...]:
    """Calculate which historical events are causally invalid without mutating them."""

    event_list = list(events)
    invalidated = set(invalid_event_ids or set())

    for event in event_list:
        if event.get("status", "active") == "invalidated":  # legacy compatibility
            invalidated.add(str(event.get("id", "")))
            continue
        # Invalidation control events describe the correction; they are not themselves
        # causal consequences of the facts they invalidate.
        if event.get("kind") in {"retcon.applied", "event.invalidation"}:
            continue
        dependencies = event.get("dependencies", {}) or {}
        fact_ids = set(dependencies.get("fact_ids", []) or [])
        targets = set(event.get("targets", []) or [])
        if fact_ids.intersection(invalid_fact_ids) or targets.intersection(invalid_fact_ids):
            invalidated.add(str(event.get("id", "")))

    changed = True
    while changed:
        changed = False
        for event in event_list:
            event_id = str(event.get("id", ""))
            if event_id in invalidated:
                continue
            dependencies = event.get("dependencies", {}) or {}
            if set(dependencies.get("event_ids", []) or []).intersection(invalidated):
                invalidated.add(event_id)
                changed = True

    invalidated.discard("")
    return tuple(sorted(invalidated))


def resolve_invalidated_event_ids(events: Iterable[Mapping[str, Any]]) -> tuple[str, ...]:
    """Project invalidated event IDs from immutable invalidation/retcon events."""

    event_list = list(events)
    invalid_facts: set[str] = set()
    explicit_events: set[str] = set()
    for event in event_list:
        if event.get("status", "active") == "invalidated":  # legacy import path
            explicit_events.add(str(event.get("id", "")))
        metadata = event.get("metadata", {}) or {}
        invalid_facts.update(str(value) for value in metadata.get("invalidates_fact_ids", []) or [])
        explicit_events.update(str(value) for value in metadata.get("invalidates_event_ids", []) or [])
    explicit_events.discard("")
    return dependent_event_ids(event_list, invalid_facts, explicit_events)


def active_events(events: Iterable[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    event_list = list(events)
    invalidated = set(resolve_invalidated_event_ids(event_list))
    return [event for event in event_list if str(event.get("id", "")) not in invalidated]
