"""NPC/player knowledge scoping and audit helpers.

This module is intentionally pure: no storage, no LLM calls and no network I/O.
Knowledge is expressed with stable fact IDs. Facts may additionally carry a
``known_by`` retrieval hint using this token grammar:

- ``player`` (player-character/in-character knowledge)
- ``ooc`` (visible to the human user, not known by the player character)
- ``npc:<id>``
- ``faction:<normalized name>``
- a bare token, treated as ``npc:<id>`` for migration compatibility

``known_by`` omitted means public/broadcast. ``known_by: []`` means secret.
The authoritative epistemic buckets live on NPC records: knows, suspects,
believes and remembers.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Iterable, Mapping


_SEP_RE = re.compile(r"[,;/]")
_WS_RE = re.compile(r"\s+")


@dataclass(frozen=True)
class KnownByToken:
    kind: str
    value: str = ""


@dataclass(frozen=True)
class KnowledgeIssue:
    level: str
    code: str
    message: str
    npc_id: str = ""
    fact_id: str = ""


def normalize_faction(value: str) -> str:
    return _WS_RE.sub(" ", (value or "").strip().lower())


def parse_factions(value: str | None) -> list[str]:
    if not value:
        return []
    out: list[str] = []
    for piece in _SEP_RE.split(value):
        normalized = normalize_faction(piece)
        if normalized and normalized not in out:
            out.append(normalized)
    return out


def parse_known_by_token(token: str) -> KnownByToken | None:
    if not isinstance(token, str):
        return None
    raw = token.strip()
    if not raw:
        return None
    if raw.lower() == "player":
        return KnownByToken("player", "player")
    if raw.lower() == "ooc":
        return KnownByToken("ooc", "ooc")
    lowered = raw.lower()
    if lowered.startswith("npc:"):
        value = raw[4:].strip()
        return KnownByToken("npc", value) if value else None
    if lowered.startswith("faction:"):
        value = normalize_faction(raw[8:])
        return KnownByToken("faction", value) if value else None
    return KnownByToken("npc", raw)


def _npc_records(npc_state: Mapping[str, Any]) -> Mapping[str, Any]:
    return npc_state.get("npcs", {}) if isinstance(npc_state, Mapping) else {}


def expand_known_by(
    known_by: list[str] | None,
    npc_state: Mapping[str, Any],
) -> set[str]:
    """Expand retrieval-hint tokens to synthetic actor IDs.

    Returned NPC actor IDs are ``npc:<id>``. The player is returned as ``player``.
    Omitted ``known_by`` is public and therefore intentionally returns an empty set;
    callers should special-case public facts separately.
    """

    out: set[str] = set()
    if known_by is None:
        return out
    npcs = _npc_records(npc_state)
    for raw in known_by:
        parsed = parse_known_by_token(raw)
        if parsed is None:
            continue
        if parsed.kind == "player":
            out.add("player")
        elif parsed.kind == "ooc":
            out.add("ooc")
        elif parsed.kind == "npc":
            out.add(f"npc:{parsed.value}")
        elif parsed.kind == "faction":
            for npc_id, npc in npcs.items():
                if parsed.value in parse_factions(str(npc.get("faction", ""))):
                    out.add(f"npc:{npc_id}")
    return out


def is_public_fact(fact: Mapping[str, Any]) -> bool:
    return "known_by" not in fact or fact.get("known_by") is None


def fact_known_to_player(fact: Mapping[str, Any]) -> bool:
    if is_public_fact(fact):
        return True
    for raw in fact.get("known_by", []):
        parsed = parse_known_by_token(raw)
        if parsed and parsed.kind == "player":
            return True
    return False


def fact_visible_ooc(fact: Mapping[str, Any]) -> bool:
    """Return whether the human user has been shown a non-PC fact out of character."""

    if is_public_fact(fact):
        return True
    for raw in fact.get("known_by", []):
        parsed = parse_known_by_token(raw)
        if parsed and parsed.kind == "ooc":
            return True
    return False


def fact_known_to_npc(
    fact: Mapping[str, Any],
    npc_id: str,
    npc_state: Mapping[str, Any],
) -> bool:
    if is_public_fact(fact):
        return True
    npcs = _npc_records(npc_state)
    npc = npcs.get(npc_id, {})
    npc_factions = set(parse_factions(str(npc.get("faction", ""))))
    for raw in fact.get("known_by", []):
        parsed = parse_known_by_token(raw)
        if not parsed:
            continue
        if parsed.kind == "npc" and parsed.value == npc_id:
            return True
        if parsed.kind == "faction" and parsed.value in npc_factions:
            return True
    return False


def referenced_fact_ids(npc: Mapping[str, Any]) -> set[str]:
    knowledge = npc.get("knowledge", {}) if isinstance(npc, Mapping) else {}
    out: set[str] = set()
    for bucket in ("knows", "suspects", "believes", "remembers"):
        values = knowledge.get(bucket, [])
        if isinstance(values, list):
            out.update(value for value in values if isinstance(value, str))
    return out


def _fact_map(facts: Iterable[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    out: dict[str, Mapping[str, Any]] = {}
    for fact in facts:
        fact_id = fact.get("id")
        if isinstance(fact_id, str) and fact_id:
            out[fact_id] = fact
    return out


def audit_actor_knowledge(
    knowledge: Mapping[str, Any],
    facts: Iterable[Mapping[str, Any]],
    *,
    actor_id: str = "player",
) -> list[KnowledgeIssue]:
    """Audit one actor epistemic record against the fact ledger."""

    fact_by_id = _fact_map(facts)
    issues: list[KnowledgeIssue] = []
    for bucket in ("knows", "suspects", "believes", "remembers"):
        for fact_id in knowledge.get(bucket, []) or []:
            fact = fact_by_id.get(fact_id)
            if fact is None:
                issues.append(KnowledgeIssue(
                    "error", "unknown_fact_reference",
                    f"{bucket} references a missing fact.", actor_id, fact_id
                ))
                continue
            status = str(fact.get("status", "active"))
            if status in {"retconned", "superseded", "retracted"}:
                issues.append(KnowledgeIssue(
                    "error", "inactive_fact_reference",
                    f"{bucket} references an inactive fact ({status}).", actor_id, fact_id
                ))
    return issues


def sanitize_actor_knowledge(
    knowledge: Mapping[str, Any],
    invalid_fact_ids: set[str],
) -> tuple[dict[str, Any], dict[str, list[str]]]:
    """Remove invalidated fact IDs from one actor epistemic record."""

    import copy
    result = copy.deepcopy(dict(knowledge))
    removed: dict[str, list[str]] = {}
    for bucket in ("knows", "suspects", "believes", "remembers"):
        before = list(result.get(bucket, []) or [])
        after = [fid for fid in before if fid not in invalid_fact_ids]
        if after != before:
            result[bucket] = after
            removed[bucket] = [fid for fid in before if fid in invalid_fact_ids]
    return result, removed

def audit_knowledge(
    npc_state: Mapping[str, Any],
    facts: Iterable[Mapping[str, Any]],
) -> list[KnowledgeIssue]:
    """Report broken or lifecycle-invalid fact references in NPC epistemic state."""

    fact_by_id = _fact_map(facts)
    issues: list[KnowledgeIssue] = []
    for npc_id, npc in _npc_records(npc_state).items():
        knowledge = npc.get("knowledge", {})
        for bucket in ("knows", "suspects", "believes", "remembers"):
            for fact_id in knowledge.get(bucket, []):
                fact = fact_by_id.get(fact_id)
                if fact is None:
                    issues.append(
                        KnowledgeIssue(
                            "error",
                            "unknown_fact_reference",
                            f"{bucket} references a missing fact.",
                            npc_id,
                            fact_id,
                        )
                    )
                    continue
                status = str(fact.get("status", "active"))
                if status in {"retconned", "superseded", "retracted"}:
                    issues.append(
                        KnowledgeIssue(
                            "error",
                            "inactive_fact_reference",
                            f"{bucket} references an inactive fact ({status}).",
                            npc_id,
                            fact_id,
                        )
                    )
    return issues


def sanitize_knowledge(
    npc_state: Mapping[str, Any],
    invalid_fact_ids: set[str],
) -> tuple[dict[str, Any], dict[str, dict[str, list[str]]]]:
    """Remove invalidated fact IDs from all NPC epistemic buckets.

    Returns a deep-enough copied NPC state and a removal report keyed by NPC and bucket.
    """

    import copy

    result = copy.deepcopy(dict(npc_state))
    removed: dict[str, dict[str, list[str]]] = {}
    for npc_id, npc in _npc_records(result).items():
        knowledge = npc.get("knowledge", {})
        for bucket in ("knows", "suspects", "believes", "remembers"):
            before = list(knowledge.get(bucket, []))
            after = [fid for fid in before if fid not in invalid_fact_ids]
            if after != before:
                knowledge[bucket] = after
                removed.setdefault(npc_id, {})[bucket] = [
                    fid for fid in before if fid in invalid_fact_ids
                ]
    return result, removed
