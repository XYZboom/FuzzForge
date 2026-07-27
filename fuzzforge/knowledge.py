"""
FuzzForge: embedded knowledge base — extracted from production fuzzer projects.

This module contains distilled design patterns from real-world fuzzer implementations.
NO project names, NO source references — only the universal lessons.
"""

from typing import Any

# ──────────────────────────────────────────────────────────────────────────────
# Computation Graph IR — for AI compilers, dataflow frameworks, pipeline systems
# ──────────────────────────────────────────────────────────────────────────────

COMPUTATION_GRAPH_KNOWLEDGE: dict[str, Any] = {
    "ir_rationale": (
        "A computation graph IR represents programs as directed acyclic graphs (DAGs) "
        "of operator nodes connected by value references. This is the standard IR for "
        "AI compilers, tensor computation frameworks, and dataflow systems."
    ),
    "element_hierarchy": [
        {
            "name": "Element",
            "kind": "root",
            "note": "Root interface. Every IR node must implement accept(visitor), transform(transformer), acceptChildren, transformChildren.",
        },
        {
            "name": "NamedElement",
            "kind": "interface",
            "fields": [("name", "String", False)],
            "note": "Mixin for elements that have a name. Inherited by Graph and Node.",
        },
        {
            "name": "Program",
            "kind": "interface",
            "fields": [
                ("graphs", "List<Graph>", True),
                ("metadata", "Map<String,String>", False),
            ],
            "note": "Top-level container. Holds all graphs and optional metadata (seed, config, etc).",
        },
        {
            "name": "Graph",
            "kind": "abstract",
            "parent": "NamedElement",
            "fields": [
                ("nodes", "List<Node>", True),
                ("inputs", "List<ValueRef>", True),
                ("outputs", "List<ValueRef>", True),
            ],
            "note": "A single computation graph. Inputs are external values, nodes are operators, outputs are the graph's results.",
        },
        {
            "name": "Node",
            "kind": "abstract",
            "parent": "NamedElement",
            "fields": [
                ("op", "OpKind", False),
                ("inputs", "List<ValueRef>", True),
                ("outputs", "List<ValueRef>", True),
                ("attributes", "Map<String,Attribute>", False),
            ],
            "note": "A single operator invocation. Has an op kind, input value references, output value references, and optional attributes.",
        },
        {
            "name": "ValueRef",
            "kind": "abstract",
            "fields": [
                ("valueId", "String", False),
                ("type", "TensorType", False),
            ],
            "note": "A reference to a computed value. Links a value ID to its tensor type. Used as both inputs and outputs of nodes.",
        },
    ],
    "type_system": [
        {
            "name": "Type",
            "kind": "abstract",
            "fields": [("typeKind", "TypeKind", False)],
            "note": "Base type. Has a discriminator enum for runtime type checking.",
        },
        {
            "name": "TensorType",
            "kind": "abstract",
            "parent": "Type",
            "fields": [
                ("shape", "Shape", False),
                ("dtype", "DataType", False),
            ],
            "note": "A tensor type. Shape describes its dimensions, dtype describes the element type.",
        },
        {
            "name": "Shape",
            "kind": "abstract",
            "fields": [("dims", "List<Dim>", True)],
            "note": "A list of dimensions. Each dim is either a constant value or symbolic/unknown.",
        },
        {
            "name": "Dim",
            "kind": "abstract",
            "fields": [
                ("dimKind", "DimKind", False),
                ("value", "Int?", False),
            ],
            "note": "A single dimension. CONSTANT dims have a fixed value; SYMBOLIC dims are variables; UNKNOWN dims are dynamic.",
        },
        {
            "name": "DataType",
            "kind": "abstract",
            "fields": [
                ("name", "String", False),
                ("bits", "Int", False),
            ],
            "note": "Element data type. e.g. float32, int64, bfloat16.",
        },
    ],
    "attribute_system": [
        {
            "name": "Attribute",
            "kind": "abstract",
            "fields": [("attrKind", "AttrKind", False)],
            "note": "Base attribute type. Discriminator enum for runtime type checking.",
        },
        {
            "name": "IntAttr",
            "kind": "abstract",
            "parent": "Attribute",
            "fields": [("value", "Int", False)],
            "note": "Integer attribute.",
        },
        {
            "name": "StringAttr",
            "kind": "abstract",
            "parent": "Attribute",
            "fields": [("value", "String", False)],
            "note": "String attribute.",
        },
    ],
    "operator_categories": {
        "element_wise_unary": [
            "RELU", "LEAKY_RELU", "ELU", "SELU", "MISH", "HARDTANH",
            "SIGMOID", "TANH", "GELU", "SILU",
            "NEG", "ABS", "SIGN", "EXP", "LOG", "LOG2", "SQRT",
            "RSQRT", "RECIPROCAL", "CEIL", "FLOOR", "ROUND", "CLAMP",
            "SOFTMAX", "LOG_SOFTMAX", "CAST",
        ],
        "element_wise_binary": [
            "ADD", "SUBTRACT", "MULTIPLY", "DIVIDE", "MAXIMUM", "MINIMUM", "POWER",
        ],
        "linear_algebra": [
            "MATMUL",
        ],
        "convolution_pooling": [
            "CONV2D", "MAX_POOL2D", "AVG_POOL2D",
        ],
        "normalization": [
            "LAYER_NORM", "BATCH_NORM",
        ],
        "reduction": [
            "REDUCE_SUM", "REDUCE_MEAN", "REDUCE_MAX", "REDUCE_MIN",
            "CUMSUM", "CUMPROD", "ARGMAX", "ARGMIN",
        ],
        "shape_transform": [
            "RESHAPE", "TRANSPOSE", "SQUEEZE", "UNSQUEEZE",
            "BROADCAST_TO", "TILE", "CONCAT", "SPLIT",
        ],
        "indexing_slicing": [
            "GATHER", "STRIDED_SLICE",
        ],
        "constant": [
            "ARANGE", "FULL", "ONES", "ZEROS",
        ],
        "interpolation": [
            "INTERPOLATE", "RESIZE2D",
        ],
        "triangular": [
            "TRIL", "TRIU",
        ],
    },
    "generator_pattern": {
        "strategy": (
            "Start with input tensors (ValueRefs). Maintain an 'availableValues' pool. "
            "At each step: select an op, pick compatible inputs from the pool, generate outputs, "
            "add outputs to the pool. Repeat until the graph reaches the desired size."
        ),
        "key_techniques": [
            "Shape inference: pre-compute output shapes for each op so downstream nodes can use compatible shapes.",
            "Shape tiers: tiny/small/medium/conv/extreme — control max dim size and total element count to avoid OOM.",
            "Avoid NaN/Inf ops: exclude LOG, SQRT, DIVIDE, etc. when generating 'safe' programs.",
            "Avoid extreme ops: exclude CEIL, FLOOR, ROUND, ARGMAX which amplify tiny precision errors.",
            "Available value pool: track all produced values across the graph so nodes can reference them.",
            "Multi-graph: generate 3-5 graphs per program, each with its own inputs and outputs.",
        ],
    },
    "translator_pattern": {
        "strategy": (
            "Map each IR element to target-specific code. The translator walks the IR tree "
            "and emits the corresponding target syntax."
        ),
        "key_techniques": [
            "Op name mapping: maintain a Map<OpKind, String> that maps each op to its target API name.",
            "Dtype mapping: maintain a Map<String, String> for dtype name translation.",
            "Shape emission: convert Shape/Dim to target-specific shape expressions.",
            "Attribute handling: convert each attribute type to target-specific syntax.",
        ],
    },
    "differential_testing_modes": [
        {
            "mode": "cross_target",
            "description": "Build the same IR for two targets (e.g. CPU and GPU), run both with identical inputs, compare outputs elementwise.",
            "tolerance": "Use np.allclose(atol=0.5, rtol=0.1) — floating-point reordering causes small differences.",
            "classification": "Mismatches are wrong-code bugs (not crashes).",
        },
        {
            "mode": "optimize_vs_unoptimized",
            "description": "Build the same IR with and without compiler optimizations, compare outputs.",
            "classification": "Mismatches are optimization correctness bugs.",
        },
    ],
    "pattern_dedup": {
        "strategy": (
            "Maintain a set of known-bug trigger patterns. As each node is generated, "
            "check it against active patterns. A pattern is a sequence of nodes with op types "
            "and shape constraints. Full match = regenerate the node. Prefix match = keep tracking."
        ),
        "key_rules": [
            "Full match (all nodes + all constraints satisfied) → regenerate the node (up to maxRetries=5).",
            "Prefix match → keep the pattern active for future nodes, but never trigger regeneration.",
            "Value constraints match by position, not by value ID (IDs are random).",
            "One pattern per ndim value — shape array length must match ndim exactly.",
        ],
    },
}

