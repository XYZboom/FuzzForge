"""
FuzzForge: healer — autonomous build-fix engine.
Scans build errors, calls real LLM (GLM-5.2 via SF) for patches, applies fixes, retries.
"""

import json
import os
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from fuzzforge.runner import run_gradle, diagnose_failure
from fuzzforge.tree_api import build_fix_guidelines
from fuzzforge.classifier_agent import classify_error, generate_fix_report


def _load_sf_config() -> tuple[str, str, str]:
    api_key = ""
    base_url = "https://api.sfkey.cn/v1"
    model = "glm-5.2"
    try:
        import yaml
        with open(os.path.expanduser("~/.hermes/config.yaml")) as f:
            cfg = yaml.safe_load(f)
        for prov in cfg.get("custom_providers", []):
            if prov.get("name") == "sf":
                api_key = prov.get("api_key", "")
        if not api_key:
            api_key = cfg.get("model", {}).get("api_key", "")
    except Exception:
        api_key = os.environ.get("FUZZFORGE_API_KEY", "")
    return api_key, base_url, model


SF_API_KEY, SF_BASE_URL, SF_MODEL = _load_sf_config()


def call_llm_for_fix(prompt: str) -> str:
    """Call the real LLM (GLM-5.2 via SF) to generate fix patches. Retries on 5xx."""
    if not SF_API_KEY:
        return "[]"

    data = json.dumps({
        "model": SF_MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a Kotlin compiler fixer for the FuzzForge fuzzer framework. "
                    "Your job is to analyze build errors and output patches to fix ONLY the business code.\n\n"
                    "CRITICAL RULES:\n"
                    "1. NEVER patch files under 'tree/' — they are auto-generated or boilerplate.\n"
                    "2. ONLY patch files under 'src/main/kotlin/com/fuzzforge/'.\n"
                    "3. NEVER create new files. NEVER delete files.\n"
                    "4. Each patch replaces one unique string with another. Include 3-5 lines of context.\n"
                    "5. Fix missing imports: add 'import com.fuzzforge.ir.*' or 'import com.fuzzforge.ir.builder.*'.\n"
                    "6. Available builders: buildProgram, buildClassContainer, buildFuncContainer, "
                    "buildClassDeclaration, buildFunctionDeclaration, buildFundamentalType, "
                    "buildParameter, buildParameterList, buildTemplateParameter (NOT buildFunctionContainer).\n"
                    "7. All generated types use Uir prefix: UirProgram, UirClassDeclaration, UirFunctionDeclaration, UirFundamentalType, UirFuncContainer, etc.\n"
                    "8. Only output valid JSON array, no markdown fences, no extra text.\n\n"
                    "Output format:\n"
                    "[\n"
                    '  {\n'
                    '    "file_path": "relative/path/from/project/root/Filename.kt",\n'
                    '    "old_string": "exact text to find and replace",\n'
                    '    "new_string": "replacement text"\n'
                    '  }\n'
                    "]\n"
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.1,
    }).encode()

    req = urllib.request.Request(
        f"{SF_BASE_URL}/chat/completions",
        data=data,
        headers={
            "Authorization": f"Bearer {SF_API_KEY}",
            "Content-Type": "application/json",
        },
    )

    for attempt in range(3):
        try:
            resp = urllib.request.urlopen(req, timeout=120)
            result = json.loads(resp.read())
            return result["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as e:
            if e.code >= 500 and attempt < 2:
                time.sleep(5 * (attempt + 1))
                continue
            raise RuntimeError(f"LLM call failed: {e.code} {e.reason}")
        except Exception as e:
            raise RuntimeError(f"LLM call failed: {e}")


def build_fix_prompt(
    project_dir: str,
    stderr: str,
    stdout: str,
    design: dict[str, Any],
    max_files: int = 5,
) -> str:
    """Build a compact fix prompt with error context and key business code files."""
    lines = []
    lines.append("Build errors (only fix business code, never tree/ files):")
    lines.append(stderr[:3000])
    lines.append("")

    base = Path(project_dir)

    patterns = [
        "src/main/kotlin/com/fuzzforge/cli/App.kt",
        "src/main/kotlin/com/fuzzforge/generator/*.kt",
        "src/main/kotlin/com/fuzzforge/translator/*.kt",
        "src/main/kotlin/com/fuzzforge/runner/*.kt",
        "src/main/kotlin/com/fuzzforge/config/*.kt",
    ]

    for pattern in patterns:
        for f in sorted(base.glob(pattern)):
            rel = f.relative_to(base)
            lines.append(f"--- {rel} ---")
            lines.append(f.read_text())
            if len(lines) > max_files * 30:
                break

    lines.append("")
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
        depth = 0
        last_complete = -1
        for i, ch in enumerate(raw):
            if ch == '[':
                depth += 1
            elif ch == ']':
                depth -= 1
                if depth == 0:
                    last_complete = i + 1
        if last_complete > 0:
            try:
                patches = json.loads(raw[:last_complete])
                if isinstance(patches, list):
                    return patches
            except json.JSONDecodeError:
                pass
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

        if file_path.startswith("tree/"):
            applied.append(f"REJECTED {file_path} — tree/ files are not business code")
            continue

        if old_str in ("__FILE_MISSING__", "__FILE_DELETE__"):
            applied.append(f"REJECTED {file_path} ({old_str}) — no file creation/deletion allowed")
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
    llm_cmd: str | None = None,
    max_iterations: int = 5,
) -> dict[str, Any]:
    """Auto-fix loop: build -> classify -> fix via real LLM -> rebuild.

    Multi-agent loop:
      1. Compiler Agent: build with g++, collect ALL errors
      2. Classifier Agent: classify each error as generator/compiler/semantic
      3. LLM (BizCode Agent): generate patches for generator bugs
      4. Repeat until 100% of generated programs compile
    """
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

        stderr = result.get("stderr", "")
        classified = classify_error(stderr, "")
        if not classified:
            issues = diagnose_failure(result)
            for issue in issues:
                print(f"    - {issue}")
        else:
            fix_report = generate_fix_report(classified)
            print(f"  Classifier Agent report:")
            for line in fix_report.split("\n"):
                print(f"    {line}")

        prompt = build_fix_prompt(project_dir, result["stderr"], result["stdout"], design)

        if classified:
            report = generate_fix_report(classified)
            prompt = f"ERROR CLASSIFICATION:\n{report}\n\n{prompt}"

        try:
            print(f"  Calling GLM-5.2 for fixes...")
            raw = call_llm_for_fix(prompt)
            patches = parse_fix_response(raw)
            if not patches:
                print(f"  LLM returned no valid patches")
                print(f"  Raw response: {raw[:500]}")
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