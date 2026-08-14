import copy
import json
from pathlib import Path

from runtime.cloud_bootstrap import plan_cloud_bootstrap
from runtime.cloud_documents import (
    CloudDocumentRead,
    build_save_envelope,
    idle_save_journal,
    prepare_save_journal,
)
from runtime.persistence import DocumentHandle

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    return json.loads((ROOT / "examples/minimal" / name).read_text())


def schema(name):
    return json.loads((ROOT / "schemas" / name).read_text())


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


def docs_with_routing(journal_id="doc-journal"):
    docs = {
        "manifest": load("manifest.json"),
        "head": load("head.json"),
        "active_state": load("active_state.json"),
        "npc_state": load("npc_state.json"),
        "thread_state": load("thread_state.json"),
        "facts": load("facts.json"),
        "event_log": load("event_log.json"),
    }
    docs["manifest"]["canonical_files"] = {
        key: f"doc-{key}" for key in docs if key != "manifest"
    }
    docs["manifest"].setdefault("storage", {})["transaction_journal_id"] = journal_id
    return docs


def read(document_id, value, revision="rev-1"):
    return CloudDocumentRead(document_id, revision, json.dumps(value, ensure_ascii=False))


def reads_for(docs):
    return {
        key: read(f"doc-{key}", docs[key], f"rev-{key}")
        for key in docs
        if key != "manifest"
    }


def decision_for(docs, journal):
    return plan_cloud_bootstrap(
        manifest_read=read("doc-manifest", docs["manifest"], "rev-manifest"),
        canonical_reads=reads_for(docs),
        journal_read=read("doc-journal", journal, "rev-journal"),
        schemas=schemas(),
    )


def test_idle_journal_and_valid_campaign_is_ready():
    docs = docs_with_routing()
    decision = decision_for(docs, idle_save_journal())
    assert decision.status == "ready"
    assert decision.ready
    assert decision.preflight and decision.preflight.ok
    assert decision.recovery is None


def test_declared_journal_requires_exact_fresh_read():
    docs = docs_with_routing()
    missing = plan_cloud_bootstrap(
        manifest_read=read("doc-manifest", docs["manifest"]),
        canonical_reads=reads_for(docs),
        schemas=schemas(),
    )
    assert missing.blocked
    assert "no fresh journal read" in missing.problems[0]

    wrong = plan_cloud_bootstrap(
        manifest_read=read("doc-manifest", docs["manifest"]),
        canonical_reads=reads_for(docs),
        journal_read=read("wrong-journal", idle_save_journal()),
        schemas=schemas(),
    )
    assert wrong.blocked
    assert "journal routing mismatch" in wrong.problems[0]


def make_prepared_case():
    before = docs_with_routing()
    after = copy.deepcopy(before)
    after["active_state"]["condition"] = "changed"
    after["manifest"]["last_event_seq"] += 1
    handles = {
        key: DocumentHandle(key, f"doc-{key}", f"rev-{key}")
        for key in before
    }
    envelope = build_save_envelope(
        transaction_id="tx-bootstrap",
        before=before,
        after=after,
        handles=handles,
        changed_documents={"active_state", "manifest"},
    )
    return before, after, prepare_save_journal(envelope)


def test_partial_save_demands_roll_forward_before_preflight():
    before, after, journal = make_prepared_case()
    current = copy.deepcopy(before)
    current["active_state"] = after["active_state"]
    decision = decision_for(current, journal)
    assert decision.status == "recovery_required"
    assert decision.preflight is None
    assert decision.recovery.status == "roll_forward"
    assert [w.key for w in decision.recovery.pending_writes] == ["manifest"]
    assert decision.journal_action == "keep_prepared"


def test_stale_prepared_journal_after_commit_requires_only_clear():
    before, after, journal = make_prepared_case()
    decision = decision_for(after, journal)
    assert decision.status == "recovery_required"
    assert decision.recovery.status == "committed"
    assert decision.recovery.pending_writes == ()
    assert decision.journal_action == "clear"


def test_external_edit_blocks_bootstrap_instead_of_overwriting():
    before, after, journal = make_prepared_case()
    current = copy.deepcopy(before)
    current["active_state"]["condition"] = "human edit"
    decision = decision_for(current, journal)
    assert decision.blocked
    assert decision.recovery.status == "blocked"
    assert any("unexpected content:active_state" in p for p in decision.problems)


def test_idle_campaign_with_semantic_integrity_error_is_blocked():
    docs = docs_with_routing()
    docs["head"]["present_npcs"] = ["npc.does-not-exist"]
    decision = decision_for(docs, idle_save_journal())
    assert decision.blocked
    assert decision.preflight is not None
    assert any("npc" in problem.lower() for problem in decision.problems)


def test_legacy_manifest_without_journal_can_still_preflight():
    docs = docs_with_routing()
    docs["manifest"]["storage"].pop("transaction_journal_id")
    decision = plan_cloud_bootstrap(
        manifest_read=read("doc-manifest", docs["manifest"]),
        canonical_reads=reads_for(docs),
        schemas=schemas(),
        journal_read=None,
    )
    assert decision.ready


def test_cloud_bootstrap_scale_fixture_roughly_matches_long_campaign_hot_state():
    """Regression fixture: dozens of facts and NPC records still preflight as one bootstrap."""
    docs = docs_with_routing()

    hidden_template = {
        "id": "placeholder",
        "text": "Background proposition.",
        "status": "active",
        "truth_status": "true",
        "known_by": [],
        "witnesses": [],
        "source": {"scene_id": "archive-scene", "session": 1, "kind": "system"},
        "depends_on": [],
        "importance": 5,
    }
    while len(docs["facts"]) < 80:
        index = len(docs["facts"])
        fact = copy.deepcopy(hidden_template)
        fact["id"] = f"fact.scale.{index:03d}"
        fact["text"] = f"Background proposition {index}."
        docs["facts"].append(fact)

    while len(docs["npc_state"]["npcs"]) < 16:
        index = len(docs["npc_state"]["npcs"])
        docs["npc_state"]["npcs"][f"scale-{index:02d}"] = {
            "name": f"Scale NPC {index}",
            "faction": "Background",
            "location": "Offstage",
            "knowledge": {"knows": [], "suspects": [], "believes": [], "remembers": []},
            "relationships": {},
            "goals": [],
        }

    decision = decision_for(docs, idle_save_journal())
    assert decision.ready
    assert decision.preflight and decision.preflight.ok
    assert len(docs["facts"]) == 80
    assert len(docs["npc_state"]["npcs"]) == 16
