"""FuzzForge: scaffold module — creates the Kotlin project directory structure."""

import os
from pathlib import Path


def create_project_scaffold(output_dir: str, project_name: str) -> dict:
    """Create the full Kotlin project directory structure.

    Returns a dict of all created directories (relative to output_dir).
    """
    base = Path(output_dir)
    dirs = {
        "output": base,
        "tree_src": base / "tree" / "src" / "main" / "kotlin" / "com" / "fuzzforge" / "ir",
        "tree_gen": base / "tree" / "gen" / "com" / "fuzzforge" / "ir",
        "tree_generator": base / "tree" / "tree-generator" / "src" / "main" / "kotlin" / "com" / "fuzzforge" / "tree" / "generator",
        "tree_generator_model": base / "tree" / "tree-generator" / "src" / "main" / "kotlin" / "com" / "fuzzforge" / "tree" / "generator" / "model",
        "tree_generator_printer": base / "tree" / "tree-generator" / "src" / "main" / "kotlin" / "com" / "fuzzforge" / "tree" / "generator" / "printer",
        "src_main": base / "src" / "main" / "kotlin" / "com" / "fuzzforge",
        "src_generator": base / "src" / "main" / "kotlin" / "com" / "fuzzforge" / "generator",
        "src_translator": base / "src" / "main" / "kotlin" / "com" / "fuzzforge" / "translator",
        "src_runner": base / "src" / "main" / "kotlin" / "com" / "fuzzforge" / "runner",
        "src_reducer": base / "src" / "main" / "kotlin" / "com" / "fuzzforge" / "reducer",
        "src_config": base / "src" / "main" / "kotlin" / "com" / "fuzzforge" / "config",
        "src_cli": base / "src" / "main" / "kotlin" / "com" / "fuzzforge" / "cli",
        "src_pattern": base / "src" / "main" / "kotlin" / "com" / "fuzzforge" / "pattern",
        "resources": base / "src" / "main" / "resources",
        "test_kotlin": base / "src" / "test" / "kotlin" / "com" / "fuzzforge",
        "configs": base / "configs",
        "libs": base / "libs",
    }

    for d in dirs.values():
        d.mkdir(parents=True, exist_ok=True)

    return {k: str(v) for k, v in dirs.items()}