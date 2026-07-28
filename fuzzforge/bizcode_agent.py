"""
FuzzForge: Business Code Agent.
Generates Generator, Translator, Runner, Reducer, BugCollector, DiffTester, CLI.
"""

from pathlib import Path
from typing import Any


def _pn(design: dict) -> str:
    return design.get("project_name", "my-fuzzer").capitalize().replace("-", "").replace("_", "")


def _write(path: Path, content: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return str(path)


def gen_generator_config(design: dict[str, Any], output_dir: str) -> str:
    fields = design.get("generator_config", {}).get("fields", [])
    lines = [f"    val {f['name']}: {f['type']} = {f.get('default_value', '')}," for f in fields]
    sep = "\n"
    return _write(
        Path(output_dir) / "src" / "main" / "kotlin" / "com" / "fuzzforge" / "generator" / "GeneratorConfig.kt",
        f"package com.fuzzforge.generator\n\ndata class GeneratorConfig(\n    val seed: Long = System.currentTimeMillis(),\n{sep.join(lines)}\n) {{\n    companion object {{\n        val default = GeneratorConfig()\n    }}\n}}\n")


def gen_run_config(output_dir: str) -> str:
    return _write(
        Path(output_dir) / "src" / "main" / "kotlin" / "com" / "fuzzforge" / "config" / "RunConfig.kt",
        "package com.fuzzforge.config\n\nimport com.fuzzforge.generator.GeneratorConfig\n\ndata class RunConfig(\n    val outputDir: String = \"./reports\",\n    val logLevel: String = \"info\",\n    val workers: Int = 4,\n    val batchSize: Int = 200,\n    val runTimeoutSeconds: Int = 120,\n    val generatorConfig: GeneratorConfig = GeneratorConfig.default,\n) {\n    companion object {\n        val default = RunConfig()\n    }\n}\n")


def gen_generator(design: dict[str, Any], output_dir: str) -> str:
    base = _pn(design)
    return _write(
        Path(output_dir) / "src" / "main" / "kotlin" / "com" / "fuzzforge" / "generator" / "Generator.kt",
        f"""package com.fuzzforge.generator

import kotlin.random.Random
import com.fuzzforge.ir.*
import com.fuzzforge.ir.builder.*

class {base}Generator(
    private val config: GeneratorConfig = GeneratorConfig.default,
) {{
    private val random: Random = Random.Default

    fun generate(): UirProgram {{
        val numClasses = if (config.maxClasses > config.minClasses)
            random.nextInt(config.minClasses, config.maxClasses + 1) else config.minClasses

        val classes = mutableListOf<UirClassDeclaration>()
        for (i in 0 until numClasses) {{
            classes.add(generateClass("C$i"))
        }}

        val container = buildClassContainer {{
            this.classes.addAll(classes)
        }}

        return buildProgram {{
            this.classContainer = container
        }}
    }}

    private fun generateClass(name: String): UirClassDeclaration {{
        val classKind = ClassKind.entries[random.nextInt(ClassKind.entries.size)]
        val isFinal = random.nextFloat() < 0.3f
        val isAbstract = classKind == ClassKind.ABSTRACT || random.nextFloat() < 0.1f

        val numFuncs = random.nextInt(config.minFunctionsPerClass, config.maxFunctionsPerClass + 1)
        val funcs = mutableListOf<UirFunctionDeclaration>()
        for (i in 0 until numFuncs) {{
            funcs.add(generateFunction("m$i", name))
        }}

        val hasSuperType = random.nextFloat() < config.inheritanceProbability
        val superType = if (hasSuperType) generateFundamentalType() else null

        val hasTemplate = random.nextFloat() < config.templateProbability
        val templateParams = if (hasTemplate) {{
            mutableListOf(generateTemplateParam())
        }} else mutableListOf()

        return buildClassDeclaration {{
            this.name = name
            this.language = Language.CPP17
            this.classKind = classKind
            this.superType = superType
            this.isFinal = isFinal
            this.isAbstract = isAbstract
            this.templateParams.addAll(templateParams)
        }}
    }}

    private fun generateFunction(name: String, className: String): UirFunctionDeclaration {{
        val isVirtual = random.nextFloat() < config.virtualProbability
        val isPureVirtual = isVirtual && random.nextFloat() < 0.3f
        val isConst = random.nextFloat() < 0.3f
        val isStatic = random.nextFloat() < 0.2f
        val isTemplate = random.nextFloat() < config.templateProbability && !isVirtual

        val returnType = generateFundamentalType()
        val numParams = random.nextInt(config.minParams, config.maxParams + 1)
        val params = (0 until numParams).map {{ generateParameter() }}
        val paramList = buildParameterList {{
            this.parameters.addAll(params)
        }}

        return buildFunctionDeclaration {{
            this.name = name
            this.language = Language.CPP17
            this.isVirtual = isVirtual
            this.isPureVirtual = isPureVirtual
            this.isOverride = false
            this.isConst = isConst
            this.isStatic = isStatic
            this.isTemplate = isTemplate
            this.returnType = returnType
            this.parameterList = paramList
            this.containingClassName = className
        }}
    }}

    private fun generateFundamentalType(): UirFundamentalType {{
        val types = listOf("int" to 4, "float" to 4, "double" to 8, "char" to 1, "bool" to 1, "long" to 8, "short" to 2)
        val (name, size) = types[random.nextInt(types.size)]
        return buildFundamentalType {{
            this.typeKind = TypeKind.FUNDAMENTAL
            this.name = name
            this.size = size
        }}
    }}

    private fun generateParameter(): UirParameter {{
        val type = generateFundamentalType()
        return buildParameter {{
            this.name = "p${{random.nextInt(1000)}}"
            this.type = type
        }}
    }}

    private fun generateTemplateParam(): UirTemplateParameter {{
        return buildTemplateParameter {{
            this.name = "T${{random.nextInt(100)}}"
            this.typeKind = TypeKind.TEMPLATE_PARAMETER
            this.isTypeParameter = true
        }}
    }}
}}
""")


def gen_translator(design: dict[str, Any], output_dir: str) -> str:
    base = _pn(design)
    return _write(
        Path(output_dir) / "src" / "main" / "kotlin" / "com" / "fuzzforge" / "translator" / "Translator.kt",
        f"""package com.fuzzforge.translator

import com.fuzzforge.ir.*
import com.fuzzforge.ir.visitors.UirDefaultVisitor

interface FuzzForgeTranslator<R> {{
    fun translate(program: UirProgram): R
}}

class CppGenVisitor : UirDefaultVisitor<Unit, StringBuilder>() {{
    override fun visitProgram(program: UirProgram, data: StringBuilder) {{
        data.appendLine("// Generated by FuzzForge - C++ Compiler Fuzzer")
        data.appendLine("#include <cstdint>")
        data.appendLine()
        program.acceptChildren(this, data)
        if (data.length < 100) {{
            data.appendLine("int main() {{ return 0; }}")
        }}
    }}

    override fun visitClassContainer(container: UirClassContainer, data: StringBuilder) {{
        for (clazz in container.classes) {{
            clazz.accept(this, data)
        }}
    }}

    override fun visitClassDeclaration(cd: UirClassDeclaration, data: StringBuilder) {{
        if (cd.templateParams.isNotEmpty()) {{
            val params = cd.templateParams.joinToString(", ") {{ it.name }}
            data.appendLine("template<$params>")
        }}
        val kind = if (cd.classKind == ClassKind.UNION) "union" else "class"
        data.append("$kind ${{cd.name}}")
        if (cd.superType != null) {{
            data.append(" : public ${{cd.superType!!.name}}")
        }}
        data.appendLine(" {{")
        data.appendLine("public:")
        data.appendLine("    virtual ~${{cd.name}}() = default;")
        cd.acceptChildren(this, data)
        data.appendLine("}};")
        data.appendLine()
    }}

    override fun visitFunctionDeclaration(fd: UirFunctionDeclaration, data: StringBuilder) {{
        val retType = when (fd.returnType) {{
            is UirFundamentalType -> (fd.returnType as UirFundamentalType).name
            is UirPointerType -> (fd.returnType as UirPointerType).pointeeType.let {{ it is UirFundamentalType -> it.name; else -> "void" }}
            else -> "int"
        }}
        val params = fd.parameterList.parameters.joinToString(", ") {{ p ->
            val ptype = when (p.type) {{
                is UirFundamentalType -> (p.type as UirFundamentalType).name
                else -> "int"
            }}
            "$ptype ${{p.name}}"
        }}
        val virtual = if (fd.isVirtual) "virtual " else ""
        val pure = if (fd.isPureVirtual) " = 0" else ""
        val const_ = if (fd.isConst) " const" else ""
        val static_ = if (fd.isStatic) "static " else ""
        if (fd.isPureVirtual) {{
            data.appendLine("    $static_$virtual$retType ${{fd.name}}($params)$const_$pure;")
        }} else {{
            data.appendLine("    $static_$virtual$retType ${{fd.name}}($params)$const_ {{")
            data.appendLine("        // TODO: implement")
            data.appendLine("    }}")
        }}
    }}

    override fun visitElement(element: UirElement, data: StringBuilder) {{
        element.acceptChildren(this, data)
    }}
}}

class {base}Translator : FuzzForgeTranslator<String> {{
    override fun translate(program: UirProgram): String {{
        val sb = StringBuilder()
        val visitor = CppGenVisitor()
        program.accept(visitor, sb)
        return sb.toString()
    }}
}}
""")


def gen_runner(design: dict[str, Any], output_dir: str) -> str:
    base = _pn(design)
    return _write(
        Path(output_dir) / "src" / "main" / "kotlin" / "com" / "fuzzforge" / "runner" / "Runner.kt",
        f"""package com.fuzzforge.runner

import com.fuzzforge.generator.{base}Generator
import com.fuzzforge.translator.{base}Translator
import com.fuzzforge.config.RunConfig
import kotlinx.coroutines.*
import java.io.File

data class RunResult(
    val success: Boolean,
    val stdout: String,
    val stderr: String,
    val exitCode: Int,
    val durationMs: Long,
    val sourceCode: String = "",
)

class {base}Runner(
    private val config: RunConfig,
) {{
    private val generator = {base}Generator(config.generatorConfig)
    private val translator = {base}Translator()
    private val tempDir = File(config.outputDir, "temp")
    private var programCounter = 0

    init {{
        tempDir.mkdirs()
    }}

    private fun compileWithGcc(code: String): RunResult {{
        val id = programCounter++
        val cppFile = File(tempDir, "test_$id.cpp")
        cppFile.writeText(code)

        val start = System.currentTimeMillis()
        val proc = ProcessBuilder(
            "g++", "-std=c++17", "-O2", "-Wall", "-Wextra", "-o",
            File(tempDir, "test_$id").absolutePath,
            cppFile.absolutePath
        ).redirectErrorStream(false).start()

        val stdout = proc.inputStream.bufferedReader().readText()
        val stderr = proc.errorStream.bufferedReader().readText()
        val exitCode = proc.waitFor()
        val duration = System.currentTimeMillis() - start

        cppFile.delete()
        File(tempDir, "test_$id").delete()

        return RunResult(success = exitCode == 0, stdout = stdout, stderr = stderr,
            exitCode = exitCode, durationMs = duration, sourceCode = code)
    }}

    private fun compileWithClang(code: String): RunResult {{
        val id = programCounter++
        val cppFile = File(tempDir, "test_$id.cpp")
        cppFile.writeText(code)

        val start = System.currentTimeMillis()
        val proc = ProcessBuilder(
            "clang++", "-std=c++17", "-O2", "-Wall", "-Wextra", "-o",
            File(tempDir, "test_$id").absolutePath,
            cppFile.absolutePath
        ).redirectErrorStream(false).start()

        val stdout = proc.inputStream.bufferedReader().readText()
        val stderr = proc.errorStream.bufferedReader().readText()
        val exitCode = proc.waitFor()
        val duration = System.currentTimeMillis() - start

        cppFile.delete()
        File(tempDir, "test_$id").delete()

        return RunResult(success = exitCode == 0, stdout = stdout, stderr = stderr,
            exitCode = exitCode, durationMs = duration, sourceCode = code)
    }}

    suspend fun compileAndRunSingle(seed: Long? = null): RunResult {{
        val program = if (seed != null) {{
            {base}Generator(config.generatorConfig.copy(seed = seed)).generate()
        }} else {{
            generator.generate()
        }}
        val code = translator.translate(program)
        return compileWithGcc(code)
    }}

    suspend fun diffTestSingle(seed: Long? = null): Pair<RunResult, RunResult> {{
        val program = if (seed != null) {{
            {base}Generator(config.generatorConfig.copy(seed = seed)).generate()
        }} else {{
            generator.generate()
        }}
        val code = translator.translate(program)
        return Pair(compileWithGcc(code), compileWithClang(code))
    }}

    suspend fun runBatch(count: Int): List<RunResult> = coroutineScope {{
        (0 until count).map {{ compileAndRunSingle() }}
    }}

    suspend fun diffTestBatch(count: Int): List<Pair<RunResult, RunResult>> = coroutineScope {{
        (0 until count).map {{ diffTestSingle() }}
    }}
}}
""")


def gen_app(design: dict[str, Any], output_dir: str) -> str:
    pn = design.get("project_name", "my-fuzzer").lower()
    base = _pn(design)
    desc = design.get("description", "Fuzzer generated by FuzzForge")
    return _write(
        Path(output_dir) / "src" / "main" / "kotlin" / "com" / "fuzzforge" / "cli" / "App.kt",
        f"""package com.fuzzforge.cli

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

class {base}Command : CliktCommand(name = "{pn}", help = "{desc}") {{
    init {{
        context {{ helpFormatter = {{ MordantHelpFormatter(it, showDefaultValues = true) }} }}
        subcommands(RunCommand(), GenerateCommand(), DiffCommand())
    }}
    override fun run() {{
        echo("{base} — Fuzzer")
        echo("Run with a subcommand: run, generate, or diff")
    }}
}}

class RunCommand : CliktCommand(name = "run", help = "Run fuzzing campaign with g++") {{
    val count: Int by option("-n").int().default(10)
    val output: String by option("-o").default("./reports")
    override fun run() {{
        echo("Running campaign: $count programs with g++")
        val config = RunConfig(outputDir = output)
        val runner = {base}Runner(config)
        runBlocking {{
            val results = runner.runBatch(count)
            val success = results.count {{ it.success }}
            val failures = results.filter {{ !it.success }}
            echo("Done: $success/$count compiled OK")
            if (failures.isNotEmpty()) {{
                echo("Errors:")
                for (r in failures.take(5)) {{
                    echo("  ---")
                    echo(r.stderr.take(500))
                }}
            }}
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

class DiffCommand : CliktCommand(name = "diff", help = "Differential test: g++ vs clang++") {{
    val count: Int by option("-n").int().default(10)
    val output: String by option("-o").default("./reports")
    override fun run() {{
        echo("Running differential test: $count programs")
        val config = RunConfig(outputDir = output)
        val runner = {base}Runner(config)
        runBlocking {{
            val results = runner.diffTestBatch(count)
            var gccOk = 0; var clangOk = 0; var diffMismatch = 0
            for ((gcc, clang) in results) {{
                if (gcc.success) gccOk++
                if (clang.success) clangOk++
                if (gcc.success != clang.success) {{
                    diffMismatch++
                    echo("DIFF MISMATCH:")
                    echo("  gcc:   exit=${{gcc.exitCode}} ${{gcc.stderr.take(200)}}")
                    echo("  clang: exit=${{clang.exitCode}} ${{clang.stderr.take(200)}}")
                }}
            }}
            echo("Results: g++ $gccOk/$count OK, clang++ $clangOk/$count OK, diff_mismatches: $diffMismatch")
        }}
    }}
}}

fun main(args: Array<String>) = {base}Command().main(args)
""")


def gen_root_build(design: dict[str, Any], output_dir: str) -> str:
    return _write(
        Path(output_dir) / "build.gradle.kts",
        'plugins { id("java"); kotlin("jvm"); application; kotlin("plugin.serialization") version "2.4.0" }\n'
        'group = "com.fuzzforge"; version = "1.0-SNAPSHOT"\nrepositories { mavenCentral() }\n'
        'kotlin { jvmToolchain(17) }\n'
        'dependencies {\n'
        '    implementation(kotlin("stdlib"))\n    implementation(project(":tree"))\n'
        '    implementation("org.yaml:snakeyaml:2.0")\n'
        '    implementation("com.github.ajalt.clikt:clikt-jvm:4.2.2")\n'
        '    implementation("org.jetbrains.kotlinx:kotlinx-serialization-json:1.7.3")\n'
        '    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-core:1.9.0")\n'
        '    implementation("io.github.oshai:kotlin-logging-jvm:7.0.3")\n'
        '    implementation("ch.qos.logback:logback-classic:1.5.18")\n'
        '}\n'
        'application { mainClass = "com.fuzzforge.cli.AppKt" }\n'
        'sourceSets.main { kotlin.srcDir("src/main/kotlin") }\n'
        'tasks.test { useJUnitPlatform() }\n')


def gen_reducer(output_dir: str) -> str:
    return _write(
        Path(output_dir) / "src" / "main" / "kotlin" / "com" / "fuzzforge" / "reducer" / "ProgramReducer.kt",
        "package com.fuzzforge.reducer\n\nimport com.fuzzforge.ir.UirProgram\nimport com.fuzzforge.translator.FuzzForgeTranslator\n\n"
        "class ProgramReducer(\n    private val translator: FuzzForgeTranslator<String>,\n) {\n"
        "    fun reduce(program: UirProgram, testOracle: (UirProgram) -> Boolean, maxPasses: Int = 10): UirProgram {\n"
        "        var current = program\n        for (pass in 1..maxPasses) {\n"
        "            val n = (2 shl (pass - 1).coerceAtMost(5))\n"
        "            val reduced = tryRemove(current, n, testOracle)\n"
        "            if (reduced == current) break\n            current = reduced\n        }\n"
        "        return current\n    }\n\n"
        "    private fun tryRemove(program: UirProgram, nGroups: Int, testOracle: (UirProgram) -> Boolean): UirProgram {\n"
        "        return program\n    }\n}\n\n"
        "class ConsistencyChecker {\n    fun check(program: UirProgram): List<String> = emptyList()\n}\n")


def gen_bug_collector(output_dir: str) -> str:
    return _write(
        Path(output_dir) / "src" / "main" / "kotlin" / "com" / "fuzzforge" / "collector" / "BugCollector.kt",
        "package com.fuzzforge.collector\n\nimport com.fuzzforge.ir.UirProgram\nimport com.fuzzforge.translator.FuzzForgeTranslator\n"
        "import java.io.File\nimport java.nio.file.Path\nimport java.time.Instant\n\n"
        "data class BugReport(\n    val id: String,\n    val timestamp: Long = Instant.now().toEpochMilli(),\n"
        "    val category: BugCategory,\n    val program: UirProgram,\n    val sourceCode: String,\n"
        "    val errorMessage: String,\n    val diffMismatch: String? = null,\n    val compiler: String? = null,\n    val seed: Long? = null,\n)\n\n"
        "enum class BugCategory {\n    CRASH, COMPILE_ERROR, WRONG_CODE, ASSERTION_FAILURE, SEGFAULT, TIMEOUT, DIFF_MISMATCH, COMPILER_HANG, UNKNOWN\n}\n\n"
        "class BugCollector(\n    private val outputDir: Path,\n    private val translator: FuzzForgeTranslator<String>,\n) {\n"
        "    private val knownPatterns = mutableSetOf<String>()\n"
        "    private val reportsDir: File = outputDir.resolve(\"reports\").toFile()\n"
        "    init { reportsDir.mkdirs() }\n"
        "    fun submit(report: BugReport): Boolean {\n"
        "        val normalized = normalizeError(report.errorMessage)\n"
        "        if (normalized in knownPatterns) return false\n"
        "        knownPatterns.add(normalized)\n        saveReport(report)\n        return true\n    }\n"
        "    fun isDuplicate(errorMessage: String): Boolean = normalizeError(errorMessage) in knownPatterns\n"
        "    private fun normalizeError(msg: String): String = msg.trim()\n"
        "    private fun saveReport(report: BugReport) {\n"
        "        val dir = File(reportsDir, \"bug_${report.id}\"); dir.mkdirs()\n"
        "        File(dir, \"source.cpp\").writeText(report.sourceCode)\n"
        "        File(dir, \"report.md\").writeText(\"id: ${report.id}\\ntimestamp: ${report.timestamp}\\ncategory: ${report.category}\\nerror: ${report.errorMessage}\")\n"
        "    }\n"
        "    fun summary(): Map<BugCategory, Int> {\n"
        "        val counts = mutableMapOf<BugCategory, Int>()\n"
        "        for (cat in BugCategory.entries) counts[cat] = 0\n        return counts\n    }\n}\n")


def gen_diff_tester(design: dict[str, Any], output_dir: str) -> str:
    base = _pn(design)
    return _write(
        Path(output_dir) / "src" / "main" / "kotlin" / "com" / "fuzzforge" / "diff" / "DiffTester.kt",
        f"package com.fuzzforge.diff\n\nimport com.fuzzforge.ir.UirProgram\nimport com.fuzzforge.translator.FuzzForgeTranslator\n"
        f"import com.fuzzforge.runner.RunResult\nimport kotlinx.coroutines.*\n\n"
        f"enum class DiffMode {{\n    CROSS_TARGET, OPTIMIZE_VS_UNOPTIMIZED, CROSS_COMPILER\n}}\n\n"
        f"data class DiffResult(\n    val program: UirProgram,\n    val sourceCode: String,\n    val resultA: RunResult,\n    val resultB: RunResult,\n    val match: Boolean,\n    val mode: DiffMode,\n)\n\n"
        f"class {base}DiffTester(\n    private val translator: FuzzForgeTranslator<String>,\n) {{\n"
        f"    suspend fun testSingle(program: UirProgram, mode: DiffMode): DiffResult {{\n"
        f"        val code = translator.translate(program)\n"
        f"        val rA = RunResult(success = true, stdout = code, stderr = \"\", exitCode = 0, durationMs = 0)\n"
        f"        val rB = RunResult(success = true, stdout = code, stderr = \"\", exitCode = 0, durationMs = 0)\n"
        f"        return DiffResult(program, code, rA, rB, rA.stdout == rB.stdout, mode)\n    }}\n\n"
        f"    suspend fun testBatch(programs: List<UirProgram>, mode: DiffMode): List<DiffResult> = coroutineScope {{\n"
        f"        programs.map {{ testSingle(it, mode) }}.filter {{ !it.match }}\n    }}\n}}\n")


def generate_business_code(design: dict[str, Any], output_dir: str) -> list[str]:
    paths = []
    paths.append(gen_generator_config(design, output_dir))
    paths.append(gen_run_config(output_dir))
    paths.append(gen_generator(design, output_dir))
    paths.append(gen_translator(design, output_dir))
    paths.append(gen_runner(design, output_dir))
    paths.append(gen_app(design, output_dir))
    paths.append(gen_root_build(design, output_dir))
    paths.append(gen_reducer(output_dir))
    paths.append(gen_bug_collector(output_dir))
    paths.append(gen_diff_tester(design, output_dir))

    (Path(output_dir) / ".gitignore").write_text(".gradle/\nbuild/\nout/\ngen/\n")
    (Path(output_dir) / "README.md").write_text(f"# {design.get('project_name', 'fuzzer')}\n\nFuzzer generated by FuzzForge.\n")
    return paths