# ──────────────────────────────────────────────────────────────────────────────
# Class Declaration IR — for JVM language compilers, type system testing
# ──────────────────────────────────────────────────────────────────────────────

CLASS_DECLARATION_KNOWLEDGE: dict[str, Any] = {
    "ir_rationale": (
        "A class declaration IR represents programs as a hierarchy of declarations: "
        "classes contain functions and properties, which reference types. This is the "
        "standard IR for testing compilers of object-oriented languages (Kotlin, Java, Scala, Groovy)."
    ),
    "element_hierarchy": [
        {
            "name": "Element",
            "kind": "root",
            "note": "Root interface. Every IR node must implement accept(visitor), transform(transformer), acceptChildren, transformChildren.",
        },
        {
            "name": "NamedElement",
            "kind": "interface",
            "fields": [("name", "String", False)],
            "note": "Mixin for elements that have a name.",
        },
        {
            "name": "Declaration",
            "kind": "interface",
            "parent": "NamedElement",
            "fields": [("language", "Language", False)],
            "note": "Base for all declarations. Has a language tag for multi-language output.",
        },
        {
            "name": "Program",
            "kind": "interface",
            "parent": "ClassContainer, FuncContainer, PropertyContainer",
            "note": "Top-level program. Contains classes, top-level functions, and top-level properties.",
        },
        {
            "name": "ClassDeclaration",
            "kind": "abstract",
            "parent": "Declaration, FuncContainer, TypeParameterContainer",
            "fields": [
                ("classKind", "ClassKind", False),
                ("superType", "Type?", False),
                ("allSuperTypeArguments", "Map<TypeParameterName, Pair<TypeParameter, Type>>", False),
                ("implementedTypes", "List<Type>", False),
            ],
            "note": "A class or interface declaration. Has a kind (abstract/interface/open/final), optional super type, and implemented interfaces.",
        },
        {
            "name": "FunctionDeclaration",
            "kind": "abstract",
            "parent": "Declaration, TypeParameterContainer",
            "fields": [
                ("printNullableAnnotations", "Boolean", False),
                ("body", "Block?", False),
                ("isOverride", "Boolean", False),
                ("isOverrideStub", "Boolean", False),
                ("override", "List<FunctionDeclaration>", False),
                ("isFinal", "Boolean", False),
                ("parameterList", "ParameterList", False),
                ("returnType", "Type", False),
                ("containingClassName", "String?", False),
            ],
            "note": "A function declaration. Has parameters, return type, optional body, override tracking.",
        },
        {
            "name": "PropertyDeclaration",
            "kind": "abstract",
            "parent": "Declaration",
            "note": "A property declaration. Minimal — can be extended with getter/setter.",
        },
        {
            "name": "Parameter",
            "kind": "abstract",
            "fields": [
                ("name", "String", True),
                ("type", "Type", True),
                ("defaultValue", "Expression?", False),
            ],
            "note": "A function parameter. Has name, type, and optional default value.",
        },
        {
            "name": "ParameterList",
            "kind": "abstract",
            "fields": [("parameters", "List<Parameter>", True)],
            "note": "Container for function parameters.",
        },
    ],
    "container_types": [
        {
            "name": "ClassContainer",
            "kind": "interface",
            "fields": [("classes", "List<ClassDeclaration>", True)],
            "note": "Mixin for elements that contain class declarations.",
        },
        {
            "name": "FuncContainer",
            "kind": "interface",
            "fields": [("functions", "List<FunctionDeclaration>", True)],
            "note": "Mixin for elements that contain function declarations.",
        },
        {
            "name": "PropertyContainer",
            "kind": "interface",
            "fields": [("properties", "List<PropertyDeclaration>", True)],
            "note": "Mixin for elements that contain property declarations.",
        },
        {
            "name": "TypeParameterContainer",
            "kind": "interface",
            "fields": [("typeParameters", "List<TypeParameter>", True)],
            "note": "Mixin for elements that have type parameters.",
        },
        {
            "name": "ExpressionContainer",
            "kind": "interface",
            "fields": [("expressions", "List<Expression>", True)],
            "note": "Mixin for elements that contain expressions.",
        },
    ],
    "type_system": [
        {
            "name": "Type",
            "kind": "abstract",
            "fields": [("classKind", "ClassKind", False)],
            "note": "Base type. Has a discriminator for runtime type checking.",
        },
        {
            "name": "TypeContainer",
            "kind": "abstract",
            "parent": "Type",
            "fields": [("innerType", "Type", False)],
            "note": "A type that wraps another type.",
        },
        {
            "name": "NullableType",
            "kind": "abstract",
            "parent": "Type, TypeContainer",
            "note": "A nullable type (e.g. String?).",
        },
        {
            "name": "PlatformType",
            "kind": "abstract",
            "parent": "Type, TypeContainer",
            "note": "A platform type resulting from Java interop (e.g. String!).",
        },
        {
            "name": "DefinitelyNotNullType",
            "kind": "abstract",
            "parent": "Type, TypeContainer",
            "fields": [("innerType", "TypeParameter", True)],
            "note": "A definitely-not-null type (e.g. T & Any).",
        },
        {
            "name": "TypeParameter",
            "kind": "abstract",
            "parent": "Type, NamedElement",
            "fields": [("upperbound", "Type", False)],
            "note": "A type parameter with an upper bound.",
        },
        {
            "name": "Classifier",
            "kind": "sealed",
            "parent": "Type",
            "fields": [("classDecl", "ClassDeclaration", False)],
            "note": "A classifier type that references a class declaration.",
        },
        {
            "name": "SimpleClassifier",
            "kind": "abstract",
            "parent": "Classifier",
            "note": "A simple classifier (e.g. 'Int', 'String').",
        },
        {
            "name": "ParameterizedClassifier",
            "kind": "abstract",
            "parent": "Classifier",
            "fields": [("arguments", "Map<TypeParameterName, Pair<TypeParameter, Type?>>", False)],
            "note": "A parameterized classifier (e.g. 'List<Int>').",
        },
    ],
    "expression_system": [
        {
            "name": "Expression",
            "kind": "abstract",
            "note": "Base expression type.",
        },
        {
            "name": "Block",
            "kind": "abstract",
            "parent": "ExpressionContainer",
            "note": "A block of expressions.",
        },
    ],
    "enums": {
        "ClassKind": ["ABSTRACT", "INTERFACE", "OPEN", "FINAL", "SEALED", "DATA"],
        "Language": ["KOTLIN", "JAVA", "SCALA", "GROOVY4", "GROOVY5"],
    },
    "generator_pattern": {
        "strategy": (
            "Start from an empty Program. Generate top-level declarations (classes, functions, properties). "
            "For each class: generate members (functions, properties) with compatible types. "
            "Maintain a subClassMap to track inheritance relationships. "
            "Check override constraints during generation, not after."
        ),
        "key_techniques": [
            "Generate-in-legal: override constraints are checked during generation, so the IR is always valid.",
            "subClassMap: track which classes extend which other classes for type compatibility checks.",
            "notSubClassCache: cache negative results to avoid redundant checks.",
            "collectFunctionSignatureMap: build a map of all function signatures for override detection.",
            "getOverrideCandidates: find functions that must be overridden when generating a subclass.",
            "Type selection: use sequential selection (pick from ordered list) or filtered selection (filter by constraint).",
            "Keyword avoidance: maintain a set of reserved keywords per language to avoid generating invalid identifiers.",
        ],
    },
    "mutator_pattern": {
        "strategy": (
            "Apply random mutations to a generated IR program to increase diversity. "
            "Mutations may produce semantically invalid IR — this is intentional, as "
            "invalid IR can still trigger compiler bugs."
        ),
        "mutation_types": [
            "mutateGenericArgumentInParent: change generic type arguments in super type references.",
            "removeOverrideMemberFunction: remove the body of an override function (making it a stub).",
            "mutateGenericArgumentInMemberFunctionParameter: change generic type args in function parameters.",
            "mutateParameterNullability: toggle parameter nullability (nullable ↔ non-null).",
            "mutateClassTypeParameterUpperBoundNullability: change nullability of type parameter upper bounds.",
            "mutateClassTypeParameterUpperBound: change the upper bound type of a type parameter.",
        ],
    },
    "translator_pattern": {
        "strategy": (
            "Walk the IR tree and emit source code for each target language. "
            "Each class becomes a source file; top-level functions/properties go to a special file."
        ),
        "language_specific_notes": [
            "Kotlin: 'val' for properties, 'fun' for functions, ':' for type annotations.",
            "Java: 'final' for non-mutable properties, no top-level functions (use static methods).",
            "Scala: 'val'/'var' for properties, 'def' for functions, ':' for type annotations.",
            "Groovy: largely compatible with Java syntax; can reuse the Java printer.",
        ],
    },
    "validator_pattern": {
        "strategy": (
            "A validator checks IR legality. It is only used during reduction (minimization), "
            "NOT during generation or mutation. After removing elements during reduction, "
            "the validator verifies the remaining program is still legal."
        ),
        "validation_checks": [
            "Class hierarchy legality (interface vs class inheritance rules).",
            "Override method signature matching.",
            "Type parameter upper bound constraints.",
            "Type parameter scope availability.",
        ],
    },
}

