"""Prepare auditable turn/state transactions without performing storage I/O."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .events import make_event
from .state_diff import Change, diff
from .state_validate import validate_data


@dataclass(frozen=True)
class DocumentChange:
    document: str
    change: Change


@dataclass(frozen=True)
class TransactionPlan:
    ok: bool
    validation_errors: dict[str, tuple[str, ...]]
    changes: tuple[DocumentChange, ...]
    event: dict[str, Any] | None
    expected_revisions: dict[str, str]


def prepare_transaction(
    *,
    before: Mapping[str, Any],
    after: Mapping[str, Any],
    schemas: Mapping[str, Mapping[str, Any]],
    source: Mapping[str, Any],
    summary: str,
    kind: str = "state.mutation",
    seq: int = 1,
    event_id: str | None = None,
    timestamp: str | None = None,
    expected_revisions: Mapping[str, str] | None = None,
    fact_dependencies: list[str] | None = None,
    event_dependencies: list[str] | None = None,
) -> TransactionPlan:
    validation_errors: dict[str, tuple[str, ...]] = {}
    for name, value in after.items():
        schema = schemas.get(name)
        if schema is None:
            continue
        errors = validate_data(value, schema)
        if errors:
            validation_errors[name] = tuple(errors)

    if validation_errors:
        return TransactionPlan(
            False,
            validation_errors,
            (),
            None,
            dict(expected_revisions or {}),
        )

    changes: list[DocumentChange] = []
    document_names = sorted(set(before) | set(after))
    for name in document_names:
        for change in diff(before.get(name), after.get(name), path="$"):
            changes.append(DocumentChange(name, change))

    if not changes:
        return TransactionPlan(
            True,
            {},
            (),
            None,
            dict(expected_revisions or {}),
        )

    mutation_records = [
        {
            "document": item.document,
            "op": item.change.op,
            "path": item.change.path,
            "before": item.change.before,
            "after": item.change.after,
        }
        for item in changes
    ]
    event = make_event(
        seq=seq,
        kind=kind,
        source=source,
        summary=summary,
        mutations=mutation_records,
        fact_ids=fact_dependencies,
        event_ids=event_dependencies,
        event_id=event_id,
        timestamp=timestamp,
    )
    return TransactionPlan(
        True,
        {},
        tuple(changes),
        event,
        dict(expected_revisions or {}),
    )
