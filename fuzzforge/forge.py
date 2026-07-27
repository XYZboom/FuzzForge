"""FuzzForge: main orchestrator — CLI entry point and workflow management."""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from fuzzforge.ir_designer import design_ir, validate_ir_design
from fuzzforge.codegen import generate_project
from fuzzforge.runner import run_gradle, run_fuzzer, diagnose_failure
from fuzzforge.utils import print_header, print_step


class FuzzForge:
    """Main orchestrator for the FuzzForge agent."""

    def __init__(self, provider: str = "auto"):
        self.provider = provider
        self.design: dict[str, Any] | None = None
        self.output_dir: str | None = None

    def create(
        self,
        target: str,
        output_dir: str,
        mode: str = "computation_graph",
        provider: str | None = None,
        skip_build: bool = False,
    ) -> dict[str, Any]:
        """Full workflow: design IR -> generate project -> optionally build.

        Returns a result dict with status and metadata.
        """
        provider = provider or self.provider
        steps = 3 if not skip_build else 2
        step = 0

        # Step 1: Design IR
        step += 1
        print_header(f"Step {step}/{steps}: Design IR Structure")
        print_step(step, steps, f"Designing IR for: {target}")
        self.design = design_ir(target, provider, mode)
        errors = validate_ir_design(self.design)
        if errors:
            print(f"  WARNING: {len(errors)} validation issues found")
            for e in errors:
                print(f"    - {e}")
        else:
            print(f"  IR design validated: {len(self.design.get('tree_builder_elements', []))} elements, "
                  f"{len(self.design.get('enums', {}).get('op_kind', []))} ops")

        # Step 2: Generate project
        step += 1
        print_header(f"Step {step}/{steps}: Generate Kotlin Project")
        print_step(step, steps, f"Generating project to: {output_dir}")
        self.output_dir = generate_project(self.design, output_dir)
        print(f"  Project generated at: {self.output_dir}")
        self._print_project_summary()

        # Step 3: Build (optional)
        if not skip_build:
            step += 1
            print_header(f"Step {step}/{steps}: Build Project")
            print_step(step, steps, "Running gradle compileKotlin...")
            result = run_gradle(self.output_dir, "compileKotlin")

            if result["success"]:
                print(f"  Build succeeded in {result['elapsed_seconds']}s!")
            else:
                print(f"  Build failed in {result['elapsed_seconds']}s (exit code {result['return_code']})")
                issues = diagnose_failure(result)
                print(f"  Issues found:")
                for issue in issues:
                    print(f"    - {issue}")
                print(f"  !!! BUILD FAILED — review stderr above and fix manually !!!")

            return {
                "status": "built" if result["success"] else "build_failed",
                "output_dir": self.output_dir,
                "design": self.design,
                "build_result": result,
            }

        return {
            "status": "generated",
            "output_dir": self.output_dir,
            "design": self.design,
        }

    def run(
        self,
        fuzzer_dir: str,
        args: str = "run -n 10",
    ) -> dict[str, Any]:
        """Run the generated fuzzer."""
        print_header("Run Fuzzer")
        print(f"  Fuzzer: {fuzzer_dir}")
        print(f"  Args: {args}")
        result = run_fuzzer(fuzzer_dir, args)
        if result["success"]:
            print(f"  Fuzzer ran successfully in {result['elapsed_seconds']}s")
        else:
            print(f"  Fuzzer run failed (exit code {result['return_code']})")
        return result

    def _print_project_summary(self) -> None:
        """Print a summary of the generated project."""
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

    def save_design(self, path: str | None = None) -> str:
        """Save the IR design to a JSON file for later reuse."""
        if not self.design:
            raise RuntimeError("No design to save. Run create() first.")
        path = path or "fuzzforge-design.json"
        with open(path, "w") as f:
            json.dump(self.design, f, indent=2)
        print(f"  Design saved to: {path}")
        return path

    def load_design(self, path: str) -> dict[str, Any]:
        """Load a previously saved IR design."""
        with open(path) as f:
            self.design = json.load(f)
        print(f"  Design loaded from: {path}")
        errors = validate_ir_design(self.design)
        if errors:
            print(f"  WARNING: {len(errors)} validation issues")
        return self.design


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="FuzzForge — Autonomous Fuzzer Code Generation Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  fuzzforge create --target "TVM Relax compiler" --output ./tvm-fuzzer
  fuzzforge create --target "PyTorch Inductor" --provider openai
  fuzzforge create --target "ONNX Runtime" --mode computation_graph --skip-build
  fuzzforge create --target "Kotlin compiler" --mode class_declaration
  fuzzforge run --fuzzer ./my-fuzzer --args "run -n 100"
  fuzzforge design --target "My custom IR" --save design.json
        """,
    )
    parser.add_argument("--version", action="version", version="FuzzForge 0.1.0")
    subparsers = parser.add_subparsers(dest="command", help="Command")

    # create
    create_parser = subparsers.add_parser("create", help="Create a new fuzzer project")
    create_parser.add_argument("--target", "-t", required=True, help="Target description (e.g. 'TVM Relax compiler')")
    create_parser.add_argument("--output", "-o", default="./generated-fuzzer", help="Output directory")
    create_parser.add_argument("--mode", "-m", default="computation_graph",
                              choices=["computation_graph", "class_declaration"],
                              help="IR mode: computation_graph (AI compilers) or class_declaration (language compilers)")
    create_parser.add_argument("--provider", "-p", default="auto", help="LLM provider (auto, ollama, openai)")
    create_parser.add_argument("--skip-build", action="store_true", help="Skip gradle build step")

    # run
    run_parser = subparsers.add_parser("run", help="Run a generated fuzzer")
    run_parser.add_argument("--fuzzer", "-f", required=True, help="Path to generated fuzzer project")
    run_parser.add_argument("--args", "-a", default="run -n 10", help="Arguments to pass to fuzzer CLI")

    # design
    design_parser = subparsers.add_parser("design", help="Design IR only (no project generation)")
    design_parser.add_argument("--target", "-t", required=True, help="Target description")
    design_parser.add_argument("--mode", "-m", default="computation_graph",
                              choices=["computation_graph", "class_declaration"],
                              help="IR mode to use for the design")
    design_parser.add_argument("--save", "-s", help="Save design to JSON file")
    design_parser.add_argument("--provider", default="auto", help="LLM provider")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    forge = FuzzForge(provider=getattr(args, "provider", "auto"))

    if args.command == "create":
        result = forge.create(
            target=args.target,
            output_dir=args.output,
            mode=args.mode,
            provider=args.provider,
            skip_build=args.skip_build,
        )
        print(f"\n  Done! Status: {result['status']}")
        print(f"  Project: {result['output_dir']}")

    elif args.command == "run":
        result = forge.run(
            fuzzer_dir=args.fuzzer,
            args=args.args,
        )
        if result["stdout"]:
            print(result["stdout"][:2000])

    elif args.command == "design":
        print_header("Design IR Only")
        design = design_ir(args.target, args.provider, args.mode)
        print(json.dumps(design, indent=2))
        if args.save:
            with open(args.save, "w") as f:
                json.dump(design, f, indent=2)
            print(f"  Design saved to: {args.save}")


if __name__ == "__main__":
    main()