import json
from pathlib import Path

from runtime.context_assembler import assemble
from runtime.rng import d100, weighted_choice
from runtime.state_diff import diff
from runtime.state_validate import validate_file
from runtime.world_tick import tick_goal

ROOT = Path(__file__).resolve().parents[1]


def test_seeded_rng_is_reproducible():
    assert d100(seed=123).value == d100(seed=123).value


def test_weighted_choice_seeded_is_reproducible():
    assert weighted_choice(["a", "b"], [1, 3], seed=7) == weighted_choice(
        ["a", "b"], [1, 3], seed=7
    )


def test_diff_detects_list_addition():
    changes = diff({"k": ["a"]}, {"k": ["a", "b"]})
    assert any(c.op == "add-item" and c.after == "b" for c in changes)


def test_tick_seeded_is_reproducible():
    a = tick_goal("npc", {"id": "goal", "dc": 60}, seed=42)
    b = tick_goal("npc", {"id": "goal", "dc": 60}, seed=42)
    assert a == b


def test_example_state_validates():
    errors = validate_file(
        ROOT / "examples/minimal/npc_state.json",
        ROOT / "schemas/npc_state.schema.json",
    )
    assert errors == []


def test_example_facts_validate():
    errors = validate_file(
        ROOT / "examples/minimal/facts.json",
        ROOT / "schemas/facts.schema.json",
    )
    assert errors == []


def test_context_assembler_scopes_present_npcs_and_threads():
    npc_state = json.loads((ROOT / "examples/minimal/npc_state.json").read_text())
    facts = json.loads((ROOT / "examples/minimal/facts.json").read_text())
    context = assemble(
        {"campaign": "Example"},
        {"present": ["Mira"], "active_threads": ["missing_scout"]},
        npc_state,
        {"threads": {"missing_scout": {"status": "active"}, "other": {}}},
        facts,
    )
    assert set(context["present_npcs"]) == {"Mira"}
    assert set(context["active_threads"]) == {"missing_scout"}
    assert {fact["id"] for fact in context["scoped_facts"]} == {
        "fact.scout.missing",
        "fact.player.private-note",
    }
