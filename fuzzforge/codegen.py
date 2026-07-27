"""FuzzForge: code generation engine — generates Kotlin source from IR design."""

import os
from pathlib import Path
from typing import Any

from fuzzforge.scaffold import create_project_scaffold

# ---------------------------------------------------------------------------
# Helper: build Kotlin package line
# ---------------------------------------------------------------------------

def _pkg(parts: list[str]) -> str:
    return "package " + ".".join(parts)


# ---------------------------------------------------------------------------
# 1. Enums
# ---------------------------------------------------------------------------

def _gen_enum(enum_name: str, values: list[str], pkg: str) -> str:
    body = ",\n    ".join(values)
    return f"""\
{_pkg([pkg])}

enum class {enum_name} {{
    {body}
}}
"""


# ---------------------------------------------------------------------------
# 2. TreeBuilder.kt
# ---------------------------------------------------------------------------

def _gen_tree_builder(design: dict[str, Any], pkg: str) -> str:
    elements = design.get("tree_builder_elements", [])
    enums = design.get("enums", {})

    # Build element definitions
    def_lines = []
    field_helper = ""

    for elem in elements:
        var_name = elem["var_name"]
        el_name = elem["element_name"]
        kind = elem.get("kind", "Other")
        parent = elem.get("parent")
        interface_kind = elem.get("interface_kind")
        fields = elem.get("fields", [])

        # Interface kind
        ik_str = ""
        if interface_kind:
            ik_str = f"\n        kind = ImplementationKind.{interface_kind}"

        # Parent
        parent_str = ""
        if parent:
            parent_str = f"\n        parent({parent})"

        # Fields
        field_lines = []
        for f in fields:
            fname = f["name"]
            ftype = f["type"]
            is_child = f.get("is_child", True)
            nullable = f.get("nullable", False)
            is_mutable = f.get("is_mutable", True)
            with_transform = f.get("with_transform", True)
            with_replace = f.get("with_replace", False)

            # Determine if it's a list field
            if ftype.startswith("List<"):
                base_type = f.get("list_base_type", ftype[5:-1])
                list_str = f'"{base_type}",'
                field_lines.append(
                    f'        +listField("{fname}", {list_str}\n'
                    f'            withReplace = {str(with_replace).lower()},\n'
                    f'            withTransform = {str(with_transform).lower()},\n'
                    f'            isChild = {str(is_child).lower()})'
                )
            else:
                # Map type names to TypeRef constants
                type_ref = _map_type_ref(ftype, enums)
                nullable_str = str(nullable).lower()
                field_lines.append(
                    f'        +field("{fname}", {type_ref},\n'
                    f'            nullable = {nullable_str},\n'
                    f'            isMutable = {str(is_mutable).lower()},\n'
                    f'            isChild = {str(is_child).lower()},\n'
                    f'            withReplace = {str(with_replace).lower()},\n'
                    f'            withTransform = {str(with_transform).lower()})'
                )

        fields_str = "\n".join(field_lines) if field_lines else ""

        # Build the element DSL block
        if var_name == "element":
            # Root element
            def_lines.append(f"""\
    override val rootElement: Element by element(Element.Kind.{kind}, name = "{el_name}") {{
        hasAcceptChildrenMethod = true
        hasTransformChildrenMethod = true
    }}
""")
        else:
            def_lines.append(f"""\
    val {var_name}: Element by element(Element.Kind.{kind}, name = "{el_name}") {{{ik_str}{parent_str}
{fields_str}
    }}
""")

    # Build type references
    type_refs = []
    for e in elements:
        en = e["element_name"]
        # Lowercase the first letter for the type ref name
        ref_name = en[0].lower() + en[1:] if en else ""
        type_refs.append(f"    val {ref_name}Type = generatedType(\"{en}\")")

    # Build the enum type references
    enum_refs = []
    for enum_name in ["op_kind", "type_kind", "attr_kind", "dim_kind", "block_kind"]:
        vals = enums.get(enum_name, [])
        if vals:
            # Convert snake_case to PascalCase for the Kotlin class name
            class_name = "".join(w.capitalize() for w in enum_name.split("_")) + "Kind"
            ref_name = enum_name  # e.g. "op_kind" -> "opKindType" in the types file
            enum_refs.append(f"    val {enum_name}Type = generatedType(\"{class_name}\")")

    imports = """\
import com.fuzzforge.tree.generator.model.Element
import com.fuzzforge.tree.generator.model.Field
import com.fuzzforge.tree.generator.model.ListField
import com.fuzzforge.tree.generator.model.SimpleField
import org.jetbrains.kotlin.generators.tree.ImplementationKind
import org.jetbrains.kotlin.generators.tree.StandardTypes
import org.jetbrains.kotlin.generators.tree.config.AbstractElementConfigurator
"""

    return f"""\
{imports}

object TreeBuilder : AbstractElementConfigurator<Element, Field, Element.Kind>() {{

    // ---- Type references ----
{chr(10).join(type_refs)}
{chr(10).join(enum_refs)}

    // ---- Elements ----
{chr(10).join(def_lines)}

    // ---- Helper methods ----
    fun field(
        name: String,
        type: TypeRefWithNullability,
        nullable: Boolean = false,
        isMutable: Boolean = true,
        withReplace: Boolean = false,
        withTransform: Boolean = true,
        isChild: Boolean = true,
        initializer: SimpleField.() -> Unit = {{}},
    ): SimpleField {{
        return SimpleField(
            name,
            type.copy(nullable),
            isChild = isChild,
            isMutable = isMutable,
            withReplace = withReplace,
            withTransform = withTransform
        ).apply(initializer)
    }}

    fun listField(
        name: String,
        baseType: TypeRef,
        withReplace: Boolean = false,
        withTransform: Boolean = true,
        useMutableOrEmpty: Boolean = true,
        isChild: Boolean = true,
        initializer: ListField.() -> Unit = {{}},
    ): Field {{
        return ListField(
            name,
            baseType,
            withReplace = withReplace,
            isChild = isChild,
            isMutableOrEmptyList = useMutableOrEmpty,
            withTransform = withTransform,
        ).apply(initializer)
    }}

    override fun createElement(
        name: String,
        propertyName: String,
        category: Element.Kind
    ): Element {{
        return Element(name, propertyName, category)
    }}
}}
"""


