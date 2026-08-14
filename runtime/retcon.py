"""Cross-document retcon impact planning.

Retcons are destructive semantic operations. This module separates deterministic
invalidation from persistence so a caller can checkpoint, inspect the impact and then
write with optimistic concurrency. Historical events remain immutable.
"""

from __future__ import annotations

from dataclasses import dataclass
import copy
from typing import Any, Mapping

from .events import dependent_event_ids, make_event
from .facts import cascade_retcon
from .knowledge import sanitize_actor_knowledge, sanitize_knowledge


@dataclass(frozen=True)
class RetconPlan:
    facts: list[dict[str, Any]]
    head: dict[str, Any]
    active_state: dict[str, Any]
    npc_state: dict[str, Any]
    thread_state: dict[str, Any]
    events: list[dict[str, Any]]
    invalidated_fact_ids: tuple[str, ...]
    invalidated_thread_ids: tuple[str, ...]
    invalidated_goal_paths: tuple[str, ...]
    invalidated_event_ids: tuple[str, ...]
    removed_knowledge: dict[str, dict[str, list[str]]]
    removed_player_knowledge: dict[str, list[str]]
    relationship_review_paths: tuple[str, ...]
    missing_fact_ids: tuple[str, ...]


def plan_retcon(
    *,
    facts: list[Mapping[str, Any]],
    head: Mapping[str, Any],
    active_state: Mapping[str, Any],
    npc_state: Mapping[str, Any],
    thread_state: Mapping[str, Any],
    events: list[Mapping[str, Any]],
    target_fact_ids: list[str],
    reason: str = "",
    retcon_event_id: str | None = None,
) -> RetconPlan:
    fact_result = cascade_retcon(
        facts,
        target_fact_ids,
        reason=reason,
        retcon_event_id=retcon_event_id,
    )
    invalid = set(fact_result.invalidated_fact_ids)
    clean_npc_state, removed = sanitize_knowledge(npc_state, invalid)
    clean_active_state = copy.deepcopy(dict(active_state))
    clean_pc_knowledge, removed_player = sanitize_actor_knowledge(
        clean_active_state.get("knowledge", {}) or {}, invalid
    )
    clean_active_state["knowledge"] = clean_pc_knowledge

    clean_threads = copy.deepcopy(dict(thread_state))
    invalid_threads: list[str] = []
    for thread_id, thread in clean_threads.get("threads", {}).items():
        dependencies = set(thread.get("depends_on_fact_ids", []) or [])
        if dependencies.intersection(invalid) and thread.get("status") not in {"resolved", "invalidated"}:
            thread["status"] = "invalidated"
            thread["invalidated_by_retcon"] = sorted(dependencies.intersection(invalid))
            invalid_threads.append(thread_id)

    clean_head = copy.deepcopy(dict(head))
    if invalid_threads:
        active_threads = list(clean_head.get("active_threads", []) or [])
        clean_head["active_threads"] = [
            thread_id for thread_id in active_threads if thread_id not in set(invalid_threads)
        ]

    invalid_goals: list[str] = []
    for npc_id, npc in clean_npc_state.get("npcs", {}).items():
        for goal in npc.get("goals", []) or []:
            dependencies = set(goal.get("depends_on_fact_ids", []) or [])
            if goal.get("status", "active") == "active" and dependencies.intersection(invalid):
                goal["status"] = "invalidated"
                goal["invalidated_by_retcon"] = sorted(dependencies.intersection(invalid))
                invalid_goals.append(f"npcs.{npc_id}.goals.{goal.get('id', '')}")

    immutable_events = [copy.deepcopy(dict(event)) for event in events]
    invalid_event_ids = dependent_event_ids(immutable_events, invalid)

    review_paths: list[str] = []
    for npc_id, npc in clean_npc_state.get("npcs", {}).items():
        relationships = npc.get("relationships", {})
        for other_id, relationship in relationships.items():
            basis = set(relationship.get("basis_fact_ids", []) or [])
            impacted = basis.intersection(invalid)
            if impacted:
                relationship["basis_fact_ids"] = [fid for fid in relationship.get("basis_fact_ids", []) if fid not in invalid]
                relationship["needs_rebuild"] = True
                relationship["invalidated_basis_fact_ids"] = sorted(impacted)
                review_paths.append(f"npcs.{npc_id}.relationships.{other_id}")

    return RetconPlan(
        facts=fact_result.facts,
        head=clean_head,
        active_state=clean_active_state,
        npc_state=clean_npc_state,
        thread_state=clean_threads,
        events=immutable_events,
        invalidated_fact_ids=fact_result.invalidated_fact_ids,
        invalidated_thread_ids=tuple(sorted(invalid_threads)),
        invalidated_goal_paths=tuple(sorted(invalid_goals)),
        invalidated_event_ids=invalid_event_ids,
        removed_knowledge=removed,
        removed_player_knowledge=removed_player,
        relationship_review_paths=tuple(sorted(review_paths)),
        missing_fact_ids=fact_result.missing_target_ids,
    )