# ──────────────────────────────────────────────────────────────────────────────
# Universal IR Design Principles (apply to both modes)
# ──────────────────────────────────────────────────────────────────────────────

UNIVERSAL_DESIGN_PRINCIPLES = [
    {
        "principle": "Tree-generator-common library",
        "detail": (
            "The Kotlin compiler's tree-generator-common library provides AbstractElementConfigurator, "
            "which auto-generates Visitor, Transformer, Builder, and Implementation classes from "
            "a declarative TreeBuilder model. This is the foundation of the entire IR system."
        ),
    },
    {
        "principle": "Element hierarchy",
        "detail": (
            "All elements inherit from a root Element interface. Elements with isChild=true are "
            "visited by Visitor/Transformer; elements with isChild=false are value properties "
            "that don't participate in traversal."
        ),
    },
    {
        "principle": "PureAbstractElement marker",
        "detail": (
            "A marker interface (or abstract class) for elements that are 'pure' IR nodes. "
            "Elements extending this must implement acceptChildren and transformChildren."
        ),
    },
    {
        "principle": "Transformer for tree mutation",
        "detail": (
            "The auto-generated Transformer class provides a transformElement method for every "
            "element type. Override specific transform methods to replace subtrees. "
            "The D type parameter carries arbitrary context data."
        ),
    },
    {
        "principle": "Builder DSL",
        "detail": (
            "Auto-generated Builder classes provide a type-safe DSL for constructing IR trees. "
            "Each builder has setter methods for each field and a build() method."
        ),
    },
    {
        "principle": "PureAbstractElement tag",
        "detail": (
            "A marker interface (or abstract class) for elements that are 'pure' IR nodes. "
            "Elements extending this must implement acceptChildren and transformChildren."
        ),
    },
    {
        "principle": "Serializer for persistence",
        "detail": (
            "IR programs should be serializable to JSON for saving/reloading bug-triggering programs. "
            "Use kotlinx.serialization or Gson."
        ),
    },
    {
        "principle": "DDMin for reduction",
        "detail": (
            "Delta Debugging Minimization (DDMin) splits the program into groups, tests each group "
            "independently, and removes groups that don't reproduce the bug. Split into 2 groups, "
            "test, if no group reproduces alone, increase to n groups. Repeat until each group is "
            "a single element."
        ),
    },
    {
        "principle": "Shape adaptation during reduction",
        "detail": (
            "When removing a node from a computation graph, replace its outputs with shape-compatible "
            "stand-ins (zeros, ones, astype identity) to keep the graph valid."
        ),
    },
    {
        "principle": "Multi-thread safety",
        "detail": (
            "Generators maintain mutable state (availableValues, subClassMap) and are NOT thread-safe. "
            "Each worker must use its own generator instance."
        ),
    },
]


