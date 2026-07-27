"""
FuzzForge: code generation engine — generates Kotlin source from IR design.

Architecture follows a 3-phase model (inspired by WhiteFox):
  Phase 1 (Planning): IR design → JSON
  Phase 2 (Generation): IR design + templates → Kotlin project (this module)
  Phase 3 (Feedback): Build errors → LLM patches → rebuild (healer.py)
"""

import os
import re
import shutil
from pathlib import Path
from typing import Any

from fuzzforge.scaffold import create_project_scaffold


def _pkg(parts: list[str]) -> str:
    return "package " + ".".join(parts)


# ---------------------------------------------------------------------------
# Phase 2a: Copy tree-generator boilerplate (from aiFuzzer, verified working)
# ---------------------------------------------------------------------------

def _copy_tree_generator_boilerplate(output_dir: str) -> None:
    """Copy the tree-generator boilerplate from aiFuzzer.

    These files are verified to work with the tree-generator-common.jar we have.
    We only change the package name and enum type names.
    """
    base = Path(output_dir)

    # license directory (needed by tree-generator-common.jar)
    license_src = Path("/root/Code/kotlin/aifuzzer/license")
    license_dst = base / "license"
    if license_src.exists() and not license_dst.exists():
        shutil.copytree(str(license_src), str(license_dst))

    # tree-generator source
    tgen_src = Path("/root/Code/kotlin/aifuzzer/tree/tree-generator/src/main/kotlin/io/github/xyzboom/aiFuzzer/tree/generator")
    tgen_dst = base / "tree" / "tree-generator" / "src" / "main" / "kotlin" / "com" / "fuzzforge" / "tree" / "generator"
    if tgen_src.exists():
        if tgen_dst.exists():
            shutil.rmtree(tgen_dst)
        shutil.copytree(str(tgen_src), str(tgen_dst))
        for f in tgen_dst.rglob("*.kt"):
            content = f.read_text()
            content = content.replace("io.github.xyzboom.aiFuzzer", "com.fuzzforge")
            content = content.replace("UirTypeKind", "TypeKind")
            content = content.replace("UirDimKind", "DimKind")
            content = content.replace("UirAttrKind", "AttrKind")
            content = content.replace("UirBlockKind", "BlockKind")
            content = content.replace("UirOpKind", "OpKind")
            f.write_text(content)

    # ir support files
    ir_src = Path("/root/Code/kotlin/aifuzzer/tree/src/io/github/xyzboom/aiFuzzer/ir")
    ir_dst = base / "tree" / "src" / "main" / "kotlin" / "com" / "fuzzforge" / "ir"
    for fname in ["visitors/transformInplace.kt", "builder/BuilderDsl.kt", "UirPureAbstractElement.kt"]:
        src = ir_src / fname
        dst = ir_dst / fname
        if src.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            content = src.read_text()
            content = content.replace("io.github.xyzboom.aiFuzzer", "com.fuzzforge")
            dst.write_text(content)

    # IrImplementationDetail marker
    (ir_dst / "IrImplementationDetail.kt").write_text("""package com.fuzzforge.ir

@RequiresOptIn(message = "This is an implementation detail of the FuzzForge IR tree")
@Retention(AnnotationRetention.BINARY)
@Target(AnnotationTarget.CLASS, AnnotationTarget.FUNCTION)
annotation class IrImplementationDetail
""")


# ---------------------------------------------------------------------------
# Phase 2b: Generate ImplConfigurator + BuilderConfigurator from design
# ---------------------------------------------------------------------------

def _gen_impl_configurator(elements: list[dict]) -> str:
    names = [e["var_name"] for e in elements if e["var_name"] not in ("element", "rootElement")]
    impl_lines = "\n".join(f"        impl({name})" for name in names)
    return f"""package com.fuzzforge.tree.generator

import com.fuzzforge.tree.generator.model.Element
import com.fuzzforge.tree.generator.model.Field
import com.fuzzforge.tree.generator.model.Implementation
import org.jetbrains.kotlin.generators.tree.Model
import org.jetbrains.kotlin.generators.tree.config.AbstractImplementationConfigurator

object ImplConfigurator : AbstractImplementationConfigurator<Implementation, Element, Field>() {{
    override fun createImplementation(element: Element, name: String?): Implementation =
        Implementation(element, name)

    override fun configure(model: Model<Element>) = with(TreeBuilder) {{
{impl_lines}
        Unit
    }}

    override fun configureAllImplementations(model: Model<Element>) {{ }}
}}
"""