def _map_type_ref(ftype: str, enums: dict) -> str:
    """Map a field type string to a Kotlin TypeRef expression."""
    type_map = {
        "String": "StandardTypes.string",
        "Int": "StandardTypes.int",
        "Boolean": "StandardTypes.boolean",
        "Long": "StandardTypes.long",
        "Float": "StandardTypes.float",
    }
    if ftype in type_map:
        return type_map[ftype]

    # Check if it's an enum type
    for enum_name in ["OpKind", "TypeKind", "AttrKind", "DimKind", "BlockKind"]:
        enum_key = enum_name[0].lower() + ("_".join(
            c.lower() for c in re.findall(r'[A-Z][a-z]*', enum_name)
        ) if len(enum_name) > 1 else "")
        if ftype == enum_name:
            return f"{enum_key}Type"

    # Assume it's a generated element type
    ref_name = ftype[0].lower() + ftype[1:]
    return f"{ref_name}Type"


# ---------------------------------------------------------------------------
# 3. PureAbstractElement
# ---------------------------------------------------------------------------

def _gen_pure_abstract(pkg: str) -> str:
    return f"""\
{_pkg([pkg, "ir"])}

interface FuzzForgePureAbstractElement
"""


# ---------------------------------------------------------------------------
# 4. GeneratorConfig.kt
# ---------------------------------------------------------------------------

def _gen_generator_config(design: dict[str, Any], pkg: str) -> str:
    config = design.get("generator_config", {})
    fields = config.get("fields", [])

    field_lines = []
    for f in fields:
        name = f["name"]
        ftype = f["type"]
        default = f.get("default_value", "")
        desc = f.get("description", "")
        comment = f"    // {desc}" if desc else ""
        field_lines.append(f"    val {name}: {ftype} = {default},{comment}")

    fields_str = "\n".join(field_lines)

    return f"""\
{_pkg([pkg, "generator"])}

import kotlin.random.Random

data class GeneratorConfig(
    val seed: Long = System.currentTimeMillis(),
{fields_str}
) {{
    companion object {{
        val default = GeneratorConfig()
    }}
}}
"""


# ---------------------------------------------------------------------------
# 5. Generator.kt
# ---------------------------------------------------------------------------

