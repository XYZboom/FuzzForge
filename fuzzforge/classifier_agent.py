"""
FuzzForge: Error Classifier Agent.

Classifies compilation errors from g++/clang++ into:
  1. Generator Bug — bug in the fuzzer's code generation logic (must fix the generator)
  2. Compiler Bug — bug in the C++ compiler being tested (save to bug collector)
  3. Semantic Issue — known C++ limitation (add to C++ knowledge base)

Uses pattern matching + LLM for classification.
"""

import json
import os
import subprocess
import urllib.request
from typing import Any


def _load_sf_config() -> tuple[str, str, str]:
    """Load SF API config from Hermes config."""
    api_key = ""
    base_url = "https://api.sfkey.cn/v1"
    model = "glm-5.2"
    try:
        import yaml
        with open(os.path.expanduser("~/.hermes/config.yaml")) as f:
            cfg = yaml.safe_load(f)
        for prov in cfg.get("custom_providers", []):
            if prov.get("name") == "sf":
                api_key = prov.get("api_key", "")
        if not api_key:
            api_key = cfg.get("model", {}).get("api_key", "")
    except Exception:
        api_key = os.environ.get("FUZZFORGE_API_KEY", "")
    return api_key, base_url, model


# Known C++ semantic limitations — patterns that are NOT compiler bugs
KNOWN_SEMANTIC_ISSUES = [
    # Cannot inherit from fundamental types
    {"pattern": "cannot inherit", "category": "semantic", "fix": "Do not inherit from fundamental types (int, float, bool, char, etc.)"},
    {"pattern": "expected class-name before", "category": "semantic", "fix": "Only inherit from class types, not primitives"},
    # Template requires typename/class keyword
    {"pattern": "has not been declared", "category": "semantic_keyword", "fix": "Template parameters need 'typename' or 'class' keyword: template<typename T> not template<T>"},
    # Missing return statement
    {"pattern": "no return statement", "category": "semantic", "fix": "Non-void functions must have a return statement"},
    # Unused parameter (warning)
    {"pattern": "unused parameter", "category": "warning", "fix": "Add [[maybe_unused]] attribute or suppress warning"},
    # Static and virtual cannot be combined
    {"pattern": "cannot be overloaded", "category": "semantic", "fix": "static virtual functions are not allowed in C++"},
    # Pure virtual function in non-abstract class
    {"pattern": "cannot be instantiated", "category": "semantic", "fix": "Make class abstract or provide implementation for pure virtual functions"},
    # Union with virtual functions
    {"pattern": "union cannot have", "category": "semantic", "fix": "Unions cannot have virtual functions in C++"},
    # Multiple inheritance ambiguity
    {"pattern": "ambiguous", "category": "semantic", "fix": "Resolve inheritance ambiguity"},
]


def classify_error(stderr: str, source_code: str) -> list[dict[str, Any]]:
    """Classify compilation errors using pattern matching + LLM if needed.

    Returns list of error classifications, each with:
      - error_text: the raw error message
      - category: 'generator_bug' | 'compiler_bug' | 'semantic_issue' | 'warning'
      - fix_suggestion: suggested fix for the generator
      - confidence: 0.0 to 1.0
    """
    errors = []
    lines = stderr.split("\n")

    for line in lines:
        line = line.strip()
        if not line or line.startswith("In file included from") or line.startswith("                 from"):
            continue

        # Check against known semantic issues
        classified = False
        for issue in KNOWN_SEMANTIC_ISSUES:
            if issue["pattern"] in line.lower():
                errors.append({
                    "error_text": line[:200],
                    "category": issue["category"],
                    "fix_suggestion": issue["fix"],
                    "confidence": 0.9,
                })
                classified = True
                break

        if not classified and ("error:" in line or "warning:" in line):
            # Unknown error — classify as potentially generator bug
            errors.append({
                "error_text": line[:200],
                "category": "generator_bug",
                "fix_suggestion": "Unknown error pattern. Review the generator output.",
                "confidence": 0.5,
            })

    return errors


def classify_with_llm(stderr: str, source_code: str) -> str:
    """Use LLM to classify complex errors that pattern matching can't handle."""
    api_key, base_url, model = _load_sf_config()
    if not api_key:
        return ""

    prompt = f"""Analyze the following C++ compilation error and generated source code.

SOURCE CODE:
```cpp
{source_code[:2000]}
```

COMPILER OUTPUT:
```
{stderr[:2000]}
```

Classify each error as one of:
1. GENERATOR_BUG — The fuzzer generator produced invalid C++ (fix the generator)
2. COMPILER_BUG — The C++ compiler has a bug
3. SEMANTIC_ISSUE — Known C++ limitation (e.g., cannot inherit from int)
4. WARNING — Non-fatal warning

For each GENERATOR_BUG, suggest a specific fix for the Kotlin generator code.
Output JSON: [{{"error": "...", "category": "GENERATOR_BUG|COMPILER_BUG|SEMANTIC_ISSUE|WARNING", "fix_suggestion": "..."}}]
"""

    body = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": "You are a C++ compiler error classifier for the FuzzForge fuzzer framework. Classify errors and suggest fixes for the generator."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.1,
        "max_tokens": 2048,
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
        resp = urllib.request.urlopen(req, timeout=60)
        data = json.loads(resp.read())
        return data["choices"][0]["message"]["content"]
    except Exception as e:
        return f"// LLM classification failed: {e}"


def generate_fix_report(errors: list[dict[str, Any]]) -> str:
    """Generate a human-readable fix report from classified errors."""
    lines = []
    lines.append("=== Error Classification Report ===")
    lines.append("")

    for err in errors:
        icon = {"generator_bug": "🐛", "compiler_bug": "🔥", "semantic_issue": "📝", "warning": "⚠️"}.get(err["category"], "❓")
        lines.append(f"{icon} [{err['category'].upper()}] (confidence: {err['confidence']})")
        lines.append(f"   Error: {err['error_text']}")
        lines.append(f"   Fix:   {err['fix_suggestion']}")
        lines.append("")

    # Count by category
    from collections import Counter
    counts = Counter(e["category"] for e in errors)
    lines.append("--- Summary ---")
    lines.append(f"  Generator bugs:  {counts.get('generator_bug', 0)}")
    lines.append(f"  Compiler bugs:   {counts.get('compiler_bug', 0)}")
    lines.append(f"  Semantic issues: {counts.get('semantic_issue', 0)}")
    lines.append(f"  Warnings:        {counts.get('warning', 0)}")
    lines.append("")

    if counts.get("generator_bug", 0) > 0 or counts.get("semantic_issue", 0) > 0:
        lines.append("Recommended: Fix the fuzzer generator to avoid these issues.")
    if counts.get("compiler_bug", 0) > 0:
        lines.append("Recommended: Save failing programs to the bug collector for compiler developers.")

    return "\n".join(lines)