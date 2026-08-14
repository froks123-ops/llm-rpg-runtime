from __future__ import annotations
import json
from pathlib import Path
from jsonschema import Draft202012Validator


def validate_file(data_path: str | Path, schema_path: str | Path) -> list[str]:
    data = json.loads(Path(data_path).read_text(encoding='utf-8'))
    schema = json.loads(Path(schema_path).read_text(encoding='utf-8'))
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(data), key=lambda e: list(e.absolute_path))
    out = []
    for err in errors:
        p = '$' + ''.join(f'[{x!r}]' if isinstance(x, str) else f'[{x}]' for x in err.absolute_path)
        out.append(f'{p}: {err.message}')
    return out
