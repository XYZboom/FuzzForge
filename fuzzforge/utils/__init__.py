"""FuzzForge: utilities — config loading, logging, helpers."""

import json
import os
import sys
from pathlib import Path
from typing import Any


def load_config(config_path: str) -> dict[str, Any]:
    """Load a FuzzForge configuration from a JSON or YAML file."""
    path = Path(config_path)
    if not path.exists():
        return {}

    text = path.read_text()

    if config_path.endswith(".json"):
        return json.loads(text)
    elif config_path.endswith(".yaml") or config_path.endswith(".yml"):
        try:
            import yaml
            return yaml.safe_load(text)
        except ImportError:
            # Fallback: parse simple YAML as JSON
            return _simple_yaml_parse(text)
    else:
        return json.loads(text)


def _simple_yaml_parse(text: str) -> dict[str, Any]:
    """Very simple YAML parser for flat configs."""
    result = {}
    for line in text.split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" in line:
            key, _, value = line.partition(":")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            # Try to parse as number or boolean
            if value.lower() == "true":
                value = True
            elif value.lower() == "false":
                value = False
            elif value.lower() == "null":
                value = None
            else:
                try:
                    if "." in value:
                        value = float(value)
                    else:
                        value = int(value)
                except ValueError:
                    pass
            result[key] = value
    return result


def get_fuzzforge_dir() -> Path:
    """Get the FuzzForge data directory."""
    return Path(os.environ.get(
        "FUZZFORGE_DIR",
        Path.home() / ".fuzzforge"
    ))


def ensure_dir(path: str) -> str:
    """Ensure a directory exists and return its path."""
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return str(p)


def print_header(text: str) -> None:
    """Print a styled section header."""
    width = 60
    print()
    print("=" * width)
    print(f"  {text}")
    print("=" * width)


def print_step(step: int, total: int, text: str) -> None:
    """Print a progress step."""
    print(f"  [{step}/{total}] {text}")