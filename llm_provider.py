#!/usr/bin/env python3
"""FuzzForge LLM provider: reads prompt from stdin, outputs IR design or fix patches."""
import json
import re
import sys

prompt = sys.stdin.read()

# Detect mode from args
mode = "design"
for i, arg in enumerate(sys.argv):
    if arg == "--mode" and i + 1 < len(sys.argv):
        mode = sys.argv[i + 1]
        break

if mode == "fix":
    # ======================================================================
    # FIX MODE: analyze build errors and output patches
    # ======================================================================

    # Extract key files from the prompt to understand what exists
    files = {}
    current_file = None
    for line in prompt.split("\n"):
        if line.startswith("### FILE:"):
            current_file = line.replace("### FILE:", "").strip()
            files[current_file] = ""
        elif current_file is not None:
            if line.startswith("```"):
                continue
            files[current_file] += line + "\n"

    patches = []

    # Step 1: Detect Uir prefix from generated files
    # All generated types use "Uir" prefix (UirProgram, UirNode, etc.)
    # Business code uses non-prefixed names (Program, Node, etc.)
    # Fix: patch business code to use Uir prefix
    uir_types = set()
    for fp, content in files.items():
        if "tree/gen" in fp:
            for m in re.finditer(r'\bUir(\w+)\b', content):
                uir_types.add(m.group(1))

    # Step 2: For each business code file, replace non-prefixed type refs
    for fp, content in files.items():
        if "src/main/kotlin/com/fuzzforge" in fp and "tree/" not in fp:
            new_content = content
            for t in sorted(uir_types, key=len, reverse=True):
                new_content = re.sub(
                    r'\b' + t + r'\b(?!Impl)',
                    lambda m: m.group(0) if m.group(0).startswith('Uir') else 'Uir' + t,
                    new_content
                )
            if new_content != content:
                patches.append({
                    "file_path": fp,
                    "old_string": content,
                    "new_string": new_content
                })

    # Step 3: Fix common import issues
    for fp, content in files.items():
        if "Generator.kt" in fp:
            if "import com.fuzzforge.ir.types.*" in content:
                patches.append({
                    "file_path": fp,
                    "old_string": "import com.fuzzforge.ir.types.*\nimport com.fuzzforge.ir.types.impl.*",
                    "new_string": "// Types are in ir package directly"
                })
            if "ProgramImpl()" in content:
                patches.append({
                    "file_path": fp,
                    "old_string": "return ProgramImpl()",
                    "new_string": "return UirProgramImpl()"
                })

    # Step 4: Fix App.kt references to non-existent properties
    for fp, content in files.items():
        if "App.kt" in fp:
            if "program.graphs" in content:
                patches.append({
                    "file_path": fp,
                    "old_string": "echo(\"Generated program ${i + 1}: ${program.graphs.size} graphs\")",
                    "new_string": "echo(\"Generated program ${i + 1}\")"
                })
            if "program.classes" in content:
                patches.append({
                    "file_path": fp,
                    "old_string": "echo(\"Generated program ${i + 1}: ${program.classes.size} classes\")",
                    "new_string": "echo(\"Generated program ${i + 1}\")"
                })

    # Step 5: Fix Translator.kt references
    for fp, content in files.items():
        if "Translator.kt" in fp:
            if "for ((i, graph) in program.graphs.withIndex()) {" in content:
                patches.append({
                    "file_path": fp,
                    "old_string": "for ((i, graph) in program.graphs.withIndex()) {",
                    "new_string": "// Graphs not available in this mode"
                })
            if "com.fuzzforge.ir.types.TensorType" in content:
                patches.append({
                    "file_path": fp,
                    "old_string": "com.fuzzforge.ir.types.TensorType",
                    "new_string": "com.fuzzforge.ir.TensorType"
                })
            if "program.classes" in content:
                patches.append({
                    "file_path": fp,
                    "old_string": "for (clazz in program.classes) {",
                    "new_string": "// Classes not available in this mode"
                })

    print(json.dumps(patches, indent=2))
    sys.exit(0)

# ======================================================================
# DESIGN MODE: C++ fuzzer IR design
# ======================================================================

