import json
from pathlib import Path

from runtime.facts import cascade_retcon, resolve_state_slots, supersede_fact
from runtime.retcon import make_retcon_event, plan_retcon

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    return json.loads((ROOT / "examples/minimal" / name).read_text())


def test_state_slot_resolution_has_one_active_location():
    slots = resolve_state_slots(load("facts.json"))
    assert slots["npc:scout:location"]["id"] == "fact.scout.location"


def test_guarded_supersession_replaces_only_exact_state_slot():
    facts = [
        {"id": "f1", "text": "A", "status": "active", "source": "s", "state_key": "npc:x:location"}
    ]
    accepted = supersede_fact(
        facts,
        {"id": "f2", "text": "B", "source": "s2", "state_key": "npc:x:location"},
        "f1",
    )
    assert accepted.replaced_fact_id == "f1"
    assert accepted.facts[0]["status"] == "superseded"

    rejected = supersede_fact(
        facts,
        {"id": "f3", "text": "C", "source": "s3", "state_key": "npc:x:status"},
        "f1",
    )
    assert rejected.replaced_fact_id is None
    assert rejected.reason == "guard_rejected"
    assert rejected.facts[0]["status"] == "active"


def test_retcon_cascades_through_hard_fact_dependencies():
    result = cascade_retcon(
        load("facts.json"),
        ["fact.scout.missing"],
        reason="test rollback",
        retcon_event_id="evt:retcon",
    )
    assert set(result.invalidated_fact_ids) == {
        "fact.scout.missing",
        "fact.road.unsafe-rumor",
    }
    by_id = {fact["id"]: fact for fact in result.facts}
    assert by_id["fact.scout.missing"]["status"] == "retconned"
    assert by_id["fact.road.unsafe-rumor"]["status"] == "retconned"
    assert by_id["fact.gm.hidden-cause"]["status"] == "active"


def test_cross_document_retcon_plan_invalidates_epistemics_threads_events_and_relationship_basis():
    facts = load("facts.json")
    npc_state = load("npc_state.json")
    active_state = load("active_state.json")
    active_state["knowledge"]["knows"].append("fact.scout.missing")
    threads = load("thread_state.json")
    events = load("event_log.json")
    events.append(
        {
            "id": "evt:002",
            "seq": 2,
            "timestamp": "2026-01-01T00:01:00Z",
            "kind": "npc.reaction",
            "status": "active",
            "source": {"session": 1, "scene_id": "s001-sc001", "turn": 1},
            "actor": "npc:mira",
            "targets": ["npc:mira"],
            "dependencies": {"fact_ids": ["fact.scout.missing"], "event_ids": ["evt:001"]},
            "mutations": [],
            "summary": "Mira reacts to the missing scout."
        }
    )
    plan = plan_retcon(
        facts=facts,
        head=load("head.json"),
        active_state=active_state,
        npc_state=npc_state,
        thread_state=threads,
        events=events,
        target_fact_ids=["fact.scout.missing"],
        reason="event never happened",
        retcon_event_id="evt:retcon",
    )

    assert set(plan.invalidated_fact_ids) == {"fact.scout.missing", "fact.road.unsafe-rumor"}
    assert plan.invalidated_thread_ids == ("missing_scout",)
    assert plan.head["active_threads"] == []
    assert plan.invalidated_goal_paths == ("npcs.mira.goals.find-scout",)
    assert plan.npc_state["npcs"]["mira"]["goals"][0]["status"] == "invalidated"
    assert set(plan.invalidated_event_ids) == {"evt:001", "evt:002"}
    assert all(event["status"] == "active" for event in plan.events)  # immutable history
    retcon_event = make_retcon_event(
        plan,
        seq=3,
        source={"session": 1, "scene_id": "s001-sc001", "turn": 2},
        summary="The missing-scout event never happened.",
        event_id="evt:retcon",
        timestamp="2026-01-01T00:02:00Z",
    )
    assert set(retcon_event["metadata"]["invalidates_event_ids"]) == {"evt:001", "evt:002"}
    assert plan.npc_state["npcs"]["mira"]["knowledge"]["knows"] == []
    assert plan.active_state["knowledge"]["knows"] == []
    assert plan.removed_player_knowledge["knows"] == ["fact.scout.missing"]
    assert plan.npc_state["npcs"]["mira"]["knowledge"]["suspects"] == []
    relation = plan.npc_state["npcs"]["mira"]["relationships"]["pc:traveler"]
    assert relation["needs_rebuild"] is True
    assert relation["basis_fact_ids"] == []


def test_checkpoint_gated_retcon_transaction_produces_integrity_safe_documents():
    from runtime.preflight import run_preflight
    from runtime.retcon import prepare_retcon_transaction

    documents = {
        "manifest": load("manifest.json"),
        "head": load("head.json"),
        "active_state": load("active_state.json"),
        "npc_state": load("npc_state.json"),
        "thread_state": load("thread_state.json"),
        "facts": load("facts.json"),
        "event_log": load("event_log.json"),
    }
    schemas = {
        "manifest": json.loads((ROOT / "schemas/manifest.schema.json").read_text()),
        "head": json.loads((ROOT / "schemas/head.schema.json").read_text()),
        "active_state": json.loads((ROOT / "schemas/active_state.schema.json").read_text()),
        "npc_state": json.loads((ROOT / "schemas/npc_state.schema.json").read_text()),
        "thread_state": json.loads((ROOT / "schemas/thread_state.schema.json").read_text()),
        "facts": json.loads((ROOT / "schemas/facts.schema.json").read_text()),
        "event_log": json.loads((ROOT / "schemas/event_log.schema.json").read_text()),
    }
    transaction = prepare_retcon_transaction(
        documents=documents,
        schemas=schemas,
        target_fact_ids=["fact.scout.missing"],
        checkpoint_id="cp:before-retcon",
        source={"session": 1, "scene_id": "s001-sc001", "turn": 2},
        summary="The missing-scout event never occurred.",
        seq=2,
        event_id="evt:retcon",
        timestamp="2026-01-01T00:02:00Z",
        reason="test retcon",
    )
    assert transaction.ok
    assert transaction.event["metadata"]["checkpoint_id"] == "cp:before-retcon"
    assert transaction.documents["manifest"]["last_event_seq"] == 2
    assert transaction.documents["head"]["active_threads"] == []
    assert transaction.documents["head"]["last_canonical_event_id"] == "evt:retcon"
    assert transaction.documents["event_log"][0] == documents["event_log"][0]
    assert transaction.documents["event_log"][1]["kind"] == "retcon.applied"

    report = run_preflight(transaction.documents, schemas)
    assert report.ok
    assert any(issue.code == "relationship_needs_rebuild" for issue in report.integrity_issues)


def test_retcon_transaction_requires_checkpoint_id():
    import pytest
    from runtime.retcon import prepare_retcon_transaction

    documents = {
        "manifest": load("manifest.json"),
        "head": load("head.json"),
        "active_state": load("active_state.json"),
        "npc_state": load("npc_state.json"),
        "thread_state": load("thread_state.json"),
        "facts": load("facts.json"),
        "event_log": load("event_log.json"),
    }
    with pytest.raises(ValueError):
        prepare_retcon_transaction(
            documents=documents,
            schemas={},
            target_fact_ids=["fact.scout.missing"],
            checkpoint_id="",
            source={},
            summary="bad",
            seq=2,
            event_id="evt:retcon",
        )
