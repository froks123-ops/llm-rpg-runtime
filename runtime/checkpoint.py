"""Deterministic checkpoint manifests and integrity verification."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from typing import Any, Mapping


@dataclass(frozen=True)
class CheckpointVerification:
    ok: bool
    mismatches: tuple[str, ...]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def sha256_value(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def build_checkpoint_manifest(
    *,
    checkpoint_id: str,
    campaign_id: str,
    session: int,
    scene_id: str,
    documents: Mapping[str, Any],
    created_at: str | None = None,
) -> dict[str, Any]:
    file_records = {
        name: {
            "sha256": sha256_value(value),
            "bytes": len(canonical_json_bytes(value)),
        }
        for name, value in sorted(documents.items())
    }
    root_material = {name: record["sha256"] for name, record in file_records.items()}
    return {
        "schema_version": 1,
        "checkpoint_id": checkpoint_id,
        "campaign_id": campaign_id,
        "created_at": created_at or utc_now(),
        "session": session,
        "scene_id": scene_id,
        "files": file_records,
        "root_sha256": sha256_value(root_material),
    }


def verify_checkpoint(
    manifest: Mapping[str, Any],
    documents: Mapping[str, Any],
) -> CheckpointVerification:
    mismatches: list[str] = []
    expected_files = manifest.get("files", {})
    for name, record in expected_files.items():
        if name not in documents:
            mismatches.append(f"missing:{name}")
            continue
        actual = sha256_value(documents[name])
        if actual != record.get("sha256"):
            mismatches.append(f"hash:{name}")
    for name in documents:
        if name not in expected_files:
            mismatches.append(f"unexpected:{name}")
    root_material = {
        name: record.get("sha256")
        for name, record in sorted(expected_files.items())
    }
    if sha256_value(root_material) != manifest.get("root_sha256"):
        mismatches.append("manifest-root")
    return CheckpointVerification(not mismatches, tuple(sorted(mismatches)))