def get_knowledge_for_mode(mode: str) -> dict[str, Any]:
    """Get the embedded knowledge for a given IR mode."""
    if mode == "computation_graph":
        return COMPUTATION_GRAPH_KNOWLEDGE
    elif mode == "class_declaration":
        return CLASS_DECLARATION_KNOWLEDGE
    else:
        return COMPUTATION_GRAPH_KNOWLEDGE


def build_knowledge_context(mode: str) -> str:
    """Build a textual knowledge context for the LLM prompt."""
    knowledge = get_knowledge_for_mode(mode)
    lines = []

    lines.append("## IR Structure Knowledge")
    lines.append("")
    lines.append(knowledge["ir_rationale"])
    lines.append("")

    lines.append("### Element Hierarchy")
    for elem in knowledge["element_hierarchy"]:
        note = elem.get("note", "")
        parent = elem.get("parent", "")
        kind = elem.get("kind", "abstract")
        fields = elem.get("fields", [])
        field_str = "; ".join(f"{n}: {t}" for n, t, _ in fields) if fields else "none"
        parent_str = f" parent={parent}" if parent else ""
        lines.append(f"- {elem['name']} ({kind}{parent_str}): {note}")
        if fields:
            lines.append(f"  Fields: {field_str}")

    lines.append("")
    lines.append("### Type System")
    for t in knowledge.get("type_system", []):
        note = t.get("note", "")
        lines.append(f"- {t['name']}: {note}")

    if "enums" in knowledge:
        lines.append("")
        lines.append("### Enums")
        for name, values in knowledge["enums"].items():
            lines.append(f"- {name}: {', '.join(values)}")

    lines.append("")
    lines.append("### Generator Strategy")
    lines.append(knowledge["generator_pattern"]["strategy"])
    for t in knowledge["generator_pattern"]["key_techniques"]:
        lines.append(f"- {t}")

    lines.append("")
    lines.append("### Translator Strategy")
    lines.append(knowledge["translator_pattern"]["strategy"])
    if "key_techniques" in knowledge["translator_pattern"]:
        for t in knowledge["translator_pattern"]["key_techniques"]:
            lines.append(f"- {t}")
    if "language_specific_notes" in knowledge["translator_pattern"]:
        for t in knowledge["translator_pattern"]["language_specific_notes"]:
            lines.append(f"- {t}")

    if "differential_testing_modes" in knowledge:
        lines.append("")
        lines.append("### Differential Testing Modes")
        for mode_info in knowledge["differential_testing_modes"]:
            lines.append(f"- {mode_info['mode']}: {mode_info['description']}")

    if "pattern_dedup" in knowledge:
        lines.append("")
        lines.append("### Generation-time Dedup")
        lines.append(knowledge["pattern_dedup"]["strategy"])
        for r in knowledge["pattern_dedup"]["key_rules"]:
            lines.append(f"- {r}")

    if "mutator_pattern" in knowledge:
        lines.append("")
        lines.append("### Mutator Techniques")
        lines.append(knowledge["mutator_pattern"]["strategy"])
        for m in knowledge["mutator_pattern"]["mutation_types"]:
            lines.append(f"- {m}")

    if "validator_pattern" in knowledge:
        lines.append("")
        lines.append("### Validator (reduction only)")
        lines.append(knowledge["validator_pattern"]["strategy"])
        for c in knowledge["validator_pattern"]["validation_checks"]:
            lines.append(f"- {c}")

    lines.append("")
    lines.append("## Universal Design Principles")
    for p in UNIVERSAL_DESIGN_PRINCIPLES:
        lines.append(f"- {p['principle']}: {p['detail']}")

    return "\n".join(lines)