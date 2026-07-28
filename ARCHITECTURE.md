# FuzzForge Multi-Agent Architecture

## Three Loops

### Loop 1: Tool Loop (Global)
FuzzForge development cycle: write FuzzForge code → generate fuzzer project → compile → fix FuzzForge → repeat.

### Loop 2: Compile Loop (Healer)
Fix Kotlin compilation errors: build → classify errors → LLM patches → rebuild.

### Loop 3: Semantic Loop (Small Loop)
Fix C++ semantic validity: generate C++ programs → compile with g++ → classify errors → trace root cause → fix → repeat.

## Agents

### 1. Generator Agent
- **Role**: Generates IR programs (classes, functions, types) via Kotlin IR builders
- **Knowledge**: `fuzzforge-cpp-generator` skill — builder API, randomization, class/function generation
- **Input**: IR design JSON, GeneratorConfig
- **Output**: UirProgram IR tree

### 2. Translation Agent
- **Role**: Translates IR to C++ source code using UirDefaultVisitor
- **Knowledge**: `fuzzforge-cpp-translator` skill — visitor patterns, C++ syntax rules, type dispatch
- **Key Insight**: `acceptChildren()` is empty in impl classes — directly access child fields
- **Input**: UirProgram IR tree
- **Output**: C++ source code string

### 3. Compiler Agent
- **Role**: Invokes g++/clang++, collects ALL errors and warnings
- **Knowledge**: Compiler flags, error output parsing
- **Input**: C++ source code
- **Output**: Compilation result (exit code, stdout, stderr)

### 4. Classifier Agent
- **Role**: Classifies each error as generator_bug, compiler_bug, semantic_issue, or warning
- **Knowledge**: `fuzzforge-classifier` skill — C++ error patterns, known semantic issues
- **Input**: Compilation error, generated code
- **Output**: Error classification with fix suggestions

### 5. Fix Agent (Structured Reasoning Chain)
- **Role**: Traces C++ errors back to root cause in Kotlin generator code
- **Method**: Two-phase reasoning:
  1. Phase 1: Trace error → generated C++ → Translator.kt → Generator.kt → root cause
  2. Phase 2: Generate JSON patches based on analysis
- **Knowledge**: Loads `fuzzforge-cpp-translator` and `fuzzforge-cpp-generator` skills dynamically
- **Key Insight**: The reasoning chain is explicit — the LLM is guided through each step:
  ```
  Error: "static virtual" not allowed
  → Which C++ construct? "static virtual short m1()" in output
  → Which Translator code? outputs $static_$virtual
  → What IR data? isStatic=true AND isVirtual=true
  → How does Generator set this? independently sets both flags
  → ROOT CAUSE: Generator.kt must ensure isStatic and isVirtual are mutually exclusive
  ```

## Knowledge Sharing

All agents access a layered skill tree:

```
fuzzforge-knowledge-index (root index)
  ├── fuzzforge-ir-design        (IR hierarchy patterns)
  ├── fuzzforge-cpp-generator     (builder API, generation patterns)
  ├── fuzzforge-cpp-translator    (visitor, C++ syntax rules)
  └── fuzzforge-classifier       (error classification patterns)
```

Agents load skills on demand via `tool_skill_view()`. The Python framework pre-fetches
relevant skill content before calling the LLM, so the LLM doesn't need tool-use capability.

## How the Semantic Loop Works

```
for each iteration:
  1. Generate 5 C++ programs (Generator + Translator)
  2. Compile with g++, collect ALL errors
  3. Classifier: deduplicate and categorize errors
  4. Fix Agent:
     a. Load C++ translator skill (C++ syntax rules)
     b. Load C++ generator skill (builder API docs)
     c. Read current Translator.kt and Generator.kt
     d. Read first failing C++ program
     e. Structured reasoning: trace error -> output -> translator -> generator -> root cause
     f. Generate JSON patches
     g. Apply patches
  5. If 5/5 compile OK -> done
  6. Otherwise -> next iteration
```

## Key Principles

1. ALL errors are collected. No errors are ignored.
2. Every error is either: generator bug, compiler bug, or C++ semantic limitation.
3. The structured reasoning chain is the key optimization — it forces the LLM to trace
   the error back through the code generation pipeline instead of guessing.
4. Skills are loaded dynamically from the layered skill tree. The LLM never needs tools.
5. All agent code is in English.