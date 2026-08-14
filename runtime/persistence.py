"""Storage-agnostic write planning for cloud adapters.

The runtime does not call Google Drive directly. It produces explicit write intents that
an adapter/tool layer can execute with optimistic concurrency. The manifest is ordered
last so it acts as the commit pointer for a multi-document save.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


DEFAULT_WRITE_ORDER = (
    "active_state",
    "npc_state",
    "thread_state",
    "facts",
    "event_log",
    "head",
    "manifest",
)


@dataclass(frozen=True)
class DocumentHandle:
    key: str
    document_id: str
    revision: str


@dataclass(frozen=True)
class WriteIntent:
    key: str
    document_id: str
    expected_revision: str
    content: Any
    order: int


def build_write_intents(
    *,
    changed_documents: set[str],
    after: Mapping[str, Any],
    handles: Mapping[str, DocumentHandle],
    write_order: tuple[str, ...] = DEFAULT_WRITE_ORDER,
) -> list[WriteIntent]:
    missing_handles = sorted(key for key in changed_documents if key not in handles)
    missing_content = sorted(key for key in changed_documents if key not in after)
    if missing_handles:
        raise ValueError(f"missing document handles: {', '.join(missing_handles)}")
    if missing_content:
        raise ValueError(f"missing after-state content: {', '.join(missing_content)}")

    priority = {key: index for index, key in enumerate(write_order)}
    ordered = sorted(changed_documents, key=lambda key: (priority.get(key, len(priority)), key))
    return [
        WriteIntent(
            key=key,
            document_id=handles[key].document_id,
            expected_revision=handles[key].revision,
            content=after[key],
            order=index,
        )
        for index, key in enumerate(ordered)
    ]
