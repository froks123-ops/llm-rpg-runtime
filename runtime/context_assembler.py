from __future__ import annotations
from typing import Any


def assemble(manifest: dict[str, Any], head: dict[str, Any], npc_state: dict[str, Any], thread_state: dict[str, Any], facts: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    present = head.get('present', [])
    active_threads = head.get('active_threads', [])
    npcs = {name: npc_state.get('npcs', {}).get(name, {}) for name in present if name in npc_state.get('npcs', {})}
    threads = {name: thread_state.get('threads', {}).get(name, {}) for name in active_threads if name in thread_state.get('threads', {})}

    scoped_facts = []
    for fact in facts or []:
        known_by = set(fact.get('known_by', []))
        if not known_by or known_by.intersection(present) or 'player' in known_by:
            scoped_facts.append(fact)

    return {
        'campaign': manifest.get('campaign'),
        'head': head,
        'present_npcs': npcs,
        'active_threads': threads,
        'scoped_facts': scoped_facts,
    }