def _gen_generator(design: dict[str, Any], pkg: str) -> str:
    ir_mode = design.get("ir_mode", "computation_graph")
    project_name = design.get("project_name", "MyFuzzer")
    class_name = f"{project_name.capitalize().replace('-', '').replace('_', '')}Generator"

    elements = design.get("tree_builder_elements", [])
    op_kind_values = design.get("enums", {}).get("op_kind", [])

    # Find the node element
    node_elem = None
    graph_elem = None
    program_elem = None
    for e in elements:
        if e["element_name"] == "Node":
            node_elem = e
        elif e["element_name"] == "Graph":
            graph_elem = e
        elif e["element_name"] == "Program":
            program_elem = e

    body = ""

    if ir_mode == "computation_graph" and node_elem:
        body = f"""\
    private val random: Random = Random.Default

    fun generate(): Program {{
        val program = ProgramImpl(mutableListOf(), mutableMapOf())
        val numGraphs = random.nextInt(1, 4)
        for (g in 0 until numGraphs) {{
            val graph = generateGraph()
            program.graphs.add(graph)
        }}
        return program
    }}

    private fun generateGraph(): Graph {{
        val numNodes = random.nextInt(config.minNodesPerGraph, config.maxNodesPerGraph + 1)
        val numInputs = random.nextInt(config.minInputs, config.maxInputs + 1)
        val availableValues = mutableListOf<ValueRef>()

        // Create input values
        val inputs = mutableListOf<ValueRef>()
        for (i in 0 until numInputs) {{
            val valueRef = ValueRefImpl(
                valueId = "v_input_${{i}}_{random.nextLong().toString(36)}",
                type = generateTensorType()
            )
            inputs.add(valueRef)
            availableValues.add(valueRef)
        }}

        // Create nodes
        val nodes = mutableListOf<Node>()
        for (n in 0 until numNodes) {{
            val node = generateNode(availableValues)
            nodes.add(node)
            // Add node outputs to available values
            for (output in node.outputs) {{
                availableValues.add(output)
            }}
        }}

        // Select outputs from available values
        val numOutputs = minOf(random.nextInt(1, 4), availableValues.size)
        val outputs = availableValues.shuffled(random).take(numOutputs).toMutableList()

        return GraphImpl(
            name = "graph_${{random.nextInt()}}",
            nodes = nodes,
            inputs = inputs,
            outputs = outputs,
        )
    }}

    private fun generateNode(availableValues: List<ValueRef>): Node {{
        val op = selectOp()
        val numInputs = when (op) {{
            {_gen_op_input_count(op_kind_values)}
            else -> 1
        }}
        val actualInputs = minOf(numInputs, availableValues.size)
        val selectedInputs = if (availableValues.isEmpty()) {{
            mutableListOf()
        }} else {{
            availableValues.shuffled(random).take(actualInputs).toMutableList()
        }}
        val numOutputs = random.nextInt(1, 3)
        val outputs = mutableListOf<ValueRef>()
        for (o in 0 until numOutputs) {{
            outputs.add(ValueRefImpl(
                valueId = "v_${{random.nextLong().toString(36)}}",
                type = generateTensorType()
            ))
        }}
        return NodeImpl(
            name = "node_${{random.nextInt()}}",
            op = op,
            inputs = selectedInputs,
            outputs = outputs,
            attributes = mutableMapOf(),
        )
    }}

    private fun selectOp(): OpKind {{
        val ops = config.ops
        val allOps = OpKind.entries.toList()
        val filtered = if (ops.isEmpty()) allOps else allOps.filter {{ it.name in ops }}
        if (filtered.isEmpty()) return OpKind.ADD
        return filtered[random.nextInt(filtered.size)]
    }}

    private fun generateTensorType(): TensorType {{
        val ndim = random.nextInt(2, 5)
        val dims = mutableListOf<Dim>()
        for (d in 0 until ndim) {{
            dims.add(DimImpl(DimKind.CONSTANT, random.nextInt(1, 17)))
        }}
        return TensorTypeImpl(
            typeKind = TypeKind.TENSOR,
            shape = ShapeImpl(dims),
            dtype = DataTypeImpl("float32", 32),
        )
    }}
"""
    else:
        # Generic fallback generator
        body = f"""\
    private val random: Random = Random.Default

    fun generate(): Program {{
        // TODO: implement domain-specific generator logic
        return ProgramImpl(mutableListOf(), mutableMapOf())
    }}
"""

    return f"""\
{_pkg([pkg, "generator"])}

import kotlin.random.Random
import com.fuzzforge.ir.*
import com.fuzzforge.ir.types.*
import com.fuzzforge.ir.impl.*
import com.fuzzforge.ir.types.impl.*

class {class_name}(
    private val config: GeneratorConfig = GeneratorConfig.default,
) {{
{body}
}}
"""


