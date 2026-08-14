import json
from pathlib import Path

from runtime.state_diff import diff
from runtime.state_validate import validate_file

ROOT = Path(__file__).resolve().parents[1]


def test_examples_validate_against_all_v02_schemas():
    pairs = [
        ("manifest.json", "manifest.schema.json"),
        ("head.json", "head.schema.json"),
        ("npc_state.json", "npc_state.schema.json"),
        ("facts.json", "facts.schema.json"),
        ("thread_state.json", "thread_state.schema.json"),
        ("event_log.json", "event_log.schema.json"),
    ]
    for data_name, schema_name in pairs:
        assert validate_file(
            ROOT / "examples/minimal" / data_name,
            ROOT / "schemas" / schema_name,
        ) == []


def test_diff_detects_nested_fact_reference_addition():
    before = {"npcs": {"mira": {"knowledge": {"knows": ["fact.a"]}}}}
    after = {"npcs": {"mira": {"knowledge": {"knows": ["fact.a", "fact.b"]}}}}
    changes = diff(before, after)
    assert any(
        change.op == "add-item"
        and change.path == "$/npcs/mira/knowledge/knows"
        and change.after == "fact.b"
        for change in changes
    )


def test_diff_treats_list_reorder_as_replace_not_fake_add_remove():
    changes = diff({"x": [1, 2]}, {"x": [2, 1]})
    assert len(changes) == 1
    assert changes[0].op == "replace"
