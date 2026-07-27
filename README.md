# FuzzForge

**Autonomous Fuzzer Code Generation Agent**

FuzzForge is a meta-agent that designs and generates complete
Kotlin fuzzer projects using LLM-driven IR design. Given a target
description, it autonomously creates the full project scaffold:

1. **Design** the IR data structure via LLM (TreeBuilder, OpKinds, types)
2. **Generate** a complete Kotlin project with Generator, Translator, Runner
3. **Build** and iterate until the project compiles

## Architecture

```
FuzzForge/
├── fuzzforge/
│   ├── __init__.py          # Package init
│   ├── __main__.py          # CLI entry point
│   ├── forge.py             # Main orchestrator + CLI
│   ├── knowledge.py         # Embedded design knowledge base
│   ├── ir_designer.py       # LLM-driven IR design
│   ├── codegen.py           # Kotlin code generation engine
│   ├── runner.py            # Build/run/diagnose generated projects
│   ├── scaffold.py          # Project directory structure
│   ├── templates/           # YAML template presets
│   │   ├── computation_graph.yaml
│   │   └── class_declaration.yaml
│   └── utils/
│       └── __init__.py      # Config loading, helpers
├── pyproject.toml
├── requirements.txt
└── README.md
```

## Quick Start

```bash
# Install
pip install -e .

# Create a fuzzer for an AI compiler
fuzzforge create --target "TVM Relax compiler" --output ./tvm-fuzzer

# Create a fuzzer for a language compiler
fuzzforge create --target "Kotlin compiler" --mode class_declaration --output ./kt-fuzzer

# Create with a specific LLM provider
fuzzforge create --target "PyTorch Inductor" --provider openai --output ./pt-fuzzer

# Run the generated fuzzer
fuzzforge run --fuzzer ./tvm-fuzzer --args "run -n 100"

# Design IR only (no code generation)
fuzzforge design --target "My custom IR" --save design.json
```

## LLM Provider Configuration

FuzzForge uses an LLM to design the IR structure. Set via environment:

```bash
# Ollama (default auto-detect)
export FUZZFORGE_LLM_PROVIDER=ollama
export FUZZFORGE_LLM_MODEL=llama3.2

# OpenAI
export FUZZFORGE_LLM_PROVIDER=openai
export OPENAI_API_KEY=sk-...
export FUZZFORGE_LLM_MODEL=gpt-4o

# Custom command (accepts prompt on stdin, returns JSON on stdout)
export FUZZFORGE_LLM_PROVIDER=auto
export FUZZFORGE_LLM_CMD="llm -m my-model"
```

## Generated Project Structure

```
./tvm-fuzzer/
├── tree/
│   ├── src/                 # Hand-written enums, DSL, utils
│   ├── gen/                 # Auto-generated IR code (DO NOT EDIT)
│   └── tree-generator/      # TreeBuilder meta-model + code generator
├── src/main/kotlin/com/fuzzforge/
│   ├── generator/           # Program generator
│   ├── translator/          # Backend translators
│   ├── runner/              # Test execution framework
│   ├── reducer/             # DDMin minimizer
│   ├── config/              # Configuration classes
│   ├── pattern/             # Pattern-based dedup
│   └── cli/App.kt           # CLI entry point
├── configs/                 # YAML run configurations
├── build.gradle.kts
├── settings.gradle.kts
└── README.md
```

## IR Modes

| Mode | Description | Typical Targets |
|------|-------------|-----------------|
| `computation_graph` | DAG of operator nodes + value refs | AI compilers, tensor frameworks, dataflow systems |
| `class_declaration` | Class hierarchy + functions + types | Language compilers, type system testers |

## How It Works

1. **User provides target description** (e.g., "TVM Relax compiler")
2. **FuzzForge calls LLM** with embedded knowledge base (proven design patterns from production fuzzers)
3. **IR design is validated** (element hierarchy, parent refs, required fields)
4. **Code generator produces** complete Kotlin source files:
   - TreeBuilder.kt with element definitions
   - Enum files (OpKind, TypeKind, etc.)
   - Generator, Translator, Runner, Config, CLI
   - Gradle build files
5. **Build is attempted** with diagnostics on failure
6. **User can iterate** by fixing and re-running

## Knowledge Base

FuzzForge ships with an embedded knowledge base (`knowledge.py`) containing
distilled design patterns from production fuzzer implementations. This includes:

- IR element hierarchies for both computation graph and class declaration modes
- Type system designs (tensor types, parameterized types, nullable types)
- Operator categorizations (unary, binary, reduction, shape transform, etc.)
- Generator strategies (shape inference, available value pools, override detection)
- Translator patterns (op name mapping, dtype mapping, multi-target output)
- Differential testing modes (cross-target, optimize-vs-unoptimized, cross-language)
- Pattern-based generation-time dedup
- DDMin reduction algorithms
- Mutator techniques for IR diversity