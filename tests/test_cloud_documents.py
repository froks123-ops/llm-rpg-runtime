import copy
import json
from pathlib import Path

import pytest

from runtime.checkpoint import sha256_value
from runtime.cloud_documents import (
    CloudDocumentError,
    CloudDocumentRead,
    RecoveryState,
    assemble_bootstrap,
    assess_recovery,
    build_save_envelope,
    paragraphs_to_text,
    parse_json_document,
    read_from_paragraphs,
)
from runtime.persistence import DocumentHandle

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    return json.loads((ROOT / "examples/minimal" / name).read_text())


def campaign_docs():
    return {
        "manifest": load("manifest.json"),
        "head": load("head.json"),
        "active_state": load("active_state.json"),
        "npc_state": load("npc_state.json"),
        "thread_state": load("thread_state.json"),
        "facts": load("facts.json"),
        "event_log": load("event_log.json"),
    }


def routed_docs():
    docs = campaign_docs()
    docs["manifest"]["canonical_files"] = {
        "head": "doc-head",
        "active_state": "doc-active_state",
        "npc_state": "doc-npc_state",
        "thread_state": "doc-thread_state",
        "facts": "doc-facts",
        "event_log": "doc-event_log",
    }
    return docs


def read_for(key, value, revision="rev-1"):
    return CloudDocumentRead(
        document_id=f"doc-{key}",
        revision_id=revision,
        text=json.dumps(value, ensure_ascii=False, indent=2),
    )


def handles_for(docs):
    return {
        key: DocumentHandle(key, f"doc-{key}", f"rev-{key}")
        for key in docs
    }


def test_paragraph_reconstruction_and_json_parse_roundtrip():
    value = {"name": "Kyōraku", "items": [1, 2], "nested": {"ok": True}}
    lines = json.dumps(value, ensure_ascii=False, indent=2).splitlines()
    text = paragraphs_to_text([{"text": line} for line in lines])
    assert parse_json_document(text) == value


def test_json_parser_accepts_bom_and_fenced_json():
    assert parse_json_document("\ufeff  {\"x\": 1}\n") == {"x": 1}
    assert parse_json_document("```json\n{\"x\": 2}\n```") == {"x": 2}


def test_json_parser_fails_closed_with_location():
    with pytest.raises(CloudDocumentError, match="line 1 column"):
        parse_json_document('{"x": }')


def test_read_from_paragraphs_requires_revision_and_reconstructs():
    read = read_from_paragraphs(
        document_id="doc-1",
        revision_id="rev-9",
        paragraphs=["{", '  "x": 1', "}"],
    )
    assert read.value == {"x": 1}
    assert read.revision_id == "rev-9"
    with pytest.raises(CloudDocumentError):
        read_from_paragraphs(document_id="doc-1", revision_id="", paragraphs=["{}"])


def test_bootstrap_uses_manifest_routing_and_builds_handles():
    docs = routed_docs()
    manifest_read = CloudDocumentRead(
        "doc-manifest", "rev-manifest", json.dumps(docs["manifest"])
    )
    reads = {
        key: read_for(key, docs[key], revision=f"rev-{key}")
        for key in docs
        if key != "manifest"
    }
    boot = assemble_bootstrap(manifest_read=manifest_read, canonical_reads=reads)
    assert boot.documents["head"] == docs["head"]
    assert boot.handles["facts"].document_id == "doc-facts"
    assert boot.handles["facts"].revision == "rev-facts"


def test_bootstrap_rejects_missing_read_routing_mismatch_and_duplicate_ids():
    docs = routed_docs()
    manifest_read = CloudDocumentRead("doc-manifest", "rev", json.dumps(docs["manifest"]))
    reads = {key: read_for(key, docs[key]) for key in docs if key != "manifest"}

    missing = dict(reads)
    missing.pop("facts")
    with pytest.raises(CloudDocumentError, match="missing canonical reads"):
        assemble_bootstrap(manifest_read=manifest_read, canonical_reads=missing)

    wrong = dict(reads)
    wrong["facts"] = CloudDocumentRead("wrong", "rev", json.dumps(docs["facts"]))
    with pytest.raises(CloudDocumentError, match="routing mismatch"):
        assemble_bootstrap(manifest_read=manifest_read, canonical_reads=wrong)

    duplicate_manifest = copy.deepcopy(docs["manifest"])
    duplicate_manifest["canonical_files"]["facts"] = duplicate_manifest["canonical_files"]["head"]
    with pytest.raises(CloudDocumentError, match="same document id"):
        assemble_bootstrap(
            manifest_read=CloudDocumentRead("doc-manifest", "rev", json.dumps(duplicate_manifest)),
            canonical_reads=reads,
        )


