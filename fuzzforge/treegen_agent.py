"""
FuzzForge: Tree Generator Agent.

Responsible for the tree-generator infrastructure only:
  1. Copy tree-generator boilerplate from aiFuzzer
  2. Generate TreeBuilder.kt, ImplConfigurator.kt, BuilderConfigurator.kt
  3. Write enum files
  4. Run generateTree

This agent NEVER touches business code (src/main/kotlin/).
"""

import os
import shutil
from pathlib import Path
from typing import Any

from fuzzforge.scaffold import create_project_scaffold
from fuzzforge.runner import run_gradle


def _pkg(parts: list[str]) -> str:
    return "package " + ".".join(parts)


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


def _copy_boilerplate(output_dir: str) -> dict:
    """Copy tree-generator boilerplate from aiFuzzer. Returns dirs dict."""
    base = Path(output_dir)
    dirs = create_project_scaffold(output_dir, "fuzzer")

    # license
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
            for old, new in [("UirTypeKind", "TypeKind"), ("UirDimKind", "DimKind"),
                            ("UirAttrKind", "AttrKind"), ("UirBlockKind", "BlockKind"),
                            ("UirOpKind", "OpKind")]:
                content = content.replace(old, new)
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

    # IrImplementationDetail
    (ir_dst / "IrImplementationDetail.kt").write_text(
        'package com.fuzzforge.ir\n\n@RequiresOptIn(message = "FuzzForge IR implementation detail")\n'
        '@Retention(AnnotationRetention.BINARY)\n@Target(AnnotationTarget.CLASS, AnnotationTarget.FUNCTION)\n'
        'annotation class IrImplementationDetail\n')

    return dirs


def _gen_enum(enum_name: str, values: list[str], pkg: str) -> str:
    sep = ",\n    "
    return f"{_pkg([pkg])}\n\nenum class {enum_name} {{\n    {sep.join(values)}\n}}\n"


def _gen_tree_builder(design: dict[str, Any]) -> str:
    """Generate TreeBuilder.kt from IR design.

    This is the ONLY file that codegen generates — all other tree-generator
    files are copied boilerplate from aiFuzzer.
    """
    elements = design.get("tree_builder_elements", [])
    enums = design.get("enums", {})

    # Type references for elements
    type_refs = []
    for e in elements:
        en = e["element_name"]
        ref = en[0].lower() + en[1:]
        type_refs.append(f"    val {ref}Type = generatedType(\"Uir{en}\")")

    # Enum type references
    seen_vars = set()
    enum_refs = []
    for e in elements:
        for f in e.get("fields", []):
            ftype = f["type"]
            if ftype in ENUM_VAR_MAP and ENUM_VAR_MAP[ftype] not in seen_vars:
                enum_refs.append(f"    val {ENUM_VAR_MAP[ftype]} = generatedType(\"{ftype}\")")
                seen_vars.add(ENUM_VAR_MAP[ftype])

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
        if var_name != "element":
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

{elements_str(def_lines)}

    // ---- Helper methods ----
    fun field(name: String, type: TypeRefWithNullability,
        nullable: Boolean = false, isMutable: Boolean = true,
        withReplace: Boolean = false, withTransform: Boolean = true,
        isChild: Boolean = true, initializer: SimpleField.() -> Unit = {{}},
    ): SimpleField {{
        return SimpleField(name, type.copy(nullable), isChild = isChild, isMutable = isMutable,
            withReplace = withReplace, withTransform = withTransform).apply(initializer)
    }}

    fun listField(name: String, baseType: TypeRef,
        withReplace: Boolean = false, withTransform: Boolean = true,
        useMutableOrEmpty: Boolean = true, isChild: Boolean = true,
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


def elements_str(def_lines: list[str]) -> str:
    return "\n\n".join(def_lines)


def _gen_impl_configurator(elements: list[dict]) -> str:
    names = [e["var_name"] for e in elements if e["var_name"] not in ("element", "rootElement")]
    lines = "\n".join(f"        impl({n})" for n in names)
    return f"""\
package com.fuzzforge.tree.generator

import com.fuzzforge.tree.generator.model.Element
import com.fuzzforge.tree.generator.model.Field
import com.fuzzforge.tree.generator.model.Implementation
import org.jetbrains.kotlin.generators.tree.Model
import org.jetbrains.kotlin.generators.tree.config.AbstractImplementationConfigurator

object ImplConfigurator : AbstractImplementationConfigurator<Implementation, Element, Field>() {{
    override fun createImplementation(element: Element, name: String?): Implementation =
        Implementation(element, name)
    override fun configure(model: Model<Element>) = with(TreeBuilder) {{
{lines}
        Unit
    }}
    override fun configureAllImplementations(model: Model<Element>) {{ }}
}}
"""


def _gen_builder_configurator(elements: list[dict]) -> str:
    names = [e["var_name"] for e in elements if e["var_name"] not in ("element", "rootElement")]
    lines = "\n".join(f"        builder({n}) {{ }}" for n in names)
    return f"""\
package com.fuzzforge.tree.generator

import com.fuzzforge.tree.generator.model.Element
import com.fuzzforge.tree.generator.model.Field
import com.fuzzforge.tree.generator.model.Implementation
import org.jetbrains.kotlin.generators.tree.config.AbstractBuilderConfigurator

class BuilderConfigurator(model: org.jetbrains.kotlin.generators.tree.Model<Element>) :
    AbstractBuilderConfigurator<Element, Implementation, Field>(model) {{
    override val namePrefix: String get() = "Uir"
    override val defaultBuilderPackage: String get() = "com.fuzzforge.ir.builder"
    override fun configureBuilders() = with(TreeBuilder) {{
{lines}
    }}
}}
"""


def setup_tree_infrastructure(output_dir: str, design: dict[str, Any]) -> bool:
    """Phase 1: Set up the tree-generator infrastructure.

    Returns True if generateTree succeeded.
    """
    elements = design.get("tree_builder_elements", [])
    enums = design.get("enums", {})
    dirs = _copy_boilerplate(output_dir)
    base = Path(output_dir)

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
                _gen_enum(class_name, values, f"com.fuzzforge.ir"))

    # Build files
    Path(dirs["output"]).joinpath("settings.gradle.kts").write_text(
        'pluginManagement { plugins { kotlin("jvm") version "2.4.0" } }\n'
        'rootProject.name = "fuzzer"\ninclude(":tree")\ninclude(":tree:tree-generator")\n')

    Path(dirs["output"]).joinpath("tree", "build.gradle.kts").write_text(_gen_tree_build())
    Path(dirs["output"]).joinpath("tree", "tree-generator", "build.gradle.kts").write_text(
        'plugins { kotlin("jvm"); application }\n'
        'repositories { mavenCentral() }\n'
        'kotlin { jvmToolchain(17) }\n'
        'application { mainClass = "com.fuzzforge.tree.generator.MainKt" }\n'
        'tasks.named<JavaExec>("run") { workingDir = rootDir }\n'
        'dependencies { implementation(files(rootProject.file("libs/tree-generator-common.jar"))) }\n')

    # Run generateTree
    print("  [TreeGen] Running generateTree...")
    result = run_gradle(str(base), ":tree:generateTree")
    if result["success"]:
        print(f"  [TreeGen] generateTree succeeded in {result['elapsed_seconds']}s!")
        return True
    else:
        print(f"  [TreeGen] generateTree failed: {result['stderr'][:500]}")
        return False


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