"""
FuzzForge: healer — autonomous build-fix engine.
Scans build errors, calls LLM for patches, applies fixes, retries.
"""

import json
import os
import subprocess
from pathlib import Path
from typing import Any

from fuzzforge.runner import run_gradle, diagnose_failure


def build_fix_prompt(
    project_dir: str,
    stderr: str,
    stdout: str,
    design: dict[str, Any],
    max_files: int = 12,
) -> str:
    """Build a comprehensive fix prompt with error context and relevant source files."""
    lines = []
    lines.append("The generated Kotlin fuzzer project has build errors.")
    lines.append("")
    lines.append("## Build Error (stderr)")
    lines.append(stderr[:6000])
    lines.append("")
    lines.append("## Build Output (stdout)")
    lines.append(stdout[-2000:])
    lines.append("")

    lines.append("## Relevant Source Files")
    base = Path(project_dir)

    patterns = [
        "**/cli/App.kt", "**/generator/*.kt", "**/translator/*.kt",
        "**/runner/*.kt", "**/config/*.kt", "**/build.gradle.kts",
        "**/settings.gradle.kts",
        "**/ir/OpKind.kt", "**/ir/TypeKind.kt",
        "**/ir/ClassKind.kt", "**/ir/Language.kt",
        "**/TreeBuilder.kt",
        "**/tree-gen/**/*.kt",
    ]

    seen = set()
    for pattern in patterns:
        for f in sorted(base.glob(pattern)):
            if f.name in seen:
                continue
            seen.add(f.name)
            rel = f.relative_to(base)
            content = f.read_text()
            lines.append(f"")
            lines.append(f"### FILE: {rel}")
            lines.append("```kotlin")
            lines.append(content)
            lines.append("```")
            if len(seen) >= max_files:
                break
        if len(seen) >= max_files:
            break

    lines.append("")
    lines.append("## IR Design (for reference)")
    lines.append(json.dumps(design, indent=2)[:3000])

    return "\n".join(lines)


def parse_fix_response(raw: str) -> list[dict[str, str]]:
    """Parse LLM fix response into a list of patches."""
    raw = raw.strip()
    if raw.startswith("```"):
        lines = raw.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        raw = "\n".join(lines)
    try:
        patches = json.loads(raw)
        if isinstance(patches, dict):
            for v in patches.values():
                if isinstance(v, list):
                    patches = v
                    break
        if not isinstance(patches, list):
            return []
        return patches
    except json.JSONDecodeError:
        return []


def apply_patches(project_dir: str, patches: list[dict[str, str]]) -> list[str]:
    """Apply a list of patches to the project."""
    applied = []
    base = Path(project_dir)

    for patch in patches:
        file_path = patch.get("file_path", "")
        old_str = patch.get("old_string", "")
        new_str = patch.get("new_string", "")
        if not file_path:
            continue

        full_path = base / file_path

        if old_str == "__FILE_MISSING__":
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(new_str)
            applied.append(f"CREATED {file_path}")
            continue

        if old_str == "__FILE_DELETE__":
            if full_path.exists():
                full_path.unlink()
                applied.append(f"DELETED {file_path}")
            continue

        if not full_path.exists():
            applied.append(f"SKIPPED {file_path} (not found)")
            continue

        content = full_path.read_text()
        if old_str not in content:
            applied.append(f"SKIPPED {file_path} (no match)")
            continue

        new_content = content.replace(old_str, new_str, 1)
        full_path.write_text(new_content)
        applied.append(f"PATCHED {file_path}")

    return applied


def fix_and_rebuild(
    project_dir: str,
    design: dict[str, Any],
    llm_cmd: str,
    max_iterations: int = 5,
) -> dict[str, Any]:
    """Auto-fix loop: build -> diagnose -> fix -> rebuild."""
    print(f"\n{'='*60}")
    print(f"  Auto-Fix Loop: max {max_iterations} iterations")
    print(f"{'='*60}")

    for iteration in range(1, max_iterations + 1):
        print(f"\n  --- Iteration {iteration}/{max_iterations} ---")

        result = run_gradle(project_dir, "compileKotlin", timeout=300)
        if result["success"]:
            print(f"  Build succeeded on iteration {iteration}!")
            return {"success": True, "iterations": iteration, "build_result": result}

        print(f"  Build failed (exit code {result['return_code']})")
        issues = diagnose_failure(result)
        for issue in issues:
            print(f"    - {issue}")

        prompt = build_fix_prompt(project_dir, result["stderr"], result["stdout"], design)

        try:
            proc = subprocess.run(
                llm_cmd.split() + ["--mode", "fix"],
                input=prompt,
                capture_output=True,
                text=True,
                timeout=120,
            )
            if proc.returncode != 0:
                print(f"  LLM failed: {proc.stderr[:200]}")
                continue

            patches = parse_fix_response(proc.stdout)
            if not patches:
                print(f"  LLM returned no valid patches")
                continue

            print(f"  LLM returned {len(patches)} patch(es)")
            applied = apply_patches(project_dir, patches)
            for a in applied:
                print(f"    {a}")

        except Exception as e:
            print(f"  Fix iteration failed: {e}")
            continue

    print(f"\n  Auto-fix exhausted after {max_iterations} iterations")
    return {
        "success": False,
        "iterations": max_iterations,
        "build_result": run_gradle(project_dir, "compileKotlin", timeout=300),
    }