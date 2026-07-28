"""FuzzForge: runner — executes the generated fuzzer and manages iteration."""

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


def run_gradle(fuzzer_dir: str, task: str = "build", timeout: int = 300) -> dict[str, Any]:
    """Run a gradle task in the generated fuzzer project.

    Returns dict with stdout, stderr, return_code, success.
    """
    print(f"  [FuzzForge] Running gradle {task} in {fuzzer_dir}...")
    start = time.time()

    proc = subprocess.run(
        ["./gradlew", task, "--no-daemon", "-q"],
        cwd=fuzzer_dir,
        capture_output=True,
        text=True,
        timeout=timeout,
    )

    elapsed = time.time() - start
    success = proc.returncode == 0

    return {
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "return_code": proc.returncode,
        "success": success,
        "elapsed_seconds": round(elapsed, 1),
    }


def run_fuzzer(fuzzer_dir: str, args: str = "run -n 10", timeout: int = 120) -> dict[str, Any]:
    """Run the generated fuzzer CLI.

    Example args: "run -n 100", "generate -n 5".
    """
    print(f"  [FuzzForge] Running fuzzer: {args}")
    start = time.time()

    proc = subprocess.run(
        ["./gradlew", ":run", "--args", f'"{args}"', "--no-daemon", "-q"],
        cwd=fuzzer_dir,
        capture_output=True,
        text=True,
        timeout=timeout,
    )

    elapsed = time.time() - start
    success = proc.returncode == 0

    return {
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "return_code": proc.returncode,
        "success": success,
        "elapsed_seconds": round(elapsed, 1),
    }


def diagnose_failure(build_result: dict[str, Any]) -> list[str]:
    """Analyze build failure output and return actionable diagnostics."""
    issues = []
    stderr = build_result.get("stderr", "")
    stdout = build_result.get("stdout", "")

    if "Unresolved reference" in stderr:
        matches = []
        lines = stderr.split("\n")
        for line in lines:
            if "Unresolved reference" in line:
                matches.append(line.strip())
        issues.append(f"Unresolved references found: {matches[:3]}")

    if "Syntax error" in stderr:
        matches = []
        lines = stderr.split("\n")
        for line in lines:
            if "Syntax error" in line:
                matches.append(line.strip()[:100])
        issues.append(f"Syntax errors: {matches[:3]}")

    if "An interface cannot extend a class" in stderr:
        issues.append("An interface cannot extend a class — root element missing 'kind = ImplementationKind.Interface' or misconfigured")

    if "This type has a constructor" in stderr:
        issues.append("Abstract class used as interface — check element hierarchy for missing 'interface_kind'")

    if "Cycle in supertypes" in stderr:
        issues.append("Cycle in supertypes — self-referencing element detected")

    if "cannot be overridden" in stderr:
        issues.append("Final method override — check root element is interface not abstract class")

    if "Type mismatch" in stderr:
        issues.append("Type mismatch errors — check enum references and field types in TreeBuilder")

    if "None of the following functions" in stderr:
        issues.append("Function signature mismatch — check parent() calls and field() signatures")

    if "is not a valid implementation" in stderr:
        issues.append("Implementation kind mismatch — check Interface vs AbstractClass declarations")

    if "Circular dependency" in stderr:
        issues.append("Circular dependency in parent references — check element hierarchy")

    if "package" in stderr and "does not exist" in stderr:
        issues.append("Package resolution error — check package declarations in generated files")

    if not issues:
        issues.append("Unknown build error. Check the full stderr output.")

    return issues


def suggest_fix(issues: list[str], design: dict[str, Any]) -> list[str]:
    """Generate LLM prompt for fixing the generated project."""
    prompt_parts = [
        "The following issues were found in the generated FuzzForge project:",
        "",
    ]
    for issue in issues:
        prompt_parts.append(f"- {issue}")

    prompt_parts.extend([
        "",
        "Project IR design:",
        json.dumps(design, indent=2),
        "",
        "Please suggest fixes for the generated Kotlin source files.",
    ])

    return prompt_parts


def run_iteration_cycle(
    fuzzer_dir: str,
    design: dict[str, Any],
    max_attempts: int = 3,
) -> dict[str, Any]:
    """Run a build-fix cycle: build, diagnose, suggest fix, and retry.

    Returns the final build result.
    """
    for attempt in range(1, max_attempts + 1):
        print(f"\n[FuzzForge] Build attempt {attempt}/{max_attempts}")

        result = run_gradle(fuzzer_dir, "compileKotlin", timeout=300)

        if result["success"]:
            print(f"  [FuzzForge] Build succeeded on attempt {attempt}!")
            return result

        print(f"  [FuzzForge] Build failed (exit code {result['return_code']})")
        issues = diagnose_failure(result)

        print(f"  [FuzzForge] Diagnosed {len(issues)} issue(s):")
        for issue in issues:
            print(f"    - {issue}")

        if attempt < max_attempts:
            print(f"  [FuzzForge] Generating fix suggestions...")
            fix_prompt = suggest_fix(issues, design)
            print(f"  [FuzzForge] Fix prompt ready. Apply fixes manually or via LLM.")
            # In auto mode, we'd call the LLM here and apply patches
            # For now, print the fix instructions
            print("\n".join(fix_prompt[-10:]))

    print(f"\n[FuzzForge] Build failed after {max_attempts} attempts.")
    return result


def run_post_generation_tests(fuzzer_dir: str) -> dict[str, Any]:
    """Run the generated project's tests to verify correctness."""
    print("[FuzzForge] Running post-generation tests...")
    result = run_gradle(fuzzer_dir, "test", timeout=300)

    if result["success"]:
        print(f"  [FuzzForge] All tests passed!")
    else:
        print(f"  [FuzzForge] Some tests failed (exit code {result['return_code']})")

    return result