"""Scene-scoped context assembly with an explicit epistemic firewall."""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from .facts import fact_map, is_fact_active
from .knowledge import fact_known_to_npc, fact_known_to_player, fact_visible_ooc, referenced_fact_ids


_EPISTEMIC_BUCKETS = ("knows", "suspects", "believes", "remembers")


def _source_ref(source: Any) -> str | None:
    if isinstance(source, str):
        return source or None
    if isinstance(source, Mapping):
        for key in ("chunk_ref", "source_ref", "scene_id", "event_id"):
            value = source.get(key)
            if value:
                return str(value)
    return None


def _fact_view(fact: Mapping[str, Any], *, include_truth: bool) -> dict[str, Any]:
    out = {
        "id": fact.get("id"),
        "text": fact.get("text", ""),
    }
    if include_truth:
        out.update(
            {
                "truth_status": fact.get("truth_status", "true"),
                "source": fact.get("source"),
                "state_key": fact.get("state_key"),
                "depends_on": list(fact.get("depends_on", []) or []),
            }
        )
    return out


def _present_npcs(head: Mapping[str, Any]) -> list[str]:
    values = head.get("present_npcs")
    if values is None:  # v0.1 compatibility
        values = head.get("present", [])
    return [str(value) for value in values or []]


def _active_threads(head: Mapping[str, Any]) -> list[str]:
    return [str(value) for value in head.get("active_threads", []) or []]


def _source_scene_id(source: Any) -> str | None:
    if isinstance(source, Mapping):
        value = source.get("scene_id")
        return str(value) if value else None
    return None


def _relevance_score(
    fact: Mapping[str, Any],
    *,
    present_npcs: set[str],
    active_threads: set[str],
    present_npc_refs: set[str],
    player_refs: set[str],
    player_character: str | None,
    current_scene_id: str | None,
    requested_fact_ids: set[str],
) -> int | None:
    """Return a deterministic scene relevance score or ``None`` for cold facts."""

    fact_id = str(fact.get("id", ""))
    importance = int(fact.get("importance", 50) or 0)
    score = max(0, min(100, importance))
    signaled = False

    if fact_id in requested_fact_ids:
        score += 10000
        signaled = True
    if fact.get("pinned"):
        score += 1000
        signaled = True

    threads = set(str(value) for value in fact.get("threads", []) or [])
    if threads.intersection(active_threads):
        score += 800
        signaled = True

    tags = {str(value).lower() for value in fact.get("tags", []) or []}
    if any(tag == "current" or tag.startswith("current-") or tag == "head" for tag in tags):
        score += 600
        signaled = True

    if current_scene_id and _source_scene_id(fact.get("source")) == current_scene_id:
        score += 500
        signaled = True

    entities = set(str(value) for value in fact.get("entities", []) or [])
    normalized_present_npcs = present_npcs | {f"npc:{npc}" for npc in present_npcs}
    present_hits = len(entities.intersection(normalized_present_npcs))
    if present_hits:
        score += 180 * present_hits
        signaled = True

    if player_character and str(player_character) in entities:
        other_entities = entities - {str(player_character)}
        if not other_entities:
            score += 120
            signaled = True

    if fact_id in present_npc_refs:
        score += 60
        signaled = True
    if fact_id in player_refs:
        score += 30
        signaled = True

    return score if signaled else None

def _npc_view(
    npc_id: str,
    npc: Mapping[str, Any],
    fact_by_id: Mapping[str, Mapping[str, Any]],
    npc_state: Mapping[str, Any],
    relevant_ids: set[str],
) -> dict[str, list[dict[str, Any]]]:
    knowledge = npc.get("knowledge", {}) or {}
    explicit_bucket: dict[str, str] = {}
    for bucket in _EPISTEMIC_BUCKETS:
        for fact_id in knowledge.get(bucket, []) or []:
            explicit_bucket[str(fact_id)] = bucket

    result: dict[str, list[dict[str, Any]]] = {bucket: [] for bucket in _EPISTEMIC_BUCKETS}
    added: set[str] = set()

    # Explicit epistemic state wins over inferred known_by/public routing.
    for bucket in _EPISTEMIC_BUCKETS:
        for fact_id in knowledge.get(bucket, []) or []:
            fact = fact_by_id.get(str(fact_id))
            if not fact or not is_fact_active(fact) or str(fact_id) not in relevant_ids:
                continue
            result[bucket].append(_fact_view(fact, include_truth=False))
            added.add(str(fact_id))

    for fact_id in relevant_ids:
        if fact_id in added:
            continue
        fact = fact_by_id[fact_id]
        if fact_known_to_npc(fact, npc_id, npc_state):
            result["knows"].append(_fact_view(fact, include_truth=False))
            added.add(fact_id)

    return result



def _player_epistemic_view(
    active_state: Mapping[str, Any],
    fact_by_id: Mapping[str, Mapping[str, Any]],
    relevant_ids: set[str],
) -> dict[str, list[dict[str, Any]]]:
    knowledge = active_state.get("knowledge", {}) or {}
    result: dict[str, list[dict[str, Any]]] = {bucket: [] for bucket in _EPISTEMIC_BUCKETS}
    added: set[str] = set()
    for bucket in _EPISTEMIC_BUCKETS:
        for fact_id in knowledge.get(bucket, []) or []:
            fid = str(fact_id)
            fact = fact_by_id.get(fid)
            if not fact or not is_fact_active(fact) or fid not in relevant_ids:
                continue
            result[bucket].append(_fact_view(fact, include_truth=False))
            added.add(fid)
    for fact_id in relevant_ids:
        if fact_id in added:
            continue
        fact = fact_by_id[fact_id]
        if fact_known_to_player(fact):
            result["knows"].append(_fact_view(fact, include_truth=False))
            added.add(fact_id)
    return result


