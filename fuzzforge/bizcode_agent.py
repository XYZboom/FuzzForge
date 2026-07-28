"""
FuzzForge: BizCode Agent — generates business code via LLM.

This agent does NOT hardcode Kotlin templates. Instead, it:
1. Reads the IR design and knowledge base
2. Calls the LLM to generate each business code file
3. The LLM decides what code to write based on the IR structure

The knowledge base (knowledge.py) contains the design patterns.
The IR design (from llm_provider.py) describes the element hierarchy.
"""

import json
import os
import subprocess
from pathlib import Path
from typing import Any


def _call_llm(prompt: str) -> str:
    """Call the LLM (GLM-5.2) to generate code."""
    api_key = None
    base_url = "https://api.sfkey.cn/v1"
    model = "glm-5.2"

    # Read API key from Hermes config
    try:
        import yaml
        with open(os.path.expanduser("~/.hermes/config.yaml")) as f:
            cfg = yaml.safe_load(f)
        for prov in cfg.get("custom_providers", []):
            if prov.get("name") == "sf":
                api_key = prov.get("api_key")
        if not api_key:
            api_key = cfg.get("model", {}).get("api_key")
    except Exception:
        api_key = os.environ.get("FUZZFORGE_API_KEY")

    if not api_key:
        return "// ERROR: No API key available"

    import urllib.request
    body = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": "You are a Kotlin code generator for the FuzzForge fuzzer framework. Generate ONLY valid Kotlin code. No markdown fences, no explanations. Output the raw .kt file content."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.3,
        "max_tokens": 4096,
    }).encode()

    req = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    try:
        resp = urllib.request.urlopen(req, timeout=120)
        data = json.loads(resp.read())
        return data["choices"][0]["message"]["content"]
    except Exception as e:
        return f"// ERROR: LLM call failed: {e}"


