from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("extract_test_values.py")
SPEC = importlib.util.spec_from_file_location("extract_test_values_multilang", SCRIPT)
assert SPEC and SPEC.loader
EXTRACTOR = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = EXTRACTOR
SPEC.loader.exec_module(EXTRACTOR)


METADATA_PAYLOAD = (
    "@test-value v1",
    'kind = "invariant"',
    'claim = "同じkeyによる再試行で請求件数が1件を超えない"',
    'oracle = { type = "contract", ref = "PAYMENT-004" }',
    'failure_mode = "応答喪失後の再送で請求を二重に永続化する"',
    'scope = "payment-api"',
    'lifecycle = "permanent"',
    "@end-test-value",
)


def metadata_block(prefix: str, indent: str = "") -> str:
    return "".join(f"{indent}{prefix} {line}\n" for line in METADATA_PAYLOAD)


class ExtractMultilanguageTestValuesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def write(self, relative: str, content: str) -> None:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="")

    def write_utf8_bom(self, relative: str, content: str) -> None:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"\xef\xbb\xbf" + content.encode("utf-8"))

    def extract(self, *paths: str) -> tuple[dict, int]:
        return EXTRACTOR.extract_repository(self.root, list(paths))

    def git(self, *args: str) -> str:
        completed = subprocess.run(
            ["git", *args],
            cwd=self.root,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        return completed.stdout.strip()

    def initialize_git(self) -> str:
        self.git("init", "--quiet")
        self.git("config", "user.name", "Test User")
        self.git("config", "user.email", "test@example.invalid")
        self.git("add", "--all")
        self.git("commit", "--quiet", "--allow-empty", "-m", "base")
        return self.git("rev-parse", "HEAD")

    def extract_git(
        self, base: str, language: str, *extra: str
    ) -> tuple[dict, int, str]:
        completed = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--root",
                str(self.root),
                "--changed-from",
                base,
                "--language",
                language,
                *extra,
            ],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        result = json.loads(completed.stdout) if completed.stdout else {}
        return result, completed.returncode, completed.stderr

    # @test-value v1
    # kind = "contract"
    # claim = "describe配下のtest.eachをgroup付きの一宣言として抽出する"
    # oracle = { type = "adr", ref = "ADR-0020" }
    # failure_mode = "parameterized testを欠落または複数recordへ誤分割する"
    # scope = "typescript-source-adapter"
    # lifecycle = "permanent"
    # @end-test-value
    def test_typescript_extracts_describe_and_parameterized_declaration(self) -> None:
        self.write(
            "tests/payment.test.ts",
            "const namedHandler = (attempt) => {\n"
            + "  expect(chargeCount(attempt)).toBe(1);\n"
            + "};\n"
            + "describe(\"payment\", () => {\n"
            + metadata_block("//", "  ")
            + '  test.each([1, 2])("retry %s", namedHandler);\n'
            + "});\n",
        )

        result, exit_status = self.extract("tests/payment.test.ts")

        self.assertEqual(exit_status, 0)
        self.assertEqual(result["adapter"], "typescript-source-v1")
        self.assertEqual(result["coverage"], "typescript-source-declarations-v1")
        self.assertEqual(result["diagnostics"], [])
        self.assertEqual(len(result["tests"]), 1)
        record = result["tests"][0]
        self.assertEqual(record["source"]["symbol"], "payment > retry %s")
        self.assertTrue(record["source_text"].startswith("  test.each"))
        self.assertIn("namedHandler", record["source_text"])
        self.assertEqual(record["metadata"]["oracle"]["ref"], "PAYMENT-004")

    # @test-value v1
    # kind = "invariant"
    # claim = "symbolが衝突してもpathとdeclaration_start_lineのlocatorを一意にする"
    # oracle = { type = "adr", ref = "ADR-0020" }
    # failure_mode = "qualified symbolをrecord keyにして別testを上書きする"
    # scope = "result-identity"
    # lifecycle = "permanent"
    # @end-test-value
    def test_record_locator_is_unique_when_qualified_symbols_collide(self) -> None:
        self.write(
            "tests/colliding-symbols.test.ts",
            'describe("a > b", () => {\n'
            + metadata_block("//", "  ")
            + '  test("c", () => {});\n'
            + '});\n'
            + 'describe("a", () => {\n'
            + metadata_block("//", "  ")
            + '  test("b > c", () => {});\n'
            + '});\n',
        )

        result, exit_status = self.extract("tests/colliding-symbols.test.ts")

        self.assertEqual(exit_status, 0)
        self.assertEqual(result["diagnostics"], [])
        self.assertEqual(
            [record["source"]["symbol"] for record in result["tests"]],
            ["a > b > c", "a > b > c"],
        )
        locators = {
            (
                record["source"]["path"],
                record["source"]["declaration_start_line"],
            )
            for record in result["tests"]
        }
        self.assertEqual(len(locators), 2)

    # @test-value v1
    # kind = "regression"
    # claim = "動的titleのTypeScript testをUNSUPPORTEDとして値を推測しない"
    # oracle = { type = "adr", ref = "ADR-0020" }
    # failure_mode = "実行時titleを静的recordとして黙って成功扱いする"
    # scope = "typescript-source-adapter"
    # lifecycle = "permanent"
    # @end-test-value
    def test_typescript_rejects_dynamic_title_without_inference(self) -> None:
        self.write(
            "tests/dynamic.test.ts",
            "const title = \"dynamic\";\n"
            "test(title, () => {\n"
            "  expect(true).toBe(true);\n"
            "});\n",
        )

        result, exit_status = self.extract("tests/dynamic.test.ts")

        self.assertEqual(exit_status, 1)
        self.assertEqual(result["tests"], [])
        self.assertEqual(
            [item["code"] for item in result["diagnostics"]],
            ["TEST_DECLARATION_UNSUPPORTED"],
        )

    # @test-value v1
    # kind = "regression"
    # claim = "parenthesized・as assertion・non-null wrapper付き宣言を全て抽出する"
    # oracle = { type = "adr", ref = "ADR-0020" }
    # failure_mode = "transparent wrapperだけで有効test宣言を空結果にする"
    # scope = "typescript-source-adapter"
    # lifecycle = "permanent"
    # @end-test-value
    def test_typescript_extracts_declarations_through_transparent_wrappers(self) -> None:
        self.write(
            "tests/wrapped.test.ts",
            metadata_block("//")
            + '(test)("parenthesized", () => {});\n'
            + metadata_block("//")
            + '(test as any)("asserted", () => {});\n'
            + metadata_block("//")
            + '(test!).only("non-null", () => {});\n'
            + '(test.describe)("group", () => {\n'
            + metadata_block("//", "  ")
            + '  test("child", () => {});\n'
            + '});\n',
        )

        result, exit_status = self.extract("tests/wrapped.test.ts")

        self.assertEqual(exit_status, 0)
        self.assertEqual(result["diagnostics"], [])
        self.assertEqual(
            [record["source"]["symbol"] for record in result["tests"]],
            ["parenthesized", "asserted", "non-null", "group > child"],
        )

    # @test-value v1
    # kind = "regression"
    # claim = "引数なしcallをUNSUPPORTEDにし同一fileの有効recordは保持する"
    # oracle = { type = "adr", ref = "ADR-0020" }
    # failure_mode = "検出可能な不正宣言でadapter crashするか有効recordまで失う"
    # scope = "typescript-source-adapter"
    # lifecycle = "permanent"
    # @end-test-value
    def test_typescript_reports_argumentless_calls_and_preserves_valid_record(self) -> None:
        self.write(
            "tests/argumentless.test.ts",
            "test();\n"
            + "test.only();\n"
            + "describe();\n"
            + "test.describe();\n"
            + "test.each([1])();\n"
            + metadata_block("//")
            + 'test("valid", () => {});\n',
        )

        result, exit_status = self.extract("tests/argumentless.test.ts")

        self.assertEqual(exit_status, 1)
        self.assertEqual(
            [record["source"]["symbol"] for record in result["tests"]],
            ["valid"],
        )
        self.assertEqual(
            [item["code"] for item in result["diagnostics"]],
            ["TEST_DECLARATION_UNSUPPORTED"] * 5,
        )

    # @test-value v1
    # kind = "regression"
    # claim = "未対応concurrent modifierをUNSUPPORTEDとして返す"
    # oracle = { type = "adr", ref = "ADR-0020" }
    # failure_mode = "検出可能な未対応test modifierを非testとして黙って捨てる"
    # scope = "typescript-source-adapter"
    # lifecycle = "permanent"
    # @end-test-value
    def test_typescript_rejects_unsupported_modifier(self) -> None:
        self.write(
            "tests/concurrent.test.ts",
            'test.concurrent("parallel", () => {});\n',
        )

        result, exit_status = self.extract("tests/concurrent.test.ts")

        self.assertEqual(exit_status, 1)
        self.assertEqual(result["tests"], [])
        self.assertEqual(
            [item["code"] for item in result["diagnostics"]],
            ["TEST_DECLARATION_UNSUPPORTED"],
        )

    # @test-value v1
    # kind = "regression"
    # claim = "concurrent.eachの複合call chainをUNSUPPORTEDとして返す"
    # oracle = { type = "adr", ref = "ADR-0020" }
    # failure_mode = "nested call chainの未対応modifierを空結果で成功扱いする"
    # scope = "typescript-source-adapter"
    # lifecycle = "permanent"
    # @end-test-value
    def test_typescript_rejects_unsupported_modifier_in_each_chain(self) -> None:
        self.write(
            "tests/concurrent-each.test.ts",
            'test.concurrent.each([1, 2])("parallel %s", () => {});\n'
            + 'it.concurrent.each([1, 2])("also parallel %s", () => {});\n'
            + 'test.each([1, 2]).only("focused %s", () => {});\n'
            + 'test.each([1, 2]).only.concurrent("deep %s", () => {});\n'
            + '(test.each([1, 2])).only("wrapped %s", () => {});\n'
            + 'test.each`value | expected\n${1} | ${1}`("tagged", () => {});\n'
            + 'test.each`value | expected\n${1} | ${1}`.only("tagged modifier", () => {});\n'
            + '(test.each`value | expected\n${1} | ${1}`).only("wrapped tagged", () => {});\n',
        )

        result, exit_status = self.extract("tests/concurrent-each.test.ts")

        self.assertEqual(exit_status, 1)
        self.assertEqual(result["tests"], [])
        self.assertEqual(
            [item["code"] for item in result["diagnostics"]],
            ["TEST_DECLARATION_UNSUPPORTED"] * 8,
        )

    # @test-value v1
    # kind = "contract"
    # claim = "Playwright hook・config・runtime annotationを宣言と区別し実testだけ抽出する"
    # oracle = { type = "adr", ref = "ADR-0020" }
    # failure_mode = "非宣言APIをtestとして誤拒否するか実testを欠落させる"
    # scope = "typescript-source-adapter"
    # lifecycle = "permanent"
    # @end-test-value
    def test_typescript_ignores_playwright_hooks_config_and_runtime_annotations(self) -> None:
        self.write(
            "tests/playwright.test.ts",
            "test.beforeAll(async () => {});\n"
            "test.beforeEach(async () => {});\n"
            "test.beforeEach('titled setup', async () => {});\n"
            "test.afterEach(async () => {});\n"
            "test.afterAll(async () => {});\n"
            "test.use({ locale: 'en-US' });\n"
            "test.setTimeout(30_000);\n"
            "const extended = test.extend({});\n"
            "test.describe.configure({ mode: 'parallel' });\n"
            + metadata_block("//")
            + 'test("playwright", async ({ browserName }) => {\n'
            + "  test.skip(browserName !== 'webkit', 'Safari only');\n"
            + "  test.fail(browserName === 'webkit', 'Known failure');\n"
            + "  test.fixme(browserName === 'firefox', 'Needs work');\n"
            + "  test.slow(browserName === 'chromium', 'Slow path');\n"
            + "  test.info();\n"
            + "  await test.step('step', async () => {});\n"
            + "  await test.expect(browserName).toBe('chromium');\n"
            + "  test.abort('stop');\n"
            + "});\n",
        )

        result, exit_status = self.extract("tests/playwright.test.ts")

        self.assertEqual(exit_status, 0)
        self.assertEqual(result["diagnostics"], [])
        self.assertEqual(
            [record["source"]["symbol"] for record in result["tests"]],
            ["playwright"],
        )

    # @test-value v1
    # kind = "regression"
    # claim = "modifier付きitの動的titleをUNSUPPORTEDとして返す"
    # oracle = { type = "adr", ref = "ADR-0020" }
    # failure_mode = "modifier経路だけ動的titleを静的宣言として通す"
    # scope = "typescript-source-adapter"
    # lifecycle = "permanent"
    # @end-test-value
    def test_typescript_rejects_dynamic_it_modifier_title(self) -> None:
        self.write(
            "tests/dynamic-it.test.ts",
            'const title = "dynamic";\n'
            "it.skip(title, () => {});\n",
        )

        result, exit_status = self.extract("tests/dynamic-it.test.ts")

        self.assertEqual(exit_status, 1)
        self.assertEqual(result["tests"], [])
        self.assertEqual(
            [item["code"] for item in result["diagnostics"]],
            ["TEST_DECLARATION_UNSUPPORTED"],
        )

    # @test-value v1
    # kind = "regression"
    # claim = "同一行の前置code付き宣言をUNSUPPORTED、metadataをUNBOUNDにする"
    # oracle = { type = "adr", ref = "ADR-0020" }
    # failure_mode = "indent不明の宣言へ直前metadataを誤結合する"
    # scope = "typescript-source-adapter"
    # lifecycle = "permanent"
    # @end-test-value
    def test_typescript_rejects_declaration_after_code_on_same_line(self) -> None:
        self.write(
            "tests/prefixed.test.ts",
            metadata_block("//")
            + 'const before = 1; test("prefixed", () => {});\n',
        )

        result, exit_status = self.extract("tests/prefixed.test.ts")

        self.assertEqual(exit_status, 1)
        self.assertEqual(result["tests"], [])
        self.assertEqual(
            [item["code"] for item in result["diagnostics"]],
            ["TEST_VALUE_UNBOUND", "TEST_DECLARATION_UNSUPPORTED"],
        )

    # @test-value v1
    # kind = "regression"
    # claim = "動的describeをUNSUPPORTEDにし内側testをgroupなしrecordとして出さない"
    # oracle = { type = "adr", ref = "ADR-0020" }
    # failure_mode = "親groupを失ったnested testを別identityで抽出する"
    # scope = "typescript-source-adapter"
    # lifecycle = "permanent"
    # @end-test-value
    def test_typescript_rejects_dynamic_describe_and_nested_test(self) -> None:
        self.write(
            "tests/dynamic-describe.test.ts",
            'const group = "payment";\n'
            "describe(group, () => {\n"
            '  test("retry", () => {});\n'
            "});\n",
        )

        result, exit_status = self.extract("tests/dynamic-describe.test.ts")

        self.assertEqual(exit_status, 1)
        self.assertEqual(result["tests"], [])
        self.assertEqual(
            [item["code"] for item in result["diagnostics"]],
            ["TEST_DECLARATION_UNSUPPORTED"],
        )

    # @test-value v1
    # kind = "regression"
    # claim = "同一行の複数test宣言をUNSUPPORTEDにし一blockを再利用しない"
    # oracle = { type = "adr", ref = "ADR-0020" }
    # failure_mode = "一つのmetadataとsource_textを複数testへ誤結合する"
    # scope = "typescript-source-adapter"
    # lifecycle = "permanent"
    # @end-test-value
    def test_typescript_rejects_multiple_declarations_on_one_line(self) -> None:
        self.write(
            "tests/same-line.test.ts",
            metadata_block("//")
            + 'test("A", () => {}); test("B", () => {});\n',
        )

        result, exit_status = self.extract("tests/same-line.test.ts")

        self.assertEqual(exit_status, 1)
        self.assertEqual(result["tests"], [])
        self.assertEqual(
            [item["code"] for item in result["diagnostics"]],
            ["TEST_VALUE_UNBOUND", "TEST_DECLARATION_UNSUPPORTED"],
        )

    # @test-value v1
    # kind = "regression"
    # claim = "TypeScript syntax error時はSOURCE_SYNTAX_ERRORだけを返し部分recordを出さない"
    # oracle = { type = "adr", ref = "ADR-0020" }
    # failure_mode = "壊れたfileから一部testだけを完全な抽出結果として渡す"
    # scope = "typescript-source-adapter"
    # lifecycle = "permanent"
    # @end-test-value
    def test_typescript_syntax_error_does_not_emit_partial_records(self) -> None:
        self.write(
            "tests/broken.test.ts",
            metadata_block("//") + "test(\"broken\", () => {\n",
        )

        result, exit_status = self.extract("tests/broken.test.ts")

        self.assertEqual(exit_status, 1)
        self.assertEqual(result["tests"], [])
        self.assertIn(
            "SOURCE_SYNTAX_ERROR",
            [item["code"] for item in result["diagnostics"]],
        )

    # @test-value v1
    # kind = "contract"
    # claim = "TSXとonly・skip・fail・todoの対応modifier宣言を抽出する"
    # oracle = { type = "adr", ref = "ADR-0020" }
    # failure_mode = "対応済み拡張子またはmodifierをUNSUPPORTEDとして誤拒否する"
    # scope = "typescript-source-adapter"
    # lifecycle = "permanent"
    # @end-test-value
    def test_typescript_supports_tsx_and_common_test_modifiers(self) -> None:
        self.write(
            "tests/component.test.tsx",
            "const namedHandler = () => { expect(true).toBe(true); };\n"
            + metadata_block("//")
            + 'it.only("renders", () => { expect(<div />).toBeTruthy(); });\n'
            + metadata_block("//")
            + 'test.skip("disabled", namedHandler);\n'
            + metadata_block("//")
            + 'test.fail.only("focused failure", namedHandler);\n'
            + metadata_block("//")
            + 'test.todo("not implemented");\n',
        )

        result, exit_status = self.extract("tests/component.test.tsx")

        self.assertEqual(exit_status, 0)
        self.assertEqual(
            [record["source"]["symbol"] for record in result["tests"]],
            ["renders", "disabled", "focused failure", "not implemented"],
        )

    # @test-value v1
    # kind = "contract"
    # claim = "test.describe.onlyのstatic group名をqualified symbolへ保持する"
    # oracle = { type = "adr", ref = "ADR-0020" }
    # failure_mode = "対応group modifierを欠落させtest identityを変える"
    # scope = "typescript-source-adapter"
    # lifecycle = "permanent"
    # @end-test-value
    def test_typescript_supports_playwright_describe_modifier(self) -> None:
        self.write(
            "tests/group.test.ts",
            'test.describe.only("group", () => {\n'
            + metadata_block("//", "  ")
            + '  test("child", () => {});\n'
            + "});\n",
        )

        result, exit_status = self.extract("tests/group.test.ts")

        self.assertEqual(exit_status, 0)
        self.assertEqual(result["diagnostics"], [])
        self.assertEqual(result["tests"][0]["source"]["symbol"], "group > child")

    # @test-value v1
    # kind = "contract"
    # claim = "public CLIはTypeScript入力をtypescript adapter/profileへdispatchする"
    # oracle = { type = "adr", ref = "ADR-0020" }
    # failure_mode = "拡張子判定を誤り別adapterまたはcoverageを返す"
    # scope = "public-cli"
    # lifecycle = "permanent"
    # @end-test-value
    def test_public_cli_dispatches_typescript_adapter(self) -> None:
        self.write(
            "tests/public.test.ts",
            metadata_block("//") + 'test("public", () => {});\n',
        )

        completed = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--root",
                str(self.root),
                "tests/public.test.ts",
            ],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )

        self.assertEqual(completed.returncode, 0)
        self.assertEqual(completed.stderr, "")
        result = json.loads(completed.stdout)
        self.assertEqual(result["adapter"], "typescript-source-v1")
        self.assertEqual(result["tests"][0]["source"]["symbol"], "public")

    # @test-value v1
    # kind = "contract"
    # claim = "xUnit TheoryとInlineDataを一つのC# source declarationとして抽出する"
    # oracle = { type = "adr", ref = "ADR-0020" }
    # failure_mode = "data rowごとに静的recordを捏造するかTheoryを欠落させる"
    # scope = "csharp-source-adapter"
    # lifecycle = "permanent"
    # @end-test-value
    def test_csharp_extracts_xunit_theory_as_one_source_declaration(self) -> None:
        self.write(
            "tests/PaymentTests.cs",
            "namespace Billing;\n"
            "\n"
            "public class PaymentTests\n"
            "{\n"
            + metadata_block("//", "    ")
            + "    [Theory]\n"
            + "    [InlineData(1)]\n"
            + "    [InlineData(2)]\n"
            + "    public void Retry(int attempt)\n"
            + "    {\n"
            + '        var marker = "// @test-value v1";\n'
            + "        Assert.Equal(1, ChargeCount(attempt));\n"
            + "    }\n"
            + "}\n",
        )

        result, exit_status = self.extract("tests/PaymentTests.cs")

        self.assertEqual(exit_status, 0)
        self.assertEqual(result["adapter"], "csharp-source-v1")
        self.assertEqual(result["coverage"], "csharp-source-declarations-v1")
        self.assertEqual(result["diagnostics"], [])
        self.assertEqual(len(result["tests"]), 1)
        record = result["tests"][0]
        self.assertEqual(record["source"]["symbol"], "Billing.PaymentTests.Retry")
        self.assertTrue(record["source_text"].startswith("    [Theory]"))
        self.assertIn("Assert.Equal(1, ChargeCount(attempt))", record["source_text"])

    # @test-value v1
    # kind = "contract"
    # claim = "NUnitとMSTestの対応attribute付きmethodを各一recordとして抽出する"
    # oracle = { type = "adr", ref = "ADR-0020" }
    # failure_mode = "対応framework attributeを通常methodとして見落とす"
    # scope = "csharp-source-adapter"
    # lifecycle = "permanent"
    # @end-test-value
    def test_csharp_recognizes_nunit_and_mstest_attributes(self) -> None:
        self.write(
            "tests/FrameworkTests.cs",
            "public class FrameworkTests\n"
            "{\n"
            + metadata_block("//", "    ")
            + "    [NUnit.Framework.TestCase(1)]\n"
            + "    public void NUnitCase(int value) => Assert.That(value, Is.EqualTo(1));\n"
            + metadata_block("//", "    ")
            + "    [Microsoft.VisualStudio.TestTools.UnitTesting.DataTestMethodAttribute]\n"
            + "    public void MsTestCase() { }\n"
            + "}\n",
        )

        result, exit_status = self.extract("tests/FrameworkTests.cs")

        self.assertEqual(exit_status, 0)
        self.assertEqual(
            [record["source"]["symbol"] for record in result["tests"]],
            ["FrameworkTests.NUnitCase", "FrameworkTests.MsTestCase"],
        )

    # @test-value v1
    # kind = "regression"
    # claim = "C# syntax error時はSOURCE_SYNTAX_ERRORだけを返し部分recordを出さない"
    # oracle = { type = "adr", ref = "ADR-0020" }
    # failure_mode = "壊れたC# fileから一部testを完全な結果として返す"
    # scope = "csharp-source-adapter"
    # lifecycle = "permanent"
    # @end-test-value
    def test_csharp_syntax_error_does_not_emit_partial_records(self) -> None:
        self.write(
            "tests/BrokenTests.cs",
            metadata_block("//")
            + "[Fact]\n"
            + "public void Broken(\n",
        )

        result, exit_status = self.extract("tests/BrokenTests.cs")

        self.assertEqual(exit_status, 1)
        self.assertEqual(result["tests"], [])
        self.assertIn(
            "SOURCE_SYNTAX_ERROR",
            [item["code"] for item in result["diagnostics"]],
        )

    # @test-value v1
    # kind = "invariant"
    # claim = "C# syntax diagnostic JSONをCurrentUICultureに依存させない"
    # oracle = { type = "adr", ref = "ADR-0020" }
    # failure_mode = "同じsourceのmessageとJSONが実行環境cultureで変動する"
    # scope = "csharp-source-adapter"
    # lifecycle = "permanent"
    # @end-test-value
    def test_csharp_syntax_diagnostic_uses_invariant_culture(self) -> None:
        self.write("tests/CultureInvariant.cs", "public class Broken {")

        result, exit_status = self.extract("tests/CultureInvariant.cs")
        self.assertEqual(exit_status, 1)
        self.assertEqual(result["tests"], [])
        self.assertEqual(
            [item["code"] for item in result["diagnostics"]],
            ["SOURCE_SYNTAX_ERROR"],
        )

        check_project = (
            SCRIPT.parent
            / "adapters"
            / "csharp"
            / "culture-check"
            / "CultureCheck.csproj"
        )
        completed = subprocess.run(
            [
                "dotnet",
                "run",
                "--project",
                str(check_project),
                "--configuration",
                "Release",
                "--nologo",
            ],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)

    # @test-value v1
    # kind = "regression"
    # claim = "条件付きコンパイル領域のtestをUNSUPPORTEDとして明示する"
    # oracle = { type = "adr", ref = "ADR-0020" }
    # failure_mode = "project symbolなしで消えたtestを宣言なしとして成功扱いする"
    # scope = "csharp-source-adapter"
    # lifecycle = "permanent"
    # @end-test-value
    def test_csharp_rejects_conditional_compilation_regions(self) -> None:
        self.write(
            "tests/ConditionalTests.cs",
            "using Xunit;\n"
            "#if DEBUG\n"
            "public class DebugConditionalTests\n"
            "{\n"
            "    [Fact]\n"
            "    public void DebugOnly() { }\n"
            "}\n"
            "#else\n"
            "public class ReleaseConditionalTests\n"
            "{\n"
            "    [Fact]\n"
            "    public void ReleaseOnly() { }\n"
            "}\n"
            "#endif\n"
            "public class AlwaysTests\n"
            "{\n"
            + metadata_block("//", "    ")
            + "    [Fact]\n"
            "    public void Always() { }\n"
            "}\n",
        )

        result, exit_status = self.extract("tests/ConditionalTests.cs")

        self.assertEqual(exit_status, 1)
        self.assertEqual(
            [record["source"]["symbol"] for record in result["tests"]],
            ["AlwaysTests.Always"],
        )
        self.assertEqual(
            [item["code"] for item in result["diagnostics"]],
            ["TEST_DECLARATION_UNSUPPORTED"],
        )

    # @test-value v1
    # kind = "compatibility"
    # claim = "project symbolを必要としない#if true内のC# testを通常宣言として抽出する"
    # oracle = { type = "adr", ref = "ADR-0020" }
    # failure_mode = "静的条件をproject依存と誤分類しfile全体のtestを審査から消す"
    # scope = "csharp-source-adapter"
    # lifecycle = "permanent"
    # @end-test-value
    def test_csharp_extracts_static_true_conditional_region(self) -> None:
        self.write(
            "tests/StaticConditionalTests.cs",
            "using Xunit;\n"
            "#if true\n"
            "public class StaticConditionalTests\n"
            "{\n"
            + metadata_block("//", "    ")
            + "    [Fact]\n"
            "    public void StaticTrue() { }\n"
            "}\n"
            "#endif\n",
        )

        result, exit_status = self.extract("tests/StaticConditionalTests.cs")

        self.assertEqual(exit_status, 0)
        self.assertEqual(result["diagnostics"], [])
        self.assertEqual(
            [record["source"]["symbol"] for record in result["tests"]],
            ["StaticConditionalTests.StaticTrue"],
        )

    # @test-value v1
    # kind = "regression"
    # claim = "symbol参照conditional groupのactive branchもsupported recordとして抽出しない"
    # oracle = { type = "adr", ref = "ADR-0020" }
    # failure_mode = "既定symbolでactiveになった不確実branchを通常testとしてAI審査へ渡す"
    # scope = "csharp-source-adapter"
    # lifecycle = "permanent"
    # @end-test-value
    def test_csharp_rejects_active_symbol_conditional_branch(self) -> None:
        self.write(
            "tests/ActiveConditionalTests.cs",
            "using Xunit;\n"
            "#if !DEBUG\n"
            "public class ActiveConditionalTests\n"
            "{\n"
            "    [Fact]\n"
            "    public void ActiveWithoutDebug() { }\n"
            "}\n"
            "#endif\n",
        )

        result, exit_status = self.extract("tests/ActiveConditionalTests.cs")

        self.assertEqual(exit_status, 1)
        self.assertEqual(result["tests"], [])
        self.assertEqual(
            [item["code"] for item in result["diagnostics"]],
            ["TEST_DECLARATION_UNSUPPORTED"],
        )

    # @test-value v1
    # kind = "regression"
    # claim = "一つの#if・#elif symbol groupを一件のUNSUPPORTED diagnosticへ集約する"
    # oracle = { type = "adr", ref = "ADR-0020" }
    # failure_mode = "同じ不確実領域を複数宣言として数えるか一部branchを通常抽出する"
    # scope = "csharp-source-adapter"
    # lifecycle = "permanent"
    # @end-test-value
    def test_csharp_reports_one_diagnostic_per_symbol_conditional_group(self) -> None:
        self.write(
            "tests/ElifConditionalTests.cs",
            "#if DEBUG\n"
            "public class DebugTests { }\n"
            "#elif RELEASE\n"
            "public class ReleaseTests { }\n"
            "#endif\n",
        )

        result, exit_status = self.extract("tests/ElifConditionalTests.cs")

        self.assertEqual(exit_status, 1)
        self.assertEqual(result["tests"], [])
        self.assertEqual(
            [item["code"] for item in result["diagnostics"]],
            ["TEST_DECLARATION_UNSUPPORTED"],
        )

    # @test-value v1
    # kind = "regression"
    # claim = "同一行のclass code後にあるC# testをUNSUPPORTED、metadataをUNBOUNDにする"
    # oracle = { type = "adr", ref = "ADR-0020" }
    # failure_mode = "indent不明のmethodへ別scopeのmetadataを誤結合する"
    # scope = "csharp-source-adapter"
    # lifecycle = "permanent"
    # @end-test-value
    def test_csharp_rejects_declaration_after_code_on_same_line(self) -> None:
        self.write(
            "tests/PrefixedTests.cs",
            metadata_block("//")
            + "public class PrefixedTests { [Fact] public void Value() { } }\n",
        )

        result, exit_status = self.extract("tests/PrefixedTests.cs")

        self.assertEqual(exit_status, 1)
        self.assertEqual(result["tests"], [])
        self.assertEqual(
            [item["code"] for item in result["diagnostics"]],
            ["TEST_VALUE_UNBOUND", "TEST_DECLARATION_UNSUPPORTED"],
        )

    # @test-value v1
    # kind = "compatibility"
    # claim = "Python・TypeScript・C#全adapterでUTF-8 BOMをencoding markerとして除去する"
    # oracle = { type = "adr", ref = "ADR-0020" }
    # failure_mode = "BOMをsource文字やindentとして扱いparseまたはmetadata結合を壊す"
    # scope = "source-decoding"
    # lifecycle = "permanent"
    # @end-test-value
    def test_utf8_bom_is_removed_for_all_adapters(self) -> None:
        cases = (
            (
                "tests/test_bom.py",
                metadata_block("#") + "def test_bom():\n    assert True\n",
            ),
            (
                "tests/bom.test.ts",
                metadata_block("//") + 'test("bom", () => {});\n',
            ),
            (
                "tests/BomTests.cs",
                "public class BomTests\n"
                "{\n"
                + metadata_block("//", "    ")
                + "    [Fact]\n"
                + "    public void Bom() { }\n"
                + "}\n",
            ),
        )

        for relative, source in cases:
            with self.subTest(relative=relative):
                self.write_utf8_bom(relative, source)
                result, exit_status = self.extract(relative)
                self.assertEqual(exit_status, 0)
                self.assertEqual(result["diagnostics"], [])
                self.assertNotIn("\ufeff", result["tests"][0]["source_text"])

    # @test-value v1
    # kind = "contract"
    # claim = "Git modeはTypeScriptとC#でも変更testだけを言語別に選択する"
    # oracle = { type = "adr", ref = "ADR-0021" }
    # failure_mode = "native adapterの変更testが漏れるか未変更legacy testで停止する"
    # scope = "git-diff-selection"
    # lifecycle = "permanent"
    # @end-test-value
    def test_git_mode_selects_changed_typescript_and_csharp_tests(self) -> None:
        typescript = (
            'test("legacy", () => { expect(true).toBe(true); });\n'
            + metadata_block("//")
            + 'test("changed", () => { expect(observed()).toBe(1); });\n'
        )
        csharp = (
            "using Xunit;\n"
            "public class ValueTests\n"
            "{\n"
            "    [Fact] public void Legacy() { Assert.True(true); }\n"
            + metadata_block("//", "    ")
            + "    [Fact] public void Changed() { Assert.Equal(1, Observed()); }\n"
            "}\n"
        )
        ts_path = self.root / "tests/value.test.ts"
        cs_path = self.root / "tests/ValueTests.cs"
        self.write("tests/value.test.ts", typescript)
        self.write("tests/ValueTests.cs", csharp)
        base = self.initialize_git()
        ts_path.write_text(typescript.replace("toBe(1)", "toBe(2)"), encoding="utf-8")
        cs_path.write_text(csharp.replace("Equal(1", "Equal(2"), encoding="utf-8")

        ts_result, ts_status, ts_stderr = self.extract_git(base, "typescript")
        cs_result, cs_status, cs_stderr = self.extract_git(base, "csharp")

        self.assertEqual(ts_status, 0, ts_stderr)
        self.assertEqual(cs_status, 0, cs_stderr)
        self.assertEqual(ts_result["diagnostics"], [])
        self.assertEqual(cs_result["diagnostics"], [])
        self.assertEqual(
            [record["source"]["symbol"] for record in ts_result["tests"]],
            ["changed"],
        )
        self.assertEqual(
            [record["source"]["symbol"] for record in cs_result["tests"]],
            ["ValueTests.Changed"],
        )

    # @test-value v1
    # kind = "regression"
    # claim = "先頭C# attributeだけを削除したsurviving testをbase側rangeから選択する"
    # oracle = { type = "adr", ref = "ADR-0021" }
    # failure_mode = "旧開始attributeの削除anchorが現開始attributeと一致せず変更testが消える"
    # scope = "git-diff-selection"
    # lifecycle = "permanent"
    # @end-test-value
    def test_git_mode_selects_test_after_leading_csharp_attribute_deletion(self) -> None:
        source = (
            "using Xunit;\n"
            "public class AttributeTests\n"
            "{\n"
            + metadata_block("//", "    ")
            + '    [Trait("Kind", "Value")]\n'
            "    [Fact]\n"
            "    public void Survives() { }\n"
            "}\n"
        )
        path = self.root / "tests/AttributeTests.cs"
        self.write("tests/AttributeTests.cs", source)
        base = self.initialize_git()
        path.write_text(
            source.replace('    [Trait("Kind", "Value")]\n', ""),
            encoding="utf-8",
        )

        working = self.extract_git(base, "csharp")
        self.git("add", "tests/AttributeTests.cs")
        staged = self.extract_git(base, "csharp", "--staged")
        self.git("commit", "--quiet", "-m", "remove leading attribute")
        head = self.git("rev-parse", "HEAD")
        committed = self.extract_git(base, "csharp", "--head", head)

        for mode, (result, exit_status, stderr) in {
            "working": working,
            "staged": staged,
            "head": committed,
        }.items():
            with self.subTest(mode=mode):
                self.assertEqual(exit_status, 0, stderr)
                self.assertEqual(result["diagnostics"], [])
                self.assertEqual(
                    [record["source"]["symbol"] for record in result["tests"]],
                    ["AttributeTests.Survives"],
                )

    # @test-value v1
    # kind = "regression"
    # claim = "TypeScript未対応modifier宣言の本文変更をUNSUPPORTED diagnosticへ結合する"
    # oracle = { type = "adr", ref = "ADR-0021" }
    # failure_mode = "未対応callの開始行以外の変更を空結果として成功扱いする"
    # scope = "git-diff-selection"
    # lifecycle = "permanent"
    # @end-test-value
    def test_git_mode_selects_changed_unsupported_typescript_test(self) -> None:
        source = (
            'test.concurrent("parallel", () => {\n'
            "  expect(observed()).toBe(1);\n"
            "});\n"
        )
        path = self.root / "tests/concurrent-change.test.ts"
        self.write("tests/concurrent-change.test.ts", source)
        base = self.initialize_git()
        path.write_text(source.replace("toBe(1)", "toBe(2)"), encoding="utf-8")

        working = self.extract_git(base, "typescript")
        self.git("add", "tests/concurrent-change.test.ts")
        staged = self.extract_git(base, "typescript", "--staged")
        self.git("commit", "--quiet", "-m", "change unsupported typescript test")
        head = self.git("rev-parse", "HEAD")
        committed = self.extract_git(base, "typescript", "--head", head)

        for mode, (result, exit_status, stderr) in {
            "working": working,
            "staged": staged,
            "head": committed,
        }.items():
            with self.subTest(mode=mode):
                self.assertEqual(exit_status, 1, stderr)
                self.assertEqual(result["tests"], [])
                self.assertEqual(
                    [item["code"] for item in result["diagnostics"]],
                    ["TEST_DECLARATION_UNSUPPORTED"],
                )

    # @test-value v1
    # kind = "regression"
    # claim = "C# test attribute付きlocal functionの本文変更をUNSUPPORTED diagnosticへ結合する"
    # oracle = { type = "adr", ref = "ADR-0021" }
    # failure_mode = "未対応local functionの開始行以外の変更を空結果として成功扱いする"
    # scope = "git-diff-selection"
    # lifecycle = "permanent"
    # @end-test-value
    def test_git_mode_selects_changed_unsupported_csharp_local_function(self) -> None:
        source = (
            "using Xunit;\n"
            "public class LocalFunctionTests\n"
            "{\n"
            "    public void Helper()\n"
            "    {\n"
            "        [Fact]\n"
            "        void LocalTest()\n"
            "        {\n"
            "            Assert.Equal(1, Observed());\n"
            "        }\n"
            "    }\n"
            "}\n"
        )
        path = self.root / "tests/LocalFunctionTests.cs"
        self.write("tests/LocalFunctionTests.cs", source)
        base = self.initialize_git()
        path.write_text(source.replace("Equal(1", "Equal(2"), encoding="utf-8")

        working = self.extract_git(base, "csharp")
        self.git("add", "tests/LocalFunctionTests.cs")
        staged = self.extract_git(base, "csharp", "--staged")
        self.git("commit", "--quiet", "-m", "change unsupported csharp test")
        head = self.git("rev-parse", "HEAD")
        committed = self.extract_git(base, "csharp", "--head", head)

        for mode, (result, exit_status, stderr) in {
            "working": working,
            "staged": staged,
            "head": committed,
        }.items():
            with self.subTest(mode=mode):
                self.assertEqual(exit_status, 1, stderr)
                self.assertEqual(result["tests"], [])
                self.assertEqual(
                    [item["code"] for item in result["diagnostics"]],
                    ["TEST_DECLARATION_UNSUPPORTED"],
                )

    # @test-value v1
    # kind = "regression"
    # claim = "symbol依存C# conditional group内の本文変更をUNSUPPORTED diagnosticへ結合する"
    # oracle = { type = "adr", ref = "ADR-0021" }
    # failure_mode = "不確実領域の開始directive以外の変更を空結果として成功扱いする"
    # scope = "git-diff-selection"
    # lifecycle = "permanent"
    # @end-test-value
    def test_git_mode_selects_changed_csharp_symbol_conditional_group(self) -> None:
        source = (
            "#if !DEBUG\n"
            "public class ConditionalTests\n"
            "{\n"
            "    [Fact]\n"
            "    public void ActiveWithoutDebug()\n"
            "    {\n"
            "        Assert.Equal(1, Observed());\n"
            "    }\n"
            "}\n"
            "#endif\n"
        )
        path = self.root / "tests/ConditionalChangeTests.cs"
        self.write("tests/ConditionalChangeTests.cs", source)
        base = self.initialize_git()
        path.write_text(source.replace("Equal(1", "Equal(2"), encoding="utf-8")

        working = self.extract_git(base, "csharp")
        self.git("add", "tests/ConditionalChangeTests.cs")
        staged = self.extract_git(base, "csharp", "--staged")
        self.git("commit", "--quiet", "-m", "change conditional test")
        head = self.git("rev-parse", "HEAD")
        committed = self.extract_git(base, "csharp", "--head", head)

        for mode, (result, exit_status, stderr) in {
            "working": working,
            "staged": staged,
            "head": committed,
        }.items():
            with self.subTest(mode=mode):
                self.assertEqual(exit_status, 1, stderr)
                self.assertEqual(result["tests"], [])
                self.assertEqual(
                    [item["code"] for item in result["diagnostics"]],
                    ["TEST_DECLARATION_UNSUPPORTED"],
                )

    # @test-value v1
    # kind = "contract"
    # claim = "一回のpath modeへ複数言語を渡すとexit 2かつJSONなしで拒否する"
    # oracle = { type = "adr", ref = "ADR-0020" }
    # failure_mode = "異なるadapterのrecordを一つのresultへ混在させる"
    # scope = "public-cli"
    # lifecycle = "permanent"
    # @end-test-value
    def test_mixed_languages_are_rejected_as_invalid_invocation(self) -> None:
        self.write("tests/test_one.py", "def test_one():\n    assert True\n")
        self.write("tests/one.test.ts", 'test("one", () => {});\n')

        completed = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--root",
                str(self.root),
                "tests/test_one.py",
                "tests/one.test.ts",
            ],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )

        self.assertEqual(completed.returncode, 2)
        self.assertEqual(completed.stdout, "")
        self.assertIn("one language per invocation", completed.stderr)

    # @test-value v1
    # kind = "contract"
    # claim = "未対応extensionはexit 2かつ部分JSONなしで拒否する"
    # oracle = { type = "adr", ref = "ADR-0020" }
    # failure_mode = "adapter coverage外sourceを成功または空結果として扱う"
    # scope = "public-cli"
    # lifecycle = "permanent"
    # @end-test-value
    def test_unsupported_extension_is_rejected_as_invalid_invocation(self) -> None:
        self.write("tests/value.js", 'test("value", () => {});\n')

        completed = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--root",
                str(self.root),
                "tests/value.js",
            ],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )

        self.assertEqual(completed.returncode, 2)
        self.assertEqual(completed.stdout, "")
        self.assertIn("unsupported source extension: .js", completed.stderr)

    # @test-value v1
    # kind = "contract"
    # claim = "root外path diagnosticでも要求言語のadapterとcoverageを保持する"
    # oracle = { type = "adr", ref = "ADR-0020" }
    # failure_mode = "error projectionで無関係なPython profileを返しconsumerを誤誘導する"
    # scope = "result-projection"
    # lifecycle = "permanent"
    # @end-test-value
    def test_outside_root_path_preserves_requested_language_profile(self) -> None:
        cases = (
            (
                "outside.test.ts",
                "typescript-source-v1",
                "typescript-source-declarations-v1",
            ),
            (
                "OutsideTests.cs",
                "csharp-source-v1",
                "csharp-source-declarations-v1",
            ),
        )
        for filename, adapter, coverage in cases:
            with self.subTest(filename=filename):
                outside = self.root.parent / f"{self.root.name}-{filename}"
                outside.write_text("not read", encoding="utf-8")
                try:
                    result, exit_status = self.extract(str(outside))
                finally:
                    outside.unlink(missing_ok=True)

                self.assertEqual(exit_status, 1)
                self.assertEqual(result["adapter"], adapter)
                self.assertEqual(result["coverage"], coverage)
                self.assertEqual(result["tests"], [])
                self.assertEqual(
                    [item["code"] for item in result["diagnostics"]],
                    ["SOURCE_OUTSIDE_ROOT"],
                )

    # @test-value v1
    # kind = "invariant"
    # claim = "TypeScriptとC#で同じmetadataから同じcanonical metadata hashを生成する"
    # oracle = { type = "adr", ref = "ADR-0020" }
    # failure_mode = "adapterごとにmetadata projectionまたはhash規則が分岐する"
    # scope = "result-projection"
    # lifecycle = "permanent"
    # @end-test-value
    def test_language_adapters_share_metadata_projection(self) -> None:
        self.write(
            "tests/value.test.ts",
            metadata_block("//") + 'test("value", () => {});\n',
        )
        self.write(
            "tests/ValueTests.cs",
            "public class ValueTests\n"
            "{\n"
            + metadata_block("//", "    ")
            + "    [Fact]\n"
            + "    public void Value() { }\n"
            + "}\n",
        )

        typescript, typescript_status = self.extract("tests/value.test.ts")
        csharp, csharp_status = self.extract("tests/ValueTests.cs")

        self.assertEqual(typescript_status, 0)
        self.assertEqual(csharp_status, 0)
        self.assertEqual(
            typescript["tests"][0]["metadata"],
            csharp["tests"][0]["metadata"],
        )
        self.assertEqual(
            typescript["tests"][0]["metadata_hash"],
            csharp["tests"][0]["metadata_hash"],
        )


if __name__ == "__main__":
    unittest.main()
