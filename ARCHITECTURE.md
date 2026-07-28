# FuzzForge Multi-Agent Architecture

## Core Loop (Small Loop): Semantic Validation Loop
```
Generator Agent → Translation Agent → Compiler Agent → Classifier Agent → Fix Loop
```

## Agents

### 1. Generator Agent
- **Role**: Generates IR programs (classes, functions, types)
- **Knowledge**: IR structure, builder API, randomization strategies
- **Input**: IR design JSON, GeneratorConfig
- **Output**: UirProgram IR tree

### 2. Translation Agent
- **Role**: Translates IR to C++ source code
- **Knowledge**: C++ syntax rules, visitor pattern, type system
- **Input**: UirProgram IR tree
- **Output**: C++ source code string

### 3. Compiler Agent
- **Role**: Invokes g++/clang++, collects ALL errors and warnings
- **Knowledge**: Compiler flags, error output parsing
- **Input**: C++ source code
- **Output**: Compilation result (exit code, stdout, stderr)

### 4. Classifier Agent
- **Role**: Classifies each error as:
  - **Generator Bug**: Bug in the fuzzer's code generation logic
  - **Compiler Bug**: Bug in the C++ compiler being tested
  - **Semantic Issue**: Known C++ limitation (e.g. can't inherit from int)
- **Knowledge**: C++ standards, common compiler bugs, fuzzer design patterns
- **Input**: Compilation error, the generated code
- **Output**: Error classification with fix suggestions

## Knowledge Sharing
All agents share:
- `tree_api.py`: Tree-generator API documentation (what is auto-generated, what can be modified)
- `knowledge.py`: Fuzzing design patterns extracted from real projects
- `fuzzforge-agent` skill: Agent's own skill documentation

## Fix Loop
1. Generator produces IR → Translation Agent produces C++
2. Compiler Agent compiles with g++, collects ALL errors
3. Classifier Agent classifies each error
4. If Generator Bug → Fix Generator Agent's knowledge
5. If Compiler Bug → Save to BugCollector
6. If Semantic Issue → Add to C++ knowledge base
7. Repeat until 100% of generated programs are semantically valid C++

## Key Principle
ALL errors are collected. No errors are ignored. Every error is either:
- A bug in FuzzForge's generator (must fix the generator)
- A bug in the compiler being tested (save to bug collector)
- A known C++ limitation (add to knowledge base)