design = {
    "project_name": "cpp-fuzzer",
    "description": "C++ compiler fuzzer — generates random C++ class/function declarations to test g++ and clang",
    "ir_mode": "class_declaration",
    "tree_builder_elements": [
        {"var_name": "element", "element_name": "Element", "kind": "Other", "parent": None, "interface_kind": None, "fields": []},
        {"var_name": "namedElement", "element_name": "NamedElement", "kind": "Other", "parent": None, "interface_kind": "Interface", "fields": [{"name": "name", "type": "String", "is_child": False, "nullable": False, "is_mutable": True, "with_transform": False, "with_replace": False, "list_base_type": None}]},
        {"var_name": "declaration", "element_name": "Declaration", "kind": "Other", "parent": "namedElement", "interface_kind": "Interface", "fields": [{"name": "language", "type": "Language", "is_child": False, "nullable": False, "is_mutable": True, "with_transform": False, "with_replace": False, "list_base_type": None}]},
        {"var_name": "program", "element_name": "Program", "kind": "Other", "parent": None, "interface_kind": "Interface", "fields": []},
        {"var_name": "classContainer", "element_name": "ClassContainer", "kind": "Other", "parent": None, "interface_kind": "Interface", "fields": [{"name": "classes", "type": "List<ClassDeclaration>", "is_child": True, "nullable": False, "is_mutable": True, "with_transform": True, "with_replace": False, "list_base_type": "ClassDeclaration"}]},
        {"var_name": "funcContainer", "element_name": "FuncContainer", "kind": "Other", "parent": None, "interface_kind": "Interface", "fields": [{"name": "functions", "type": "List<FunctionDeclaration>", "is_child": True, "nullable": False, "is_mutable": True, "with_transform": True, "with_replace": False, "list_base_type": "FunctionDeclaration"}]},
        {"var_name": "typeParamContainer", "element_name": "TypeParameterContainer", "kind": "Other", "parent": None, "interface_kind": "Interface", "fields": [{"name": "typeParameters", "type": "List<TemplateParameter>", "is_child": True, "nullable": False, "is_mutable": True, "with_transform": True, "with_replace": False, "list_base_type": "TemplateParameter"}]},
        {"var_name": "exprContainer", "element_name": "ExpressionContainer", "kind": "Other", "parent": None, "interface_kind": "Interface", "fields": [{"name": "expressions", "type": "List<Expression>", "is_child": True, "nullable": False, "is_mutable": True, "with_transform": True, "with_replace": False, "list_base_type": "Expression"}]},
        {"var_name": "classDecl", "element_name": "ClassDeclaration", "kind": "Other", "parent": "declaration", "interface_kind": "AbstractClass", "fields": [{"name": "classKind", "type": "ClassKind", "is_child": False, "nullable": False, "is_mutable": True, "with_transform": False, "with_replace": False, "list_base_type": None}, {"name": "superType", "type": "Type", "is_child": False, "nullable": True, "is_mutable": True, "with_transform": False, "with_replace": False, "list_base_type": None}, {"name": "isFinal", "type": "Boolean", "is_child": False, "nullable": False, "is_mutable": True, "with_transform": False, "with_replace": False, "list_base_type": None}]},
        {"var_name": "funcDecl", "element_name": "FunctionDeclaration", "kind": "Other", "parent": "declaration", "interface_kind": "AbstractClass", "fields": [{"name": "isVirtual", "type": "Boolean", "is_child": False, "nullable": False, "is_mutable": True, "with_transform": False, "with_replace": False, "list_base_type": None}, {"name": "isPureVirtual", "type": "Boolean", "is_child": False, "nullable": False, "is_mutable": True, "with_transform": False, "with_replace": False, "list_base_type": None}, {"name": "isOverride", "type": "Boolean", "is_child": False, "nullable": False, "is_mutable": True, "with_transform": False, "with_replace": False, "list_base_type": None}, {"name": "isConst", "type": "Boolean", "is_child": False, "nullable": False, "is_mutable": True, "with_transform": False, "with_replace": False, "list_base_type": None}, {"name": "isStatic", "type": "Boolean", "is_child": False, "nullable": False, "is_mutable": True, "with_transform": False, "with_replace": False, "list_base_type": None}, {"name": "isTemplate", "type": "Boolean", "is_child": False, "nullable": False, "is_mutable": True, "with_transform": False, "with_replace": False, "list_base_type": None}, {"name": "returnType", "type": "Type", "is_child": False, "nullable": False, "is_mutable": True, "with_transform": False, "with_replace": False, "list_base_type": None}, {"name": "parameterList", "type": "ParameterList", "is_child": False, "nullable": False, "is_mutable": True, "with_transform": True, "with_replace": False, "list_base_type": None}, {"name": "body", "type": "Block", "is_child": True, "nullable": True, "is_mutable": True, "with_transform": True, "with_replace": False, "list_base_type": None}, {"name": "containingClassName", "type": "String", "is_child": False, "nullable": True, "is_mutable": True, "with_transform": False, "with_replace": False, "list_base_type": None}]},
        {"var_name": "parameter", "element_name": "Parameter", "kind": "Other", "parent": None, "interface_kind": "AbstractClass", "fields": [{"name": "name", "type": "String", "is_child": False, "nullable": False, "is_mutable": True, "with_transform": False, "with_replace": False, "list_base_type": None}, {"name": "type", "type": "Type", "is_child": False, "nullable": False, "is_mutable": True, "with_transform": False, "with_replace": False, "list_base_type": None}, {"name": "defaultValue", "type": "Expression", "is_child": True, "nullable": True, "is_mutable": True, "with_transform": True, "with_replace": False, "list_base_type": None}]},
        {"var_name": "parameterList", "element_name": "ParameterList", "kind": "Other", "parent": None, "interface_kind": "AbstractClass", "fields": [{"name": "parameters", "type": "List<Parameter>", "is_child": True, "nullable": False, "is_mutable": True, "with_transform": True, "with_replace": False, "list_base_type": "Parameter"}]},
        {"var_name": "type", "element_name": "Type", "kind": "Other", "parent": None, "interface_kind": "AbstractClass", "fields": [{"name": "typeKind", "type": "TypeKind", "is_child": False, "nullable": False, "is_mutable": False, "with_transform": False, "with_replace": False, "list_base_type": None}]},
        {"var_name": "fundamentalType", "element_name": "FundamentalType", "kind": "Other", "parent": "type", "interface_kind": "AbstractClass", "fields": [{"name": "name", "type": "String", "is_child": False, "nullable": False, "is_mutable": True, "with_transform": False, "with_replace": False, "list_base_type": None}, {"name": "size", "type": "Int", "is_child": False, "nullable": False, "is_mutable": True, "with_transform": False, "with_replace": False, "list_base_type": None}]},
        {"var_name": "pointerType", "element_name": "PointerType", "kind": "Other", "parent": "type", "interface_kind": "AbstractClass", "fields": [{"name": "pointeeType", "type": "Type", "is_child": False, "nullable": False, "is_mutable": True, "with_transform": False, "with_replace": False, "list_base_type": None}]},
        {"var_name": "referenceType", "element_name": "ReferenceType", "kind": "Other", "parent": "type", "interface_kind": "AbstractClass", "fields": [{"name": "referencedType", "type": "Type", "is_child": False, "nullable": False, "is_mutable": True, "with_transform": False, "with_replace": False, "list_base_type": None}]},
        {"var_name": "templateParam", "element_name": "TemplateParameter", "kind": "Other", "parent": "type", "interface_kind": "AbstractClass", "fields": [{"name": "name", "type": "String", "is_child": False, "nullable": False, "is_mutable": True, "with_transform": False, "with_replace": False, "list_base_type": None}, {"name": "isTypeParameter", "type": "Boolean", "is_child": False, "nullable": False, "is_mutable": True, "with_transform": False, "with_replace": False, "list_base_type": None}]},
        {"var_name": "expression", "element_name": "Expression", "kind": "Other", "parent": None, "interface_kind": "AbstractClass", "fields": []},
        {"var_name": "block", "element_name": "Block", "kind": "Other", "parent": "expression", "interface_kind": "AbstractClass", "fields": []},
    ],
    "enums": {
        "op_kind": ["ADD", "SUBTRACT", "MULTIPLY", "DIVIDE", "CALL", "ALLOCATE", "DEREFERENCE", "ASSIGN", "RETURN", "IF", "FOR"],
        "type_kind": ["FUNDAMENTAL", "POINTER", "REFERENCE", "TEMPLATE_PARAMETER", "CLASS_TYPE"],
        "attr_kind": ["INT", "STRING", "BOOL"],
        "dim_kind": ["CONSTANT"],
        "block_kind": ["THEN", "ELSE", "BODY"],
        "class_kind": ["ABSTRACT", "INTERFACE", "OPEN", "FINAL", "SEALED", "DATA"],
        "language": ["KOTLIN", "JAVA", "SCALA", "GROOVY4", "GROOVY5"],
    },
    "generator_config": {"fields": [
        {"name": "minClasses", "type": "Int", "default_value": "2", "description": "Minimum number of top-level classes"},
        {"name": "maxClasses", "type": "Int", "default_value": "8", "description": "Maximum number of top-level classes"},
        {"name": "minFunctionsPerClass", "type": "Int", "default_value": "1", "description": "Minimum functions per class"},
        {"name": "maxFunctionsPerClass", "type": "Int", "default_value": "5", "description": "Maximum functions per class"},
        {"name": "minParams", "type": "Int", "default_value": "0", "description": "Minimum function parameters"},
        {"name": "maxParams", "type": "Int", "default_value": "4", "description": "Maximum function parameters"},
        {"name": "templateProbability", "type": "Float", "default_value": "0.3f", "description": "Probability of adding template parameters"},
        {"name": "virtualProbability", "type": "Float", "default_value": "0.2f", "description": "Probability of marking function virtual"},
        {"name": "inheritanceProbability", "type": "Float", "default_value": "0.3f", "description": "Probability of class having a super class"},
    ]},
    "translator_targets": ["cpp_source"],
    "diff_test_modes": ["cross_compiler"],
    "has_pattern_dedup": False,
    "requires_reducer": True,
}

print(json.dumps(design, indent=2))