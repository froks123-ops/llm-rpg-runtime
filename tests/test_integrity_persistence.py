import copy
import json
from pathlib import Path

from runtime.campaign_transaction import prepare_campaign_transaction
from runtime.integrity import audit_campaign
from runtime.persistence import DocumentHandle, build_write_intents

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    return json.loads((ROOT / "examples/minimal" / name).read_text())


def schema(name):
    return json.loads((ROOT / "schemas" / name).read_text())


def campaign_docs():
    return {
        "manifest": load("manifest.json"),
        "head": load("head.json"),
        "npc_state": load("npc_state.json"),
        "thread_state": load("thread_state.json"),
        "facts": load("facts.json"),
        "event_log": load("event_log.json"),
        "active_state": load("active_state.json"),
    }


def schemas():
    return {
        "manifest": schema("manifest.schema.json"),
        "head": schema("head.schema.json"),
        "active_state": schema("active_state.schema.json"),
        "npc_state": schema("npc_state.schema.json"),
        "thread_state": schema("thread_state.schema.json"),
        "facts": schema("facts.schema.json"),
        "event_log": schema("event_log.schema.json"),
    }


def test_example_campaign_has_no_cross_document_integrity_errors():
    docs = campaign_docs()
    assert audit_campaign(
        manifest=docs["manifest"],
        head=docs["head"],
        active_state=docs["active_state"],
        npc_state=docs["npc_state"],
        thread_state=docs["thread_state"],
        facts=docs["facts"],
        events=docs["event_log"],
    ) == []


def test_integrity_detects_unknown_epistemic_reference_and_stale_thread_dependency():
    docs = campaign_docs()
    docs["npc_state"]["npcs"]["mira"]["knowledge"]["believes"].append("fact.does-not-exist")
    for fact in docs["facts"]:
        if fact["id"] == "fact.scout.missing":
            fact["status"] = "retconned"
    issues = audit_campaign(
        manifest=docs["manifest"],
        head=docs["head"],
        active_state=docs["active_state"],
        npc_state=docs["npc_state"],
        thread_state=docs["thread_state"],
        facts=docs["facts"],
        events=docs["event_log"],
    )
    codes = {issue.code for issue in issues}
    assert "unknown_fact_reference" in codes
    assert "active_thread_invalid_dependency" in codes
    assert "relationship_stale_basis" in codes


def test_campaign_transaction_appends_event_and_updates_manifest_and_head_atomically_in_plan():
    before = campaign_docs()
    after = copy.deepcopy(before)
    after["npc_state"]["npcs"]["mira"]["knowledge"]["knows"].append("fact.gm.hidden-cause")

    plan = prepare_campaign_transaction(
        before=before,
        after=after,
        schemas=schemas(),
        source={"session": 1, "scene_id": "s001-sc001", "turn": 2},
        summary="Mira learns the cause of the delay.",
        seq=2,
        event_id="evt:002",
        timestamp="2026-01-01T00:01:00Z",
        fact_dependencies=["fact.gm.hidden-cause"],
    )
    assert plan.ok
    assert plan.transaction.event["id"] == "evt:002"
    assert len(plan.documents["event_log"]) == 2
    assert plan.documents["manifest"]["last_event_seq"] == 2
    assert plan.documents["head"]["last_canonical_event_id"] == "evt:002"
    assert plan.integrity_issues == ()


def test_campaign_transaction_blocks_semantically_invalid_fact_reference_even_when_schema_passes():
    before = campaign_docs()
    after = copy.deepcopy(before)
    after["npc_state"]["npcs"]["mira"]["knowledge"]["believes"].append("fact.ghost")

    plan = prepare_campaign_transaction(
        before=before,
        after=after,
        schemas=schemas(),
        source={"session": 1, "scene_id": "s001-sc001", "turn": 2},
        summary="Invalid semantic reference.",
        seq=2,
        event_id="evt:002",
        timestamp="2026-01-01T00:01:00Z",
    )
    assert not plan.ok
    assert any(issue.code == "unknown_fact_reference" for issue in plan.integrity_issues)


def test_persistence_write_order_places_manifest_last_and_preserves_revision_tokens():
    after = campaign_docs()
    handles = {
        key: DocumentHandle(key, f"doc-{key}", f"rev-{key}")
        for key in after
    }
    changed = {"manifest", "head", "npc_state", "facts", "event_log"}
    intents = build_write_intents(
        changed_documents=changed,
        after=after,
        handles=handles,
    )
    assert [intent.key for intent in intents] == [
        "npc_state",
        "facts",
        "event_log",
        "head",
        "manifest",
    ]
    assert intents[-1].expected_revision == "rev-manifest"


def test_integrity_detects_active_state_actor_mismatch():
    docs = campaign_docs()
    docs["active_state"]["actor_id"] = "pc:wrong"
    issues = audit_campaign(
        manifest=docs["manifest"],
        head=docs["head"],
        active_state=docs["active_state"],
        npc_state=docs["npc_state"],
        thread_state=docs["thread_state"],
        facts=docs["facts"],
        events=docs["event_log"],
    )
    assert any(issue.code == "active_state_actor_mismatch" for issue in issues)
