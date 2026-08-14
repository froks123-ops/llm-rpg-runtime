from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from jsonschema import Draft202012Validator


def _format_errors(errors: list[Any]) -> list[str]:
    out: list[str] = []
    for err in errors:
        path = "$" + "".join(
            f"[{value!r}]" if isinstance(value, str) else f"[{value}]"
            for value in err.absolute_path
        )
        out.append(f"{path}: {err.message}")
    return out


def validate_data(data: Any, schema: Mapping[str, Any]) -> list[str]:
    Draft202012Validator.check_schema(dict(schema))
    validator = Draft202012Validator(dict(schema))
    errors = sorted(
        validator.iter_errors(data),
        key=lambda error: [str(value) for value in error.absolute_path],
    )
    return _format_errors(errors)


def validate_file(data_path: str | Path, schema_path: str | Path) -> list[str]:
    data = json.loads(Path(data_path).read_text(encoding="utf-8"))
    schema = json.loads(Path(schema_path).read_text(encoding="utf-8"))
    return validate_data(data, schema)