def _safe_npc_record(npc: Mapping[str, Any]) -> dict[str, Any]:
    """Return scene-useful NPC state while suppressing stale relationship aggregates."""

    out = {key: value for key, value in npc.items() if key not in {"knowledge", "relationships"}}
    safe_relationships: dict[str, Any] = {}
    for other_id, relationship in (npc.get("relationships", {}) or {}).items():
        relation = dict(relationship)
        if relation.get("needs_rebuild"):
            safe_relationships[other_id] = {
                "needs_rebuild": True,
                "basis_fact_ids": list(relation.get("basis_fact_ids", []) or []),
                "invalidated_basis_fact_ids": list(relation.get("invalidated_basis_fact_ids", []) or []),
            }
        else:
            safe_relationships[other_id] = relation
    out["relationships"] = safe_relationships
    return out

def assemble(
    manifest: Mapping[str, Any],
    head: Mapping[str, Any],
    npc_state: Mapping[str, Any],
    thread_state: Mapping[str, Any],
    facts: Iterable[Mapping[str, Any]] | None = None,
    active_state: Mapping[str, Any] | None = None,
    *,
    requested_fact_ids: Iterable[str] | None = None,
    max_facts: int = 36,
) -> dict[str, Any]:
    """Build a compact GM context pack with separated truth and actor knowledge.

    ``gm_truth`` may contain hidden information needed to simulate the world. NPC/player
    views intentionally omit truth metadata and provenance to reduce accidental leakage.
    Retconned/superseded facts never enter any view.
    """

    present = _present_npcs(head)
    active_thread_ids = _active_threads(head)
    all_npcs = npc_state.get("npcs", {}) or {}
    raw_present_records = {
        npc_id: all_npcs[npc_id]
        for npc_id in present
        if npc_id in all_npcs
    }
    present_records = {npc_id: _safe_npc_record(npc) for npc_id, npc in raw_present_records.items()}
    all_threads = thread_state.get("threads", {}) or {}
    threads = {
        thread_id: all_threads[thread_id]
        for thread_id in active_thread_ids
        if thread_id in all_threads
        and all_threads[thread_id].get("status") != "invalidated"
    }

    fact_by_id = fact_map(facts or [])
    present_npc_refs: set[str] = set()
    for npc in raw_present_records.values():
        present_npc_refs.update(referenced_fact_ids(npc))
    player_refs: set[str] = set()
    active_knowledge = (active_state or {}).get("knowledge", {}) or {}
    for bucket in _EPISTEMIC_BUCKETS:
        player_refs.update(str(fid) for fid in active_knowledge.get(bucket, []) or [])

    requested = {str(fid) for fid in (requested_fact_ids or [])}
    scored: list[tuple[int, int, str]] = []
    for fact_id, fact in fact_by_id.items():
        if not is_fact_active(fact):
            continue
        score = _relevance_score(
            fact,
            present_npcs=set(present),
            active_threads=set(active_thread_ids),
            present_npc_refs=present_npc_refs,
            player_refs=player_refs,
            player_character=head.get("player_character"),
            current_scene_id=head.get("scene_id"),
            requested_fact_ids=requested,
        )
        if score is not None:
            importance = int(fact.get("importance", 50) or 0)
            scored.append((score, importance, fact_id))

    scored.sort(key=lambda item: (-item[0], -item[1], item[2]))
    if max_facts < 1:
        raise ValueError("max_facts must be >= 1")
    relevant_ids = {fact_id for _, _, fact_id in scored[:max_facts]}
    relevance_scores = {fact_id: score for score, _, fact_id in scored[:max_facts]}

    gm_truth = [
        _fact_view(fact_by_id[fact_id], include_truth=True)
        for fact_id in sorted(relevant_ids)
        if fact_by_id[fact_id].get("truth_status", "true") in {"true", "subjective"}
    ]

    player_view = [
        _fact_view(fact_by_id[fact_id], include_truth=False)
        for fact_id in sorted(relevant_ids)
        if fact_known_to_player(fact_by_id[fact_id])
    ]

    ooc_view = [
        _fact_view(fact_by_id[fact_id], include_truth=False)
        for fact_id in sorted(relevant_ids)
        if fact_visible_ooc(fact_by_id[fact_id]) and not fact_known_to_player(fact_by_id[fact_id])
    ]

    player_epistemic_view = _player_epistemic_view(
        active_state or {}, fact_by_id, relevant_ids
    )

    npc_views = {
        npc_id: _npc_view(
            npc_id,
            npc,
            fact_by_id,
            npc_state,
            relevant_ids,
        )
        for npc_id, npc in raw_present_records.items()
    }

    source_refs = sorted(
        {
            ref
            for fact_id in relevant_ids
            if (ref := _source_ref(fact_by_id[fact_id].get("source")))
        }
    )

    return {
        "campaign": manifest.get("campaign") or manifest.get("name"),
        "campaign_id": manifest.get("campaign_id") or manifest.get("campaignId"),
        "head": dict(head),
        "active_state": dict(active_state or {}),
        "present_npcs": present_records,
        "active_threads": threads,
        "gm_truth": gm_truth,
        "player_view": player_view,
        "player_epistemic_view": player_epistemic_view,
        "ooc_view": ooc_view,
        "npc_views": npc_views,
        "retrieval_hints": {
            "fact_ids": sorted(relevant_ids),
            "thread_ids": sorted(threads),
            "source_refs": source_refs,
            "fact_scores": relevance_scores,
            "fact_budget": max_facts,
        },
    }
