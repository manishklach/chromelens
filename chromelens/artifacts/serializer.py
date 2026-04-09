"""Helpers for deterministic artifact serialization."""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any


def _sort_value(value: Any) -> Any:
    """Recursively sort JSON-like values for stable output."""
    if isinstance(value, dict):
        return {key: _sort_value(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        return [_sort_value(item) for item in value]
    if is_dataclass(value):
        return _sort_value(asdict(value))
    return value


def artifact_to_dict(artifact: Any) -> dict[str, Any]:
    """Convert a dataclass artifact to a deterministically ordered dict."""
    if not is_dataclass(artifact):
        raise TypeError("artifact_to_dict expects a dataclass instance")
    return _sort_value(asdict(artifact))


def write_artifact_json(artifact: Any, output_path: Path) -> Path:
    """Write an artifact as stable JSON."""
    payload = artifact_to_dict(artifact)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return output_path


def read_artifact_json(path: Path) -> dict[str, Any]:
    """Read a previously written JSON artifact."""
    return json.loads(path.read_text(encoding="utf-8"))
