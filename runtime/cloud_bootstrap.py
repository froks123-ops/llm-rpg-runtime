"""Cloud bootstrap orchestration for campaign resume and crash recovery.

This module bridges provider reads with the storage-agnostic campaign runtime.  It does
not call Google Drive itself.  A connector layer supplies fresh document reads; the
runtime decides whether it is safe to play, whether an interrupted save must be rolled
forward, or whether the campaign must stop for manual inspection.

The last committed manifest is the routing/commit pointer.  When it declares a stable
transaction journal, that journal is inspected before semantic preflight.  A prepared
journal means the previous process may have stopped between canonical writes; normal
play must not continue until the recovery plan is completed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .cloud_documents import (
    CloudBootstrap,
    CloudDocumentError,
    CloudDocumentRead,
    RecoveryReport,
    assemble_bootstrap,
    recover_from_journal,
    transaction_journal_id,
)
from .preflight import PreflightReport, run_preflight


@dataclass(frozen=True)
class CloudBootstrapDecision:
    """One fail-closed decision for a fresh cloud campaign bootstrap."""

    status: str
    bootstrap: CloudBootstrap | None
    preflight: PreflightReport | None
    recovery: RecoveryReport | None
    journal_action: str
    problems: tuple[str, ...]

    @property
    def ready(self) -> bool:
        return self.status == "ready"

    @property
    def blocked(self) -> bool:
        return self.status == "blocked"


def plan_cloud_bootstrap(
    *,
    manifest_read: CloudDocumentRead,
    canonical_reads: Mapping[str, CloudDocumentRead],
    schemas: Mapping[str, Mapping[str, Any]],
    journal_read: CloudDocumentRead | None = None,
) -> CloudBootstrapDecision:
    """Decide whether a freshly-read cloud campaign may enter normal play.

    Decision order is intentionally strict:

    1. parse/validate manifest routing and canonical document IDs;
    2. if the committed manifest declares a transaction journal, require and parse it;
    3. if the journal is PREPARED, assess crash recovery before semantic preflight;
    4. only an IDLE/no-journal campaign may run normal schema + integrity preflight;
    5. normal play starts only on a READY decision.

    ``recovery_required`` never means "best effort".  The caller must execute exactly
    the returned recovery write intents (if any), then clear the journal and bootstrap
    again from fresh provider reads.
    """

    try:
        bootstrap = assemble_bootstrap(
            manifest_read=manifest_read,
            canonical_reads=canonical_reads,
        )
        manifest = bootstrap.documents["manifest"]
        declared_journal_id = transaction_journal_id(manifest)
    except CloudDocumentError as exc:
        return _blocked(str(exc))

    if declared_journal_id is not None:
        if journal_read is None:
            return _blocked("manifest declares transaction journal but no fresh journal read was supplied", bootstrap)
        if journal_read.document_id != declared_journal_id:
            return _blocked(
                "transaction journal routing mismatch: "
                f"manifest={declared_journal_id!r}, read={journal_read.document_id!r}",
                bootstrap,
            )
        try:
            journal = journal_read.value
        except CloudDocumentError as exc:
            return _blocked(f"invalid transaction journal: {exc}", bootstrap)
        if not isinstance(journal, Mapping):
            return _blocked("transaction journal JSON must be an object", bootstrap)

        fresh_reads: dict[str, CloudDocumentRead] = {"manifest": manifest_read}
        fresh_reads.update(canonical_reads)
        recovery = recover_from_journal(journal=journal, current_reads=fresh_reads)
        if recovery.status == "blocked":
            return CloudBootstrapDecision(
                status="blocked",
                bootstrap=bootstrap,
                preflight=None,
                recovery=recovery,
                journal_action="none",
                problems=recovery.problems,
            )
        if recovery.status in {"not_started", "roll_forward"}:
            return CloudBootstrapDecision(
                status="recovery_required",
                bootstrap=bootstrap,
                preflight=None,
                recovery=recovery,
                journal_action="keep_prepared",
                problems=(),
            )
        if recovery.status == "committed":
            # Canonical commit pointer already reached AFTER.  No canonical document may
            # be rewritten; the only safe remaining action is clearing the stale journal.
            return CloudBootstrapDecision(
                status="recovery_required",
                bootstrap=bootstrap,
                preflight=None,
                recovery=recovery,
                journal_action="clear",
                problems=(),
            )
        if recovery.status != "idle":
            return _blocked(f"unsupported recovery status:{recovery.status}", bootstrap)

    preflight = run_preflight(bootstrap.documents, schemas)
    if not preflight.ok:
        problems = _preflight_problems(preflight)
        return CloudBootstrapDecision(
            status="blocked",
            bootstrap=bootstrap,
            preflight=preflight,
            recovery=None,
            journal_action="none",
            problems=problems,
        )

    return CloudBootstrapDecision(
        status="ready",
        bootstrap=bootstrap,
        preflight=preflight,
        recovery=None,
        journal_action="none",
        problems=(),
    )


def _blocked(message: str, bootstrap: CloudBootstrap | None = None) -> CloudBootstrapDecision:
    return CloudBootstrapDecision(
        status="blocked",
        bootstrap=bootstrap,
        preflight=None,
        recovery=None,
        journal_action="none",
        problems=(message,),
    )


def _preflight_problems(report: PreflightReport) -> tuple[str, ...]:
    problems: list[str] = []
    problems.extend(f"missing document:{name}" for name in report.missing_documents)
    for name, errors in sorted(report.schema_errors.items()):
        problems.extend(f"schema {name}:{error}" for error in errors)
    for issue in report.integrity_issues:
        suffix = f" [{issue.path}]" if issue.path else ""
        problems.append(f"{issue.level}:{issue.code}:{issue.message}{suffix}")
    return tuple(problems) or ("campaign preflight failed",)
