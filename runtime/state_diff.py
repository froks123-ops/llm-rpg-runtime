from __future__ import annotations
from dataclasses import dataclass
from typing import Any

@dataclass(frozen=True)
class Change:
    op: str
    path: str
    before: Any = None
    after: Any = None


def diff(before: Any, after: Any, path: str = '$') -> list[Change]:
    if type(before) is not type(after):
        return [Change('replace', path, before, after)]
    if isinstance(before, dict):
        out: list[Change] = []
        bkeys, akeys = set(before), set(after)
        for key in sorted(bkeys - akeys):
            out.append(Change('remove', f'{path}.{key}', before[key], None))
        for key in sorted(akeys - bkeys):
            out.append(Change('add', f'{path}.{key}', None, after[key]))
        for key in sorted(bkeys & akeys):
            out.extend(diff(before[key], after[key], f'{path}.{key}'))
        return out
    if isinstance(before, list):
        if before == after:
            return []
        # Stable, audit-friendly list semantics: additions/removals when possible.
        out: list[Change] = []
        for item in before:
            if item not in after:
                out.append(Change('remove-item', path, item, None))
        for item in after:
            if item not in before:
                out.append(Change('add-item', path, None, item))
        if not out:
            out.append(Change('replace', path, before, after))
        return out
    return [] if before == after else [Change('replace', path, before, after)]
