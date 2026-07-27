# FuzzForge Architecture

## Inspiration from WhiteFox

WhiteFox ([Liu et al. 2024](https://arxiv.org/abs/2406.09264)) is a white-box compiler fuzzing agent.
Its agent architecture uses three phases:

1. **Planning** — LLM analyzes source code, designs test strategy
2. **Generation** — LLM generates test programs targeting specific code paths
3. **Feedback** — execution results feed back to refine the next iteration

We adapt this for **black-box fuzzer code generation**:

| Aspect | WhiteFox | FuzzForge |
|--------|----------|-----------|
| Target knowledge | Source code analysis | API surface / docs |
| Output | Test programs (inputs) | Fuzzer framework (code) |
| Mode | White-box | Black-box |
| Loop trigger | Coverage feedback | Compilation errors |
| Knowledge source | Code paths | IR design patterns |

## FuzzForge Agent Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     FuzzForge Agent (Orchestrator)              │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Phase 1: Target Analysis (scanner)                             │
│  ┌─────────────────────────────────────────────────────┐       │
│  │  - Scan target API/compiler surface                  │       │
│  │  - Identify op kinds, type system, constraints       │       │
│  │  - Build "domain vocabulary" for IR design           │       │
│  └──────────────┬──────────────────────────────────────┘       │
│                 │                                              │
│                 ▼                                              │
│  Phase 2: IR Design (ir_designer)                              │
│  ┌─────────────────────────────────────────────────────┐       │
│  │  - Define TreeBuilder elements (WhiteFox "planning") │       │
│  │  - Design op/type/attr enums                        │       │
│  │  - Design GeneratorConfig                           │       │
│  │  - Output: IR design JSON                           │       │
│  └──────────────┬──────────────────────────────────────┘       │
│                 │                                              │
│                 ▼                                              │
│  Phase 3: Code Generation (codegen)                             │
│  ┌─────────────────────────────────────────────────────┐       │
│  │  - Generate Kotlin project scaffold                 │       │
│  │  - Generate TreeBuilder.kt from IR design           │       │
│  │  - Generate enums, Generator, Translator, Runner    │       │
│  │  - Generate Gradle build files                      │       │
│  └──────────────┬──────────────────────────────────────┘       │
│                 │                                              │
│                 ▼                                              │
│  Phase 4: Build & Fix (healer)                                 │
│  ┌─────────────────────────────────────────────────────┐       │
│  │  Build Failed? ───► LLM reads errors, outputs patches       │
│  │  │                                                     │       │
│  │  └──► Iterate until build succeeds or max_attempts     │       │
│  └─────────────────────────────────────────────────────┘       │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## Key Design Principles

### 1. Black-box IR Design

Unlike WhiteFox which reads source code, FuzzForge designs IR from:
- Target description (user-provided)
- Embedded knowledge base (proven patterns from real fuzzers)
- Template presets (computation_graph / class_declaration)

### 2. Code Generation, Not Test Generation

FuzzForge generates a **fuzzer framework** (Kotlin project), not test programs.
The generated fuzzer will later generate test programs at runtime.

### 3. Compilation Feedback Loop

The healer loop mirrors WhiteFox's execution feedback:
- WhiteFox: test program crash → refine test
- FuzzForge: generated code doesn't compile → LLM patches the code

### 4. Agent Capabilities

The agent (LLM) is responsible for:
- **IR Design**: Proposing element hierarchies, types, ops
- **Code Fixing**: Reading build errors and outputting precise patches
- **Knowledge Application**: Using embedded patterns to avoid common mistakes

### 5. Extensibility

New IR modes can be added via:
- New knowledge entries in `knowledge.py`
- New templates in `templates/`
- New LLM provider for the fix loop

## Component Responsibilities

| Component | Role | WhiteFox Analog |
|-----------|------|-----------------|
| `scanner.py` | Target analysis | Source code analysis |
| `ir_designer.py` | IR planning | Test strategy design |
| `codegen.py` | Code generation | Test program generation |
| `healer.py` | Build-fix loop | Execution feedback loop |
| `knowledge.py` | Pattern knowledge | Compiler IR knowledge |
| `forge.py` | Orchestrator | Agent controller |