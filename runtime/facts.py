"""Fact lifecycle, supersession and retcon propagation."""

from __future__ import annotations

from dataclasses import dataclass
import copy
from typing import Any, Iterable, Mapping


ACTIVE_STATUSES = {"active", "canonical"}  # ``canonical`` is v0.1 compatibility.
INACTIVE_STATUSES = {"superseded", "retconned", "retracted"}


@dataclass(frozen=True)
class RetconResult:
    facts: list[dict[str, Any]]
    invalidated_fact_ids: tuple[str, ...]
    missing_target_ids: tuple[str, ...]


@dataclass(frozen=True)
class SupersedeResult:
    facts: list[dict[str, Any]]
    replaced_fact_id: str | None
    reason: str


def is_fact_active(fact: Mapping[str, Any]) -> bool:
    return str(fact.get("status", "active")) in ACTIVE_STATUSES


def fact_map(facts: Iterable[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    result: dict[str, Mapping[str, Any]] = {}
    for fact in facts:
        fact_id = fact.get("id")
        if not isinstance(fact_id, str) or not fact_id:
            raise ValueError("every fact must have a non-empty string id")
        if fact_id in result:
            raise ValueError(f"duplicate fact id: {fact_id}")
        result[fact_id] = fact
    return result


def active_facts(facts: Iterable[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    return [fact for fact in facts if is_fact_active(fact)]


def resolve_state_slots(
    facts: Iterable[Mapping[str, Any]],
) -> dict[str, Mapping[str, Any]]:
    """Resolve singleton state slots by explicit lifecycle, then source order.

    Only facts with a ``state_key`` participate. Multiple active facts in the same slot
    are treated as an integrity error instead of silently picking a winner.
    """

    slots: dict[str, Mapping[str, Any]] = {}
    for fact in facts:
        if not is_fact_active(fact):
            continue
        state_key = fact.get("state_key")
        if not state_key:
            continue
        if state_key in slots:
            raise ValueError(f"multiple active facts for state_key {state_key!r}")
        slots[str(state_key)] = fact
    return slots


def supersede_fact(
    facts: Iterable[Mapping[str, Any]],
    new_fact: Mapping[str, Any],
    supersedes_fact_id: str | None = None,
) -> SupersedeResult:
    """Append a fact and guardedly supersede one exact state-slot predecessor.

    Fail closed: a target is replaced only when it exists, is active, and has the exact
    same non-empty ``state_key`` as the new fact. Ambiguous requests become additive.
    """

    out = [copy.deepcopy(dict(fact)) for fact in facts]
    new_record = copy.deepcopy(dict(new_fact))
    new_record.setdefault("status", "active")
    target_id = supersedes_fact_id or new_record.get("supersedes")
    new_key = new_record.get("state_key")
    replaced: str | None = None
    reason = "additive"

    if target_id and new_key:
        for index, existing in enumerate(out):
            if existing.get("id") != target_id:
                continue
            if is_fact_active(existing) and existing.get("state_key") == new_key:
                out[index]["status"] = "superseded"
                out[index]["superseded_by"] = new_record.get("id")
                replaced = str(target_id)
                reason = "same_state_slot"
            else:
                reason = "guard_rejected"
            break
        else:
            reason = "target_missing"

    out.append(new_record)
    fact_map(out)  # enforce unique IDs.
    return SupersedeResult(out, replaced, reason)


def cascade_retcon(
    facts: Iterable[Mapping[str, Any]],
    target_fact_ids: Iterable[str],
    *,
    reason: str = "",
    retcon_event_id: str | None = None,
) -> RetconResult:
    """Retcon target facts and all facts that hard-depend on them.

    ``depends_on`` means the dependent fact is invalid if *any* dependency becomes
    invalid. The function mutates only lifecycle metadata; cleanup of NPC knowledge,
    threads and other projections is handled by dedicated helpers so the impact remains
    auditable.
    """

    out = [copy.deepcopy(dict(fact)) for fact in facts]
    by_id = {str(f["id"]): f for f in out}
    requested = {str(fid) for fid in target_fact_ids}
    missing = sorted(fid for fid in requested if fid not in by_id)
    invalidated = {fid for fid in requested if fid in by_id}

    changed = True
    while changed:
        changed = False
        for fact_id, fact in by_id.items():
            if fact_id in invalidated:
                continue
            dependencies = set(fact.get("depends_on", []) or [])
            if dependencies.intersection(invalidated):
                invalidated.add(fact_id)
                changed = True

    for fact_id in sorted(invalidated):
        fact = by_id[fact_id]
        fact["status"] = "retconned"
        if reason:
            fact["retcon_reason"] = reason
        if retcon_event_id:
            fact["retconned_by"] = retcon_event_id

    return RetconResult(out, tuple(sorted(invalidated)), tuple(missing))