def _gen_op_input_count(op_kind_values: list[str]) -> str:
    """Generate the when-branch for op input counts."""
    unary_ops = {"NEG", "ABS", "SIGN", "EXP", "LOG", "LOG2", "SQRT", "RSQRT",
                 "RECIPROCAL", "CEIL", "FLOOR", "ROUND", "RELU", "LEAKY_RELU",
                 "ELU", "SELU", "MISH", "HARDTANH", "SIGMOID", "TANH", "GELU",
                 "SILU", "SOFTMAX", "LOG_SOFTMAX", "CAST"}
    binary_ops = {"ADD", "SUBTRACT", "MULTIPLY", "DIVIDE", "MAXIMUM", "MINIMUM", "POWER"}

    lines = []
    for op in op_kind_values:
        if op in unary_ops:
            lines.append(f"            OpKind.{op} -> 1")
        elif op in binary_ops:
            lines.append(f"            OpKind.{op} -> 2")
        else:
            lines.append(f"            OpKind.{op} -> random.nextInt(1, 3)")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 6. Translator interface + default implementation
# ---------------------------------------------------------------------------

def _gen_translator_interface(design: dict[str, Any], pkg: str) -> str:
    mode = design.get("ir_mode", "computation_graph")
    targets = design.get("translator_targets", [])
    project_name = design.get("project_name", "MyFuzzer")
    class_name = f"{project_name.capitalize().replace('-', '').replace('_', '')}Translator"

    target_comment = "\n".join(f" *   - {t}" for t in targets)

    return f"""\
{_pkg([pkg, "translator"])}

import com.fuzzforge.ir.Program

/**
 * Translator interface: converts FuzzForge IR to target backend code.
 *
 * Supported targets:
{target_comment}
 */
interface FuzzForgeTranslator<R> {{
    fun translate(program: Program): R
}}

/**
 * Default translator that outputs a textual representation of the IR.
 * Useful as a starting point before implementing real backends.
 */
class {class_name} : FuzzForgeTranslator<String> {{
    override fun translate(program: Program): String {{
        val sb = StringBuilder()
        sb.appendLine("// Generated by FuzzForge - {project_name}")
        sb.appendLine()
        for ((i, graph) in program.graphs.withIndex()) {{
            sb.appendLine("// === Graph ${{i + 1}}: ${{graph.name}} ===")
            sb.appendLine("// Inputs: ${{graph.inputs.size}}")
            for (input in graph.inputs) {{
                sb.appendLine("//   ${{input.valueId}}: ${{renderType(input.type)}}")
            }}
            sb.appendLine("// Nodes: ${{graph.nodes.size}}")
            for (node in graph.nodes) {{
                val inputIds = node.inputs.joinToString(", ") {{ it.valueId }}
                val outputIds = node.outputs.joinToString(", ") {{ it.valueId }}
                sb.appendLine("//   ${{node.name}}: ${{node.op}}($inputIds) -> [$outputIds]")
            }}
            sb.appendLine("// Outputs: ${{graph.outputs.size}}")
            for (output in graph.outputs) {{
                sb.appendLine("//   ${{output.valueId}}: ${{renderType(output.type)}}")
            }}
            sb.appendLine()
        }}
        return sb.toString()
    }}

    private fun renderType(type: com.fuzzforge.ir.types.TensorType): String {{
        val dims = type.shape.dims.joinToString("x") {{ dim ->
            dim.value?.toString() ?: "?"
        }}
        return "Tensor[$dims]:${{type.dtype.name}}"
    }}
}}
"""


# ---------------------------------------------------------------------------
# 7. Runner
# ---------------------------------------------------------------------------

