from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Change:
    op: str
    path: str
    before: Any = None
    after: Any = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "op": self.op,
            "path": self.path,
            "before": self.before,
            "after": self.after,
        }


def _path(parent: str, key: str) -> str:
    escaped = key.replace("~", "~0").replace("/", "~1")
    return f"{parent}/{escaped}" if parent != "$" else f"$/{escaped}"


def diff(before: Any, after: Any, path: str = "$") -> list[Change]:
    if type(before) is not type(after):
        return [Change("replace", path, before, after)]
    if isinstance(before, dict):
        out: list[Change] = []
        before_keys, after_keys = set(before), set(after)
        for key in sorted(before_keys - after_keys):
            out.append(Change("remove", _path(path, str(key)), before[key], None))
        for key in sorted(after_keys - before_keys):
            out.append(Change("add", _path(path, str(key)), None, after[key]))
        for key in sorted(before_keys & after_keys):
            out.extend(diff(before[key], after[key], _path(path, str(key))))
        return out
    if isinstance(before, list):
        if before == after:
            return []
        # Audit-friendly set-like semantics when equality can identify additions/removals.
        out: list[Change] = []
        for item in before:
            if item not in after:
                out.append(Change("remove-item", path, item, None))
        for item in after:
            if item not in before:
                out.append(Change("add-item", path, None, item))
        if not out:
            out.append(Change("replace", path, before, after))
        return out
    return [] if before == after else [Change("replace", path, before, after)]
