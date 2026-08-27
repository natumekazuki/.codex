from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("extract_test_values.py")
SPEC = importlib.util.spec_from_file_location("extract_test_values", SCRIPT)
assert SPEC and SPEC.loader
EXTRACTOR = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = EXTRACTOR
SPEC.loader.exec_module(EXTRACTOR)


VALID_METADATA = '''# @test-value v1
# kind = "invariant"
# claim = "同じkeyによる再試行で請求件数が1件を超えない"
# oracle = { type = "contract", ref = "PAYMENT-004" }
# failure_mode = "応答喪失後の再送で請求を二重に永続化する"
# scope = "payment-api"
# lifecycle = "permanent"
# @end-test-value
'''


class ExtractTestValuesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def write(self, relative: str, content: str, *, newline: str = "\n") -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content.replace("\n", newline).encode("utf-8"))
        return path

    def extract(self, *paths: str) -> tuple[dict, int]:
        return EXTRACTOR.extract_repository(self.root, list(paths))

    def test_extracts_bound_metadata_and_decorated_source(self) -> None:
        source = (
            "class PaymentTests:\n"
            + "".join(f"    {line}\n" for line in VALID_METADATA.splitlines())
            + "    @parameterized(\"lost-response\")\n"
            + "    def test_retry(self):\n"
            + "        # assertion rationale remains in source_text\n"
            + "        assert charge_count() == 1\n"
        )
        self.write("tests/test_payment.py", source)

        result, exit_status = self.extract("tests/test_payment.py")

        self.assertEqual(exit_status, 0)
        self.assertEqual(result["coverage"], "python-source-declarations-v1")
        self.assertEqual(result["diagnostics"], [])
        self.assertEqual(len(result["tests"]), 1)
        record = result["tests"][0]
        self.assertEqual(record["source"]["symbol"], "PaymentTests.test_retry")
        self.assertEqual(record["source"]["metadata_start_line"], 2)
        self.assertEqual(record["source"]["declaration_start_line"], 10)
        self.assertEqual(record["metadata"]["oracle"]["ref"], "PAYMENT-004")
        self.assertTrue(
            record["source_text"].startswith('    @parameterized("lost-response")')
        )
        self.assertIn("assertion rationale", record["source_text"])
        self.assertNotIn("@test-value", record["source_text"])
        self.assertRegex(record["source_hash"], r"^sha256:[0-9a-f]{64}$")
        self.assertRegex(record["metadata_hash"], r"^sha256:[0-9a-f]{64}$")

    def test_missing_metadata_is_not_inferred(self) -> None:
        self.write("tests/test_missing.py", "def test_without_value():\n    assert True\n")

        result, exit_status = self.extract("tests/test_missing.py")

        self.assertEqual(exit_status, 1)
        self.assertIsNone(result["tests"][0]["metadata"])
        self.assertIsNone(result["tests"][0]["metadata_hash"])
        self.assertEqual(
            [item["code"] for item in result["diagnostics"]],
            ["TEST_VALUE_MISSING"],
        )

    def test_blank_line_prevents_binding_and_reports_unbound_block(self) -> None:
        self.write(
            "tests/test_gap.py",
            VALID_METADATA + "\ndef test_gap():\n    assert True\n",
        )

        result, exit_status = self.extract("tests/test_gap.py")

        self.assertEqual(exit_status, 1)
        self.assertIsNone(result["tests"][0]["metadata"])
        self.assertEqual(
            {item["code"] for item in result["diagnostics"]},
            {"TEST_VALUE_MISSING", "TEST_VALUE_UNBOUND"},
        )

    def test_duplicate_adjacent_blocks_are_rejected(self) -> None:
        self.write(
            "tests/test_duplicate.py",
            VALID_METADATA + VALID_METADATA + "def test_duplicate():\n    assert True\n",
        )

        result, exit_status = self.extract("tests/test_duplicate.py")

        self.assertEqual(exit_status, 1)
        self.assertIsNone(result["tests"][0]["metadata"])
        self.assertIn(
            "TEST_VALUE_DUPLICATE",
            [item["code"] for item in result["diagnostics"]],
        )

    def test_parse_and_schema_errors_do_not_produce_metadata(self) -> None:
        malformed = '''# @test-value v1
# kind = "invariant
# @end-test-value
def test_malformed():
    assert True
'''
        unknown = VALID_METADATA.replace(
            '# lifecycle = "permanent"\n',
            '# lifecycle = "permanent"\n# invented = "value"\n',
        )
        self.write("tests/test_malformed.py", malformed)
        self.write(
            "tests/test_unknown.py",
            unknown + "def test_unknown():\n    assert True\n",
        )

        result, exit_status = self.extract(
            "tests/test_unknown.py", "tests/test_malformed.py"
        )

        self.assertEqual(exit_status, 1)
        self.assertTrue(all(record["metadata"] is None for record in result["tests"]))
        self.assertEqual(
            {item["code"] for item in result["diagnostics"]},
            {"TEST_VALUE_PARSE_ERROR", "TEST_VALUE_SCHEMA_ERROR"},
        )

    def test_wrong_types_and_invalid_lifecycle_combination_are_schema_errors(self) -> None:
        wrong_type = VALID_METADATA.replace(
            '# kind = "invariant"',
            "# kind = []",
        )
        invalid_lifecycle = VALID_METADATA.replace(
            '# lifecycle = "permanent"',
            '# lifecycle = "characterization"',
        )
        self.write(
            "tests/test_wrong_type.py",
            wrong_type + "def test_wrong_type():\n    assert True\n",
        )
        self.write(
            "tests/test_characterization.py",
            invalid_lifecycle + "def test_characterization():\n    assert True\n",
        )

        result, exit_status = self.extract(
            "tests/test_characterization.py", "tests/test_wrong_type.py"
        )

        self.assertEqual(exit_status, 1)
        self.assertTrue(all(record["metadata"] is None for record in result["tests"]))
        self.assertEqual(
            [item["code"] for item in result["diagnostics"]],
            ["TEST_VALUE_SCHEMA_ERROR", "TEST_VALUE_SCHEMA_ERROR"],
        )

    def test_characterization_accepts_explicit_review_condition(self) -> None:
        characterization = VALID_METADATA.replace(
            '# lifecycle = "permanent"\n',
            '# lifecycle = "characterization"\n'
            '# review_when = "外部契約が確定したとき"\n',
        )
        self.write(
            "tests/test_characterization.py",
            characterization + "def test_characterization():\n    assert True\n",
        )

        result, exit_status = self.extract("tests/test_characterization.py")

        self.assertEqual(exit_status, 0)
        self.assertEqual(result["diagnostics"], [])
        self.assertEqual(
            result["tests"][0]["metadata"]["review_when"],
            "外部契約が確定したとき",
        )

    def test_nested_test_and_syntax_error_are_reported(self) -> None:
        self.write(
            "tests/test_nested.py",
            "def helper():\n    def test_nested():\n        assert True\n",
        )
        self.write("tests/test_syntax.py", "def test_broken(:\n    pass\n")

        result, exit_status = self.extract(
            "tests/test_syntax.py", "tests/test_nested.py"
        )

        self.assertEqual(exit_status, 1)
        self.assertEqual(result["tests"], [])
        self.assertEqual(
            {item["code"] for item in result["diagnostics"]},
            {"SOURCE_SYNTAX_ERROR", "TEST_DECLARATION_UNSUPPORTED"},
        )

    def test_projection_is_stable_across_input_order_and_line_endings(self) -> None:
        source = VALID_METADATA + "def test_stable():\n    assert True\n"
        self.write("a/test_lf.py", source, newline="\n")
        self.write("b/test_crlf.py", source, newline="\r\n")

        first, first_status = self.extract("b/test_crlf.py", "a/test_lf.py")
        second, second_status = self.extract("a/test_lf.py", "b/test_crlf.py")

        self.assertEqual(first_status, 0)
        self.assertEqual(second_status, 0)
        self.assertEqual(EXTRACTOR.render_result(first), EXTRACTOR.render_result(second))
        self.assertEqual(
            first["tests"][0]["source_hash"], first["tests"][1]["source_hash"]
        )
        self.assertNotIn("\r", first["tests"][1]["source_text"])

    def test_metadata_like_text_inside_string_is_not_a_comment_block(self) -> None:
        self.write(
            "tests/test_string.py",
            VALID_METADATA
            + '''def test_string():
    value = """
# @test-value v1
# kind = "invariant"
# @end-test-value
"""
    assert value
''',
        )

        result, exit_status = self.extract("tests/test_string.py")

        self.assertEqual(exit_status, 0)
        self.assertEqual(result["diagnostics"], [])
        self.assertEqual(len(result["tests"]), 1)

    def test_public_cli_emits_valid_result(self) -> None:
        self.write(
            "tests/test_cli.py",
            VALID_METADATA + "def test_cli():\n    assert True\n",
        )

        completed = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--root",
                str(self.root),
                "tests/test_cli.py",
            ],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )

        self.assertEqual(completed.returncode, 0)
        self.assertEqual(completed.stderr, "")
        result = json.loads(completed.stdout)
        self.assertEqual(result["tests"][0]["source"]["symbol"], "test_cli")
        self.assertEqual(result["diagnostics"], [])

    def test_outside_root_is_rejected_by_public_cli(self) -> None:
        outside = self.root.parent / f"{self.root.name}-outside.py"
        outside.write_text("def test_outside():\n    assert True\n", encoding="utf-8")
        try:
            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--root",
                    str(self.root),
                    str(outside),
                ],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
        finally:
            outside.unlink(missing_ok=True)

        self.assertEqual(completed.returncode, 1)
        result = json.loads(completed.stdout)
        self.assertEqual(result["diagnostics"][0]["code"], "SOURCE_OUTSIDE_ROOT")
        self.assertNotIn(str(self.root), completed.stdout)

    def test_symlink_resolving_outside_root_is_rejected(self) -> None:
        outside = self.root.parent / f"{self.root.name}-target.py"
        outside.write_text("def test_outside():\n    assert True\n", encoding="utf-8")
        link = self.root / "tests" / "linked.py"
        link.parent.mkdir(parents=True)
        try:
            try:
                link.symlink_to(outside)
            except OSError as error:
                self.skipTest(f"symlink creation is unavailable: {error}")

            result, exit_status = self.extract("tests/linked.py")
        finally:
            link.unlink(missing_ok=True)
            outside.unlink(missing_ok=True)

        self.assertEqual(exit_status, 1)
        self.assertEqual(result["tests"], [])
        self.assertEqual(result["diagnostics"][0]["code"], "SOURCE_OUTSIDE_ROOT")


if __name__ == "__main__":
    unittest.main()
