"""Cross-document campaign integrity checks.

JSON Schema validates shape. This module validates *relationships between documents*:
IDs, lifecycle references, HEAD pointers, event ordering and retcon fallout.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from .events import resolve_invalidated_event_ids, validate_event_order
from .facts import fact_map, is_fact_active, resolve_state_slots
from .knowledge import audit_actor_knowledge, audit_knowledge, parse_known_by_token


@dataclass(frozen=True)
class IntegrityIssue:
    level: str
    code: str
    message: str
    path: str = ""


def _dependency_cycles(facts_by_id: Mapping[str, Mapping[str, Any]]) -> list[list[str]]:
    cycles: list[list[str]] = []
    visiting: set[str] = set()
    visited: set[str] = set()
    stack: list[str] = []

    def visit(fact_id: str) -> None:
        if fact_id in visited:
            return
        if fact_id in visiting:
            if fact_id in stack:
                start = stack.index(fact_id)
                cycles.append(stack[start:] + [fact_id])
            return
        visiting.add(fact_id)
        stack.append(fact_id)
        for dependency in facts_by_id[fact_id].get("depends_on", []) or []:
            if dependency in facts_by_id:
                visit(str(dependency))
        stack.pop()
        visiting.remove(fact_id)
        visited.add(fact_id)

    for fact_id in facts_by_id:
        visit(fact_id)
    return cycles


def audit_campaign(
    *,
    manifest: Mapping[str, Any],
    head: Mapping[str, Any],
    active_state: Mapping[str, Any],
    npc_state: Mapping[str, Any],
    thread_state: Mapping[str, Any],
    facts: Iterable[Mapping[str, Any]],
    events: Iterable[Mapping[str, Any]],
) -> list[IntegrityIssue]:
    issues: list[IntegrityIssue] = []
    facts_list = list(facts)
    events_list = list(events)

    try:
        facts_by_id = fact_map(facts_list)
    except ValueError as error:
        issues.append(IntegrityIssue("error", "fact_id_integrity", str(error), "facts"))
        return issues

    # Fact dependency graph and lifecycle.
    for fact_id, fact in facts_by_id.items():
        for dependency in fact.get("depends_on", []) or []:
            if dependency not in facts_by_id:
                issues.append(
                    IntegrityIssue(
                        "error",
                        "missing_fact_dependency",
                        f"Fact depends on missing fact {dependency!r}.",
                        f"facts.{fact_id}.depends_on",
                    )
                )
            elif is_fact_active(fact) and not is_fact_active(facts_by_id[str(dependency)]):
                issues.append(
                    IntegrityIssue(
                        "error",
                        "active_fact_depends_on_inactive_fact",
                        f"Active fact depends on inactive fact {dependency!r}; retcon/supersession projection is stale.",
                        f"facts.{fact_id}.depends_on",
                    )
                )

        known_by = fact.get("known_by")
        if isinstance(known_by, list):
            for token in known_by:
                parsed = parse_known_by_token(token)
                if parsed and parsed.kind == "npc" and parsed.value not in npc_state.get("npcs", {}):
                    issues.append(
                        IntegrityIssue(
                            "warning",
                            "unknown_known_by_npc",
                            f"known_by references unknown NPC {parsed.value!r}.",
                            f"facts.{fact_id}.known_by",
                        )
                    )

    for cycle in _dependency_cycles(facts_by_id):
        issues.append(
            IntegrityIssue(
                "error",
                "fact_dependency_cycle",
                "Fact dependency cycle: " + " -> ".join(cycle),
                "facts",
            )
        )

    try:
        resolve_state_slots(facts_list)
    except ValueError as error:
        issues.append(IntegrityIssue("error", "state_slot_conflict", str(error), "facts"))

    # Active mechanical state must describe the same player character routed by HEAD.
    if active_state is not None:
        active_actor = active_state.get("actor_id")
        head_actor = head.get("player_character")
        if head_actor and active_actor != head_actor:
            issues.append(
                IntegrityIssue(
                    "error",
                    "active_state_actor_mismatch",
                    f"Active state actor {active_actor!r} != HEAD player character {head_actor!r}.",
                    "active_state.actor_id",
                )
            )

    # Player-character epistemics.
    for issue in audit_actor_knowledge(
        active_state.get("knowledge", {}) or {}, facts_list,
        actor_id=str(active_state.get("actor_id", "player")),
    ):
        issues.append(
            IntegrityIssue(
                issue.level, issue.code, issue.message,
                f"active_state.knowledge.{issue.actor_id}",
            )
        )

    # NPC epistemics.
    for issue in audit_knowledge(npc_state, facts_list):
        issues.append(
            IntegrityIssue(
                issue.level,
                issue.code,
                issue.message,
                f"npc_state.npcs.{issue.npc_id}.knowledge",
            )
        )

    npcs = npc_state.get("npcs", {}) or {}
    for npc_id in head.get("present_npcs", head.get("present", [])) or []:
        if npc_id not in npcs:
            issues.append(
                IntegrityIssue(
                    "error",
                    "head_unknown_present_npc",
                    f"HEAD lists unknown NPC {npc_id!r} as present.",
                    "head.present_npcs",
                )
            )

    # Relationships and goals that cite facts.
    for npc_id, npc in npcs.items():
        for other_id, relationship in (npc.get("relationships", {}) or {}).items():
            if relationship.get("needs_rebuild"):
                issues.append(
                    IntegrityIssue(
                        "warning",
                        "relationship_needs_rebuild",
                        "Relationship aggregate is withheld from active context until rebuilt.",
                        f"npc_state.npcs.{npc_id}.relationships.{other_id}",
                    )
                )
            for fact_id in relationship.get("basis_fact_ids", []) or []:
                fact = facts_by_id.get(fact_id)
                if fact is None:
                    issues.append(
                        IntegrityIssue(
                            "error",
                            "relationship_missing_basis_fact",
                            f"Relationship basis references missing fact {fact_id!r}.",
                            f"npc_state.npcs.{npc_id}.relationships.{other_id}",
                        )
                    )
                elif not is_fact_active(fact) and not relationship.get("needs_rebuild"):
                    issues.append(
                        IntegrityIssue(
                            "error",
                            "relationship_stale_basis",
                            f"Relationship basis contains inactive fact {fact_id!r} without needs_rebuild flag.",
                            f"npc_state.npcs.{npc_id}.relationships.{other_id}",
                        )
                    )
        for goal in npc.get("goals", []) or []:
            if goal.get("status", "active") != "active":
                continue
            for fact_id in goal.get("depends_on_fact_ids", []) or []:
                fact = facts_by_id.get(fact_id)
                if fact is None or not is_fact_active(fact):
                    issues.append(
                        IntegrityIssue(
                            "error",
                            "active_goal_invalid_dependency",
                            f"Active goal depends on missing/inactive fact {fact_id!r}.",
                            f"npc_state.npcs.{npc_id}.goals.{goal.get('id', '')}",
                        )
                    )

    # Thread dependencies and HEAD routing.
    threads = thread_state.get("threads", {}) or {}
    for thread_id in head.get("active_threads", []) or []:
        thread = threads.get(thread_id)
        if thread is None:
            issues.append(
                IntegrityIssue(
                    "error",
                    "head_unknown_active_thread",
                    f"HEAD references unknown active thread {thread_id!r}.",
                    "head.active_threads",
                )
            )
        elif thread.get("status") != "active":
            issues.append(
                IntegrityIssue(
                    "error",
                    "head_nonactive_thread",
                    f"HEAD routes to thread {thread_id!r} with status {thread.get('status')!r}.",
                    "head.active_threads",
                )
            )

    for thread_id, thread in threads.items():
        if thread.get("status") != "active":
            continue
        for fact_id in thread.get("depends_on_fact_ids", []) or []:
            fact = facts_by_id.get(fact_id)
            if fact is None or not is_fact_active(fact):
                issues.append(
                    IntegrityIssue(
                        "error",
                        "active_thread_invalid_dependency",
                        f"Active thread depends on missing/inactive fact {fact_id!r}.",
                        f"thread_state.threads.{thread_id}",
                    )
                )

    # Manifest/HEAD continuity.
    current_session = manifest.get("current_session", manifest.get("currentSession"))
    if current_session is not None and current_session != head.get("session"):
        issues.append(
            IntegrityIssue(
                "error",
                "manifest_head_session_mismatch",
                f"Manifest session {current_session!r} != HEAD session {head.get('session')!r}.",
                "manifest.current_session",
            )
        )
    current_scene = manifest.get("current_scene", manifest.get("currentScene", {})) or {}
    if isinstance(current_scene, Mapping):
        scene_id = current_scene.get("id")
        if scene_id and scene_id != head.get("scene_id"):
            issues.append(
                IntegrityIssue(
                    "error",
                    "manifest_head_scene_mismatch",
                    f"Manifest scene {scene_id!r} != HEAD scene {head.get('scene_id')!r}.",
                    "manifest.current_scene",
                )
            )

    # Event stream integrity and references.
    for message in validate_event_order(events_list):
        issues.append(IntegrityIssue("error", "event_order", message, "event_log"))
    event_ids = {str(event.get("id")) for event in events_list if event.get("id")}
    projected_invalid_events = set(resolve_invalidated_event_ids(events_list))
    highest_seq = max((event.get("seq", 0) for event in events_list if isinstance(event.get("seq"), int)), default=0)
    manifest_seq = manifest.get("last_event_seq")
    if isinstance(manifest_seq, int) and manifest_seq != highest_seq:
        issues.append(
            IntegrityIssue(
                "error",
                "manifest_event_seq_mismatch",
                f"Manifest last_event_seq {manifest_seq} != event log {highest_seq}.",
                "manifest.last_event_seq",
            )
        )

    for event in events_list:
        dependencies = event.get("dependencies", {}) or {}
        for fact_id in dependencies.get("fact_ids", []) or []:
            if fact_id not in facts_by_id:
                issues.append(
                    IntegrityIssue(
                        "error",
                        "event_missing_fact_dependency",
                        f"Event depends on missing fact {fact_id!r}.",
                        f"event_log.{event.get('id', '')}",
                    )
                )
            elif (
                event.get("status", "active") == "active"
                and str(event.get("id", "")) not in projected_invalid_events
                and not is_fact_active(facts_by_id[fact_id])
            ):
                issues.append(
                    IntegrityIssue(
                        "error",
                        "active_event_inactive_fact_dependency",
                        f"Active event depends on inactive fact {fact_id!r}.",
                        f"event_log.{event.get('id', '')}",
                    )
                )
        for parent_event_id in dependencies.get("event_ids", []) or []:
            if parent_event_id not in event_ids:
                issues.append(
                    IntegrityIssue(
                        "error",
                        "event_missing_event_dependency",
                        f"Event depends on missing event {parent_event_id!r}.",
                        f"event_log.{event.get('id', '')}",
                    )
                )

    return issues


def has_errors(issues: Iterable[IntegrityIssue]) -> bool:
    return any(issue.level == "error" for issue in issues)
