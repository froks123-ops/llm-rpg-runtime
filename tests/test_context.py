import json
from pathlib import Path

from runtime.context_assembler import assemble

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    return json.loads((ROOT / "examples/minimal" / name).read_text())


def test_context_assembler_separates_gm_truth_player_and_npc_views():
    context = assemble(
        load("manifest.json"),
        load("head.json"),
        load("npc_state.json"),
        load("thread_state.json"),
        load("facts.json"),
    )

    gm_ids = {fact["id"] for fact in context["gm_truth"]}
    player_ids = {fact["id"] for fact in context["player_view"]}
    mira_knows = {fact["id"] for fact in context["npc_views"]["mira"]["knows"]}
    mira_suspects = {fact["id"] for fact in context["npc_views"]["mira"]["suspects"]}

    assert "fact.gm.hidden-cause" in gm_ids
    assert "fact.gm.hidden-cause" not in player_ids
    assert "fact.gm.hidden-cause" not in mira_knows
    assert "fact.scout.missing" in player_ids
    assert "fact.scout.missing" in mira_knows
    assert "fact.road.unsafe-rumor" in mira_suspects
    assert "fact.road.unsafe-rumor" not in gm_ids  # unknown proposition, not GM truth.
    assert "fact.old.location" not in context["retrieval_hints"]["fact_ids"]


def test_npc_view_does_not_receive_truth_metadata_or_source_provenance():
    context = assemble(
        load("manifest.json"),
        load("head.json"),
        load("npc_state.json"),
        load("thread_state.json"),
        load("facts.json"),
    )
    all_mira_facts = sum(context["npc_views"]["mira"].values(), [])
    assert all("truth_status" not in fact for fact in all_mira_facts)
    assert all("source" not in fact for fact in all_mira_facts)


def test_context_withholds_stale_relationship_metrics_marked_for_rebuild():
    npc_state = load("npc_state.json")
    relation = npc_state["npcs"]["mira"]["relationships"]["pc:traveler"]
    relation["needs_rebuild"] = True
    relation["invalidated_basis_fact_ids"] = ["fact.scout.missing"]

    context = assemble(
        load("manifest.json"),
        load("head.json"),
        npc_state,
        load("thread_state.json"),
        load("facts.json"),
    )
    safe_relation = context["present_npcs"]["mira"]["relationships"]["pc:traveler"]
    assert safe_relation["needs_rebuild"] is True
    assert "trust" not in safe_relation
    assert "stance" not in safe_relation


def test_retrieval_hints_prefer_stable_source_ref():
    manifest = load("manifest.json")
    head = load("head.json")
    npcs = load("npc_state.json")
    threads = load("thread_state.json")
    facts = load("facts.json")
    facts[0]["source"] = {
        "scene_id": "s001-sc001",
        "chunk_ref": "ai-studio:chunk:0055",
        "kind": "import",
    }
    pack = assemble(manifest, head, npcs, threads, facts)
    assert "ai-studio:chunk:0055" in pack["retrieval_hints"]["source_refs"]
    assert not any(ref.startswith("{") for ref in pack["retrieval_hints"]["source_refs"])


def test_ooc_view_does_not_leak_into_player_character_view():
    manifest = load("manifest.json")
    head = load("head.json")
    npcs = load("npc_state.json")
    threads = load("thread_state.json")
    facts = load("facts.json")
    facts.append({
        "id": "fact.ooc.monologue",
        "text": "Mira privately fears the bridge.",
        "status": "active",
        "truth_status": "subjective",
        "known_by": ["ooc", "npc:mira"],
        "entities": ["npc:mira"],
        "source": "test:ooc",
    })
    pack = assemble(manifest, head, npcs, threads, facts)
    player_ids = {f["id"] for f in pack["player_view"]}
    ooc_ids = {f["id"] for f in pack["ooc_view"]}
    mira_knows = {f["id"] for f in pack["npc_views"]["mira"]["knows"]}
    assert "fact.ooc.monologue" not in player_ids
    assert "fact.ooc.monologue" in ooc_ids
    assert "fact.ooc.monologue" in mira_knows


