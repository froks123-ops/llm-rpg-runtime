import json
from pathlib import Path

from runtime.knowledge import (
    audit_knowledge,
    expand_known_by,
    fact_known_to_npc,
    fact_known_to_player,
    fact_visible_ooc,
    parse_factions,
    parse_known_by_token,
    sanitize_knowledge,
)

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    return json.loads((ROOT / "examples/minimal" / name).read_text())


def test_known_by_public_player_npc_and_faction_semantics():
    npc_state = load("npc_state.json")
    assert fact_known_to_player({"id": "public"})
    assert fact_known_to_player({"known_by": ["player"]})
    assert not fact_known_to_player({"known_by": ["npc:mira"]})
    assert fact_known_to_npc({"id": "public"}, "mira", npc_state)
    assert fact_known_to_npc({"known_by": ["npc:mira"]}, "mira", npc_state)
    assert not fact_known_to_npc({"known_by": ["player"]}, "mira", npc_state)
    assert fact_known_to_npc(
        {"known_by": ["faction:north gate watch"]}, "mira", npc_state
    )


def test_known_by_expansion_and_faction_parsing():
    npc_state = load("npc_state.json")
    assert parse_factions("North Gate Watch; Market Guild / Scouts") == [
        "north gate watch",
        "market guild",
        "scouts",
    ]
    assert expand_known_by(
        ["player", "faction:north gate watch", "tomas"], npc_state
    ) == {"player", "npc:mira", "npc:tomas"}


def test_knowledge_audit_detects_missing_and_inactive_fact_refs():
    npc_state = load("npc_state.json")
    facts = load("facts.json")
    npc_state["npcs"]["mira"]["knowledge"]["knows"].append("fact.old.location")
    npc_state["npcs"]["mira"]["knowledge"]["believes"].append("fact.missing")
    issues = audit_knowledge(npc_state, facts)
    codes = {(issue.code, issue.fact_id) for issue in issues}
    assert ("inactive_fact_reference", "fact.old.location") in codes
    assert ("unknown_fact_reference", "fact.missing") in codes


def test_sanitize_knowledge_removes_retconned_refs_only():
    npc_state = load("npc_state.json")
    clean, removed = sanitize_knowledge(
        npc_state, {"fact.scout.missing", "fact.road.unsafe-rumor"}
    )
    mira = clean["npcs"]["mira"]["knowledge"]
    assert mira["knows"] == []
    assert mira["suspects"] == []
    assert removed["mira"]["knows"] == ["fact.scout.missing"]


def test_ooc_scope_is_visible_to_user_but_not_player_character():
    fact = {"id": "secret", "known_by": ["ooc", "npc:mira"]}
    assert fact_visible_ooc(fact)
    assert not fact_known_to_player(fact)
    assert parse_known_by_token("ooc").kind == "ooc"
    assert "ooc" in expand_known_by(fact["known_by"], load("npc_state.json"))