def _gen_runner(design: dict[str, Any], pkg: str) -> str:
    project_name = design.get("project_name", "MyFuzzer")
    class_name = f"{project_name.capitalize().replace('-', '').replace('_', '')}Runner"

    return f"""\
{_pkg([pkg, "runner"])}

import com.fuzzforge.generator.{project_name.capitalize().replace('-', '').replace('_', '')}Generator
import com.fuzzforge.translator.{project_name.capitalize().replace('-', '').replace('_', '')}Translator
import com.fuzzforge.config.RunConfig
import com.fuzzforge.ir.Program
import kotlinx.coroutines.*
import java.io.File
import kotlin.system.measureTimeMillis

data class RunResult(
    val success: Boolean,
    val stdout: String,
    val stderr: String,
    val exitCode: Int,
    val durationMs: Long,
)

class {class_name}(
    private val config: RunConfig,
) {{
    private val generator = {project_name.capitalize().replace('-', '').replace('_', '')}Generator(config.generatorConfig)
    private val translator = {project_name.capitalize().replace('-', '').replace('_', '')}Translator()

    suspend fun runSingle(seed: Long? = null): RunResult {{
        val program = if (seed != null) {{
            {project_name.capitalize().replace('-', '').replace('_', '')}Generator(config.generatorConfig.copy(seed = seed)).generate()
        }} else {{
            generator.generate()
        }}

        val code = translator.translate(program)
        val outputDir = File(config.outputDir)
        if (!outputDir.exists()) outputDir.mkdirs()

        val sourceFile = File(outputDir, "generated_output.txt")
        sourceFile.writeText(code)

        return RunResult(
            success = true,
            stdout = code,
            stderr = "",
            exitCode = 0,
            durationMs = 0,
        )
    }}

    suspend fun runBatch(count: Int): List<RunResult> = coroutineScope {{
        val results = mutableListOf<RunResult>()
        for (i in 0 until count) {{
            results.add(runSingle())
        }}
        results
    }}
}}
"""


# ---------------------------------------------------------------------------
# 8. RunConfig
# ---------------------------------------------------------------------------

def _gen_run_config(pkg: str) -> str:
    return f"""\
{_pkg([pkg, "config"])}

import com.fuzzforge.generator.GeneratorConfig

data class RunConfig(
    val outputDir: String = "./reports",
    val logLevel: String = "info",
    val workers: Int = 4,
    val batchSize: Int = 200,
    val runTimeoutSeconds: Int = 120,
    val generatorConfig: GeneratorConfig = GeneratorConfig.default,
) {{
    companion object {{
        val default = RunConfig()
    }}
}}
"""


# ---------------------------------------------------------------------------
# 9. App.kt
# ---------------------------------------------------------------------------

def _gen_app(design: dict[str, Any], pkg: str) -> str:
    project_name = design.get("project_name", "MyFuzzer")
    class_name = f"{project_name.capitalize().replace('-', '').replace('_', '')}"

    return f"""\
{_pkg([pkg, "cli"])}

import com.github.ajalt.clikt.core.CliktCommand
import com.github.ajalt.clikt.core.context
import com.github.ajalt.clikt.core.subcommands
import com.github.ajalt.clikt.parameters.options.*
import com.github.ajalt.clikt.output.MordantHelpFormatter
import com.fuzzforge.config.RunConfig
import com.fuzzforge.generator.{class_name}Generator
import com.fuzzforge.runner.{class_name}Runner
import kotlinx.coroutines.runBlocking

/**
 * {class_name} CLI — Fuzzer generated by FuzzForge.
 *
 * Target: {design.get("description", "AI compiler fuzzing")}
 * IR mode: {design.get("ir_mode", "computation_graph")}
 */
class {class_name}Command : CliktCommand(
    name = "{project_name.lowercase()}",
    help = "{design.get("description", "Fuzzer generated by FuzzForge")}",
) {{
    init {{
        context {{ helpFormatter = {{ MordantHelpFormatter(it, showDefaultValues = true) }} }}
        subcommands(RunCommand(), GenerateCommand())
    }}

    override fun run() {{
        echo("{class_name} — Fuzzer generated by FuzzForge")
        echo("Run with a subcommand: run or generate")
        echo("Use --help on any subcommand for details.")
    }}
}}

class RunCommand : CliktCommand(name = "run", help = "Run fuzzing campaign") {{
    val count: Int by option("-n", "--count", help = "Number of programs to generate and run")
        .int().default(10)
    val output: String by option("-o", "--output", help = "Output directory")
        .default("./reports")

    override fun run() {{
        echo("Running fuzzing campaign: $count programs")
        val config = RunConfig(outputDir = output)
        val runner = {class_name}Runner(config)
        runBlocking {{
            val results = runner.runBatch(count)
            val successes = results.count {{ it.success }}
            echo("Done: $successes/$count succeeded")
        }}
    }}
}}

class GenerateCommand : CliktCommand(name = "generate", help = "Generate programs only (no execution)") {{
    val count: Int by option("-n", "--count", help = "Number of programs to generate")
        .int().default(5)
    val output: String by option("-o", "--output", help = "Output directory")
        .default("./generated")

    override fun run() {{
        val generator = {class_name}Generator()
        for (i in 0 until count) {{
            val program = generator.generate()
            echo("Generated program ${{i + 1}}: ${{program.graphs.size}} graphs")
        }}
        echo("Generated $count programs to $output")
    }}
}}

fun main(args: Array<String>) = {class_name}Command().main(args)
"""


