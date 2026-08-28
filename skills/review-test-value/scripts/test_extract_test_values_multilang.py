from __future__ import annotations

import importlib.util
import json
import os
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

    def test_csharp_syntax_diagnostic_uses_invariant_culture(self) -> None:
        self.write("tests/CultureInvariant.cs", "public class Broken {")

        previous = os.environ.get("DOTNET_SYSTEM_GLOBALIZATION_INVARIANT")
        results = []
        try:
            for mode in ("0", "1"):
                os.environ["DOTNET_SYSTEM_GLOBALIZATION_INVARIANT"] = mode
                results.append(self.extract("tests/CultureInvariant.cs"))
        finally:
            if previous is None:
                os.environ.pop("DOTNET_SYSTEM_GLOBALIZATION_INVARIANT", None)
            else:
                os.environ["DOTNET_SYSTEM_GLOBALIZATION_INVARIANT"] = previous

        self.assertEqual(
            EXTRACTOR.render_result(results[0][0]),
            EXTRACTOR.render_result(results[1][0]),
        )
        result, exit_status = results[0]
        self.assertEqual(exit_status, 1)
        self.assertEqual(result["tests"], [])
        self.assertEqual(
            result["diagnostics"],
            [
                {
                    "code": "SOURCE_SYNTAX_ERROR",
                    "path": "tests/CultureInvariant.cs",
                    "line": 1,
                    "message": "} expected",
                }
            ],
        )
        program = (
            SCRIPT.parent / "adapters" / "csharp" / "Program.cs"
        ).read_text(encoding="utf-8")
        self.assertIn("GetMessage(CultureInfo.InvariantCulture)", program)

    def test_csharp_rejects_conditional_compilation_regions(self) -> None:
        self.write(
            "tests/ConditionalTests.cs",
            "#if DEBUG\n"
            "public class ConditionalTests\n"
            "{\n"
            "    [Fact]\n"
            "    public void DebugOnly() { }\n"
            "}\n"
            "#endif\n",
        )

        result, exit_status = self.extract("tests/ConditionalTests.cs")

        self.assertEqual(exit_status, 1)
        self.assertEqual(result["tests"], [])
        self.assertEqual(
            [item["code"] for item in result["diagnostics"]],
            ["TEST_DECLARATION_UNSUPPORTED"],
        )

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
