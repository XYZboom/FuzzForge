"""FuzzForge: main orchestrator — CLI entry point and workflow management."""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from fuzzforge.ir_designer import design_ir, validate_ir_design
from fuzzforge.treegen_agent import setup_tree_infrastructure
from fuzzforge.bizcode_agent import generate_business_code
from fuzzforge.runner import run_gradle, diagnose_failure
from fuzzforge.healer import fix_and_rebuild
from fuzzforge.utils import print_header, print_step


class FuzzForge:
    def __init__(self):
        self.design: dict[str, Any] | None = None
        self.output_dir: str | None = None

    def create(
        self,
        target: str,
        output_dir: str,
        mode: str = "computation_graph",
        provider: str = "auto",
        skip_build: bool = False,
        auto_fix: bool = False,
    ) -> dict[str, Any]:
        provider = provider or "auto"
        steps = 5 if auto_fix else (3 if not skip_build else 2)
        step = 0

        # Step 1: Design IR
        step += 1
        print_header(f"Step {step}/{steps}: Design IR Structure")
        print_step(step, steps, f"Designing IR for: {target}")
        self.design = design_ir(target, provider, mode)
        errors = validate_ir_design(self.design)
        if errors:
            print(f"  WARNING: {len(errors)} validation issues")
            for e in errors:
                print(f"    - {e}")
        else:
            print(f"  IR design validated: {len(self.design.get('tree_builder_elements', []))} elements, "
                  f"{len(self.design.get('enums', {}).get('op_kind', []))} ops")

        self.output_dir = output_dir
        base = Path(output_dir)
        base.mkdir(parents=True, exist_ok=True)

        # Step 2: TreeGen Agent — set up tree infrastructure
        step += 1
        print_header(f"Step {step}/{steps}: TreeGen Agent — IR Infrastructure")
        print_step(step, steps, "Setting up tree-generator...")
        tree_ok = setup_tree_infrastructure(output_dir, self.design)
        if tree_ok:
            print(f"  [TreeGen] Infrastructure ready")
        else:
            print(f"  [TreeGen] Warning: generateTree may need tree-generator-common.jar")

        # Step 3: BizCode Agent — generate business code
        step += 1
        print_header(f"Step {step}/{steps}: BizCode Agent — Business Code")
        print_step(step, steps, "Generating business code...")
        biz_paths = generate_business_code(self.design, output_dir)
        print(f"  [BizCode] Generated {len(biz_paths)} files:")
        for p in biz_paths:
            rel = Path(p).relative_to(base)
            print(f"    - {rel}")

        # Step 4: Build (optional)
        if not skip_build:
            step += 1
            print_header(f"Step {step}/{steps}: Build Project")
            print_step(step, steps, "Running gradle compileKotlin...")
            result = run_gradle(self.output_dir, "compileKotlin")

            if result["success"]:
                print(f"  Build succeeded in {result['elapsed_seconds']}s!")

                # Step 5: C++ Validation Loop (two-phase) — optional
                if auto_fix:
                    step += 1
                    print_header(f"Step {step}/{steps}: C++ Validation (Syntax + Semantic)")
                    print_step(step, steps, "Validating generated C++ code...")
                    self._run_cpp_validation_loop()

            else:
                print(f"  Build failed in {result['elapsed_seconds']}s (exit code {result['return_code']})")

                if auto_fix:
                    print(f"  Auto-fix enabled! Starting healer loop...")
                    heal_result = fix_and_rebuild(
                        self.output_dir, self.design, max_iterations=5,
                    )
                    result = heal_result.get("build_result", result)
                else:
                    issues = diagnose_failure(result)
                    print(f"  Issues found:")
                    for issue in issues:
                        print(f"    - {issue}")
                    print(f"  !!! BUILD FAILED !!!")

            return {
                "status": "built" if result["success"] else "build_failed",
                "output_dir": self.output_dir,
                "design": self.design,
                "build_result": result,
            }

        return {"status": "generated", "output_dir": self.output_dir, "design": self.design}

    def _run_cpp_validation_loop(self, max_iterations: int = 5) -> dict[str, Any]:
        """Two-phase C++ validation: syntax first, then semantics.

        Phase 1 — Syntax: Fix Translator.kt until 100% of programs have valid C++ syntax.
        Phase 2 — Semantic: Fix Generator.kt until 100% of programs are semantically valid.
        """
        if not self.output_dir or not self.design:
            print(f"  [CppValidation] Skipped: no project to validate")
            return {"success": False}

        output_dir = self.output_dir

        # Phase 1: Syntax Validation
        print(f"\n{'='*60}")
        print(f"  Phase 1: Syntax Validation")
        print(f"  Fixing Translator.kt for valid C++ syntax")
        print(f"{'='*60}")

        syntax_ok = self._run_validation_phase(
            phase_name="Syntax",
            max_iterations=max_iterations,
            file_to_fix="Translator.kt",
            fix_instructions=(
                "Fix the Translator.kt C++ output. Syntax errors mean the generated C++ text is malformed.\n"
                "Common fixes: use 'template<typename T>' not 'template<T>', "
                "fix type references, add missing semicolons, fix parenthesization.\n"
                "The Translator.kt uses UirDefaultVisitor to generate C++ text.\n"
                "Trace: error -> generated C++ line -> Translator.kt code snippet -> fix."
            ),
        )
        if not syntax_ok:
            print(f"  [CppValidation] Syntax validation failed")
            return {"success": False, "phase": "syntax"}

        # Phase 2: Semantic Validation
        print(f"\n{'='*60}")
        print(f"  Phase 2: Semantic Validation")
        print(f"  Fixing Generator.kt for valid C++ semantics")
        print(f"{'='*60}")

        semantic_ok = self._run_validation_phase(
            phase_name="Semantic",
            max_iterations=max_iterations,
            file_to_fix="Generator.kt",
            fix_instructions=(
                "Fix the Generator.kt IR construction. Semantic errors mean the C++ text is syntactically valid "
                "but violates C++ rules.\n"
                "Common fixes: ensure isStatic and isVirtual are mutually exclusive (no 'static virtual'), "
                "ensure isStatic and isConst are mutually exclusive (no 'static const'), "
                "non-void functions need a return statement, "
                "unions cannot have virtual functions.\n"
                "The Generator.kt builds IR elements via buildFunctionDeclaration { } with flags.\n"
                "Trace: error -> generated C++ construct -> Translator.kt output code -> "
                "IR fields (isStatic, isVirtual, etc.) -> Generator.kt flag assignment -> fix."
            ),
        )

        if semantic_ok:
            print(f"\n  [CppValidation] All programs compile successfully!")
            return {"success": True, "phase": "both"}
        else:
            print(f"  [CppValidation] Semantic validation failed")
            return {"success": False, "phase": "semantic"}

    def _run_validation_phase(
        self,
        phase_name: str,
        max_iterations: int,
        file_to_fix: str,
        fix_instructions: str,
    ) -> bool:
        """Run a single validation phase (syntax or semantic)."""
        from fuzzforge.healer import call_llm_for_fix, parse_fix_response, apply_patches
        from fuzzforge.agent_tools import tool_skill_view

        output_dir = self.output_dir
        pdir = Path(output_dir)

        for iteration in range(1, max_iterations + 1):
            print(f"\n  --- {phase_name} Iteration {iteration}/{max_iterations} ---")

            # Generate programs
            subprocess.run(
                ["./gradlew", ":run", "--args", "generate -n 5", "--no-daemon", "-q"],
                cwd=output_dir, capture_output=True, text=True, timeout=30,
            )

            # Compile with g++
            compile_out = subprocess.run(
                ["./gradlew", ":run", "--args", "run -n 5", "--no-daemon", "-q"],
                cwd=output_dir, capture_output=True, text=True, timeout=60,
            )

            stderr = compile_out.stderr
            stdout = compile_out.stdout
            error_lines = stderr.split("\n")

            # Check if errors are syntax or semantic
            has_syntax_error = any("error:" in l and (
                "expected class-name" in l or "expected" in l or
                "template" in l or "declared" in l or
                "Syntax error" in l or "Unexpected" in l
            ) for l in error_lines if "error:" in l)
            has_semantic_only = any("error:" in l and not (
                "expected class-name" in l or "expected" in l or
                "template" in l or "declared" in l or
                "Syntax error" in l or "Unexpected" in l
            ) for l in error_lines if "error:" in l)

            if phase_name == "Syntax" and not has_syntax_error and has_semantic_only:
                print(f"  [{phase_name}] No syntax errors found — remaining errors are semantic. Passing.")
                return True

            # Check success count
            success_count = 0
            for line in stdout.split("\n"):
                if "compiled OK" in line:
                    parts = line.split()
                    for p in parts:
                        if "/" in p:
                            ok, total = p.split("/")
                            success_count = int(ok)
                            break

            if success_count == 5:
                print(f"  [{phase_name}] All 5/5 programs passed!")
                return True

            print(f"  [{phase_name}] {success_count}/5 passed — errors found")

            # Deduplicate error patterns
            error_lines = stderr.split("\n")
            error_patterns = []
            seen = set()
            for line in error_lines:
                line = line.strip()
                if "error:" in line:
                    parts = line.split("error:", 1)
                    if len(parts) > 1:
                        core = parts[1].strip()[:120]
                        if core not in seen:
                            seen.add(core)
                            error_patterns.append(core)
            summary = "\n".join(f"{i+1}. {e}" for i, e in enumerate(error_patterns[:5]))

            # Load skills
            trans_skill = tool_skill_view("fuzzforge-cpp-translator").get("content", "")[:1500]

            # Read current sources
            tgen_src = Path(f"{output_dir}/src/main/kotlin/com/fuzzforge/translator/Translator.kt").read_text() if Path(f"{output_dir}/src/main/kotlin/com/fuzzforge/translator/Translator.kt").exists() else ""
            ggen_src = Path(f"{output_dir}/src/main/kotlin/com/fuzzforge/generator/Generator.kt").read_text() if Path(f"{output_dir}/src/main/kotlin/com/fuzzforge/generator/Generator.kt").exists() else ""

            cpp_code = ""
            cpp_files = sorted(pdir.glob("reports/temp/*.cpp"))
            if cpp_files:
                cpp_code = "\n".join(Path(cpp_files[0]).read_text().split("\n")[:30])

            # Focus on the right file
            if file_to_fix == "Translator.kt":
                focus_src = tgen_src[:2500]
                other_src = ggen_src[:1000]
            else:
                focus_src = ggen_src[:2500]
                other_src = tgen_src[:1000]

            # Reasoning chain prompt
            reasoning_prompt = (
                f"Trace each C++ compilation error back to its root cause.\n\n"
                f"## Step 1: The Errors\n{summary}\n\n"
                f"## Step 2: Generated C++ Code (first 30 lines)\n{cpp_code}\n\n"
                f"## Step 3: FILE TO FIX: {file_to_fix}\n{focus_src}\n\n"
                f"## Step 4: Other file (for reference)\n{other_src}\n\n"
                f"## Step 5: C++ Rules\n{trans_skill}\n\n"
                f"## Instructions\n{fix_instructions}\n\n"
                f"## Reasoning Chain\n"
                f"For each error pattern, fill in:\n"
                f"  Error: \"{error_patterns[0] if error_patterns else '(none)'}\"\n"
                f"  -> Invalid C++ construct in output\n"
                f"  -> Which code in {file_to_fix} generates it?\n"
                f"  -> ROOT CAUSE: exact change to make\n\n"
                f"Output your analysis first, then JSON patches."
            )

            try:
                print(f"  [{phase_name}] Reasoning chain analysis...")
                analysis = call_llm_for_fix(reasoning_prompt)
                print(f"  [{phase_name}] Analysis: {analysis[:400]}")

                # Generate patches
                patch_prompt = (
                    f"Based on your analysis, output JSON patches to fix {file_to_fix}.\n\n"
                    f"YOUR ANALYSIS:\n{analysis[:2000]}\n\n"
                    f"CURRENT {file_to_fix}:\n{focus_src}\n\n"
                    f"Output ONLY a JSON array of patches. NO other text.\n"
                    f'Each patch: {{"file_path": "src/main/kotlin/com/fuzzforge/.../File.kt", '
                    f'"old_string": "exact text to replace", "new_string": "replacement text"}}'
                )

                print(f"  [{phase_name}] Generating patches...")
                raw = call_llm_for_fix(patch_prompt)
                patches = parse_fix_response(raw)
                if not patches:
                    print(f"  [{phase_name}] No patches")
                    continue
                print(f"  [{phase_name}] Applying {len(patches)} patch(es)")
                applied = apply_patches(output_dir, patches)
                for a in applied:
                    print(f"    {a}")

                # Verify Kotlin still compiles after patches
                print(f"  [{phase_name}] Verifying Kotlin compilation...")
                kt_check = subprocess.run(
                    ["./gradlew", "compileKotlin", "--no-daemon", "-q"],
                    cwd=output_dir, capture_output=True, text=True, timeout=60,
                )
                if kt_check.returncode != 0:
                    print(f"  [{phase_name}] Patch broke Kotlin compilation! Reverting...")
                    # Revert by re-applying patches in reverse
                    for p in reversed(patches):
                        old = p.get("new_string", "")
                        new = p.get("old_string", "")
                        if old and new:
                            fp = Path(f"{output_dir}/{p['file_path']}")
                            if fp.exists():
                                content = fp.read_text()
                                if old in content:
                                    fp.write_text(content.replace(old, new, 1))
                                    print(f"    REVERTED {p['file_path']}")
                    print(f"  [{phase_name}] Reverted. Skipping iteration.")
                    continue
            except Exception as e:
                print(f"  [{phase_name}] Fix failed: {e}")
                continue

        return False

    def _print_project_summary(self) -> None:
        if not self.design:
            return
        print()
        print("  Project Summary:")
        print(f"    Name:    {self.design.get('project_name', 'N/A')}")
        print(f"    Mode:    {self.design.get('ir_mode', 'N/A')}")
        print(f"    Backend: {', '.join(self.design.get('translator_targets', ['N/A']))}")
        print(f"    Diff:    {', '.join(self.design.get('diff_test_modes', ['none']))}")
        print(f"    Dedup:   {'yes' if self.design.get('has_pattern_dedup') else 'no'}")
        print(f"    Reducer: {'yes' if self.design.get('requires_reducer') else 'no'}")
        print(f"    Output:  {self.output_dir}")


def main():
    parser = argparse.ArgumentParser(description="FuzzForge — Autonomous Fuzzer Code Generation Agent")
    parser.add_argument("--version", action="version", version="FuzzForge 0.2.0")
    subparsers = parser.add_subparsers(dest="command")

    create_p = subparsers.add_parser("create")
    create_p.add_argument("--target", "-t", required=True)
    create_p.add_argument("--output", "-o", default="./generated-fuzzer")
    create_p.add_argument("--mode", "-m", default="computation_graph",
                          choices=["computation_graph", "class_declaration"])
    create_p.add_argument("--provider", "-p", default="auto")
    create_p.add_argument("--skip-build", action="store_true")
    create_p.add_argument("--auto-fix", action="store_true")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return

    forge = FuzzForge()

    if args.command == "create":
        result = forge.create(
            target=args.target, output_dir=args.output,
            mode=args.mode, provider=args.provider,
            skip_build=args.skip_build, auto_fix=args.auto_fix,
        )
        print(f"\n  Done! Status: {result['status']}")
        print(f"  Project: {result['output_dir']}")


if __name__ == "__main__":
    main()