def make_envelope_case():
    before = routed_docs()
    after = copy.deepcopy(before)
    after["npc_state"]["npcs"]["mira"]["knowledge"]["knows"].append("fact.gm.hidden-cause")
    after["manifest"]["last_event_seq"] = 2
    changed = {"npc_state", "manifest"}
    handles = handles_for(before)
    envelope = build_save_envelope(
        transaction_id="tx-001",
        before=before,
        after=after,
        handles=handles,
        changed_documents=changed,
    )
    return before, after, handles, envelope


def current_reads_for(envelope, values, revisions=None):
    revisions = revisions or {}
    return {
        key: CloudDocumentRead(
            document_id=entry["document_id"],
            revision_id=revisions.get(key, f"fresh-{key}"),
            text=json.dumps(values[key], ensure_ascii=False),
        )
        for key, entry in envelope["documents"].items()
    }


def test_save_envelope_requires_manifest_and_stores_verified_target_content():
    before, after, handles, envelope = make_envelope_case()
    assert envelope["write_order"] == ["npc_state", "manifest"]
    assert envelope["documents"]["npc_state"]["after_content"] == after["npc_state"]
    assert envelope["documents"]["manifest"]["after_sha256"] == sha256_value(after["manifest"])
    with pytest.raises(CloudDocumentError, match="include manifest"):
        build_save_envelope(
            transaction_id="tx-x",
            before=before,
            after=after,
            handles=handles,
            changed_documents={"npc_state"},
        )


def test_recovery_not_started_returns_all_writes_manifest_last_with_fresh_revisions():
    before, after, handles, envelope = make_envelope_case()
    report = assess_recovery(
        envelope=envelope,
        current_reads=current_reads_for(
            envelope, before, {"npc_state": "rev-npc-fresh", "manifest": "rev-man-fresh"}
        ),
    )
    assert report.status == "not_started"
    assert report.ok
    assert [intent.key for intent in report.pending_writes] == ["npc_state", "manifest"]
    assert report.pending_writes[0].expected_revision == "rev-npc-fresh"
    assert report.pending_writes[-1].key == "manifest"


def test_recovery_rolls_forward_only_missing_documents():
    before, after, handles, envelope = make_envelope_case()
    current = {"npc_state": after["npc_state"], "manifest": before["manifest"]}
    report = assess_recovery(envelope=envelope, current_reads=current_reads_for(envelope, current))
    assert report.status == "roll_forward"
    assert report.states == {
        "npc_state": RecoveryState.AFTER,
        "manifest": RecoveryState.BEFORE,
    }
    assert [intent.key for intent in report.pending_writes] == ["manifest"]


def test_recovery_recognizes_committed_save():
    before, after, handles, envelope = make_envelope_case()
    report = assess_recovery(envelope=envelope, current_reads=current_reads_for(envelope, after))
    assert report.status == "committed"
    assert report.ok
    assert report.pending_writes == ()


def test_recovery_blocks_external_edit_instead_of_overwriting_it():
    before, after, handles, envelope = make_envelope_case()
    external = copy.deepcopy(before)
    external["npc_state"]["npcs"]["mira"]["location"] = "human edit"
    report = assess_recovery(
        envelope=envelope,
        current_reads=current_reads_for(envelope, external),
    )
    assert report.status == "blocked"
    assert not report.ok
    assert "unexpected content:npc_state" in report.problems
    assert report.pending_writes == ()


def test_recovery_blocks_manifest_that_advanced_out_of_order():
    before, after, handles, envelope = make_envelope_case()
    current = {"npc_state": before["npc_state"], "manifest": after["manifest"]}
    report = assess_recovery(envelope=envelope, current_reads=current_reads_for(envelope, current))
    assert report.status == "blocked"
    assert report.problems == ("manifest advanced before all earlier canonical writes",)


