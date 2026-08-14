import copy
import json
from pathlib import Path

from runtime.preflight import format_preflight, run_preflight

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    return json.loads((ROOT / "examples/minimal" / name).read_text())


def schema(name):
    return json.loads((ROOT / "schemas" / name).read_text())


def docs():
    return {
        "manifest": load("manifest.json"),
        "head": load("head.json"),
        "active_state": load("active_state.json"),
        "npc_state": load("npc_state.json"),
        "thread_state": load("thread_state.json"),
        "facts": load("facts.json"),
        "event_log": load("event_log.json"),
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


def test_preflight_ready_for_valid_example():
    report = run_preflight(docs(), schemas())
    assert report.ok
    assert format_preflight(report) == "STATUS: READY"


def test_preflight_stops_on_schema_error_before_semantic_noise():
    broken = docs()
    broken["head"]["present_npcs"] = "mira"
    report = run_preflight(broken, schemas())
    assert not report.ok
    assert "head" in report.schema_errors
    assert report.integrity_issues == ()


def test_preflight_reports_missing_document():
    broken = docs()
    del broken["facts"]
    report = run_preflight(broken, schemas())
    assert not report.ok
    assert report.missing_documents == ("facts",)