# ---------------------------------------------------------------------------
# 10. Build files
# ---------------------------------------------------------------------------

def _gen_settings(project_name: str) -> str:
    safe_name = project_name.lower().replace("-", "").replace("_", "")
    return f"""\
pluginManagement {{
    plugins {{
        kotlin("jvm") version "2.4.0"
    }}
}}
rootProject.name = "{safe_name}"

include(":tree")
include(":tree:tree-generator")
"""


def _gen_root_build(project_name: str) -> str:
    safe_name = project_name.lower().replace("-", "").replace("_", "")
    class_name = "".join(w.capitalize() for w in project_name.replace("-", " ").replace("_", " ").split())

    return f"""\
plugins {{
    id("java")
    kotlin("jvm")
    application
    kotlin("plugin.serialization") version "2.4.0"
}}

group = "com.fuzzforge"
version = "1.0-SNAPSHOT"

repositories {{
    mavenCentral()
}}

kotlin {{
    jvmToolchain(17)
}}

dependencies {{
    testImplementation(platform("org.junit:junit-bom:6.0.0"))
    testImplementation("org.junit.jupiter:junit-jupiter")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
    implementation(kotlin("stdlib"))
    implementation(project(":tree"))
    implementation("org.yaml:snakeyaml:2.0")
    implementation("com.github.ajalt.clikt:clikt-jvm:4.2.2")
    implementation("org.jetbrains.kotlinx:kotlinx-serialization-json:1.7.3")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-core:1.9.0")
    implementation("io.github.oshai:kotlin-logging-jvm:7.0.3")
    implementation("ch.qos.logback:logback-classic:1.5.18")
}}

application {{
    mainClass = "com.fuzzforge.cli.{class_name}CommandKt"
}}

sourceSets {{
    main {{
        kotlin {{
            srcDirs("src/main/kotlin")
        }}
    }}
}}

tasks.test {{
    useJUnitPlatform()
}}
"""


def _gen_tree_build(project_name: str) -> str:
    return f"""\
plugins {{
    kotlin("jvm")
    kotlin("plugin.serialization") version "2.4.0"
}}

repositories {{
    mavenCentral()
}}

sourceSets {{
    main {{
        kotlin.srcDir("src")
    }}
}}

val generateTree = tasks.register<JavaExec>("generateTree") {{
    group = "generation"
    description = "Generate IR tree sources into tree/gen"

    workingDir = rootDir
    classpath = project(":tree:tree-generator").sourceSets.main.get().runtimeClasspath
    mainClass.set("com.fuzzforge.tree.generator.MainKt")

    val generationRoot = layout.projectDirectory.dir("gen")
    args(generationRoot.asFile.absolutePath)

    systemProperties["line.separator"] = "\\n"

    val generatorSourceRoot = rootDir.resolve("tree/tree-generator/src")
    val generatorConfigFiles = fileTree(generatorSourceRoot) {{
        include("**/*.kt")
    }}
    inputs.files(generatorConfigFiles)
    outputs.dir(generationRoot)
}}

sourceSets.main.configure {{
    kotlin.srcDir(layout.projectDirectory.dir("gen"))
}}

tasks.compileKotlin {{
    dependsOn(generateTree)
}}

kotlin {{
    jvmToolchain(17)
}}

dependencies {{
    implementation("org.jetbrains.kotlinx:kotlinx-serialization-json:1.7.3")
}}
"""