def _gen_builder_configurator(elements: list[dict]) -> str:
    names = [e["var_name"] for e in elements if e["var_name"] not in ("element", "rootElement")]
    builder_lines = "\n".join(f"        builder({name}) {{ }}" for name in names)
    return f"""package com.fuzzforge.tree.generator

import com.fuzzforge.tree.generator.model.Element
import com.fuzzforge.tree.generator.model.Field
import com.fuzzforge.tree.generator.model.Implementation
import org.jetbrains.kotlin.generators.tree.config.AbstractBuilderConfigurator

class BuilderConfigurator(model: org.jetbrains.kotlin.generators.tree.Model<Element>) :
    AbstractBuilderConfigurator<Element, Implementation, Field>(model) {{

    override val namePrefix: String get() = "Uir"
    override val defaultBuilderPackage: String get() = "com.fuzzforge.ir.builder"

    override fun configureBuilders() = with(TreeBuilder) {{
{builder_lines}
    }}
}}
"""


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

def _gen_enum(enum_name: str, values: list[str], pkg: str) -> str:
    sep = ",\n    "
    return f"""\
{_pkg([pkg])}

enum class {enum_name} {{
    {sep.join(values)}
}}
"""


# ---------------------------------------------------------------------------
# TreeBuilder.kt
# ---------------------------------------------------------------------------

ENUM_VAR_MAP = {
    "OpKind": "opKindType", "TypeKind": "typeKindType",
    "AttrKind": "attrKindType", "DimKind": "dimKindType",
    "BlockKind": "blockKindType", "ClassKind": "classKindType",
    "Language": "languageType",
}

def _map_type_ref(ftype: str) -> str:
    if ftype in ("String", "Int", "Boolean", "Long", "Float"):
        return {"String": "StandardTypes.string", "Int": "StandardTypes.int",
                "Boolean": "StandardTypes.boolean", "Long": "StandardTypes.long",
                "Float": "StandardTypes.float"}[ftype]
    if ftype in ENUM_VAR_MAP:
        return ENUM_VAR_MAP[ftype]
    return ftype[0].lower() + ftype[1:] + "Type"


def _gen_tree_builder(design: dict[str, Any]) -> str:
    elements = design.get("tree_builder_elements", [])
    enums = design.get("enums", {})
    enum_var_map = ENUM_VAR_MAP

    # Type references
    type_refs = []
    for e in elements:
        en = e["element_name"]
        ref_name = en[0].lower() + en[1:]
        type_refs.append(f"    val {ref_name}Type = generatedType(\"Uir{en}\")")

    # Enum type references
    seen_enum_vars = set()
    enum_refs = []
    for e in elements:
        for f in e.get("fields", []):
            ftype = f["type"]
            if ftype in enum_var_map and enum_var_map[ftype] not in seen_enum_vars:
                enum_refs.append(f"    val {enum_var_map[ftype]} = generatedType(\"{ftype}\")")
                seen_enum_vars.add(enum_var_map[ftype])

    # Element definitions
    def_lines = []
    for e in elements:
        var_name = e["var_name"]
        el_name = e["element_name"]
        kind = e.get("kind", "Other")
        parent = e.get("parent")
        ik = e.get("interface_kind")
        fields = e.get("fields", [])

        parts = [f'    val {var_name}: Element by element(Element.Kind.{kind}, name = "{el_name}") {{']
        if ik:
            parts.append(f'        kind = ImplementationKind.{ik}')
        if parent:
            parts.append(f'        parent({parent})')
        for f in fields:
            fname = f["name"]
            ftype = f["type"]
            if ftype.startswith("List<"):
                bt = f.get("list_base_type", ftype[5:-1])
                bref = bt[0].lower() + bt[1:]
                parts.append(f'        +listField("{fname}", {bref}Type,')
                parts.append(f'            isChild = {str(f.get("is_child", True)).lower()})')
            else:
                ref = _map_type_ref(ftype)
                parts.append(f'        +field("{fname}", {ref},')
                parts.append(f'            nullable = {str(f.get("nullable", False)).lower()},')
                parts.append(f'            isChild = {str(f.get("is_child", True)).lower()},')
                parts.append(f'            withTransform = {str(f.get("with_transform", True)).lower()})')
        parts.append("    }")
        def_lines.append("\n".join(parts))

    imports = """\
package com.fuzzforge.tree.generator

import com.fuzzforge.tree.generator.model.Element
import com.fuzzforge.tree.generator.model.Field
import com.fuzzforge.tree.generator.model.ListField
import com.fuzzforge.tree.generator.model.SimpleField
import org.jetbrains.kotlin.generators.tree.ImplementationKind
import org.jetbrains.kotlin.generators.tree.StandardTypes
import org.jetbrains.kotlin.generators.tree.TypeRef
import org.jetbrains.kotlin.generators.tree.TypeRefWithNullability
import org.jetbrains.kotlin.generators.tree.config.AbstractElementConfigurator
import org.jetbrains.kotlin.generators.tree.withArgs
"""

    elements_str = "\n\n".join(def_lines)

    return f"""\
{imports}

object TreeBuilder : AbstractElementConfigurator<Element, Field, Element.Kind>() {{

    // ---- Type references ----
{chr(10).join(type_refs)}
{chr(10).join(enum_refs)}

    // ---- Elements ----
    override val rootElement: Element by element(Element.Kind.Other, name = "Element") {{
        hasAcceptChildrenMethod = true
        hasTransformChildrenMethod = true
    }}

{elements_str}

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
        return SimpleField(name, type.copy(nullable), isChild = isChild, isMutable = isMutable,
            withReplace = withReplace, withTransform = withTransform).apply(initializer)
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
        return ListField(name, baseType, withReplace = withReplace, isChild = isChild,
            isMutableOrEmptyList = useMutableOrEmpty, withTransform = withTransform).apply(initializer)
    }}

    override fun createElement(name: String, propertyName: String, category: Element.Kind): Element {{
        return Element(name, propertyName, category)
    }}
}}
"""


