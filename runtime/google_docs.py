"""Small pure helpers for replacing JSON stored in one-tab native Google Docs.

The runtime intentionally does not depend on Google's SDK.  ChatGPT/connector or local
adapter layers can feed paragraph metadata returned by a Docs read into these helpers and
receive deterministic `documents.batchUpdate` request objects.

Revision IDs remain provider receipts and must be supplied as `requiredRevisionId` by the
caller.  This module only plans content operations; it never performs I/O.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping
import json

from .cloud_documents import CloudDocumentError


def google_docs_body_end_index(paragraphs: Iterable[Mapping[str, Any]]) -> int:
    """Return the exclusive end index of visible body text from paragraph metadata.

    `get_document_text`-style rows expose `startIndex` / `endIndex`.  Full replacement
    retains the document's structural terminal newline while deleting visible content
    from index 1 through the greatest paragraph end index.
    """

    maximum = 1
    seen = False
    for paragraph in paragraphs:
        if not isinstance(paragraph, Mapping):
            raise CloudDocumentError("Google Docs paragraph must be an object")
        end = paragraph.get("endIndex")
        if not isinstance(end, int) or isinstance(end, bool) or end < 1:
            raise CloudDocumentError("Google Docs paragraph endIndex must be a positive integer")
        maximum = max(maximum, end)
        seen = True
    if not seen or maximum <= 1:
        raise CloudDocumentError("Google Docs body has no replaceable paragraph content")
    return maximum


def serialize_json_for_google_doc(value: Any) -> str:
    """Stable readable JSON representation for cloud-native state documents."""

    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=False)


def build_google_docs_replace_requests(
    *,
    paragraphs: Iterable[Mapping[str, Any]],
    value: Any,
) -> list[dict[str, Any]]:
    """Build raw Google Docs API requests for an in-place full JSON replacement."""

    rows = list(paragraphs)
    end_index = google_docs_body_end_index(rows)
    text = serialize_json_for_google_doc(value)
    return [
        {
            "deleteContentRange": {
                "range": {
                    "startIndex": 1,
                    "endIndex": end_index,
                }
            }
        },
        {
            "insertText": {
                "location": {"index": 1},
                "text": text,
            }
        },
    ]
