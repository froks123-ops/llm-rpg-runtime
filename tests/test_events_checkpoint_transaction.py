import json
from pathlib import Path

from runtime.checkpoint import build_checkpoint_manifest, verify_checkpoint
from runtime.events import (
    active_events,
    append_event,
    dependent_event_ids,
    resolve_invalidated_event_ids,
    validate_event_order,
)
from runtime.state_validate import validate_data
from runtime.transaction import prepare_transaction

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    return json.loads((ROOT / "examples/minimal" / name).read_text())


def schema(name):
    return json.loads((ROOT / "schemas" / name).read_text())


def test_event_append_is_monotonic():
    result = append_event(
        load("event_log.json"),
        kind="thread.progress",
        source={"session": 1, "scene_id": "s001-sc001", "turn": 2},
        summary="Search begins.",
        event_id="evt:002",
        timestamp="2026-01-01T00:01:00Z",
    )
    assert result.event["seq"] == 2
    assert validate_event_order(result.events) == []
    assert validate_data(result.events, schema("event_log.schema.json")) == []


def test_event_invalidation_is_projected_without_mutating_history():
    events = load("event_log.json")
    events.extend(
        [
            {
                "id": "evt:002",
                "seq": 2,
                "timestamp": "t",
                "kind": "reaction",
                "status": "active",
                "source": {},
                "actor": None,
                "targets": [],
                "dependencies": {"fact_ids": ["fact.scout.missing"], "event_ids": []},
                "mutations": [],
                "metadata": {},
                "summary": "reaction"
            },
            {
                "id": "evt:003",
                "seq": 3,
                "timestamp": "t",
                "kind": "consequence",
                "status": "active",
                "source": {},
                "actor": None,
                "targets": [],
                "dependencies": {"fact_ids": [], "event_ids": ["evt:002"]},
                "mutations": [],
                "metadata": {},
                "summary": "consequence"
            }
        ]
    )
    original = json.loads(json.dumps(events))
    invalid = dependent_event_ids(events, {"fact.scout.missing"})
    assert set(invalid) == {"evt:001", "evt:002", "evt:003"}
    assert events == original

    events.append(
        {
            "id": "evt:004",
            "seq": 4,
            "timestamp": "t",
            "kind": "retcon.applied",
            "status": "active",
            "source": {},
            "actor": "system",
            "targets": ["fact.scout.missing"],
            "dependencies": {"fact_ids": [], "event_ids": []},
            "mutations": [],
            "metadata": {
                "invalidates_fact_ids": ["fact.scout.missing"],
                "invalidates_event_ids": list(invalid)
            },
            "summary": "retcon"
        }
    )
    assert set(resolve_invalidated_event_ids(events)) == {"evt:001", "evt:002", "evt:003"}
    assert [event["id"] for event in active_events(events)] == ["evt:004"]


def test_checkpoint_hashes_are_deterministic_and_detect_tampering():
    docs = {
        "HEAD": load("head.json"),
        "NPC": load("npc_state.json"),
        "FACTS": load("facts.json"),
    }
    manifest = build_checkpoint_manifest(
        checkpoint_id="cp:001",
        campaign_id="example-campaign",
        session=1,
        scene_id="s001-sc001",
        documents=docs,
        created_at="2026-01-01T00:00:00Z",
    )
    same = build_checkpoint_manifest(
        checkpoint_id="cp:001",
        campaign_id="example-campaign",
        session=1,
        scene_id="s001-sc001",
        documents=docs,
        created_at="2026-01-01T00:00:00Z",
    )
    assert manifest["root_sha256"] == same["root_sha256"]
    assert validate_data(manifest, schema("checkpoint.schema.json")) == []
    assert verify_checkpoint(manifest, docs).ok

    tampered = json.loads(json.dumps(docs))
    tampered["HEAD"]["location"] = "Elsewhere"
    verification = verify_checkpoint(manifest, tampered)
    assert not verification.ok
    assert "hash:HEAD" in verification.mismatches


def test_transaction_blocks_invalid_state_before_event_creation():
    before_npc = load("npc_state.json")
    invalid_npc = json.loads(json.dumps(before_npc))
    invalid_npc["npcs"]["mira"]["relationships"]["pc:traveler"]["trust"] = 999

    plan = prepare_transaction(
        before={"npc_state": before_npc},
        after={"npc_state": invalid_npc},
        schemas={"npc_state": schema("npc_state.schema.json")},
        source={"session": 1, "scene_id": "s001-sc001", "turn": 2},
        summary="invalid trust test",
        seq=2,
        event_id="evt:002",
        timestamp="2026-01-01T00:01:00Z",
    )
    assert not plan.ok
    assert plan.event is None
    assert "npc_state" in plan.validation_errors


def test_transaction_emits_auditable_mutation_and_preserves_revision_expectations():
    before_npc = load("npc_state.json")
    after_npc = json.loads(json.dumps(before_npc))
    after_npc["npcs"]["mira"]["knowledge"]["knows"].append("fact.gm.hidden-cause")

    plan = prepare_transaction(
        before={"npc_state": before_npc},
        after={"npc_state": after_npc},
        schemas={"npc_state": schema("npc_state.schema.json")},
        source={"session": 1, "scene_id": "s001-sc001", "turn": 2},
        summary="Mira learns the hidden cause.",
        seq=2,
        event_id="evt:002",
        timestamp="2026-01-01T00:01:00Z",
        expected_revisions={"npc_state": "rev-17"},
        fact_dependencies=["fact.gm.hidden-cause"],
    )
    assert plan.ok
    assert plan.event is not None
    assert plan.expected_revisions == {"npc_state": "rev-17"}
    assert any(
        mutation["path"] == "$/npcs/mira/knowledge/knows"
        and mutation["op"] == "add-item"
        for mutation in plan.event["mutations"]
    )
