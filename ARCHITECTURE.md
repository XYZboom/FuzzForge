# FuzzForge Multi-Agent Architecture

## Four Loops

### Loop 1: Tool Loop (Global)
FuzzForge development cycle: write FuzzForge code → generate fuzzer project → compile → fix FuzzForge → repeat.

### Loop 2: Compile Loop (Healer)
Fix Kotlin compilation errors: build → classify errors → LLM patches → rebuild.

### Loop 3: Syntax Validation Loop
Ensure generated C++ code is syntactically valid (fast, g++ -fsyntax-only).
Fix Translator.kt until 100% of generated programs pass syntax check.

### Loop 4: Semantic Validation Loop
Ensure generated C++ code is semantically valid (full compilation, g++ -c).
Fix Generator.kt until 100% of generated programs pass semantic check.

### Loop 5: Fuzzing Loop (Big Loop)
Actual fuzzing: generate valid C++ programs → compile with g++ vs clang++ → compare outputs → collect compiler bugs → repeat.

## Why Syntax vs Semantic matters

For C++ compilation:
- **Syntax errors**: `template<T>` (missing typename keyword), malformed expressions
  → Fix: Translator.kt (the code that generates C++ text)
  → Fast check: g++ -fsyntax-only
- **Semantic errors**: `static virtual`, `no return statement`, `union cannot have virtual`, `static const`
  → Fix: Generator.kt (the code that builds IR with conflicting flags)
  → Full check: g++ -c (compile only, no link)

Separating these loops means:
1. Each loop has a tighter, more focused prompt
2. The LLM knows exactly which file to fix
3. Syntax errors are caught first (fast iteration), then semantic errors (slower)

## Knowledge Sharing

All agents access a layered skill tree:

```
fuzzforge-knowledge-index (root index)
  ├── fuzzforge-ir-design        (IR hierarchy patterns)
  ├── fuzzforge-cpp-generator     (builder API, generation patterns)
  ├── fuzzforge-cpp-translator    (visitor, C++ syntax rules)
  └── fuzzforge-classifier       (error classification patterns)
```