def _write(path: Path, content: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Strip markdown fences if present
    content = content.strip()
    if content.startswith("```"):
        lines = content.split("\n")
        # Remove first and last fence lines
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        content = "\n".join(lines)
    path.write_text(content + "\n")
    return str(path)


def _pn(design: dict) -> str:
    return design.get("project_name", "my-fuzzer").capitalize().replace("-", "").replace("_", "")


def _build_prompt(
    design: dict[str, Any],
    knowledge: str,
    file_name: str,
    file_description: str,
    context: str = "",
) -> str:
    """Build a prompt for the LLM to generate a single business code file."""
    base = _pn(design)
    elements = design.get("tree_builder_elements", [])
    enums = design.get("enums", {})

    element_names = [e["element_name"] for e in elements]
    enum_names = list(enums.keys())

    return f"""Generate a Kotlin source file for the FuzzForge fuzzer framework.

PROJECT: {design.get('project_name', 'fuzzer')}
IR MODE: {design.get('ir_mode', 'unknown')}
DESCRIPTION: {design.get('description', '')}

IR ELEMENTS: {', '.join(element_names)}
ENUMS: {', '.join(enum_names)}
TRANSLATOR TARGETS: {', '.join(design.get('translator_targets', ['cpp_source']))}
DIFF TEST MODES: {', '.join(design.get('diff_test_modes', ['none']))}
HAS REDUCER: {design.get('requires_reducer', False)}
HAS PATTERN DEDUP: {design.get('has_pattern_dedup', False)}

FILE TO GENERATE: {file_name}
DESCRIPTION: {file_description}

{context}

DESIGN PATTERNS:
{knowledge}

RULES:
1. All generated types use the "Uir" prefix (e.g., UirProgram, UirClassDeclaration, UirFunctionDeclaration).
2. Use the builder pattern from com.fuzzforge.ir.builder.* to construct IR instances.
3. Builders: buildProgram {{ }}, buildClassDeclaration {{ }}, buildFunctionDeclaration {{ }}, buildFundamentalType {{ }}, buildParameter {{ }}, buildParameterList {{ }}, buildTemplateParameter {{ }}, buildClassContainer {{ }}, buildFuncContainer {{ }}
4. The root package is com.fuzzforge.
5. Import types from com.fuzzforge.ir.* and builders from com.fuzzforge.ir.builder.*.
6. Use UirDefaultVisitor from com.fuzzforge.ir.visitors.* for tree traversal.
7. Output ONLY the raw Kotlin source code. No markdown, no explanations.
8. Use English for all code, comments, and identifiers."""


def generate_business_code(design: dict[str, Any], output_dir: str) -> list[str]:
    """Generate all business code files via LLM."""
    from fuzzforge.knowledge import build_knowledge_context

    mode = design.get("ir_mode", "computation_graph")
    knowledge = build_knowledge_context(mode)

    base = Path(output_dir)
    paths = []

    # 1. GeneratorConfig.kt
    fields = design.get("generator_config", {}).get("fields", [])
    field_lines = [f"    val {f['name']}: {f['type']} = {f.get('default_value', '')}," for f in fields]
    sep = "\n"
    default_config = f"data class GeneratorConfig(\n    val seed: Long = System.currentTimeMillis(),\n{sep.join(field_lines)}\n) {{\n    companion object {{\n        val default = GeneratorConfig()\n    }}\n}}"

    prompt = _build_prompt(design, knowledge, "GeneratorConfig.kt",
        "Data class for generator configuration parameters. Contains all configurable fuzzing parameters with defaults.",
        f"Use these exact fields:\n{json.dumps(fields, indent=2)}\n\nProduce a data class with package com.fuzzforge.generator.\n\nExample structure:\n{default_config}")
    paths.append(_write(
        base / "src" / "main" / "kotlin" / "com" / "fuzzforge" / "generator" / "GeneratorConfig.kt",
        _call_llm(prompt)))

    # 2. Generator.kt
    prompt = _build_prompt(design, knowledge, "Generator.kt",
        "Random program generator. Uses IR builders to construct random programs with classes, functions, parameters, types, and template parameters.",
        f"""The generator class should be named {_pn(design)}Generator.
It takes a GeneratorConfig parameter.
It uses kotlin.random.Random for random decisions.

Generate classes with:
- Random class names (C0, C1, etc.)
- Random ClassKind from ClassKind.entries
- Random number of functions (between minFunctionsPerClass and maxFunctionsPerClass)
- Random super type (based on inheritanceProbability)
- Random template parameters (based on templateProbability)

Generate functions with:
- Random function names (m0, m1, etc.)
- Random virtual/pure-virtual/const/static flags
- Random return types (fundamental types: int, float, double, char, bool, long, short)
- Random parameter lists
- The containingClassName should be set to the parent class name

Build the program with a ClassContainer containing all generated classes.

Package: com.fuzzforge.generator""")
    paths.append(_write(
        base / "src" / "main" / "kotlin" / "com" / "fuzzforge" / "generator" / "Generator.kt",
        _call_llm(prompt)))

    # 3. Translator.kt
    prompt = _build_prompt(design, knowledge, "Translator.kt",
        "Visitor-based C++ source code generator. Walks the IR tree and produces C++ code.",
        """The translator should:
1. Implement FuzzForgeTranslator<String> interface
2. Use UirDefaultVisitor<Unit, StringBuilder> to walk the IR tree
3. Generate C++ class declarations with:
   - #include <cstdint>
   - template parameters if present
   - class keyword with inheritance
   - public section with virtual destructor
4. The visitor class should be CppGenVisitor extending UirDefaultVisitor

Package: com.fuzzforge.translator""")
    paths.append(_write(
        base / "src" / "main" / "kotlin" / "com" / "fuzzforge" / "translator" / "Translator.kt",
        _call_llm(prompt)))

    # 4. Runner.kt
    prompt = _build_prompt(design, knowledge, "Runner.kt",
        "Fuzzer runner that compiles generated C++ code with g++/clang++ and collects all errors.",
        """The runner should:
1. Run a program counter to generate unique temp file names
2. Write C++ source to temp files
3. Invoke g++ with -std=c++17 -O2 -Wall -Wextra
4. Capture stdout, stderr, exit code, and duration
5. Also support clang++ for differential testing
6. Return RunResult data class with all fields
7. Support batch operations via coroutines

Package: com.fuzzforge.runner
Use java.io.File and java.lang.ProcessBuilder for compilation.""")
    paths.append(_write(
        base / "src" / "main" / "kotlin" / "com" / "fuzzforge" / "runner" / "Runner.kt",
        _call_llm(prompt)))

    # 5. RunConfig.kt
    prompt = _build_prompt(design, knowledge, "RunConfig.kt",
        "Configuration for the fuzzer runner. Output directory, log level, workers, timeout, etc.",
        "Package: com.fuzzforge.config. Simple data class with defaults.")
    paths.append(_write(
        base / "src" / "main" / "kotlin" / "com" / "fuzzforge" / "config" / "RunConfig.kt",
        _call_llm(prompt)))

    # 6. App.kt (CLI)
    prompt = _build_prompt(design, knowledge, "App.kt",
        "CLI entry point using Clikt. Subcommands: run (compile with g++), generate (just generate IR), diff (g++ vs clang++).",
        f"""The main class should be {_pn(design)}Command.
Use com.github.ajalt.clikt for CLI.
Subcommands: RunCommand, GenerateCommand, DiffCommand.
RunCommand: compiles generated programs with g++, reports errors.
GenerateCommand: just generates IR programs without compiling.
DiffCommand: compiles with both g++ and clang++, reports mismatches.

Package: com.fuzzforge.cli""")
    paths.append(_write(
        base / "src" / "main" / "kotlin" / "com" / "fuzzforge" / "cli" / "App.kt",
        _call_llm(prompt)))

    # 7. build.gradle.kts
    root_build = """plugins { id("java"); kotlin("jvm"); application; kotlin("plugin.serialization") version "2.4.0" }
group = "com.fuzzforge"; version = "1.0-SNAPSHOT"
repositories { mavenCentral() }
kotlin { jvmToolchain(17) }
dependencies {
    implementation(kotlin("stdlib"))
    implementation(project(":tree"))
    implementation("org.yaml:snakeyaml:2.0")
    implementation("com.github.ajalt.clikt:clikt-jvm:4.2.2")
    implementation("org.jetbrains.kotlinx:kotlinx-serialization-json:1.7.3")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-core:1.9.0")
    implementation("io.github.oshai:kotlin-logging-jvm:7.0.3")
    implementation("ch.qos.logback:logback-classic:1.5.18")
}
application { mainClass = "com.fuzzforge.cli.AppKt" }
sourceSets.main { kotlin.srcDir("src/main/kotlin") }
tasks.test { useJUnitPlatform() }"""
    paths.append(_write(base / "build.gradle.kts", root_build))

    # 8. ProgramReducer.kt
    prompt = _build_prompt(design, knowledge, "ProgramReducer.kt",
        "Delta Debugging Minimization (DDMin) algorithm. Takes a failing program and incrementally removes parts while keeping the failure reproducible.",
        "Package: com.fuzzforge.reducer. Include a ConsistencyChecker class.")
    paths.append(_write(
        base / "src" / "main" / "kotlin" / "com" / "fuzzforge" / "reducer" / "ProgramReducer.kt",
        _call_llm(prompt)))

    # 9. BugCollector.kt
    prompt = _build_prompt(design, knowledge, "BugCollector.kt",
        "Bug collector that deduplicates, categorizes, and saves bug reports. Uses error pattern matching for dedup.",
        "Package: com.fuzzforge.collector. Include BugReport data class and BugCategory enum.")
    paths.append(_write(
        base / "src" / "main" / "kotlin" / "com" / "fuzzforge" / "collector" / "BugCollector.kt",
        _call_llm(prompt)))

    # 10. DiffTester.kt
    prompt = _build_prompt(design, knowledge, "DiffTester.kt",
        "Differential testing: cross-compiler (g++ vs clang++) and optimize-vs-unoptimized comparisons.",
        "Package: com.fuzzforge.diff. Include DiffMode enum and DiffResult data class.")
    paths.append(_write(
        base / "src" / "main" / "kotlin" / "com" / "fuzzforge" / "diff" / "DiffTester.kt",
        _call_llm(prompt)))

    # .gitignore & README
    (base / ".gitignore").write_text(".gradle/\nbuild/\nout/\ngen/\n")
    (base / "README.md").write_text(f"# {design.get('project_name', 'fuzzer')}\n\nFuzzer generated by FuzzForge.\n")

    return paths