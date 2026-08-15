"""Parser for Google AI Studio chat exports.

The importer is intentionally conservative: it preserves raw text and provenance and
allows explicit inclusion/exclusion ranges. It does not infer canon from prose on its
own. Retconned branches should be excluded by index/range before semantic migration.

``systemInstruction`` is imported as historical source provenance only. It is never
runtime rule authority; current project/campaign instructions remain authoritative.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Any, Iterable, Mapping


_SCENE_HEADER_RE = re.compile(r"\[Dzień\s+[^\]]+\]", re.IGNORECASE)


@dataclass(frozen=True)
class StudioChunk:
    index: int
    role: str
    text: str
    token_count: int | None
    create_time: str | None
    finish_reason: str | None

    @property
    def source_ref(self) -> str:
        return f"ai-studio:chunk:{self.index:04d}"


@dataclass(frozen=True)
class StudioExport:
    run_settings: Mapping[str, Any]
    system_instruction: str
    chunks: tuple[StudioChunk, ...]
    pending_inputs: tuple[Mapping[str, Any], ...]


def _system_instruction_text(value: Any) -> str:
    """Normalize both legacy string and current AI Studio ``{"text": ...}`` shapes."""

    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, Mapping):
        text = value.get("text", "")
        if text is None:
            return ""
        if not isinstance(text, str):
            raise ValueError("systemInstruction.text must be a string")
        return text
    raise ValueError("systemInstruction must be a string, object, or null")


def parse_export(payload: Mapping[str, Any]) -> StudioExport:
    chunked = payload.get("chunkedPrompt", {}) or {}
    raw_chunks = chunked.get("chunks", []) if isinstance(chunked, Mapping) else []
    chunks: list[StudioChunk] = []
    for index, raw in enumerate(raw_chunks):
        if not isinstance(raw, Mapping):
            raise ValueError(f"chunk {index} is not an object")
        role = str(raw.get("role", "")).strip()
        if role not in {"user", "model"}:
            raise ValueError(f"chunk {index} has unsupported role {role!r}")
        text = raw.get("text", "")
        if not isinstance(text, str):
            raise ValueError(f"chunk {index} text is not a string")
        token_count = raw.get("tokenCount")
        chunks.append(
            StudioChunk(
                index=index,
                role=role,
                text=text,
                token_count=token_count if isinstance(token_count, int) else None,
                create_time=raw.get("createTime") if isinstance(raw.get("createTime"), str) else None,
                finish_reason=raw.get("finishReason") if isinstance(raw.get("finishReason"), str) else None,
            )
        )
    pending = chunked.get("pendingInputs", []) if isinstance(chunked, Mapping) else []
    return StudioExport(
        run_settings=payload.get("runSettings", {}) or {},
        system_instruction=_system_instruction_text(payload.get("systemInstruction")),
        chunks=tuple(chunks),
        pending_inputs=tuple(item for item in pending if isinstance(item, Mapping)),
    )


def load_export(path: str | Path) -> StudioExport:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("AI Studio export root must be an object")
    return parse_export(payload)


def select_chunks(
    export: StudioExport,
    *,
    start: int = 0,
    end_inclusive: int | None = None,
    exclude_ranges: Iterable[tuple[int, int]] = (),
) -> tuple[StudioChunk, ...]:
    end = len(export.chunks) - 1 if end_inclusive is None else end_inclusive
    exclusions = list(exclude_ranges)
    selected: list[StudioChunk] = []
    for chunk in export.chunks:
        if chunk.index < start or chunk.index > end:
            continue
        if any(lo <= chunk.index <= hi for lo, hi in exclusions):
            continue
        selected.append(chunk)
    return tuple(selected)


def scene_header(text: str) -> str | None:
    match = _SCENE_HEADER_RE.search(text)
    return match.group(0) if match else None


def chunk_index(chunks: Iterable[StudioChunk]) -> list[dict[str, Any]]:
    return [
        {
            "index": chunk.index,
            "source_ref": chunk.source_ref,
            "role": chunk.role,
            "token_count": chunk.token_count,
            "create_time": chunk.create_time,
            "finish_reason": chunk.finish_reason,
            "scene_header": scene_header(chunk.text),
        }
        for chunk in chunks
    ]


def archive_markdown(
    chunks: Iterable[StudioChunk],
    *,
    title: str = "Imported AI Studio session",
) -> str:
    lines = [f"# {title}", ""]
    for chunk in chunks:
        lines.extend(
            [
                f"## Chunk {chunk.index:04d} — {chunk.role}",
                "",
                f"- Source: `{chunk.source_ref}`",
                f"- Time: `{chunk.create_time or 'unknown'}`",
                f"- Tokens: `{chunk.token_count if chunk.token_count is not None else 'unknown'}`",
                "",
                chunk.text.rstrip(),
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def export_stats(export: StudioExport) -> dict[str, Any]:
    roles: dict[str, int] = {}
    tokens = 0
    tokenized_chunks = 0
    for chunk in export.chunks:
        roles[chunk.role] = roles.get(chunk.role, 0) + 1
        if chunk.token_count is not None:
            tokens += chunk.token_count
            tokenized_chunks += 1
    return {
        "chunks": len(export.chunks),
        "roles": roles,
        "token_count_sum": tokens,
        "tokenized_chunks": tokenized_chunks,
        "pending_inputs": len(export.pending_inputs),
    }
