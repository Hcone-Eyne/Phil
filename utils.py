"""Shared utilities for the Phil project."""

import json
from pathlib import Path


def load_json(path, default=None):
    """Safely load a JSON file. Returns default if file missing or corrupt."""
    path = Path(path)
    if not path.exists():
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return default


def save_json(path, data, indent=2):
    """Save data to a JSON file, creating parent dirs if needed."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=indent, ensure_ascii=False)


def load_json_file(path, default=None):
    """Load JSON from a file path. Alias for load_json."""
    return load_json(path, default)
