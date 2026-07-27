"""
FuzzForge — Autonomous Fuzzer Code Generation Agent
====================================================

FuzzForge is a meta-agent that designs and generates complete
fuzzer projects using an LLM. Given a target description, it:

1. Designs the IR data structure (TreeBuilder, OpKind, types)
2. Creates the Kotlin project scaffold
3. Generates Generator, Translator, Runner, and Reducer code
4. Optionally runs the generated fuzzer and iterates

Usage:
    fuzzforge create --target "TVM Relax compiler" --output ./tvm-fuzzer
    fuzzforge create --target "PyTorch Inductor" --provider openai
    fuzzforge run --fuzzer ./my-fuzzer --config configs/run.yaml
"""

__version__ = "0.1.0"