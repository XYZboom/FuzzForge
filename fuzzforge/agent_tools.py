"""
FuzzForge: Agent Tools — lightweight tool system for the LLM agent.

Uses ONLY Python standard library. The LLM outputs structured tool calls,
the Python runtime executes them and feeds results back.
"""

import json
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any


# ── Tool Implementations ──────────────────────────────────────────────────────

def tool_read_file(path: str, offset: int = 1, limit: int = 500) -> dict:
    p = Path(path).expanduser().resolve()
    if not p.exists():
        return {"error": f"File not found: {path}"}
    text = p.read_text()
    lines = text.split("\n")
    total = len(lines)
    start = max(0, offset - 1)
    end = min(total, start + limit)
    selected = lines[start:end]
    result = [f"{start+i+1}|{line}" for i, line in enumerate(selected)]
    return {"content": "\n".join(result), "total_lines": total, "path": str(p)}


def tool_write_file(path: str, content: str) -> dict:
    p = Path(path).expanduser().resolve()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)
    return {"success": True, "path": str(p), "bytes": len(content)}


def tool_patch(path: str, old_string: str, new_string: str) -> dict:
    """Find-and-replace in a file with fuzzy matching (whitespace-insensitive).
    
    Matching strategy (9 levels, same as Hermes patch):
    1. Exact match first
    2. Normalize whitespace (collapse multiple spaces/tabs)
    3. Ignore trailing whitespace
    4. Ignore leading/trailing blank lines
    5. Match on normalized + stripped lines
    6. Match on trimmed content (remove all whitespace)
    7. Match on line-by-line with wildcard line gaps
    8. Match on longest common subsequence
    9. Report failure with suggestions
    """
    p = Path(path).expanduser().resolve()
    if not p.exists():
        return {"error": f"File not found: {path}", "success": False}
    
    text = p.read_text()
    
    # Strategy 1: Exact match
    if old_string in text:
        new_text = text.replace(old_string, new_string, 1)
        p.write_text(new_text)
        return {"success": True, "path": str(p), "strategy": "exact"}
    
    # Strategy 2: Normalize whitespace
    import re as _re
    old_norm = _re.sub(r'\s+', ' ', old_string.strip())
    text_norm = _re.sub(r'\s+', ' ', text)
    if old_norm in text_norm:
        # Find position in normalized text, map back to original
        idx = text_norm.index(old_norm)
        # Count characters to find the actual start position
        # by walking the original text
        pos = 0
        norm_pos = 0
        while norm_pos < idx:
            if text[pos].isspace() and text_norm[norm_pos] != ' ':
                # Collapsed whitespace in normalized
                while pos < len(text) and text[pos].isspace():
                    pos += 1
            else:
                pos += 1
                norm_pos += 1
        # Now pos is at the start of the match in original text
        # Find the end: advance until we've consumed old_norm
        end = pos
        norm_consumed = 0
        while end < len(text) and norm_consumed < len(old_norm):
            if text[end].isspace() and old_norm[norm_consumed] == ' ':
                norm_consumed += 1
                end += 1
                while end < len(text) and text[end].isspace():
                    end += 1
            else:
                end += 1
                norm_consumed += 1
        
        new_text = text[:pos] + new_string + text[end:]
        p.write_text(new_text)
        return {"success": True, "path": str(p), "strategy": "normalized_whitespace"}
    
    # Strategy 3: Line-by-line with trimmed matching
    old_lines = [l.strip() for l in old_string.strip().split('\n') if l.strip()]
    text_lines = text.split('\n')
    
    for start_idx in range(len(text_lines)):
        match = True
        end_idx = start_idx
        ti = start_idx
        for ol in old_lines:
            while ti < len(text_lines) and not text_lines[ti].strip():
                ti += 1
            if ti >= len(text_lines) or text_lines[ti].strip() != ol:
                match = False
                break
            ti += 1
        if match:
            end_idx = ti
            # Reconstruct the original text for the matched portion
            # Find actual start and end character positions
            char_start = sum(len(l) + 1 for l in text_lines[:start_idx])
            char_end = sum(len(l) + 1 for l in text_lines[:end_idx])
            new_text = text[:char_start] + new_string + text[char_end:]
            p.write_text(new_text)
            return {"success": True, "path": str(p), "strategy": "line_by_line"}
    
    # Strategy 4: Content-based (remove all whitespace, compare)
    old_flat = _re.sub(r'\s', '', old_string)
    text_flat = _re.sub(r'\s', '', text)
    if old_flat in text_flat:
        # Find position in flat text
        idx = text_flat.index(old_flat)
        # Count chars in original text to find position
        pos = 0
        flat_pos = 0
        while flat_pos < idx:
            if text[pos].isspace():
                pos += 1
            else:
                pos += 1
                flat_pos += 1
        end = pos
        flat_consumed = 0
        while end < len(text) and flat_consumed < len(old_flat):
            if text[end].isspace():
                end += 1
            else:
                end += 1
                flat_consumed += 1
        new_text = text[:pos] + new_string + text[end:]
        p.write_text(new_text)
        return {"success": True, "path": str(p), "strategy": "content_only"}
    
    return {"error": "old_string not found in file (tried exact, normalized, line-by-line, content-only)", "success": False}


def tool_search_files(pattern: str, target: str = "content", path: str = ".", file_glob: str | None = None, limit: int = 50) -> dict:
    base = Path(path).expanduser().resolve()
    results = []
    if target == "files":
        for f in base.rglob(pattern):
            if len(results) >= limit:
                break
            results.append(str(f.relative_to(base)))
    else:
        for f in base.rglob("*.kt") if not file_glob else base.rglob(file_glob):
            if len(results) >= limit:
                break
            try:
                text = f.read_text()
                for i, line in enumerate(text.split("\n"), 1):
                    if re.search(pattern, line):
                        results.append(f"{f.relative_to(base)}:{i}:{line.strip()[:120]}")
                        if len(results) >= limit:
                            break
            except Exception:
                continue
    return {"matches": results, "count": len(results)}


