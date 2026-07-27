#!/usr/bin/env python3
"""FuzzForge LLM provider: reads prompt from stdin, outputs IR design JSON."""
import json
import sys

prompt = sys.stdin.read()

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