"""Provider-neutral helpers for JSON state stored in cloud-native text documents.

The module deliberately does not import a Google Drive SDK.  Connector/tool layers turn
provider responses into :class:`CloudDocumentRead` objects, while the runtime handles:

* lossless JSON reconstruction from paragraph-oriented reads;
* manifest routing validation and bootstrap assembly;
* revision receipts for optimistic concurrency;
* persistent roll-forward save envelopes for multi-document saves;
* deterministic recovery decisions after partial cloud writes.

A save envelope stores the intended *after* content for changed documents.  If a process
stops after writing only some documents, a later process can compare current content
hashes with the envelope and safely finish only the still-pending writes.  Unexpected
content blocks automatic recovery instead of overwriting a human edit.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import json
from typing import Any, Iterable, Mapping, Sequence

from .checkpoint import sha256_value
from .persistence import DEFAULT_WRITE_ORDER, DocumentHandle, WriteIntent


REQUIRED_CANONICAL_KEYS = (
    "head",
    "active_state",
    "npc_state",
    "thread_state",
    "facts",
    "event_log",
)


class CloudDocumentError(ValueError):
    """Raised when cloud document content or routing is not safe to consume."""


@dataclass(frozen=True)
class CloudDocumentRead:
    """Normalized result of one provider document read."""

    document_id: str
    revision_id: str
    text: str

    @property
    def value(self) -> Any:
        return parse_json_document(self.text)

    @property
    def sha256(self) -> str:
        return sha256_value(self.value)


@dataclass(frozen=True)
class CloudBootstrap:
    """Validated logical campaign documents reconstructed from provider reads."""

    documents: Mapping[str, Any]
    handles: Mapping[str, DocumentHandle]
    manifest_document_id: str


class RecoveryState(str, Enum):
    BEFORE = "before"
    AFTER = "after"
    UNEXPECTED = "unexpected"


@dataclass(frozen=True)
class RecoveryReport:
    """Decision produced by comparing a save envelope with fresh cloud reads."""

    status: str
    states: Mapping[str, RecoveryState]
    pending_writes: tuple[WriteIntent, ...]
    problems: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.problems


def paragraphs_to_text(paragraphs: Iterable[str | Mapping[str, Any]]) -> str:
    """Reconstruct text from Google-Docs-like paragraph rows.

    Provider APIs commonly return paragraphs without newline characters.  Imported JSON
    therefore needs one newline reinserted between rows.  Supplying plain strings is
    useful for tests and other providers.
    """

    lines: list[str] = []
    for paragraph in paragraphs:
        if isinstance(paragraph, str):
            lines.append(paragraph)
        elif isinstance(paragraph, Mapping):
            text = paragraph.get("text")
            if not isinstance(text, str):
                raise CloudDocumentError("paragraph mapping must contain string field 'text'")
            lines.append(text)
        else:
            raise CloudDocumentError("paragraph must be a string or mapping")
    return "\n".join(lines)


def parse_json_document(text: str) -> Any:
    """Parse one cloud-native text document as JSON, failing closed."""

    if not isinstance(text, str):
        raise CloudDocumentError("document text must be a string")
    normalized = text.lstrip("\ufeff").strip()
    if normalized.startswith("```"):
        lines = normalized.splitlines()
        if len(lines) >= 2 and lines[-1].strip() == "```":
            normalized = "\n".join(lines[1:-1])
            if normalized.lstrip().lower().startswith("json\n"):
                normalized = normalized.lstrip()[5:]
    try:
        return json.loads(normalized)
    except json.JSONDecodeError as exc:
        raise CloudDocumentError(
            f"invalid JSON at line {exc.lineno} column {exc.colno}: {exc.msg}"
        ) from exc


def read_from_paragraphs(
    *,
    document_id: str,
    revision_id: str,
    paragraphs: Iterable[str | Mapping[str, Any]],
) -> CloudDocumentRead:
    """Create a normalized read from a paragraph-oriented provider response."""

    return CloudDocumentRead(
        document_id=_require_nonempty(document_id, "document_id"),
        revision_id=_require_nonempty(revision_id, "revision_id"),
        text=paragraphs_to_text(paragraphs),
    )


def manifest_targets(manifest: Mapping[str, Any]) -> dict[str, str]:
    """Return and validate the canonical document routing table."""

    raw = manifest.get("canonical_files")
    if not isinstance(raw, Mapping):
        raise CloudDocumentError("manifest.canonical_files must be an object")

    targets: dict[str, str] = {}
    missing: list[str] = []
    for key in REQUIRED_CANONICAL_KEYS:
        value = raw.get(key)
        if not isinstance(value, str) or not value.strip():
            missing.append(key)
        else:
            targets[key] = value.strip()
    if missing:
        raise CloudDocumentError(
            "manifest missing canonical file ids: " + ", ".join(sorted(missing))
        )

    ids = list(targets.values())
    duplicates = sorted({value for value in ids if ids.count(value) > 1})
    if duplicates:
        raise CloudDocumentError(
            "manifest routes multiple canonical keys to the same document id: "
            + ", ".join(duplicates)
        )
    return targets


def assemble_bootstrap(
    *,
    manifest_read: CloudDocumentRead,
    canonical_reads: Mapping[str, CloudDocumentRead],
) -> CloudBootstrap:
    """Assemble a campaign only when provider reads exactly match manifest routing."""

    manifest = manifest_read.value
    if not isinstance(manifest, Mapping):
        raise CloudDocumentError("manifest JSON must be an object")
    targets = manifest_targets(manifest)

    missing = sorted(set(REQUIRED_CANONICAL_KEYS) - set(canonical_reads))
    if missing:
        raise CloudDocumentError("missing canonical reads: " + ", ".join(missing))

    documents: dict[str, Any] = {"manifest": manifest}
    handles: dict[str, DocumentHandle] = {
        "manifest": DocumentHandle(
            "manifest", manifest_read.document_id, manifest_read.revision_id
        )
    }
    for key in REQUIRED_CANONICAL_KEYS:
        read = canonical_reads[key]
        expected_id = targets[key]
        if read.document_id != expected_id:
            raise CloudDocumentError(
                f"routing mismatch for {key}: manifest={expected_id!r}, read={read.document_id!r}"
            )
        documents[key] = read.value
        handles[key] = DocumentHandle(key, read.document_id, read.revision_id)

    return CloudBootstrap(
        documents=documents,
        handles=handles,
        manifest_document_id=manifest_read.document_id,
    )


def build_save_envelope(
    *,
    transaction_id: str,
    before: Mapping[str, Any],
    after: Mapping[str, Any],
    handles: Mapping[str, DocumentHandle],
    changed_documents: set[str],
    write_order: Sequence[str] = DEFAULT_WRITE_ORDER,
) -> dict[str, Any]:
    """Build a persistent roll-forward envelope before any canonical write occurs.

    The envelope intentionally contains only changed documents.  Each entry stores both
    the base hash and intended after content.  A recovery process can therefore distinguish
    untouched, successfully-written and externally-modified documents without guessing.
    """

    transaction_id = _require_nonempty(transaction_id, "transaction_id")
    if not changed_documents:
        raise CloudDocumentError("save envelope requires at least one changed document")
    if "manifest" not in changed_documents:
        raise CloudDocumentError("cloud multi-document saves must include manifest commit pointer")

    unknown = sorted(
        key
        for key in changed_documents
        if key not in before or key not in after or key not in handles
    )
    if unknown:
        raise CloudDocumentError("missing before/after/handle for: " + ", ".join(unknown))

    priority = {key: index for index, key in enumerate(write_order)}
    ordered = sorted(changed_documents, key=lambda key: (priority.get(key, len(priority)), key))
    if ordered[-1] != "manifest":
        raise CloudDocumentError("manifest must be the last canonical write")

    campaign_id = after.get("manifest", {}).get("campaign_id")
    if not isinstance(campaign_id, str) or not campaign_id:
        raise CloudDocumentError("after.manifest.campaign_id must be present")

    entries: dict[str, Any] = {}
    for key in ordered:
        entries[key] = {
            "document_id": handles[key].document_id,
            "base_revision": handles[key].revision,
            "before_sha256": sha256_value(before[key]),
            "after_sha256": sha256_value(after[key]),
            "after_content": after[key],
        }

    return {
        "schema_version": 1,
        "transaction_id": transaction_id,
        "campaign_id": campaign_id,
        "status": "prepared",
        "write_order": ordered,
        "documents": entries,
    }


def assess_recovery(
    *,
    envelope: Mapping[str, Any],
    current_reads: Mapping[str, CloudDocumentRead],
) -> RecoveryReport:
    """Determine whether an interrupted save can be safely rolled forward.

    Automatic recovery is allowed only when every current document matches either its
    recorded before hash or intended after hash.  Any third value is treated as an
    external/concurrent edit and blocks writes.  A manifest that reached AFTER while any
    earlier document is still BEFORE is also blocked because the commit pointer advanced
    out of order.
    """

    problems: list[str] = []
    try:
        order, entries = _validate_envelope_shape(envelope)
    except CloudDocumentError as exc:
        return RecoveryReport("blocked", {}, (), (str(exc),))

    states: dict[str, RecoveryState] = {}
    for key in order:
        entry = entries[key]
        read = current_reads.get(key)
        if read is None:
            problems.append(f"missing fresh read:{key}")
            continue
        if read.document_id != entry["document_id"]:
            problems.append(f"document id changed:{key}")
            states[key] = RecoveryState.UNEXPECTED
            continue
        actual = read.sha256
        if actual == entry["after_sha256"]:
            states[key] = RecoveryState.AFTER
        elif actual == entry["before_sha256"]:
            states[key] = RecoveryState.BEFORE
        else:
            states[key] = RecoveryState.UNEXPECTED
            problems.append(f"unexpected content:{key}")

    if problems:
        return RecoveryReport("blocked", states, (), tuple(sorted(problems)))

    manifest_state = states.get("manifest")
    non_manifest = [key for key in order if key != "manifest"]
    if manifest_state is RecoveryState.AFTER and any(
        states[key] is not RecoveryState.AFTER for key in non_manifest
    ):
        return RecoveryReport(
            "blocked",
            states,
            (),
            ("manifest advanced before all earlier canonical writes",),
        )

    if all(states[key] is RecoveryState.AFTER for key in order):
        return RecoveryReport("committed", states, (), ())

    pending: list[WriteIntent] = []
    for index, key in enumerate(order):
        if states[key] is RecoveryState.AFTER:
            continue
        read = current_reads[key]
        entry = entries[key]
        pending.append(
            WriteIntent(
                key=key,
                document_id=entry["document_id"],
                expected_revision=read.revision_id,
                content=entry["after_content"],
                order=index,
            )
        )

    status = "not_started" if all(
        states[key] is RecoveryState.BEFORE for key in order
    ) else "roll_forward"
    return RecoveryReport(status, states, tuple(pending), ())


def _validate_envelope_shape(
    envelope: Mapping[str, Any],
) -> tuple[list[str], Mapping[str, Mapping[str, Any]]]:
    if envelope.get("schema_version") != 1:
        raise CloudDocumentError("unsupported save envelope schema_version")
    order_raw = envelope.get("write_order")
    entries_raw = envelope.get("documents")
    if not isinstance(order_raw, list) or not order_raw:
        raise CloudDocumentError("save envelope write_order must be a non-empty array")
    if not isinstance(entries_raw, Mapping):
        raise CloudDocumentError("save envelope documents must be an object")
    if any(not isinstance(key, str) or not key for key in order_raw):
        raise CloudDocumentError("save envelope write_order contains invalid key")
    order = list(order_raw)
    if len(set(order)) != len(order):
        raise CloudDocumentError("save envelope write_order contains duplicates")
    if order[-1] != "manifest":
        raise CloudDocumentError("save envelope does not place manifest last")
    if set(order) != set(entries_raw):
        raise CloudDocumentError("save envelope write_order/documents mismatch")

    for key in order:
        entry = entries_raw[key]
        if not isinstance(entry, Mapping):
            raise CloudDocumentError(f"save envelope entry {key} must be an object")
        for field in ("document_id", "base_revision", "before_sha256", "after_sha256"):
            value = entry.get(field)
            if not isinstance(value, str) or not value:
                raise CloudDocumentError(f"save envelope {key}.{field} is required")
        if "after_content" not in entry:
            raise CloudDocumentError(f"save envelope {key}.after_content is required")
        # Ensure stored hashes actually describe the stored target.  This prevents a
        # corrupted envelope from becoming an overwrite oracle during recovery.
        if sha256_value(entry["after_content"]) != entry["after_sha256"]:
            raise CloudDocumentError(f"save envelope target hash mismatch:{key}")
    return order, entries_raw


def _require_nonempty(value: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CloudDocumentError(f"{field} must be a non-empty string")
    return value.strip()


def idle_save_journal(*, last_transaction_id: str | None = None) -> dict[str, Any]:
    """Return the stable idle representation for a cloud transaction journal."""

    if last_transaction_id is not None:
        _require_nonempty(last_transaction_id, "last_transaction_id")
    return {
        "schema_version": 1,
        "status": "idle",
        "last_transaction_id": last_transaction_id,
        "envelope": None,
    }


def prepare_save_journal(envelope: Mapping[str, Any]) -> dict[str, Any]:
    """Persistable journal value written before any canonical document mutation."""

    _validate_envelope_shape(envelope)
    transaction_id = _require_nonempty(envelope.get("transaction_id"), "transaction_id")
    return {
        "schema_version": 1,
        "status": "prepared",
        "last_transaction_id": transaction_id,
        "envelope": dict(envelope),
    }


def recover_from_journal(
    *,
    journal: Mapping[str, Any],
    current_reads: Mapping[str, CloudDocumentRead],
) -> RecoveryReport:
    """Assess a stable transaction journal after bootstrap.

    ``idle`` means there is nothing to recover.  ``prepared`` delegates to the save
    envelope assessor.  A stale prepared journal whose canonical documents are already
    all AFTER is classified as ``committed`` and can simply be cleared.
    """

    if journal.get("schema_version") != 1:
        return RecoveryReport("blocked", {}, (), ("unsupported save journal schema_version",))
    status = journal.get("status")
    if status == "idle":
        if journal.get("envelope") is not None:
            return RecoveryReport("blocked", {}, (), ("idle save journal contains envelope",))
        return RecoveryReport("idle", {}, (), ())
    if status != "prepared":
        return RecoveryReport("blocked", {}, (), (f"unsupported save journal status:{status}",))
    envelope = journal.get("envelope")
    if not isinstance(envelope, Mapping):
        return RecoveryReport("blocked", {}, (), ("prepared save journal missing envelope",))
    return assess_recovery(envelope=envelope, current_reads=current_reads)


def transaction_journal_id(manifest: Mapping[str, Any]) -> str | None:
    """Return the stable journal document id declared by the last committed manifest."""

    storage = manifest.get("storage")
    if not isinstance(storage, Mapping):
        return None
    value = storage.get("transaction_journal_id")
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise CloudDocumentError("manifest.storage.transaction_journal_id must be a non-empty string")
    return value.strip()
