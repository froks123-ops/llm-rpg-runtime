import pytest

from runtime.cloud_documents import CloudDocumentError
from runtime.google_docs import (
    build_google_docs_replace_requests,
    google_docs_body_end_index,
    serialize_json_for_google_doc,
)


def paragraphs():
    return [
        {"text": "{", "startIndex": 1, "endIndex": 2},
        {"text": '  "x": 1', "startIndex": 3, "endIndex": 11},
        {"text": "}", "startIndex": 12, "endIndex": 13},
    ]


def test_google_docs_body_end_index_uses_greatest_paragraph_end():
    assert google_docs_body_end_index(paragraphs()) == 13


def test_google_docs_replace_plan_deletes_visible_body_then_inserts_json():
    requests = build_google_docs_replace_requests(paragraphs=paragraphs(), value={"x": 2})
    assert requests[0] == {
        "deleteContentRange": {"range": {"startIndex": 1, "endIndex": 13}}
    }
    assert requests[1]["insertText"]["location"] == {"index": 1}
    assert requests[1]["insertText"]["text"] == '{\n  "x": 2\n}'


def test_google_docs_serializer_preserves_unicode_without_ascii_escaping():
    assert "Kyōraku" in serialize_json_for_google_doc({"npc": "Kyōraku"})


def test_google_docs_replace_plan_fails_closed_on_missing_or_bad_indexes():
    with pytest.raises(CloudDocumentError):
        google_docs_body_end_index([])
    with pytest.raises(CloudDocumentError):
        google_docs_body_end_index([{"text": "x"}])
    with pytest.raises(CloudDocumentError):
        google_docs_body_end_index([{"endIndex": True}])