# ---------------------------------------------------------------------------
# Generator Config
# ---------------------------------------------------------------------------

def _gen_generator_config(design: dict[str, Any], pkg: str) -> str:
    fields = design.get("generator_config", {}).get("fields", [])
    field_lines = []
    for f in fields:
        desc = f.get("description", "")
        field_lines.append(f"    val {f['name']}: {f['type']} = {f.get('default_value', '')}    // {desc}")
    return f"""\
{_pkg([pkg, "generator"])}

data class GeneratorConfig(
    val seed: Long = System.currentTimeMillis(),
{chr(10).join(field_lines)}
) {{
    companion object {{
        val default = GeneratorConfig()
    }}
}}
"""


# ---------------------------------------------------------------------------
# Generator, Translator, Runner, Config, CLI, Build files
# ---------------------------------------------------------------------------

def _gen_generator(design: dict[str, Any], pkg: str) -> str:
    pn = design.get("project_name", "my-fuzzer")
    cn = pn.capitalize().replace("-", "").replace("_", "") + "Generator"
    return f"""\
{_pkg([pkg, "generator"])}

import kotlin.random.Random
import com.fuzzforge.ir.UirProgram
import com.fuzzforge.ir.impl.UirProgramImpl
import com.fuzzforge.ir.builder.buildUirProgram

class {cn}(
    private val config: GeneratorConfig = GeneratorConfig.default,
) {{
    private val random: Random = Random.Default

    fun generate(): UirProgram {{
        return buildUirProgram()
    }}
}}
"""


def _gen_translator(design: dict[str, Any], pkg: str) -> str:
    pn = design.get("project_name", "my-fuzzer")
    cn = pn.capitalize().replace("-", "").replace("_", "") + "Translator"
    return f"""\
{_pkg([pkg, "translator"])}

import com.fuzzforge.ir.UirProgram

interface FuzzForgeTranslator<R> {{
    fun translate(program: UirProgram): R
}}

class {cn} : FuzzForgeTranslator<String> {{
    override fun translate(program: UirProgram): String {{
        return "Generated by FuzzForge"
    }}
}}
"""


def _gen_runner(design: dict[str, Any], pkg: str) -> str:
    pn = design.get("project_name", "my-fuzzer")
    base = pn.capitalize().replace("-", "").replace("_", "")
    return f"""\
{_pkg([pkg, "runner"])}

import com.fuzzforge.generator.{base}Generator
import com.fuzzforge.translator.{base}Translator
import com.fuzzforge.config.RunConfig
import kotlinx.coroutines.*
import java.io.File

data class RunResult(val success: Boolean, val stdout: String, val stderr: String, val exitCode: Int, val durationMs: Long)

class {base}Runner(
    private val config: RunConfig,
) {{
    private val generator = {base}Generator(config.generatorConfig)
    private val translator = {base}Translator()

    suspend fun runSingle(seed: Long? = null): RunResult {{
        val program = if (seed != null) {{
            {base}Generator(config.generatorConfig.copy(seed = seed)).generate()
        }} else {{
            generator.generate()
        }}
        val code = translator.translate(program)
        return RunResult(success = true, stdout = code, stderr = "", exitCode = 0, durationMs = 0)
    }}

    suspend fun runBatch(count: Int): List<RunResult> = coroutineScope {{
        (0 until count).map {{ runSingle() }}
    }}
}}
"""


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


