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

                # Step 5: Semantic Validation Loop (small loop) — optional
                if auto_fix:
                    step += 1
                    print_header(f"Step {step}/{steps}: Semantic Validation Loop")
                    print_step(step, steps, "Generating C++ and compiling with g++...")
                    self._run_semantic_validation_loop()

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

    def _run_semantic_validation_loop(self, max_iterations: int = 2) -> dict[str, Any]:
        """Small loop: generate C++ programs -> compile with g++ -> classify errors -> fix -> repeat.

        Multi-agent: Generator Agent -> Translation Agent -> Compiler Agent -> Classifier Agent -> LLM Fix.
        """
        from fuzzforge.classifier_agent import classify_error, generate_fix_report

        if not self.output_dir or not self.design:
            print(f"  [SemanticLoop] Skipped: no project to validate")
            return {"success": False, "iterations": 0}

        print(f"  [SemanticLoop] Generating C++ programs and compiling with g++...")
        print(f"  [SemanticLoop] Max {max_iterations} iterations")

        for iteration in range(1, max_iterations + 1):
            print(f"\n  --- Semantic Iteration {iteration}/{max_iterations} ---")

            out = subprocess.run(
                ["./gradlew", ":run", "--args", "generate -n 5", "--no-daemon", "-q"],
                cwd=self.output_dir, capture_output=True, text=True, timeout=30,
            )
            compile_out = subprocess.run(
                ["./gradlew", ":run", "--args", "run -n 5", "--no-daemon", "-q"],
                cwd=self.output_dir, capture_output=True, text=True, timeout=60,
            )

            stderr = compile_out.stderr
            stdout = compile_out.stdout

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
                print(f"  [SemanticLoop] All 5/5 programs compiled successfully!")
                return {"success": True, "iterations": iteration}

            print(f"  [SemanticLoop] {success_count}/10 compiled OK — errors found")

            classified = classify_error(stderr, "")
            report = ""
            if classified:
                report = generate_fix_report(classified)
                print(f"  [Classifier Agent]")
                for line in report.split("\n"):
                    print(f"    {line}")

            # 4. Fix Agent: compact prompt with pre-fetched info
            from fuzzforge.healer import call_llm_for_fix, parse_fix_response, apply_patches
            
            tgen_src = Path(f"{self.output_dir}/src/main/kotlin/com/fuzzforge/translator/Translator.kt").read_text()[:2000] if Path(f"{self.output_dir}/src/main/kotlin/com/fuzzforge/translator/Translator.kt").exists() else ""
            ggen_src = Path(f"{self.output_dir}/src/main/kotlin/com/fuzzforge/generator/Generator.kt").read_text()[:1500] if Path(f"{self.output_dir}/src/main/kotlin/com/fuzzforge/generator/Generator.kt").exists() else ""
            
            cpp_code = ""
            cpp_files = sorted(Path(self.output_dir).glob("reports/temp/*.cpp"))
            if cpp_files:
                cpp_code = "\n".join(Path(cpp_files[0]).read_text().split("\n")[:30])

            fix_prompt = (
                f"FIX the fuzzer generator. C++ compilation errors:\n\n"
                f"{stderr[:2000]}\n\n"
                f"Generated C++:\n{cpp_code}\n\n"
                f"Translator.kt:\n{tgen_src}\n\n"
                f"Generator.kt:\n{ggen_src}\n\n"
                f"Rules: template<typename T>, not template<T>; can't inherit from int/bool/char/float; "
                f"non-void functions need return 0; no static virtual; union can't have virtual.\n"
                f"Output JSON patches. Fix Translator.kt visitor output and Generator.kt generation logic."
            )

            try:
                print(f"  [SemanticLoop] Calling GLM-5.2 for patches...")
                raw = call_llm_for_fix(fix_prompt)
                patches = parse_fix_response(raw)
                if not patches:
                    print(f"  [SemanticLoop] LLM returned no patches")
                    continue
                print(f"  [SemanticLoop] LLM returned {len(patches)} patch(es)")
                applied = apply_patches(self.output_dir, patches)
                for a in applied:
                    print(f"    {a}")
            except Exception as e:
                print(f"  [SemanticLoop] Fix failed: {e}")
                continue

        print(f"  [SemanticLoop] Exhausted after {max_iterations} iterations")
        return {"success": False, "iterations": max_iterations}

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