"""Campaign-level transaction preparation.

A campaign transaction performs four stages without doing storage I/O:

1. validate proposed document shapes;
2. compute an auditable mutation event;
3. append that event to the returned event log and advance manifest/HEAD pointers;
4. run cross-document semantic integrity checks.

The returned ``documents`` are the exact post-transaction documents a persistence
adapter should write with optimistic concurrency.
"""

from __future__ import annotations

from dataclasses import dataclass
import copy
from typing import Any, Mapping

from .integrity import IntegrityIssue, audit_campaign, has_errors
from .state_validate import validate_data
from .transaction import TransactionPlan, prepare_transaction


@dataclass(frozen=True)
class CampaignTransactionPlan:
    ok: bool
    transaction: TransactionPlan
    integrity_issues: tuple[IntegrityIssue, ...]
    documents: dict[str, Any]


def prepare_campaign_transaction(
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
) -> CampaignTransactionPlan:
    required = {"manifest", "head", "active_state", "npc_state", "thread_state", "facts", "event_log"}
    if not required.issubset(after):
        missing = sorted(required - set(after))
        empty = TransactionPlan(False, {}, (), None, dict(expected_revisions or {}))
        issue = IntegrityIssue(
            "error",
            "campaign_transaction_missing_documents",
            f"Campaign transaction requires: {', '.join(missing)}",
            "transaction",
        )
        return CampaignTransactionPlan(False, empty, (issue,), copy.deepcopy(dict(after)))

    transaction = prepare_transaction(
        before=before,
        after=after,
        schemas=schemas,
        source=source,
        summary=summary,
        kind=kind,
        seq=seq,
        event_id=event_id,
        timestamp=timestamp,
        expected_revisions=expected_revisions,
        fact_dependencies=fact_dependencies,
        event_dependencies=event_dependencies,
    )
    documents = copy.deepcopy(dict(after))
    if not transaction.ok:
        return CampaignTransactionPlan(False, transaction, (), documents)

    if transaction.event is not None:
        documents["event_log"] = list(documents["event_log"]) + [copy.deepcopy(transaction.event)]
        documents["manifest"] = copy.deepcopy(documents["manifest"])
        documents["manifest"]["last_event_seq"] = transaction.event["seq"]
        documents["head"] = copy.deepcopy(documents["head"])
        documents["head"]["last_canonical_event_id"] = transaction.event["id"]

    post_schema_issues: list[IntegrityIssue] = []
    for name in ("manifest", "head", "event_log"):
        schema = schemas.get(name)
        if not schema:
            continue
        for message in validate_data(documents[name], schema):
            post_schema_issues.append(
                IntegrityIssue(
                    "error",
                    "post_event_schema_validation",
                    message,
                    name,
                )
            )

    issues = post_schema_issues + audit_campaign(
        manifest=documents["manifest"],
        head=documents["head"],
        active_state=documents["active_state"],
        npc_state=documents["npc_state"],
        thread_state=documents["thread_state"],
        facts=documents["facts"],
        events=documents["event_log"],
    )
    return CampaignTransactionPlan(
        transaction.ok and not has_errors(issues),
        transaction,
        tuple(issues),
        documents,
    )
