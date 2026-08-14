"""Campaign preflight: schema + cross-document integrity in one report."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .integrity import IntegrityIssue, audit_campaign, has_errors
from .state_validate import validate_data


REQUIRED_CAMPAIGN_DOCUMENTS = (
    "manifest",
    "head",
    "active_state",
    "npc_state",
    "thread_state",
    "facts",
    "event_log",
)


@dataclass(frozen=True)
class PreflightReport:
    ok: bool
    schema_errors: dict[str, tuple[str, ...]]
    integrity_issues: tuple[IntegrityIssue, ...]
    missing_documents: tuple[str, ...]


def run_preflight(
    documents: Mapping[str, Any],
    schemas: Mapping[str, Mapping[str, Any]],
) -> PreflightReport:
    missing = tuple(sorted(set(REQUIRED_CAMPAIGN_DOCUMENTS) - set(documents)))
    if missing:
        return PreflightReport(False, {}, (), missing)

    schema_errors: dict[str, tuple[str, ...]] = {}
    for name in REQUIRED_CAMPAIGN_DOCUMENTS:
        schema = schemas.get(name)
        if schema is None:
            continue
        errors = validate_data(documents[name], schema)
        if errors:
            schema_errors[name] = tuple(errors)

    # Do not run semantic checks on malformed documents; they would create noisy
    # secondary errors and can mask the actual shape problem.
    if schema_errors:
        return PreflightReport(False, schema_errors, (), ())

    issues = tuple(
        audit_campaign(
            manifest=documents["manifest"],
            head=documents["head"],
            active_state=documents["active_state"],
            npc_state=documents["npc_state"],
            thread_state=documents["thread_state"],
            facts=documents["facts"],
            events=documents["event_log"],
        )
    )
    return PreflightReport(not has_errors(issues), {}, issues, ())


def format_preflight(report: PreflightReport) -> str:
    lines = [f"STATUS: {'READY' if report.ok else 'NEEDS ATTENTION'}"]
    if report.missing_documents:
        lines.append("MISSING: " + ", ".join(report.missing_documents))
    for document, errors in report.schema_errors.items():
        for error in errors:
            lines.append(f"SCHEMA {document}: {error}")
    for issue in report.integrity_issues:
        suffix = f" [{issue.path}]" if issue.path else ""
        lines.append(f"{issue.level.upper()} {issue.code}: {issue.message}{suffix}")
    return "\n".join(lines)