def _gen_app(design: dict[str, Any], pkg: str) -> str:
    pn = design.get("project_name", "my-fuzzer")
    base = pn.capitalize().replace("-", "").replace("_", "")
    return f"""\
{_pkg([pkg, "cli"])}

import com.github.ajalt.clikt.core.CliktCommand
import com.github.ajalt.clikt.core.context
import com.github.ajalt.clikt.core.subcommands
import com.github.ajalt.clikt.parameters.options.*
import com.github.ajalt.clikt.parameters.types.int
import com.github.ajalt.clikt.output.MordantHelpFormatter
import com.fuzzforge.config.RunConfig
import com.fuzzforge.generator.{base}Generator
import com.fuzzforge.runner.{base}Runner
import kotlinx.coroutines.runBlocking

class {base}Command : CliktCommand(
    name = "{pn.lower()}",
    help = "{design.get('description', 'Fuzzer generated by FuzzForge')}",
) {{
    init {{
        context {{ helpFormatter = {{ MordantHelpFormatter(it, showDefaultValues = true) }} }}
        subcommands(RunCommand(), GenerateCommand())
    }}
    override fun run() {{
        echo("{base} — Fuzzer")
        echo("Run with a subcommand: run or generate")
    }}
}}

class RunCommand : CliktCommand(name = "run", help = "Run fuzzing campaign") {{
    val count: Int by option("-n").int().default(10)
    val output: String by option("-o").default("./reports")
    override fun run() {{
        echo("Running campaign: $count programs")
        val config = RunConfig(outputDir = output)
        val runner = {base}Runner(config)
        runBlocking {{
            val results = runner.runBatch(count)
            echo("Done: ${{results.count {{ it.success }}}}/$count succeeded")
        }}
    }}
}}

class GenerateCommand : CliktCommand(name = "generate", help = "Generate programs only") {{
    val count: Int by option("-n").int().default(5)
    override fun run() {{
        val generator = {base}Generator()
        for (i in 0 until count) {{
            generator.generate()
            echo("Generated ${{i + 1}}")
        }}
    }}
}}

fun main(args: Array<String>) = {base}Command().main(args)
"""


# ---------------------------------------------------------------------------
# Build files
# ---------------------------------------------------------------------------

def _gen_settings(project_name: str) -> str:
    safe = project_name.lower().replace("-", "").replace("_", "")
    return f"""\
pluginManagement {{ plugins {{ kotlin("jvm") version "2.4.0" }} }}
rootProject.name = "{safe}"
include(":tree")
include(":tree:tree-generator")
"""


def _gen_root_build(project_name: str) -> str:
    base = "".join(w.capitalize() for w in project_name.replace("-", " ").replace("_", " ").split())
    return f"""\
plugins {{ id("java"); kotlin("jvm"); application; kotlin("plugin.serialization") version "2.4.0" }}
group = "com.fuzzforge"; version = "1.0-SNAPSHOT"
repositories {{ mavenCentral() }}
kotlin {{ jvmToolchain(17) }}
dependencies {{
    implementation(kotlin("stdlib"))
    implementation(project(":tree"))
    implementation("org.yaml:snakeyaml:2.0")
    implementation("com.github.ajalt.clikt:clikt-jvm:4.2.2")
    implementation("org.jetbrains.kotlinx:kotlinx-serialization-json:1.7.3")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-core:1.9.0")
    implementation("io.github.oshai:kotlin-logging-jvm:7.0.3")
    implementation("ch.qos.logback:logback-classic:1.5.18")
}}
application {{ mainClass = "com.fuzzforge.cli.{base}CommandKt" }}
sourceSets.main {{ kotlin.srcDir("src/main/kotlin") }}
tasks.test {{ useJUnitPlatform() }}
"""