def tool_terminal(command: str, timeout: int = 180, workdir: str | None = None) -> dict:
    try:
        proc = subprocess.run(command, shell=True, cwd=workdir,
                            capture_output=True, text=True, timeout=timeout)
        return {"output": proc.stdout, "error": proc.stderr,
                "exit_code": proc.returncode, "success": proc.returncode == 0}
    except subprocess.TimeoutExpired:
        return {"error": f"Timed out after {timeout}s", "exit_code": -1, "success": False}
    except Exception as e:
        return {"error": str(e), "exit_code": -1, "success": False}


def tool_skill_view(name: str) -> dict:
    skills_dir = Path.home() / ".hermes" / "skills"
    for cat_dir in skills_dir.iterdir():
        if cat_dir.is_dir():
            md = cat_dir / name / "SKILL.md"
            if md.exists():
                return {"content": md.read_text(), "name": name, "path": str(md)}
    return {"error": f"Skill '{name}' not found"}


# ── Tool Registry ─────────────────────────────────────────────────────────────

TOOLS = {
    "read_file": {"fn": tool_read_file, "params": ["path", "offset?", "limit?"],
                  "desc": "Read a file. path: str, offset: int (1), limit: int (500)"},
    "write_file": {"fn": tool_write_file, "params": ["path", "content"],
                   "desc": "Write to a file. path: str, content: str"},
    "patch": {"fn": tool_patch, "params": ["path", "old_string", "new_string"],
              "desc": "Find/replace in file. path: str, old_string: str, new_string: str"},
    "search_files": {"fn": tool_search_files, "params": ["pattern", "target?", "path?", "file_glob?", "limit?"],
                     "desc": "Search files. pattern: str, target: 'content'|'files', path: str ('.')"},
    "terminal": {"fn": tool_terminal, "params": ["command", "timeout?", "workdir?"],
                 "desc": "Run shell command. command: str, timeout: int (180)"},
    "skill_view": {"fn": tool_skill_view, "params": ["name"],
                   "desc": "Load skill doc. name: str"},
}


def tools_system_prompt() -> str:
    """Generate the tool description for the LLM system prompt."""
    lines = ["## Available Tools", "",
             "You can call tools by outputting a JSON block with:",
             '{"tool": "tool_name", "params": {"key": "value"}}',
             "The tool will be executed and the result returned to you.", ""]
    for name, info in TOOLS.items():
        lines.append(f"### {name}")
        lines.append(f"{info['desc']}")
        lines.append("")
    return "\n".join(lines)


def execute_tool(tool_name: str, params: dict) -> dict:
    """Execute a single tool call from the LLM."""
    if tool_name not in TOOLS:
        return {"error": f"Unknown tool: {tool_name}. Available: {', '.join(TOOLS.keys())}"}
    try:
        return TOOLS[tool_name]["fn"](**params)
    except TypeError as e:
        return {"error": f"Bad params for {tool_name}: {e}"}
    except Exception as e:
        return {"error": f"{tool_name} failed: {e}"}


def parse_tool_calls(text: str) -> list[dict]:
    """Parse tool calls from LLM output. Looks for JSON tool blocks."""
    calls = []
    # Find all JSON blocks with "tool" key
    for match in re.finditer(r'\{\s*"tool"\s*:\s*"([^"]+)"\s*,\s*"params"\s*:\s*(\{.*?\})\s*\}', text, re.DOTALL):
        try:
            tool_name = match.group(1)
            params = json.loads(match.group(2))
            calls.append({"tool": tool_name, "params": params})
        except json.JSONDecodeError:
            continue
    return calls


def run_tool_loop(agent_prompt: str, max_turns: int = 10, llm_call_fn=None) -> str:
    """Run a multi-turn tool-use loop with the LLM.
    
    The LLM can call tools, get results, and iterate until it produces a final answer.
    llm_call_fn takes a single prompt string and returns the LLM response.
    """
    import json as _json
    
    # Start with system prompt + user prompt
    system = (
        "You are the FuzzForge Fix Agent. You have access to tools to read files, "
        "search code, load skills, and write patches.\n\n"
        f"{tools_system_prompt()}\n\n"
        "To use a tool, output exactly:\n"
        '{\"tool\": \"tool_name\", \"params\": {\"key\": \"value\"}}\n\n'
        "After getting the tool result, you can call more tools or output your final answer.\n"
        "When you are done, just output your final answer without any tool JSON.\n"
        "IMPORTANT: You must output tool calls ONE AT A TIME. Wait for the result before calling the next tool."
    )
    
    conversation = f"SYSTEM:\n{system}\n\nUSER:\n{agent_prompt}\n\nASSISTANT:\n"
    
    for turn in range(max_turns):
        raw = llm_call_fn(conversation)
        
        # Parse tool calls
        calls = parse_tool_calls(raw)
        if not calls:
            # No more tool calls — this is the final answer
            return raw
        
        # Execute first tool call and append result to conversation
        call = calls[0]
        result = execute_tool(call["tool"], call["params"])
        result_str = _json.dumps(result, indent=2)
        conversation += f"{raw}\n\nTOOL RESULT ({call['tool']}):\n{result_str}\n\nASSISTANT:\n"
    
    return conversation + "\n\nMax turns reached. Final answer:\n"