def test_context_includes_active_state_and_player_character_tagged_facts():
    manifest = load("manifest.json")
    head = load("head.json")
    npcs = load("npc_state.json")
    threads = load("thread_state.json")
    facts = load("facts.json")
    facts.append({
        "id": "fact.pc.private-condition",
        "text": "The traveler has a private scar.",
        "status": "active",
        "truth_status": "true",
        "known_by": ["player"],
        "entities": ["pc:traveler"],
        "source": "test:pc",
    })
    active_state = load("active_state.json")
    pack = assemble(manifest, head, npcs, threads, facts, active_state)
    assert pack["active_state"]["actor_id"] == "pc:traveler"
    assert "fact.pc.private-condition" in pack["retrieval_hints"]["fact_ids"]
    assert "fact.pc.private-condition" in {f["id"] for f in pack["player_view"]}


def test_player_epistemic_belief_can_be_false_without_entering_gm_truth():
    manifest = load("manifest.json")
    head = load("head.json")
    npcs = load("npc_state.json")
    threads = load("thread_state.json")
    facts = load("facts.json")
    active = load("active_state.json")
    facts.append({
        "id": "fact.pc.false-belief",
        "text": "The missing scout is dead.",
        "status": "active",
        "truth_status": "false",
        "known_by": [],
        "entities": ["pc:traveler"],
        "source": "test:false-belief",
    })
    active["knowledge"]["believes"].append("fact.pc.false-belief")
    pack = assemble(manifest, head, npcs, threads, facts, active)
    assert "fact.pc.false-belief" in {f["id"] for f in pack["player_epistemic_view"]["believes"]}
    assert "fact.pc.false-belief" not in {f["id"] for f in pack["gm_truth"]}
    assert "fact.pc.false-belief" not in {f["id"] for f in pack["player_epistemic_view"]["knows"]}


def test_pc_plus_offstage_entity_does_not_become_hot_without_reference():
    manifest = load("manifest.json")
    head = load("head.json")
    npcs = load("npc_state.json")
    threads = load("thread_state.json")
    facts = load("facts.json")
    facts.append({
        "id": "fact.pc.offstage-secret",
        "text": "An offstage enemy secretly tracks the traveler.",
        "status": "active",
        "truth_status": "true",
        "known_by": ["ooc"],
        "entities": ["pc:traveler", "npc:offstage-enemy"],
        "source": "test:offstage",
    })
    pack = assemble(manifest, head, npcs, threads, facts, load("active_state.json"))
    assert "fact.pc.offstage-secret" not in pack["retrieval_hints"]["fact_ids"]


def test_context_fact_budget_prioritizes_active_thread_over_cold_history():
    manifest = load("manifest.json")
    head = load("head.json")
    npcs = load("npc_state.json")
    threads = load("thread_state.json")
    facts = load("facts.json")
    active = load("active_state.json")
    facts.append({
        "id": "fact.cold.personal-history",
        "text": "A distant offstage memory.",
        "status": "active",
        "truth_status": "true",
        "known_by": ["player"],
        "entities": ["pc:traveler", "npc:offstage"],
        "importance": 100,
        "source": "test:cold",
    })
    active["knowledge"]["remembers"].append("fact.cold.personal-history")
    pack = assemble(manifest, head, npcs, threads, facts, active, max_facts=3)
    ids = set(pack["retrieval_hints"]["fact_ids"] )
    assert "fact.scout.missing" in ids  # active thread
    assert "fact.cold.personal-history" not in ids


def test_requested_fact_overrides_normal_scene_ranking():
    manifest = load("manifest.json")
    head = load("head.json")
    npcs = load("npc_state.json")
    threads = load("thread_state.json")
    facts = load("facts.json")
    facts.append({
        "id": "fact.requested.cold",
        "text": "Cold but explicitly requested.",
        "status": "active",
        "truth_status": "true",
        "known_by": ["ooc"],
        "entities": ["npc:far-away"],
        "importance": 1,
        "source": "test:requested",
    })
    pack = assemble(
        manifest, head, npcs, threads, facts, load("active_state.json"),
        requested_fact_ids=["fact.requested.cold"], max_facts=1,
    )
    assert pack["retrieval_hints"]["fact_ids"] == ["fact.requested.cold"]