def _gen_tree_build() -> str:
    return """\
plugins { kotlin("jvm"); kotlin("plugin.serialization") version "2.4.0" }
repositories { mavenCentral() }
sourceSets.main { kotlin.srcDir("src") }
val generateTree = tasks.register<JavaExec>("generateTree") {
    group = "generation"; workingDir = rootDir
    classpath = project(":tree:tree-generator").sourceSets.main.get().runtimeClasspath
    mainClass.set("com.fuzzforge.tree.generator.MainKt")
    val generationRoot = layout.projectDirectory.dir("gen")
    args(generationRoot.asFile.absolutePath)
    systemProperties["line.separator"] = "\\n"
    val generatorSourceRoot = rootDir.resolve("tree/tree-generator/src")
    inputs.files(fileTree(generatorSourceRoot) { include("**/*.kt") })
    outputs.dir(generationRoot)
}
sourceSets.main { kotlin.srcDir(layout.projectDirectory.dir("gen")) }
tasks.compileKotlin { dependsOn(generateTree) }
kotlin { jvmToolchain(17) }
dependencies { implementation("org.jetbrains.kotlinx:kotlinx-serialization-json:1.7.3") }
"""


def _gen_tree_generator_build() -> str:
    return """\
plugins { kotlin("jvm"); application }
repositories { mavenCentral() }
kotlin { jvmToolchain(17) }
application { mainClass = "com.fuzzforge.tree.generator.MainKt" }
tasks.named<JavaExec>("run") { workingDir = rootDir }
dependencies { implementation(files(rootProject.file("libs/tree-generator-common.jar"))) }
"""


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def generate_project(design: dict[str, Any], output_dir: str) -> str:
    """Generate the complete Kotlin fuzzer project from IR design."""
    project_name = design.get("project_name", "my-fuzzer")
    pkg = "com.fuzzforge"
    tree_pkg = "com.fuzzforge"

    dirs = create_project_scaffold(output_dir, project_name)
    elements = design.get("tree_builder_elements", [])
    enums = design.get("enums", {})

    # Phase 2a: Copy tree-generator boilerplate
    _copy_tree_generator_boilerplate(output_dir)

    # Phase 2b: Generate design-specific files
    # ImplConfigurator + BuilderConfigurator
    Path(dirs["tree_generator"]).joinpath("ImplConfigurator.kt").write_text(
        _gen_impl_configurator(elements))
    Path(dirs["tree_generator"]).joinpath("BuilderConfigurator.kt").write_text(
        _gen_builder_configurator(elements))

    # TreeBuilder.kt
    Path(dirs["tree_generator"]).joinpath("TreeBuilder.kt").write_text(
        _gen_tree_builder(design))

    # Enums
    for key, class_name in [("op_kind", "OpKind"), ("type_kind", "TypeKind"),
                            ("attr_kind", "AttrKind"), ("dim_kind", "DimKind"),
                            ("block_kind", "BlockKind"), ("class_kind", "ClassKind"),
                            ("language", "Language")]:
        values = enums.get(key, [])
        if values:
            Path(dirs["tree_src"]).joinpath(f"{class_name}.kt").write_text(
                _gen_enum(class_name, values, f"{tree_pkg}.ir"))

    # GeneratorConfig
    Path(dirs["src_config"]).joinpath("GeneratorConfig.kt").write_text(
        _gen_generator_config(design, pkg))

    # Generator, Translator, Runner, Config, CLI
    Path(dirs["src_generator"]).joinpath("Generator.kt").write_text(
        _gen_generator(design, pkg))
    Path(dirs["src_translator"]).joinpath("Translator.kt").write_text(
        _gen_translator(design, pkg))
    Path(dirs["src_runner"]).joinpath("Runner.kt").write_text(
        _gen_runner(design, pkg))
    Path(dirs["src_config"]).joinpath("RunConfig.kt").write_text(
        _gen_run_config(pkg))
    Path(dirs["src_cli"]).joinpath("App.kt").write_text(
        _gen_app(design, pkg))

    # Build files
    Path(dirs["output"]).joinpath("settings.gradle.kts").write_text(_gen_settings(project_name))
    Path(dirs["output"]).joinpath("build.gradle.kts").write_text(_gen_root_build(project_name))
    Path(dirs["output"]).joinpath("tree", "build.gradle.kts").write_text(_gen_tree_build())
    Path(dirs["output"]).joinpath("tree", "tree-generator", "build.gradle.kts").write_text(
        _gen_tree_generator_build())

    # README + .gitignore
    Path(dirs["output"]).joinpath("README.md").write_text(f"# {project_name}\n\nFuzzer generated by FuzzForge.\n")
    Path(dirs["output"]).joinpath(".gitignore").write_text(".gradle/\nbuild/\nout/\ngen/\n")

    return str(dirs["output"])