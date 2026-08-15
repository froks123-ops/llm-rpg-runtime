"""Structural validation for player-visible GM output.

This module validates presentation invariants only. It deliberately does not attempt
to prove semantic properties such as player agency, spoiler safety or epistemic
correctness; those remain responsibilities of the GM constitution and campaign
integrity layer.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable


_REPORT_OPEN = "```Raport"
_REPORT_CLOSE = "```"
_HEADER_RE = re.compile(
    r"^(?P<ticks>`{1,2})(?P<header>\[Dzień [^\n]+\])(?P=ticks)$"
)
_MONOLOGUE_TITLE_RE = re.compile(r"^\*\*Monolog(?: NPC| [^*\n]+)?\*\*$")
_DEBUG_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("persistence.transaction_journal_id", re.compile(r"\btransaction_journal_id\b", re.I)),
    ("persistence.requiredRevisionId", re.compile(r"\brequiredRevisionId\b")),
    ("persistence.schema_version", re.compile(r'["\']?schema_version["\']?\s*[:=]', re.I)),
    ("persistence.roll_forward", re.compile(r"\bROLL_FORWARD\b")),
    ("persistence.journal_prepared", re.compile(r"\bjournal\s*[:=]?\s*PREPARED\b", re.I)),
    ("persistence.revision_id", re.compile(r"\brevisionId\b")),
)


@dataclass(frozen=True)
class OutputContractIssue:
    """One deterministic structural finding."""

    code: str
    message: str
    severity: str = "error"


@dataclass(frozen=True)
class OutputContractResult:
    """Result of validating one player-visible response."""

    issues: tuple[OutputContractIssue, ...]

    @property
    def errors(self) -> tuple[OutputContractIssue, ...]:
        return tuple(issue for issue in self.issues if issue.severity == "error")

    @property
    def warnings(self) -> tuple[OutputContractIssue, ...]:
        return tuple(issue for issue in self.issues if issue.severity == "warning")

    @property
    def ok(self) -> bool:
        return not self.errors


def _issue(code: str, message: str, *, severity: str = "error") -> OutputContractIssue:
    return OutputContractIssue(code=code, message=message, severity=severity)


def _split_report(text: str) -> tuple[str | None, str]:
    """Return report body and remainder without guessing malformed fences."""

    stripped = text.lstrip()
    if not stripped.startswith(_REPORT_OPEN):
        return None, stripped

    first_newline = stripped.find("\n")
    if first_newline < 0:
        return "", ""
    close_at = stripped.find("\n```", first_newline + 1)
    if close_at < 0:
        return "", ""
    body = stripped[first_newline + 1 : close_at]
    remainder = stripped[close_at + len("\n```") :].lstrip("\n")
    return body, remainder.lstrip()


def _first_line(text: str) -> tuple[str, str]:
    if "\n" not in text:
        return text, ""
    line, rest = text.split("\n", 1)
    return line.rstrip(), rest


def _valid_header(line: str) -> bool:
    match = _HEADER_RE.fullmatch(line.strip())
    if not match:
        return False
    header = match.group("header")
    return (
        " | Pora: " in header
        and " | TRYB " in header
        and re.search(r"\| TRYB \d+: [^\]]+\]$", header) is not None
    )


def _validate_monologues(text: str) -> list[OutputContractIssue]:
    """Validate explicit NPC-monologue display blocks when they are present."""

    issues: list[OutputContractIssue] = []
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if not _MONOLOGUE_TITLE_RE.fullmatch(line.strip()):
            continue

        title_line = index + 1
        before = index - 1
        while before >= 0 and not lines[before].strip():
            before -= 1
        after = index + 1
        while after < len(lines) and not lines[after].strip():
            after += 1

        if before < 0 or lines[before].strip() != "---":
            issues.append(
                _issue(
                    "monologue.open_separator",
                    f"Monologue title on line {title_line} must be preceded by '---'.",
                )
            )

        close = after
        has_italic_body = False
        while close < len(lines) and lines[close].strip() != "---":
            stripped = lines[close].strip()
            if stripped:
                if stripped.startswith("*") and stripped.endswith("*") and not stripped.startswith("**"):
                    has_italic_body = True
            close += 1

        if close >= len(lines):
            issues.append(
                _issue(
                    "monologue.close_separator",
                    f"Monologue title on line {title_line} must be closed by '---'.",
                )
            )
        if not has_italic_body:
            issues.append(
                _issue(
                    "monologue.italic_body",
                    f"Monologue title on line {title_line} requires an italicized body.",
                )
            )
    return issues


def validate_output(
    text: str,
    *,
    require_report: bool = True,
    require_header: bool = True,
    require_footer: bool = True,
    check_debug_leaks: bool = True,
    check_monologues: bool = True,
) -> OutputContractResult:
    """Validate the RPG player-visible output contract.

    Normal narrative turns use the strict order::

        Raport -> header -> narrative -> footer -> [>_]

    For pure meta/OOG/bootstrap responses callers may disable the report/header/footer
    requirements explicitly. A report is a protocol summary, never chain-of-thought.
    """

    if not isinstance(text, str):
        raise TypeError("text must be a string")

    issues: list[OutputContractIssue] = []
    report, remainder = _split_report(text)

    if require_report:
        if report is None:
            issues.append(_issue("report.missing", "Narrative output must start with ```Raport."))
        elif report == "" and not text.lstrip().startswith("```Raport\n\n```"):
            issues.append(_issue("report.unclosed", "Raport code fence is missing its closing fence."))

    if report is not None:
        normalized = report.rstrip()
        if "AGENCY TEST: PASS" not in normalized:
            issues.append(_issue("report.agency_pass", "Raport must contain AGENCY TEST: PASS."))
        if "LEAK TEST: PASS" not in normalized:
            issues.append(_issue("report.leak_pass", "Raport must contain LEAK TEST: PASS."))
        tail = [line.strip() for line in normalized.splitlines() if line.strip()]
        if len(tail) < 2 or tail[-2:] != ["AGENCY TEST: PASS", "LEAK TEST: PASS"]:
            issues.append(
                _issue(
                    "report.pass_order",
                    "Raport must end with AGENCY TEST: PASS followed by LEAK TEST: PASS.",
                )
            )

    header_line, narrative_and_footer = _first_line(remainder)
    if require_header:
        if not header_line:
            issues.append(_issue("header.missing", "Narrative output requires a scene header."))
        elif not _valid_header(header_line):
            issues.append(
                _issue(
                    "header.invalid",
                    "Header must be inline-code [Dzień ... | Pora: ... | ... | TRYB N: NAZWA].",
                )
            )

    nonempty_lines = [line.strip() for line in text.rstrip().splitlines() if line.strip()]
    if require_footer:
        if not nonempty_lines or nonempty_lines[-1] != "[>_]":
            issues.append(_issue("footer.sentinel", "Player-visible RPG output must end with [>_]."))

    if check_debug_leaks:
        for code, pattern in _DEBUG_PATTERNS:
            if pattern.search(text):
                issues.append(
                    _issue(
                        code,
                        "Internal persistence/debug detail leaked into player-visible output.",
                        severity="warning",
                    )
                )

    if check_monologues:
        issues.extend(_validate_monologues(narrative_and_footer))

    return OutputContractResult(tuple(issues))


def assert_valid_output(text: str, **kwargs: bool) -> None:
    """Raise ``ValueError`` with deterministic issue codes when validation fails."""

    result = validate_output(text, **kwargs)
    if result.errors:
        codes = ", ".join(issue.code for issue in result.errors)
        raise ValueError(f"RPG output contract failed: {codes}")
