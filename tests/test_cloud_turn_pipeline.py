import copy
import json
from pathlib import Path

from runtime.campaign_transaction import prepare_campaign_transaction
from runtime.cloud_documents import (
    CloudDocumentRead,
    build_save_envelope,
    prepare_save_journal,
    recover_from_journal,
)
from runtime.persistence import DocumentHandle
from runtime.preflight import run_preflight

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    return json.loads((ROOT / "examples" / "minimal" / name).read_text())


def schemas():
    mapping = {
        "manifest": "manifest.schema.json",
        "head": "head.schema.json",
        "active_state": "active_state.schema.json",
        "npc_state": "npc_state.schema.json",
        "thread_state": "thread_state.schema.json",
        "facts": "facts.schema.json",
        "event_log": "event_log.schema.json",
    }
    return {
        key: json.loads((ROOT / "schemas" / filename).read_text())
        for key, filename in mapping.items()
    }


def campaign():
    return {
        "manifest": load("manifest.json"),
        "head": load("head.json"),
        "active_state": load("active_state.json"),
        "npc_state": load("npc_state.json"),
        "thread_state": load("thread_state.json"),
        "facts": load("facts.json"),
        "event_log": load("event_log.json"),
    }


def test_full_turn_commit_and_every_recovery_boundary():
    before = campaign()
    after = copy.deepcopy(before)
    after["active_state"].setdefault("custom", {})["pipeline_probe"] = 1

    plan = prepare_campaign_transaction(
        before=before,
        after=after,
        schemas=schemas(),
        source={"session": 1, "scene_id": "s001-sc001", "turn": 2},
        summary="Neutral pipeline regression probe.",
        kind="system.pipeline-probe",
        seq=2,
        event_id="evt:pipeline-probe",
        timestamp="2026-01-01T00:01:00Z",
    )
    assert plan.ok
    assert run_preflight(plan.documents, schemas()).ok

    changed = {key for key in before if before[key] != plan.documents[key]}
    assert changed == {"active_state", "event_log", "head", "manifest"}

    handles = {
        key: DocumentHandle(key, f"doc-{key}", f"rev-{key}")
        for key in before
    }
    envelope = build_save_envelope(
        transaction_id="tx:pipeline-probe",
        before=before,
        after=plan.documents,
        handles=handles,
        changed_documents=changed,
    )
    assert envelope["write_order"] == ["active_state", "event_log", "head", "manifest"]
    journal = prepare_save_journal(envelope)

    order = envelope["write_order"]
    for cut in range(len(order) + 1):
        reads = {}
        for index, key in enumerate(order):
            value = plan.documents[key] if index < cut else before[key]
            reads[key] = CloudDocumentRead(
                envelope["documents"][key]["document_id"],
                f"fresh-{key}-{cut}",
                json.dumps(value, ensure_ascii=False),
            )
        report = recover_from_journal(journal=journal, current_reads=reads)
        expected = "committed" if cut == len(order) else ("not_started" if cut == 0 else "roll_forward")
        assert report.status == expected
        if cut < len(order):
            assert [write.key for write in report.pending_writes] == order[cut:]