def _gen_tree_generator_build() -> str:
    return """\
plugins {
    kotlin("jvm")
    application
}

repositories {
    mavenCentral()
}

kotlin {
    jvmToolchain(17)
}

application {
    mainClass = "com.fuzzforge.tree.generator.MainKt"
}

tasks.named<JavaExec>("run") {
    workingDir = rootDir
}

dependencies {
    implementation(files(rootProject.file("libs/tree-generator-common.jar")))
    testImplementation(kotlin("test"))
}
"""


# ---------------------------------------------------------------------------
# 11. Default config YAML
# ---------------------------------------------------------------------------

def _gen_default_config(project_name: str) -> str:
    return f"""\
# {project_name} — default fuzzing configuration
run:
  description: "{project_name} fuzzing campaign"
  seed: null
  output_dir: "./reports"
  log_level: "info"

generator:
  min_nodes: 5
  max_nodes: 40
  min_inputs: 1
  max_inputs: 4
  strategy: "random"
  ops:
    include_all: true

pipeline:
  workers: 4
  batch_size: 200
  run_timeout_seconds: 120
  reducer:
    enabled: true
"""


# ---------------------------------------------------------------------------
# Main entry point: generate full project
# ---------------------------------------------------------------------------

import re


def generate_project(design: dict[str, Any], output_dir: str) -> str:
    """Generate the complete Kotlin fuzzer project from IR design.

    Returns the path to the generated project root.
    """
    project_name = design.get("project_name", "my-fuzzer")
    pkg = "com.fuzzforge"
    tree_pkg = "com.fuzzforge"
    generator_pkg = "com.fuzzforge.tree.generator"

    dirs = create_project_scaffold(output_dir, project_name)

    elements = design.get("tree_builder_elements", [])
    enums = design.get("enums", {})

    # ---- Write enums ----
    for enum_name, values in enums.items():
        if not values:
            continue
        class_name = "".join(w.capitalize() for w in enum_name.split("_")) + "Kind"
        content = _gen_enum(class_name, values, f"{pkg}.ir")
        Path(dirs["tree_src"]) / f"{class_name}.kt"

    # Write specific enum files
    enum_map = {
        "op_kind": "OpKind",
        "type_kind": "TypeKind",
        "attr_kind": "AttrKind",
        "dim_kind": "DimKind",
        "block_kind": "BlockKind",
    }
    for key, class_name in enum_map.items():
        values = enums.get(key, [])
        if values:
            content = _gen_enum(class_name, values, f"{tree_pkg}.ir")
            Path(dirs["tree_src"]).joinpath(f"{class_name}.kt").write_text(content)

    # ---- Write PureAbstractElement ----
    Path(dirs["tree_src"]).joinpath("FuzzForgePureAbstractElement.kt").write_text(
        _gen_pure_abstract(tree_pkg)
    )

    # ---- Write TreeBuilder.kt ----
    tb_path = Path(dirs["tree_generator"]) / "TreeBuilder.kt"
    tb_path.write_text(_gen_tree_builder(design, generator_pkg))

    # ---- Write Main.kt for tree-generator ----
    main_path = Path(dirs["tree_generator"]) / "main.kt"
    main_path.write_text(
        _gen_tree_generator_main(generator_pkg)
    )

    # ---- Write GeneratorConfig.kt ----
    Path(dirs["src_config"]).joinpath("GeneratorConfig.kt").write_text(
        _gen_generator_config(design, pkg)
    )

    # ---- Write Generator.kt ----
    Path(dirs["src_generator"]).joinpath("Generator.kt").write_text(
        _gen_generator(design, pkg)
    )

    # ---- Write Translator ----
    Path(dirs["src_translator"]).joinpath("Translator.kt").write_text(
        _gen_translator_interface(design, pkg)
    )

    # ---- Write Runner ----
    Path(dirs["src_runner"]).joinpath("Runner.kt").write_text(
        _gen_runner(design, pkg)
    )

    # ---- Write RunConfig ----
    Path(dirs["src_config"]).joinpath("RunConfig.kt").write_text(
        _gen_run_config(pkg)
    )

    # ---- Write App.kt (CLI) ----
    Path(dirs["src_cli"]).joinpath("App.kt").write_text(
        _gen_app(design, pkg)
    )

    # ---- Write build files ----
    Path(dirs["output"]).joinpath("settings.gradle.kts").write_text(
        _gen_settings(project_name)
    )
    Path(dirs["output"]).joinpath("build.gradle.kts").write_text(
        _gen_root_build(project_name)
    )
    Path(dirs["output"]).joinpath("tree", "build.gradle.kts").write_text(
        _gen_tree_build(project_name)
    )
    Path(dirs["output"]).joinpath("tree", "tree-generator", "build.gradle.kts").write_text(
        _gen_tree_generator_build()
    )

    # ---- Write default config ----
    Path(dirs["configs"]).joinpath("default.yaml").write_text(
        _gen_default_config(project_name)
    )

    # ---- Write README.md ----
    readme = f"""# {project_name}

Fuzzer generated by **FuzzForge**.

Target: {design.get("description", "N/A")}
IR mode: {design.get("ir_mode", "computation_graph")}

## Build

```bash
# Download tree-generator-common.jar first
# See the tool's documentation for download instructions
mkdir -p libs
# Place tree-generator-common.jar in libs/

./gradlew :tree:generateTree
./gradlew build
```

## Run

```bash
./gradlew :run --args="run -n 100"
./gradlew :run --args="generate -n 10"
```

## Project Structure

```
tree/              # IR data structure (auto-generated)
├── src/           # Hand-written enums, DSL, utils
├── gen/           # Auto-generated IR code (DO NOT EDIT)
└── tree-generator/# TreeBuilder meta-model
src/main/kotlin/   # Generator, Translator, Runner, Reducer
configs/           # YAML run configurations
```
"""
    Path(dirs["output"]).joinpath("README.md").write_text(readme)

    # ---- Write .gitignore ----
    gitignore = """\
.gradle/
build/
out/
*.class
.idea/
*.iml
local.properties
gen/
"""
    Path(dirs["output"]).joinpath(".gitignore").write_text(gitignore)

    return str(dirs["output"])