def test_recovery_rejects_corrupted_envelope_target_hash():
    before, after, handles, envelope = make_envelope_case()
    envelope = copy.deepcopy(envelope)
    envelope["documents"]["npc_state"]["after_content"]["npcs"]["mira"]["location"] = "corrupt"
    report = assess_recovery(
        envelope=envelope,
        current_reads=current_reads_for(envelope, before),
    )
    assert report.status == "blocked"
    assert any("target hash mismatch:npc_state" in problem for problem in report.problems)

from runtime.cloud_documents import (
    idle_save_journal,
    prepare_save_journal,
    recover_from_journal,
    transaction_journal_id,
)
from runtime.state_validate import validate_data


def journal_schema():
    return json.loads((ROOT / "schemas" / "save_journal.schema.json").read_text())


def test_save_journal_idle_and_prepared_shapes_validate():
    before, after, handles, envelope = make_envelope_case()
    idle = idle_save_journal()
    prepared = prepare_save_journal(envelope)
    assert validate_data(idle, journal_schema()) == []
    assert validate_data(prepared, journal_schema()) == []
    assert prepared["last_transaction_id"] == "tx-001"


def test_recover_from_idle_journal_is_noop():
    report = recover_from_journal(journal=idle_save_journal(), current_reads={})
    assert report.status == "idle"
    assert report.ok
    assert report.pending_writes == ()


def test_recover_from_prepared_journal_rolls_forward_and_stale_prepared_can_clear():
    before, after, handles, envelope = make_envelope_case()
    journal = prepare_save_journal(envelope)
    partial = {"npc_state": after["npc_state"], "manifest": before["manifest"]}
    report = recover_from_journal(
        journal=journal,
        current_reads=current_reads_for(envelope, partial),
    )
    assert report.status == "roll_forward"
    assert [intent.key for intent in report.pending_writes] == ["manifest"]

    committed = recover_from_journal(
        journal=journal,
        current_reads=current_reads_for(envelope, after),
    )
    assert committed.status == "committed"
    assert committed.ok


def test_transaction_journal_id_is_optional_but_validated_when_present():
    manifest = routed_docs()["manifest"]
    assert transaction_journal_id(manifest) is None
    manifest = copy.deepcopy(manifest)
    manifest.setdefault("storage", {})["transaction_journal_id"] = "doc-journal"
    assert transaction_journal_id(manifest) == "doc-journal"
    manifest["storage"]["transaction_journal_id"] = " "
    with pytest.raises(CloudDocumentError):
        transaction_journal_id(manifest)


def test_recovery_soak_every_crash_cut_across_full_write_order():
    """Every possible crash boundary rolls forward only the untouched suffix."""
    from runtime.persistence import DEFAULT_WRITE_ORDER

    before = {key: {"key": key, "version": 0} for key in DEFAULT_WRITE_ORDER}
    before["manifest"] = {"campaign_id": "soak", "version": 0}
    after = copy.deepcopy(before)
    for key in DEFAULT_WRITE_ORDER:
        after[key]["version"] = 1
    handles = {
        key: DocumentHandle(key, f"doc-{key}", f"base-{key}")
        for key in DEFAULT_WRITE_ORDER
    }
    envelope = build_save_envelope(
        transaction_id="tx-soak",
        before=before,
        after=after,
        handles=handles,
        changed_documents=set(DEFAULT_WRITE_ORDER),
    )
    assert envelope["write_order"] == list(DEFAULT_WRITE_ORDER)

    for cut in range(len(DEFAULT_WRITE_ORDER) + 1):
        current = {}
        for index, key in enumerate(DEFAULT_WRITE_ORDER):
            current[key] = after[key] if index < cut else before[key]
        report = assess_recovery(
            envelope=envelope,
            current_reads=current_reads_for(envelope, current),
        )
        if cut == len(DEFAULT_WRITE_ORDER):
            assert report.status == "committed"
            assert report.pending_writes == ()
        else:
            assert report.status == ("not_started" if cut == 0 else "roll_forward")
            assert [write.key for write in report.pending_writes] == list(DEFAULT_WRITE_ORDER[cut:])
            assert report.pending_writes[-1].key == "manifest"