def make_retcon_event(
    plan: RetconPlan,
    *,
    seq: int,
    source: Mapping[str, Any],
    summary: str,
    event_id: str | None = None,
    timestamp: str | None = None,
) -> dict[str, Any]:
    """Create the immutable event that records a previously computed retcon plan."""

    return make_event(
        seq=seq,
        kind="retcon.applied",
        source=source,
        summary=summary,
        event_id=event_id,
        timestamp=timestamp,
        targets=list(plan.invalidated_fact_ids),
        metadata={
            "invalidates_fact_ids": list(plan.invalidated_fact_ids),
            "invalidates_event_ids": list(plan.invalidated_event_ids),
            "invalidates_thread_ids": list(plan.invalidated_thread_ids),
            "invalidates_goal_paths": list(plan.invalidated_goal_paths),
            "relationship_review_paths": list(plan.relationship_review_paths),
        },
    )

@dataclass(frozen=True)
class RetconTransaction:
    ok: bool
    checkpoint_id: str
    plan: RetconPlan
    event: dict[str, Any] | None
    documents: dict[str, Any]
    changes: tuple[dict[str, Any], ...]
    validation_errors: dict[str, tuple[str, ...]]
    integrity_issues: tuple[Any, ...]
    expected_revisions: dict[str, str]


def prepare_retcon_transaction(
    *,
    documents: Mapping[str, Any],
    schemas: Mapping[str, Mapping[str, Any]],
    target_fact_ids: list[str],
    checkpoint_id: str,
    source: Mapping[str, Any],
    summary: str,
    seq: int,
    event_id: str,
    timestamp: str | None = None,
    reason: str = "",
    expected_revisions: Mapping[str, str] | None = None,
) -> RetconTransaction:
    """Prepare a checkpoint-gated retcon as one auditable persistence payload."""

    if not checkpoint_id.strip():
        raise ValueError("checkpoint_id is required for a destructive retcon transaction")

    required = {"manifest", "head", "active_state", "npc_state", "thread_state", "facts", "event_log"}
    missing = sorted(required - set(documents))
    if missing:
        raise ValueError("missing campaign documents: " + ", ".join(missing))

    from .integrity import audit_campaign, has_errors
    from .state_diff import diff
    from .state_validate import validate_data

    plan = plan_retcon(
        facts=list(documents["facts"]),
        head=documents["head"],
        active_state=documents["active_state"],
        npc_state=documents["npc_state"],
        thread_state=documents["thread_state"],
        events=list(documents["event_log"]),
        target_fact_ids=target_fact_ids,
        reason=reason,
        retcon_event_id=event_id,
    )
    if plan.missing_fact_ids:
        return RetconTransaction(
            False,
            checkpoint_id,
            plan,
            None,
            copy.deepcopy(dict(documents)),
            (),
            {},
            (),
            dict(expected_revisions or {}),
        )

    after = copy.deepcopy(dict(documents))
    after["facts"] = plan.facts
    after["head"] = plan.head
    after["active_state"] = plan.active_state
    after["npc_state"] = plan.npc_state
    after["thread_state"] = plan.thread_state

    mutation_records: list[dict[str, Any]] = []
    for name in ("facts", "head", "active_state", "npc_state", "thread_state"):
        for change in diff(documents[name], after[name]):
            mutation_records.append(
                {
                    "document": name,
                    "op": change.op,
                    "path": change.path,
                    "before": change.before,
                    "after": change.after,
                }
            )

    event = make_retcon_event(
        plan,
        seq=seq,
        source=source,
        summary=summary,
        event_id=event_id,
        timestamp=timestamp,
    )
    event["mutations"] = mutation_records
    event["metadata"]["checkpoint_id"] = checkpoint_id

    after["event_log"] = list(plan.events) + [event]
    after["manifest"] = copy.deepcopy(after["manifest"])
    after["manifest"]["last_event_seq"] = seq
    after["head"] = copy.deepcopy(after["head"])
    after["head"]["last_canonical_event_id"] = event_id

    validation_errors: dict[str, tuple[str, ...]] = {}
    for name, schema in schemas.items():
        if name not in after:
            continue
        errors = validate_data(after[name], schema)
        if errors:
            validation_errors[name] = tuple(errors)
    if validation_errors:
        return RetconTransaction(
            False,
            checkpoint_id,
            plan,
            event,
            after,
            tuple(mutation_records),
            validation_errors,
            (),
            dict(expected_revisions or {}),
        )

    issues = tuple(
        audit_campaign(
            manifest=after["manifest"],
            head=after["head"],
            active_state=after["active_state"],
            npc_state=after["npc_state"],
            thread_state=after["thread_state"],
            facts=after["facts"],
            events=after["event_log"],
        )
    )
    return RetconTransaction(
        not has_errors(issues),
        checkpoint_id,
        plan,
        event,
        after,
        tuple(mutation_records),
        {},
        issues,
        dict(expected_revisions or {}),
    )