def _gen_tree_generator_main(pkg: str) -> str:
    return f"""\
package {pkg}

import {pkg}.printer.BuilderPrinter
import {pkg}.printer.DefaultVisitorVoidPrinter
import {pkg}.printer.ElementPrinter
import {pkg}.printer.ImplementationPrinter
import {pkg}.printer.TransformerPrinter
import {pkg}.printer.VisitorPrinter
import {pkg}.printer.VisitorVoidPrinter
import org.jetbrains.kotlin.generators.tree.InterfaceAndAbstractClassConfigurator
import org.jetbrains.kotlin.generators.tree.detectBaseTransformerTypes
import org.jetbrains.kotlin.generators.tree.printer.TreeGenerator
import java.io.File

fun main(args: Array<String>) {{
    val model = TreeBuilder.build()
    TreeGenerator(File("tree/gen"), "README.md").run {{
        model.inheritFields()
        detectBaseTransformerTypes(model)

        ImplConfigurator.configureImplementations(model)
        val implementations = model.elements.flatMap {{ it.implementations }}
        InterfaceAndAbstractClassConfigurator((model.elements + implementations))
            .configureInterfacesAndAbstractClasses()
        model.addPureAbstractElement(pureAbstractElementType)

        val builderConfigurator = BuilderConfigurator(model)
        builderConfigurator.configureBuilders()

        printElements(model, ::ElementPrinter)
        printElementImplementations(implementations, ::ImplementationPrinter)
        printElementBuilders(
            implementations.mapNotNull {{ it.builder }},
            ::BuilderPrinter
        )
        printVisitors(
            model,
            listOf(
                irVisitorType to {{ p, t -> VisitorPrinter(p, t, false) }},
                irDefaultVisitorType to {{ p, t -> VisitorPrinter(p, t, true) }},
                irVisitorVoidType to {{ p, t -> VisitorVoidPrinter(p, t) }},
                irDefaultVisitorVoidType to {{ p, t -> DefaultVisitorVoidPrinter(p, t) }},
                irTransformerType to {{ p, t -> TransformerPrinter(p, t, model.rootElement) }},
            )
        )
    }}
}}
"""