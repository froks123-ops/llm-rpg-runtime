from runtime.importers.ai_studio import (
    archive_markdown,
    chunk_index,
    export_stats,
    parse_export,
    select_chunks,
)


def sample_export():
    return {
        "runSettings": {"model": "x"},
        "systemInstruction": "rules",
        "chunkedPrompt": {
            "chunks": [
                {"role": "user", "text": "seed", "tokenCount": 10, "createTime": "t0"},
                {"role": "model", "text": "[Dzień 1 | Pora: Rano] scene", "tokenCount": 20, "createTime": "t1", "finishReason": "STOP"},
                {"role": "user", "text": "branch", "tokenCount": 5, "createTime": "t2"},
                {"role": "model", "text": "branch result", "tokenCount": 8, "createTime": "t3"}
            ],
            "pendingInputs": [{"role": "user", "text": ""}]
        }
    }


def test_importer_preserves_chunks_and_stats():
    export = parse_export(sample_export())
    assert export.system_instruction == "rules"
    assert export.chunks[1].source_ref == "ai-studio:chunk:0001"
    assert export_stats(export) == {
        "chunks": 4,
        "roles": {"user": 2, "model": 2},
        "token_count_sum": 43,
        "tokenized_chunks": 4,
        "pending_inputs": 1,
    }


def test_explicit_branch_exclusion_is_index_based_not_semantic_guessing():
    export = parse_export(sample_export())
    selected = select_chunks(export, exclude_ranges=[(2, 3)])
    assert [chunk.index for chunk in selected] == [0, 1]


def test_archive_and_index_keep_provenance_and_scene_header():
    export = parse_export(sample_export())
    selected = select_chunks(export, end_inclusive=1)
    index = chunk_index(selected)
    assert index[1]["scene_header"] == "[Dzień 1 | Pora: Rano]"
    archive = archive_markdown(selected, title="Test")
    assert "ai-studio:chunk:0001" in archive
    assert "[Dzień 1 | Pora: Rano] scene" in archive
