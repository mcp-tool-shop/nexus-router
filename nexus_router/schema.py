from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, cast

import jsonschema


def load_schema(path: str | Path) -> Dict[str, Any]:
    p = Path(path)
    return cast(Dict[str, Any], json.loads(p.read_text(encoding="utf-8")))


def validate(instance: Dict[str, Any], schema: Dict[str, Any]) -> None:
    jsonschema.validate(instance=instance, schema=schema)
