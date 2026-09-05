from __future__ import annotations

import importlib.util
import json
import os
import shutil
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


VALID_METADATA = '''# @test-value v2
# kind = "invariant"
# claim = "同じkeyによる再試行で請求件数が1件を超えない"
# oracle = { type = "contract", ref = "PAYMENT-004" }
# fault = "応答喪失後の再送で請求を二重に永続化する"
# observable = "永続化された請求recordの件数"
# observation_boundary = "component-behavior"
# scope = "payment-api"
# lifecycle = "permanent"
# @end-test-value
'''

V1_METADATA = '''# @test-value v1
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
        self,
        base: str,
        language: str = "python",
        *extra: str,
        env: dict[str, str] | None = None,
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
            errors="replace",
            env=env,
        )
        result = json.loads(completed.stdout) if completed.stdout else {}
        return result, completed.returncode, completed.stderr

    def extract(self, *paths: str) -> tuple[dict, int]:
        return EXTRACTOR.extract_repository(self.root, list(paths))

    # @test-value v2
    # kind = "contract"
    # claim = "metadataをdecorated testへ結合しdecoratorから末尾までのsource_textとhashを投影する"
    # oracle = { type = "adr", ref = "ADR-0020" }
    # fault = "metadataを別testへ結合するかdecoratorやassertionをsource_textから欠落させる"
    # observable = "抽出recordのmetadata、source範囲、source hash"
    # observation_boundary = "component-behavior"
    # scope = "python-source-extraction"
    # lifecycle = "permanent"
    # @end-test-value
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
        self.assertEqual(result["schema_version"], 2)
        self.assertEqual(result["coverage"], "python-source-declarations-v1")
        self.assertEqual(result["diagnostics"], [])
        self.assertEqual(result["warnings"], [])
        self.assertEqual(len(result["tests"]), 1)
        record = result["tests"][0]
        self.assertEqual(record["metadata_format_version"], 2)
        self.assertEqual(record["source"]["symbol"], "PaymentTests.test_retry")
        self.assertEqual(record["source"]["metadata_start_line"], 2)
        self.assertEqual(record["source"]["declaration_start_line"], 12)
        self.assertEqual(record["metadata"]["oracle"]["ref"], "PAYMENT-004")
        self.assertTrue(
            record["source_text"].startswith('    @parameterized("lost-response")')
        )
        self.assertIn("assertion rationale", record["source_text"])
        self.assertNotIn("@test-value", record["source_text"])
        self.assertRegex(record["source_hash"], r"^sha256:[0-9a-f]{64}$")
        self.assertRegex(record["metadata_hash"], r"^sha256:[0-9a-f]{64}$")

    # @test-value v1
    # kind = "regression"
    # claim = "metadata欠落testは値を推測せずmetadata nullとTEST_VALUE_MISSINGを返す"
    # oracle = { type = "adr", ref = "ADR-0020" }
    # failure_mode = "コメントのないtestへ架空の価値情報を補完して成功扱いする"
    # scope = "test-value-binding"
    # lifecycle = "permanent"
    # @end-test-value
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

    # @test-value v1
    # kind = "regression"
    # claim = "空行で隔てたblockはtestへ結合せずMISSINGとUNBOUNDを返す"
    # oracle = { type = "adr", ref = "ADR-0020" }
    # failure_mode = "直接隣接しないmetadataをtestへ誤結合する"
    # scope = "test-value-binding"
    # lifecycle = "permanent"
    # @end-test-value
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

    # @test-value v1
    # kind = "regression"
    # claim = "一つのtestへ隣接する複数metadata blockをDUPLICATEとして拒否する"
    # oracle = { type = "adr", ref = "ADR-0020" }
    # failure_mode = "複数blockの一つを恣意的に採用して曖昧な価値情報を通す"
    # scope = "test-value-binding"
    # lifecycle = "permanent"
    # @end-test-value
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

    # @test-value v2
    # kind = "regression"
    # claim = "TOML parse errorとschema errorはmetadata nullと対応diagnosticを返す"
    # oracle = { type = "adr", ref = "ADR-0020" }
    # fault = "壊れたpayloadやunknown fieldを有効metadataとして投影する"
    # observable = "抽出recordのmetadataとparse/schema diagnostic"
    # observation_boundary = "component-behavior"
    # scope = "test-value-schema"
    # lifecycle = "permanent"
    # @end-test-value
    def test_parse_and_schema_errors_do_not_produce_metadata(self) -> None:
        malformed = '''# @test-value v2
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

    # @test-value v1
    # kind = "regression"
    # claim = "oracleの通常tableとdotted keyをSCHEMA_ERRORとして拒否する"
    # oracle = { type = "adr", ref = "ADR-0020" }
    # failure_mode = "公開形式外のoracle構文をinline tableとして受理する"
    # scope = "test-value-schema"
    # lifecycle = "permanent"
    # @end-test-value
    def test_oracle_requires_inline_table_syntax(self) -> None:
        table_oracle = VALID_METADATA.replace(
            '# oracle = { type = "contract", ref = "PAYMENT-004" }\n',
            "",
        ).replace(
            "# @end-test-value\n",
            '# [oracle]\n# type = "contract"\n# ref = "PAYMENT-004"\n'
            "# @end-test-value\n",
        )
        dotted_oracle = VALID_METADATA.replace(
            '# oracle = { type = "contract", ref = "PAYMENT-004" }',
            '# oracle.type = "contract"\n# oracle.ref = "PAYMENT-004"',
        )
        self.write(
            "tests/test_oracle_table.py",
            table_oracle + "def test_oracle_table():\n    assert True\n",
        )
        self.write(
            "tests/test_oracle_dotted.py",
            dotted_oracle + "def test_oracle_dotted():\n    assert True\n",
        )

        result, exit_status = self.extract(
            "tests/test_oracle_table.py", "tests/test_oracle_dotted.py"
        )

        self.assertEqual(exit_status, 1)
        self.assertTrue(all(record["metadata"] is None for record in result["tests"]))
        self.assertEqual(
            [item["code"] for item in result["diagnostics"]],
            ["TEST_VALUE_SCHEMA_ERROR", "TEST_VALUE_SCHEMA_ERROR"],
        )
        self.assertTrue(
            all(
                "oracle must use inline table syntax" in item["message"]
                for item in result["diagnostics"]
            )
        )

    # @test-value v2
    # kind = "regression"
    # claim = "multiline文字列内のdecoyを無視して実際の通常oracle tableを拒否する"
    # oracle = { type = "adr", ref = "ADR-0020" }
    # fault = "claim文字列内のoracle表記を構文根拠にして通常tableを通す"
    # observable = "抽出器のoracle syntax diagnostic"
    # observation_boundary = "component-behavior"
    # scope = "test-value-schema"
    # lifecycle = "permanent"
    # @end-test-value
    def test_oracle_shape_ignores_inline_table_text_in_multiline_string(self) -> None:
        source = '''# @test-value v2
# kind = "invariant"
# claim = """
# oracle = { type = "contract", ref = "DECOY" }
# claim text
# """
# fault = "誤ったoracle構文を受理する"
# observable = "抽出器のschema diagnostic"
# observation_boundary = "component-behavior"
# scope = "metadata-parser"
# lifecycle = "permanent"
# [oracle]
# type = "contract"
# ref = "PAYMENT-004"
# @end-test-value
def test_oracle_table_with_decoy():
    assert True
'''
        self.write("tests/test_oracle_decoy.py", source)

        result, exit_status = self.extract("tests/test_oracle_decoy.py")

        self.assertEqual(exit_status, 1)
        self.assertIsNone(result["tests"][0]["metadata"])
        self.assertEqual(
            [item["code"] for item in result["diagnostics"]],
            ["TEST_VALUE_SCHEMA_ERROR"],
        )
        self.assertIn(
            "oracle must use inline table syntax",
            result["diagnostics"][0]["message"],
        )

    # @test-value v1
    # kind = "contract"
    # claim = "Unicode escapeされたquoted oracle keyを復号してinline tableとして受理する"
    # oracle = { type = "adr", ref = "ADR-0020" }
    # failure_mode = "TOML上同値なquoted keyを未知fieldとして誤拒否する"
    # scope = "test-value-schema"
    # lifecycle = "permanent"
    # @end-test-value
    def test_oracle_accepts_escaped_quoted_key_with_inline_table(self) -> None:
        metadata = VALID_METADATA.replace(
            '# oracle = { type = "contract", ref = "PAYMENT-004" }',
            '# "or\\u0061cle" = { type = "contract", ref = "PAYMENT-004" }',
        )
        self.write(
            "tests/test_quoted_oracle.py",
            metadata + "def test_quoted_oracle():\n    assert True\n",
        )

        result, exit_status = self.extract("tests/test_quoted_oracle.py")

        self.assertEqual(exit_status, 0)
        self.assertEqual(result["diagnostics"], [])
        self.assertEqual(result["tests"][0]["metadata"]["oracle"]["ref"], "PAYMENT-004")

    # @test-value v2
    # kind = "regression"
    # claim = "v2のfield型不一致とlifecycle条件不足をSCHEMA_ERRORにする"
    # oracle = { type = "issue", ref = "#43" }
    # fault = "型不正または終了条件のない一時metadataを審査可能として通す"
    # observable = "抽出結果のTEST_VALUE_SCHEMA_ERRORとmetadata null"
    # observation_boundary = "component-behavior"
    # scope = "test-value-schema"
    # lifecycle = "permanent"
    # @end-test-value
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

    # @test-value v2
    # kind = "contract"
    # claim = "review_when付きcharacterizationをdiagnosticなしで投影する"
    # oracle = { type = "issue", ref = "#43" }
    # fault = "見直し条件を持つ有効なcharacterizationを誤拒否する"
    # observable = "抽出結果のexit status、diagnostics、metadata.review_when"
    # observation_boundary = "component-behavior"
    # scope = "test-value-schema"
    # lifecycle = "permanent"
    # @end-test-value
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

    # @test-value v2
    # kind = "contract"
    # claim = "lifecycle固有の必須条件を要求し、permanent以外の追加終了条件を拒否しない"
    # oracle = { type = "issue", ref = "#43" }
    # fault = "必須終了条件の欠落を受理するか、必須条件が揃った追加条件を拒否する"
    # observable = "lifecycle別の抽出exit status、diagnostics、metadata"
    # observation_boundary = "component-behavior"
    # scope = "test-value-schema"
    # lifecycle = "permanent"
    # @end-test-value
    def test_v2_lifecycle_conditions_are_enforced(self) -> None:
        valid_ephemeral = VALID_METADATA.replace(
            '# lifecycle = "permanent"\n',
            '# lifecycle = "ephemeral"\n'
            '# remove_when = "修正後の回帰checkへ置換したとき"\n',
        )
        missing_remove = VALID_METADATA.replace(
            '# lifecycle = "permanent"',
            '# lifecycle = "ephemeral"',
        )
        permanent_with_review = VALID_METADATA.replace(
            '# lifecycle = "permanent"\n',
            '# lifecycle = "permanent"\n# review_when = "契約変更時"\n',
        )
        characterization_with_only_remove = VALID_METADATA.replace(
            '# lifecycle = "permanent"\n',
            '# lifecycle = "characterization"\n'
            '# remove_when = "実装が安定したとき"\n',
        )
        cases = {
            "tests/test_ephemeral.py": valid_ephemeral,
            "tests/test_ephemeral_extra.py": valid_ephemeral.replace(
                "# @end-test-value", '# expires_on = "2030-01-01"\n# review_when = "契約変更時"\n# @end-test-value'
            ),
            "tests/test_characterization_extra.py": characterization_with_only_remove.replace(
                "# @end-test-value", '# review_when = "契約変更時"\n# @end-test-value'
            ),
            "tests/test_missing_remove.py": missing_remove,
            "tests/test_permanent_review.py": permanent_with_review,
            "tests/test_characterization_remove.py": characterization_with_only_remove,
        }
        for relative, metadata in cases.items():
            self.write(
                relative,
                metadata + f"def {Path(relative).stem}():\n    assert True\n",
            )

        valid_result, valid_status = self.extract(
            "tests/test_ephemeral.py", "tests/test_ephemeral_extra.py", "tests/test_characterization_extra.py"
        )
        invalid_result, invalid_status = self.extract(
            "tests/test_missing_remove.py",
            "tests/test_permanent_review.py",
            "tests/test_characterization_remove.py",
        )

        self.assertEqual(valid_status, 0)
        self.assertEqual(valid_result["diagnostics"], [])
        self.assertEqual(
            next(record for record in valid_result["tests"] if record["source"]["path"] == "tests/test_ephemeral.py")["metadata"]["remove_when"],
            "修正後の回帰checkへ置換したとき",
        )
        self.assertEqual(invalid_status, 1)
        self.assertEqual(
            [item["code"] for item in invalid_result["diagnostics"]],
            [
                "TEST_VALUE_SCHEMA_ERROR",
                "TEST_VALUE_SCHEMA_ERROR",
                "TEST_VALUE_SCHEMA_ERROR",
            ],
        )

    # @test-value v2
    # kind = "contract"
    # claim = "v2固有fieldのunknown値と型不一致を抽出境界で拒否する"
    # oracle = { type = "issue", ref = "#43" }
    # fault = "未知boundary、未知risk tag、文字列risk_tags、failure_modeをv2 metadataとして通す"
    # observable = "各入力に対するTEST_VALUE_SCHEMA_ERRORとmetadata null"
    # observation_boundary = "component-behavior"
    # scope = "test-value-schema"
    # lifecycle = "permanent"
    # @end-test-value
    def test_v2_rejects_unknown_fields_enums_and_types(self) -> None:
        replacements = (
            (
                '# observation_boundary = "component-behavior"',
                '# observation_boundary = "database"',
            ),
            (
                '# observation_boundary = "component-behavior"',
                '# observation_boundary = 1',
            ),
            (
                '# lifecycle = "permanent"',
                '# lifecycle = "permanent"\n# risk_tags = ["availability"]',
            ),
            (
                '# lifecycle = "permanent"',
                '# lifecycle = "permanent"\n# risk_tags = "security"',
            ),
            (
                '# lifecycle = "permanent"',
                '# lifecycle = "permanent"\n# failure_mode = "legacy field"',
            ),
        )
        paths = []
        for index, (old, new) in enumerate(replacements):
            relative = f"tests/test_invalid_v2_{index}.py"
            paths.append(relative)
            self.write(
                relative,
                VALID_METADATA.replace(old, new)
                + f"def test_invalid_v2_{index}():\n    assert True\n",
            )

        result, exit_status = self.extract(*paths)

        self.assertEqual(exit_status, 1)
        self.assertTrue(all(record["metadata"] is None for record in result["tests"]))
        self.assertEqual(
            [item["code"] for item in result["diagnostics"]],
            ["TEST_VALUE_SCHEMA_ERROR"] * len(paths),
        )
        self.write(
            "tests/test_valid_v2.py",
            VALID_METADATA + "def test_valid_v2():\n    assert True\n",
        )
        valid_result, valid_status = self.extract("tests/test_valid_v2.py")
        self.assertEqual(valid_status, 0)
        valid_metadata = valid_result["tests"][0]["metadata"]
        for field in (
            "kind",
            "lifecycle",
            "observation_boundary",
            "risk_tags",
            "oracle",
            "expires_on",
        ):
            with self.subTest(nullable_field=field):
                errors = EXTRACTOR.validate_metadata(
                    {**valid_metadata, field: None},
                    2,
                )
                self.assertTrue(errors)

    # @test-value v2
    # kind = "contract"
    # claim = "path modeのv1を移行dataとして読取るがTEST_VALUE_V2_REQUIREDで審査開始を止める"
    # oracle = { type = "adr", ref = "ADR-0022 v1読取りをv2移行に限定する" }
    # fault = "v1 recordを成功扱いするか移行に必要なmetadataを失う"
    # observable = "exit status、diagnostic、metadata_format_version、metadata hash"
    # observation_boundary = "public-boundary"
    # scope = "extractor-path-mode"
    # lifecycle = "permanent"
    # @end-test-value
    def test_path_mode_requires_v2_and_retains_valid_v1_migration_data(self) -> None:
        self.write(
            "tests/test_v1.py",
            V1_METADATA + "def test_v1():\n    assert True\n",
        )

        result, exit_status = self.extract("tests/test_v1.py")

        self.assertEqual(exit_status, 1)
        self.assertEqual(result["warnings"], [])
        self.assertEqual(
            [item["code"] for item in result["diagnostics"]],
            ["TEST_VALUE_V2_REQUIRED"],
        )
        record = result["tests"][0]
        self.assertEqual(record["metadata_format_version"], 1)
        self.assertEqual(record["metadata"]["failure_mode"], "応答喪失後の再送で請求を二重に永続化する")
        self.assertRegex(record["metadata_hash"], r"^sha256:[0-9a-f]{64}$")

    # @test-value v1
    # kind = "regression"
    # claim = "nested testをUNSUPPORTED、syntax errorをSOURCE_SYNTAX_ERRORとしてrecordなしで返す"
    # oracle = { type = "adr", ref = "ADR-0020" }
    # failure_mode = "未対応nested宣言または壊れたsourceを黙って成功扱いする"
    # scope = "python-source-extraction"
    # lifecycle = "permanent"
    # @end-test-value
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

    # @test-value v1
    # kind = "invariant"
    # claim = "入力順とLF/CRLFが違ってもcanonical JSONとsource hashを一致させる"
    # oracle = { type = "adr", ref = "ADR-0020" }
    # failure_mode = "同じsourceのJSONやhashが列挙順または改行形式で変動する"
    # scope = "result-projection"
    # lifecycle = "permanent"
    # @end-test-value
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

    # @test-value v1
    # kind = "regression"
    # claim = "文字列内のmarker風textをmetadata comment blockとして扱わない"
    # oracle = { type = "adr", ref = "ADR-0020" }
    # failure_mode = "test本文中の文字列を追加metadataとして誤解析する"
    # scope = "python-source-extraction"
    # lifecycle = "permanent"
    # @end-test-value
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

    # @test-value v1
    # kind = "contract"
    # claim = "public CLIはexit 0でparse可能なJSONと期待recordをstdoutへ返す"
    # oracle = { type = "adr", ref = "ADR-0020" }
    # failure_mode = "library経路だけ成功しCLI consumerがJSONを取得できない"
    # scope = "public-cli"
    # lifecycle = "permanent"
    # @end-test-value
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

    # @test-value v2
    # kind = "contract"
    # claim = "明示path modeはGit snapshot間の対応を推測せずtransitionsをnullとして返す"
    # oracle = { type = "issue", ref = "natumekazuki/.codex#43" }
    # fault = "単一snapshotの全file抽出から架空のADDEDまたはSURVIVED transitionを生成する"
    # observable = "path mode抽出結果のtransitions field"
    # observation_boundary = "public-boundary"
    # scope = "test-value-output-v2"
    # lifecycle = "permanent"
    # @end-test-value
    def test_path_mode_marks_transitions_not_applicable(self) -> None:
        self.write(
            "tests/test_path_mode.py",
            VALID_METADATA + "def test_path_mode():\n    assert True\n",
        )

        result, exit_status = self.extract("tests/test_path_mode.py")

        self.assertEqual(exit_status, 0)
        self.assertIsNone(result["transitions"])
        self.assertEqual(len(result["tests"]), 1)

    # @test-value v1
    # kind = "regression"
    # claim = "Git modeは変更testだけを選び未変更legacy testを移行対象にしない"
    # oracle = { type = "adr", ref = "ADR-0021" }
    # failure_mode = "未変更testのmetadata欠落で差分審査が停止する"
    # scope = "git-diff-selection"
    # lifecycle = "permanent"
    # @end-test-value
    def test_git_mode_selects_changed_test_without_migrating_legacy_test(self) -> None:
        source = (
            "def test_legacy():\n"
            "    assert True\n\n"
            + VALID_METADATA
            + "def test_changed():\n"
            "    assert observed() == 1\n"
        )
        path = self.write("tests/test_changed.py", source)
        base = self.initialize_git()
        path.write_text(source.replace("observed() == 1", "observed() == 2"), encoding="utf-8")

        result, exit_status, stderr = self.extract_git(base)

        self.assertEqual(exit_status, 0, stderr)
        self.assertEqual(result["diagnostics"], [])
        self.assertEqual(
            [record["source"]["symbol"] for record in result["tests"]],
            ["test_changed"],
        )
        self.assertIn("observed() == 2", result["tests"][0]["source_text"])

    # @test-value v2
    # kind = "contract"
    # claim = "Git modeは追加・生存・完全削除testをtyped transitionとして返し、現snapshotのrecord集合をtestsへ一度だけ投影する"
    # oracle = { type = "issue", ref = "natumekazuki/.codex#44" }
    # fault = "完全削除testを空selectionとして失うか、transitionのafterとtestsが異なるrecord集合になる"
    # observable = "Git抽出結果のtransitions、tests、削除前record"
    # observation_boundary = "public-boundary"
    # scope = "git-diff-selection"
    # lifecycle = "permanent"
    # @end-test-value
    def test_git_mode_preserves_added_survived_and_deleted_transitions(self) -> None:
        survived_source = (
            VALID_METADATA
            + "def test_survived():\n"
            + "    assert observed() == 1\n"
        )
        deleted_source = (
            VALID_METADATA
            + "def test_deleted():\n"
            + "    assert retained_obligation()\n"
        )
        survived = self.write("tests/test_survived.py", survived_source)
        deleted = self.write("tests/test_deleted.py", deleted_source)
        base = self.initialize_git()
        survived.write_text(
            survived_source.replace("observed() == 1", "observed() == 2"),
            encoding="utf-8",
        )
        deleted.unlink()
        self.write(
            "tests/test_added.py",
            VALID_METADATA + "def test_added():\n    assert new_obligation()\n",
        )

        result, exit_status, stderr = self.extract_git(base)

        self.assertEqual(exit_status, 0, stderr)
        self.assertEqual(result["diagnostics"], [])
        self.assertEqual(
            [transition["kind"] for transition in result["transitions"]],
            ["ADDED", "DELETED", "SURVIVED"],
        )
        current_records = [
            transition["after"]
            for transition in result["transitions"]
            if transition["after"] is not None
        ]
        self.assertEqual(current_records, result["tests"])
        deleted_transition = result["transitions"][1]
        self.assertIsNone(deleted_transition["after"])
        self.assertEqual(
            deleted_transition["before"]["source"]["path"],
            "tests/test_deleted.py",
        )
        self.assertIn(
            "retained_obligation()",
            deleted_transition["before"]["source_text"],
        )

    # @test-value v2
    # kind = "regression"
    # claim = "add/deleteとして分かれたfile pair間では同じtest symbolでも別recordとして保持する"
    # oracle = { type = "issue", ref = "natumekazuki/.codex#44" }
    # fault = "削除recordと追加recordをsymbol名だけでSURVIVEDへ誤対応して元の削除義務を消す"
    # observable = "同名recordに対するDELETEDとADDEDの独立transition"
    # observation_boundary = "public-boundary"
    # scope = "git-diff-selection"
    # lifecycle = "permanent"
    # @end-test-value
    def test_git_mode_does_not_match_symbol_across_add_delete_pairs(self) -> None:
        deleted_source = (
            VALID_METADATA
            + "def test_same_symbol():\n"
            + "".join(f"    assert old_observation_{index}()\n" for index in range(20))
        )
        added_metadata = '''# @test-value v2
# kind = "security"
# claim = "新しい境界では権限外の入力を拒否する"
# oracle = { type = "contract", ref = "AUTH-NEW-009" }
# fault = "権限外の入力を処理して外部状態を変更する"
# observable = "拒否responseと外部状態の件数"
# observation_boundary = "public-boundary"
# scope = "replacement-boundary"
# lifecycle = "permanent"
# @end-test-value
'''
        added_source = (
            added_metadata
            + "def test_same_symbol():\n"
            + "".join(f"    assert new_boundary_{index}()\n" for index in range(20))
        )
        deleted = self.write("tests/test_deleted_pair.py", deleted_source)
        base = self.initialize_git()
        deleted.unlink()
        self.write("tests/test_added_pair.py", added_source)

        name_status = self.git("diff", "--find-renames", "--name-status", base)
        self.assertIn("D\ttests/test_deleted_pair.py", name_status)
        self.assertEqual(
            self.git("ls-files", "--others", "--exclude-standard"),
            "tests/test_added_pair.py",
        )

        result, exit_status, stderr = self.extract_git(base)

        self.assertEqual(exit_status, 0, stderr)
        self.assertEqual(
            [transition["kind"] for transition in result["transitions"]],
            ["ADDED", "DELETED"],
        )
        self.assertEqual(
            [
                (transition["before"] or transition["after"])["source"]["symbol"]
                for transition in result["transitions"]
            ],
            ["test_same_symbol", "test_same_symbol"],
        )

    # @test-value v2
    # kind = "compatibility"
    # claim = "完全削除されたv1 testも移行要求を保持し、v1のまま審査へ進めない"
    # oracle = { type = "issue", ref = "natumekazuki/.codex#43" }
    # fault = "削除されたv1 recordのTEST_VALUE_V2_REQUIREDを失い、DELETED transitionだけを成功結果として返す"
    # observable = "Git抽出結果のDELETED.before、diagnostic、exit status"
    # observation_boundary = "public-boundary"
    # scope = "git-diff-selection"
    # lifecycle = "ephemeral"
    # remove_when = "v1読取り対応を撤去した時"
    # @end-test-value
    def test_git_mode_keeps_v1_migration_error_for_deleted_test(self) -> None:
        deleted = self.write(
            "tests/test_deleted_v1.py",
            V1_METADATA + "def test_deleted_v1():\n    assert legacy_observation()\n",
        )
        base = self.initialize_git()
        deleted.unlink()

        result, exit_status, stderr = self.extract_git(base)

        self.assertEqual(exit_status, 1, stderr)
        self.assertEqual(result["tests"], [])
        self.assertEqual(
            [transition["kind"] for transition in result["transitions"]],
            ["DELETED"],
        )
        self.assertEqual(
            result["transitions"][0]["before"]["metadata_format_version"],
            1,
        )
        self.assertEqual(
            [value["code"] for value in result["diagnostics"]],
            ["TEST_VALUE_V2_REQUIRED"],
        )

    # @test-value v2
    # kind = "contract"
    # claim = "Git modeは未変更v1を選ばず、選択されたv1だけをV2_REQUIREDで停止する"
    # oracle = { type = "adr", ref = "ADR-0022 v1読取りをv2移行に限定する" }
    # fault = "未変更v1を一括移行対象にするか変更v1を審査対象として通す"
    # observable = "Git選択結果のrecord symbol、diagnostic、exit status"
    # observation_boundary = "public-boundary"
    # scope = "git-diff-selection"
    # lifecycle = "permanent"
    # @end-test-value
    def test_git_mode_requires_migration_only_for_selected_v1(self) -> None:
        source = (
            V1_METADATA
            + "def test_v1():\n"
            "    assert legacy_observed() == 1\n\n"
            + VALID_METADATA
            + "def test_v2():\n"
            "    assert current_observed() == 1\n"
        )
        path = self.write("tests/test_versions.py", source)
        base = self.initialize_git()
        v2_only = source.replace("current_observed() == 1", "current_observed() == 2")
        path.write_text(v2_only, encoding="utf-8")

        result, exit_status, stderr = self.extract_git(base)

        self.assertEqual(exit_status, 0, stderr)
        self.assertEqual(result["diagnostics"], [])
        self.assertEqual(result["warnings"], [])
        self.assertEqual(
            [record["source"]["symbol"] for record in result["tests"]],
            ["test_v2"],
        )

        path.write_text(
            v2_only.replace("legacy_observed() == 1", "legacy_observed() == 2"),
            encoding="utf-8",
        )
        mixed_result, mixed_status, mixed_stderr = self.extract_git(base)

        self.assertEqual(mixed_status, 1, mixed_stderr)
        self.assertEqual(
            [record["source"]["symbol"] for record in mixed_result["tests"]],
            ["test_v1", "test_v2"],
        )
        self.assertEqual(
            [item["code"] for item in mixed_result["diagnostics"]],
            ["TEST_VALUE_V2_REQUIRED"],
        )
        self.assertEqual(mixed_result["tests"][0]["metadata_format_version"], 1)

    # @test-value v1
    # kind = "regression"
    # claim = "改行コードだけの変更はtest価値の再審査対象にしない"
    # oracle = { type = "adr", ref = "ADR-0021" }
    # failure_mode = "LFからCRLFへの変換で未変更legacy testまで選択し審査を停止する"
    # scope = "git-diff-selection"
    # lifecycle = "permanent"
    # distinction = "本文変更を伴わないfile全体のline-ending変換だけを扱う"
    # @end-test-value
    def test_git_mode_ignores_line_ending_only_changes(self) -> None:
        source = (
            "def test_legacy():\n"
            "    assert True\n\n"
            + VALID_METADATA
            + "def test_unchanged():\n"
            "    assert observed() == 1\n"
        )
        path = self.write("tests/test_line_endings.py", source)
        base = self.initialize_git()
        self.git("config", "core.autocrlf", "false")
        path.write_bytes(source.replace("\n", "\r\n").encode("utf-8"))

        working = self.extract_git(base)
        self.git("add", "tests/test_line_endings.py")
        staged = self.extract_git(base, "python", "--staged")
        self.git("commit", "--quiet", "-m", "convert line endings")
        head = self.git("rev-parse", "HEAD")
        committed = self.extract_git(base, "python", "--head", head)

        for mode, (result, exit_status, stderr) in {
            "working": working,
            "staged": staged,
            "head": committed,
        }.items():
            with self.subTest(mode=mode):
                self.assertEqual(exit_status, 0, stderr)
                self.assertEqual(result["tests"], [])
                self.assertEqual(result["diagnostics"], [])

    # @test-value v1
    # kind = "regression"
    # claim = "改行コード変換と同時に意味変更したtestは審査対象に残す"
    # oracle = { type = "adr", ref = "ADR-0021" }
    # failure_mode = "line-ending差分の除外が同じfileのassertion変更まで隠す"
    # scope = "git-diff-selection"
    # lifecycle = "permanent"
    # distinction = "改行コードだけの変更ではなくassertionの意味変更を同時に含む"
    # @end-test-value
    def test_git_mode_keeps_content_change_with_line_ending_conversion(self) -> None:
        source = (
            "def test_legacy():\n"
            "    assert True\n\n"
            + VALID_METADATA
            + "def test_changed():\n"
            "    assert observed() == 1\n"
        )
        path = self.write("tests/test_line_endings.py", source)
        base = self.initialize_git()
        self.git("config", "core.autocrlf", "false")
        changed = source.replace("observed() == 1", "observed() == 2")
        path.write_bytes(changed.replace("\n", "\r\n").encode("utf-8"))

        working = self.extract_git(base)
        self.git("add", "tests/test_line_endings.py")
        staged = self.extract_git(base, "python", "--staged")
        self.git("commit", "--quiet", "-m", "change assertion and line endings")
        head = self.git("rev-parse", "HEAD")
        committed = self.extract_git(base, "python", "--head", head)

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
                    ["test_changed"],
                )
                self.assertIn("observed() == 2", result["tests"][0]["source_text"])

    # @test-value v1
    # kind = "contract"
    # claim = "metadataだけの変更も対応するtest recordを選択する"
    # oracle = { type = "adr", ref = "ADR-0021" }
    # failure_mode = "価値コメントの意味変更が審査対象から漏れる"
    # scope = "git-diff-selection"
    # lifecycle = "permanent"
    # @end-test-value
    def test_git_mode_selects_metadata_only_change(self) -> None:
        source = VALID_METADATA + "def test_changed():\n    assert True\n"
        path = self.write("tests/test_metadata.py", source)
        base = self.initialize_git()
        path.write_text(
            source.replace("同じkeyによる再試行", "同じidempotency keyによる再試行"),
            encoding="utf-8",
        )

        result, exit_status, stderr = self.extract_git(base)

        self.assertEqual(exit_status, 0, stderr)
        self.assertEqual(len(result["tests"]), 1)
        self.assertIn("idempotency key", result["tests"][0]["metadata"]["claim"])

    # @test-value v1
    # kind = "regression"
    # claim = "working tree比較は未追跡test fileも審査対象に含める"
    # oracle = { type = "adr", ref = "ADR-0021" }
    # failure_mode = "新規未追跡testが審査を通らず追加される"
    # scope = "git-diff-selection"
    # lifecycle = "permanent"
    # @end-test-value
    def test_git_mode_includes_untracked_test_file(self) -> None:
        base = self.initialize_git()
        self.write("tests/日本 語/test untracked.py", "def test_untracked():\n    assert True\n")

        result, exit_status, stderr = self.extract_git(base)

        self.assertEqual(exit_status, 1, stderr)
        self.assertEqual(
            [record["source"]["symbol"] for record in result["tests"]],
            ["test_untracked"],
        )
        self.assertEqual(
            [item["code"] for item in result["diagnostics"]],
            ["TEST_VALUE_MISSING"],
        )

    # @test-value v1
    # kind = "contract"
    # claim = "staged modeはworking treeではなくindexのsourceを抽出する"
    # oracle = { type = "adr", ref = "ADR-0021" }
    # failure_mode = "diff対象と異なるsnapshotの本文をAIへ渡す"
    # scope = "git-snapshot-selection"
    # lifecycle = "permanent"
    # @end-test-value
    def test_git_mode_reads_staged_snapshot_instead_of_worktree(self) -> None:
        source = VALID_METADATA + "def test_snapshot():\n    assert observed() == 1\n"
        path = self.write("tests/test_snapshot.py", source)
        base = self.initialize_git()
        path.write_text(source.replace("== 1", "== 2"), encoding="utf-8")
        self.git("add", "tests/test_snapshot.py")
        path.write_text(source.replace("== 1", "== 3"), encoding="utf-8")

        result, exit_status, stderr = self.extract_git(base, "python", "--staged")

        self.assertEqual(exit_status, 0, stderr)
        self.assertIn("observed() == 2", result["tests"][0]["source_text"])
        self.assertNotIn("observed() == 3", result["tests"][0]["source_text"])

    # @test-value v1
    # kind = "contract"
    # claim = "head modeは明示commitのsourceを抽出する"
    # oracle = { type = "adr", ref = "ADR-0021" }
    # failure_mode = "commit審査へ別snapshotの本文が混入する"
    # scope = "git-snapshot-selection"
    # lifecycle = "permanent"
    # @end-test-value
    def test_git_mode_reads_requested_commit_snapshot(self) -> None:
        source = VALID_METADATA + "def test_snapshot():\n    assert observed() == 1\n"
        path = self.write("tests/test_snapshot.py", source)
        base = self.initialize_git()
        path.write_text(source.replace("== 1", "== 2"), encoding="utf-8")
        self.git("add", "tests/test_snapshot.py")
        self.git("commit", "--quiet", "-m", "change")
        head = self.git("rev-parse", "HEAD")
        path.write_text(source.replace("== 1", "== 3"), encoding="utf-8")

        result, exit_status, stderr = self.extract_git(
            base, "python", "--head", head
        )

        self.assertEqual(exit_status, 0, stderr)
        self.assertIn("observed() == 2", result["tests"][0]["source_text"])
        self.assertNotIn("observed() == 3", result["tests"][0]["source_text"])

    # @test-value v2
    # kind = "contract"
    # claim = "内容を変えないrenameはtest価値の再審査対象にしない"
    # oracle = { type = "adr", ref = "ADR-0021" }
    # fault = "pure renameを新規testと誤認して不要な審査を要求する"
    # observable = "Git抽出結果のtests、transitions、diagnostics"
    # observation_boundary = "public-boundary"
    # scope = "git-diff-selection"
    # lifecycle = "permanent"
    # @end-test-value
    def test_git_mode_ignores_pure_rename_and_unchanged_language(self) -> None:
        source = VALID_METADATA + "def test_renamed():\n    assert True\n"
        self.write("tests/test_before.py", source)
        base = self.initialize_git()
        self.git("mv", "tests/test_before.py", "tests/test_after.py")

        result, exit_status, stderr = self.extract_git(base)

        self.assertEqual(exit_status, 0, stderr)
        self.assertEqual(result["tests"], [])
        self.assertEqual(result["transitions"], [])
        self.assertEqual(result["diagnostics"], [])

    # @test-value v1
    # kind = "contract"
    # claim = "解決不能なGit revisionでは部分JSONを返さずinvocation errorにする"
    # oracle = { type = "adr", ref = "ADR-0021" }
    # failure_mode = "誤ったbaseで空の審査結果を成功扱いする"
    # scope = "git-diff-selection"
    # lifecycle = "permanent"
    # @end-test-value
    def test_git_mode_rejects_invalid_revision_without_partial_result(self) -> None:
        self.initialize_git()

        result, exit_status, stderr = self.extract_git("missing-revision")

        self.assertEqual(exit_status, 2)
        self.assertEqual(result, {})
        self.assertIn("git command failed", stderr)

    # @test-value v1
    # kind = "security"
    # claim = "working treeのroot外symlinkを読まずSOURCE_OUTSIDE_ROOTにする"
    # oracle = { type = "adr", ref = "ADR-0021" }
    # failure_mode = "repository外sourceのtest本文をAI入力へ漏らす"
    # scope = "git-working-snapshot"
    # lifecycle = "permanent"
    # @end-test-value
    def test_git_mode_rejects_untracked_symlink_outside_root(self) -> None:
        base = self.initialize_git()
        outside = self.root.parent / f"{self.root.name}-outside.py"
        outside.write_text(
            VALID_METADATA + "def test_external_secret():\n    assert True\n",
            encoding="utf-8",
        )
        link = self.root / "tests" / "test_link.py"
        link.parent.mkdir(parents=True)
        try:
            try:
                link.symlink_to(outside)
            except OSError as error:
                self.skipTest(f"symlink creation is unavailable: {error}")

            result, exit_status, stderr = self.extract_git(base)
        finally:
            link.unlink(missing_ok=True)
            outside.unlink(missing_ok=True)

        self.assertEqual(exit_status, 1, stderr)
        self.assertEqual(result["tests"], [])
        self.assertEqual(
            [item["code"] for item in result["diagnostics"]],
            ["SOURCE_OUTSIDE_ROOT"],
        )
        self.assertNotIn("test_external_secret", json.dumps(result))

    # @test-value v2
    # kind = "regression"
    # claim = "部分削除はSURVIVEDとして選び、test全体の削除は隣接testへ誤対応せずDELETEDとして保持する"
    # oracle = { type = "issue", ref = "natumekazuki/.codex#44" }
    # fault = "部分削除を見落とすか、完全削除を隣接testへSURVIVEDとして結合して元recordを失う"
    # observable = "Git抽出結果のtestsとSURVIVED、DELETED transition"
    # observation_boundary = "public-boundary"
    # scope = "git-diff-selection"
    # lifecycle = "permanent"
    # @end-test-value
    def test_git_mode_selects_deletion_only_changes(self) -> None:
        body_source = (
            VALID_METADATA
            + "def test_body():\n"
            + "    assert precondition()\n"
            + "    assert observed() == 1\n"
        )
        metadata_source = VALID_METADATA + "def test_metadata():\n    assert True\n"
        removed_source = (
            VALID_METADATA
            + "def test_removed():\n"
            + "    assert True\n\n"
            + "def test_survivor():\n"
            + "    assert True\n"
        )
        syntax_repair_source = (
            VALID_METADATA
            + "def test_syntax_repair():\n"
            + "    assert True\n"
            + "    (\n"
        )
        body = self.write("tests/test_body.py", body_source)
        metadata = self.write("tests/test_metadata.py", metadata_source)
        removed = self.write("tests/test_removed.py", removed_source)
        syntax_repair = self.write(
            "tests/test_syntax_repair.py",
            syntax_repair_source,
        )
        base = self.initialize_git()
        body.write_text(
            body_source.replace("    assert observed() == 1\n", ""),
            encoding="utf-8",
        )
        metadata.write_text(
            "def test_metadata():\n    assert True\n",
            encoding="utf-8",
        )
        removed.write_text(
            "def test_survivor():\n    assert True\n",
            encoding="utf-8",
        )
        syntax_repair.write_text(
            syntax_repair_source.replace("    (\n", ""),
            encoding="utf-8",
        )

        working = self.extract_git(base)
        self.git(
            "add",
            "tests/test_body.py",
            "tests/test_metadata.py",
            "tests/test_removed.py",
            "tests/test_syntax_repair.py",
        )
        staged = self.extract_git(base, "python", "--staged")
        self.git("commit", "--quiet", "-m", "delete lines")
        head = self.git("rev-parse", "HEAD")
        committed = self.extract_git(base, "python", "--head", head)

        for mode, (result, exit_status, stderr) in {
            "working": working,
            "staged": staged,
            "head": committed,
        }.items():
            with self.subTest(mode=mode):
                self.assertEqual(exit_status, 1, stderr)
                self.assertEqual(
                    [record["source"]["symbol"] for record in result["tests"]],
                    ["test_body", "test_metadata", "test_syntax_repair"],
                )
                self.assertEqual(
                    [item["code"] for item in result["diagnostics"]],
                    ["TEST_VALUE_MISSING"],
                )
                self.assertEqual(
                    [transition["kind"] for transition in result["transitions"]],
                    ["SURVIVED", "SURVIVED", "DELETED", "ADDED"],
                )
                deleted_transition = result["transitions"][2]
                self.assertEqual(
                    deleted_transition["before"]["source"]["symbol"],
                    "test_removed",
                )
                self.assertIsNone(deleted_transition["after"])

    # @test-value v1
    # kind = "regression"
    # claim = "置換hunkのold側がsurviving testへ属する場合もそのtestを選択する"
    # oracle = { type = "adr", ref = "ADR-0021" }
    # failure_mode = "削除行の置換先がtest外にあると本文変更を空結果として成功扱いする"
    # scope = "git-diff-selection"
    # lifecycle = "permanent"
    # @end-test-value
    def test_git_mode_selects_old_side_of_replacement_hunk(self) -> None:
        source = (
            VALID_METADATA
            + "def test_replaced():\n"
            + "    assert precondition()\n"
            + "    assert observed() == 1\n"
        )
        path = self.write("tests/test_replacement.py", source)
        base = self.initialize_git()
        path.write_text(
            source.replace("    assert observed() == 1\n", "TOP_LEVEL = True\n"),
            encoding="utf-8",
        )

        working = self.extract_git(base)
        self.git("add", "tests/test_replacement.py")
        staged = self.extract_git(base, "python", "--staged")
        self.git("commit", "--quiet", "-m", "replace assertion")
        head = self.git("rev-parse", "HEAD")
        committed = self.extract_git(base, "python", "--head", head)

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
                    ["test_replaced"],
                )

    # @test-value v2
    # kind = "regression"
    # claim = "metadata結合を壊す変更もbase側recordから対応testへ投影する"
    # oracle = { type = "adr", ref = "ADR-0021" }
    # fault = "開始markerの破損でmetadata欠落diagnosticとtest recordが審査から消える"
    # observable = "Git選択されたrecordとTEST_VALUE_MISSING diagnostic"
    # observation_boundary = "component-behavior"
    # scope = "git-diff-selection"
    # lifecycle = "permanent"
    # @end-test-value
    def test_git_mode_selects_broken_metadata_binding(self) -> None:
        source = VALID_METADATA + "def test_broken_binding():\n    assert True\n"
        path = self.write("tests/test_binding.py", source)
        base = self.initialize_git()
        path.write_text(
            source.replace("@test-value v2", "@test-values v2"),
            encoding="utf-8",
        )

        working = self.extract_git(base)
        self.git("add", "tests/test_binding.py")
        staged = self.extract_git(base, "python", "--staged")
        self.git("commit", "--quiet", "-m", "break metadata binding")
        head = self.git("rev-parse", "HEAD")
        committed = self.extract_git(base, "python", "--head", head)

        for mode, (result, exit_status, stderr) in {
            "working": working,
            "staged": staged,
            "head": committed,
        }.items():
            with self.subTest(mode=mode):
                self.assertEqual(exit_status, 1, stderr)
                self.assertEqual(
                    [record["source"]["symbol"] for record in result["tests"]],
                    ["test_broken_binding"],
                )
                self.assertEqual(
                    [item["code"] for item in result["diagnostics"]],
                    ["TEST_VALUE_MISSING"],
                )

    # @test-value v1
    # kind = "regression"
    # claim = "metadataと宣言の間への純挿入もbase側recordから対応testへ投影する"
    # oracle = { type = "adr", ref = "ADR-0021" }
    # failure_mode = "挿入hunkにold側rangeがなく結合を失ったtestとdiagnosticが審査から消える"
    # scope = "git-diff-selection"
    # lifecycle = "permanent"
    # @end-test-value
    def test_git_mode_selects_inserted_metadata_separator(self) -> None:
        source = VALID_METADATA + "def test_separated_binding():\n    assert True\n"
        path = self.write("tests/test_inserted_separator.py", source)
        base = self.initialize_git()
        path.write_text(
            source.replace(
                "def test_separated_binding():",
                "SEPARATOR = True\ndef test_separated_binding():",
            ),
            encoding="utf-8",
        )

        working = self.extract_git(base)
        self.git("add", "tests/test_inserted_separator.py")
        staged = self.extract_git(base, "python", "--staged")
        self.git("commit", "--quiet", "-m", "separate metadata binding")
        head = self.git("rev-parse", "HEAD")
        committed = self.extract_git(base, "python", "--head", head)

        for mode, (result, exit_status, stderr) in {
            "working": working,
            "staged": staged,
            "head": committed,
        }.items():
            with self.subTest(mode=mode):
                self.assertEqual(exit_status, 1, stderr)
                self.assertEqual(
                    [record["source"]["symbol"] for record in result["tests"]],
                    ["test_separated_binding"],
                )
                self.assertEqual(
                    [item["code"] for item in result["diagnostics"]],
                    ["TEST_VALUE_MISSING"],
                )

    # @test-value v1
    # kind = "regression"
    # claim = "先頭decoratorだけを削除したsurviving testをbase側rangeから選択する"
    # oracle = { type = "adr", ref = "ADR-0021" }
    # failure_mode = "削除anchorへ投影した旧開始行が現開始行と一致せず変更testが審査から消える"
    # scope = "git-diff-selection"
    # lifecycle = "permanent"
    # @end-test-value
    def test_git_mode_selects_test_after_leading_decorator_deletion(self) -> None:
        source = (
            "def test_legacy():\n"
            + "    assert True\n\n"
            + VALID_METADATA
            + "@pytest.mark.one\n"
            + "@pytest.mark.two\n"
            + "def test_decorated():\n"
            + "    assert True\n"
        )
        path = self.write("tests/test_decorator_deletion.py", source)
        base = self.initialize_git()
        path.write_text(source.replace("@pytest.mark.one\n", ""), encoding="utf-8")

        working = self.extract_git(base)
        self.git("add", "tests/test_decorator_deletion.py")
        staged = self.extract_git(base, "python", "--staged")
        self.git("commit", "--quiet", "-m", "remove leading decorator")
        head = self.git("rev-parse", "HEAD")
        committed = self.extract_git(base, "python", "--head", head)

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
                    ["test_decorated"],
                )

    # @test-value v1
    # kind = "regression"
    # claim = "nested Python testの本文変更をUNSUPPORTED diagnosticへ結合する"
    # oracle = { type = "adr", ref = "ADR-0021" }
    # failure_mode = "未対応宣言の開始行以外の変更を空結果として成功扱いする"
    # scope = "git-diff-selection"
    # lifecycle = "permanent"
    # @end-test-value
    def test_git_mode_selects_changed_nested_python_test(self) -> None:
        source = (
            "def helper():\n"
            "    def test_nested():\n"
            "        assert observed() == 1\n"
        )
        path = self.write("tests/test_nested_change.py", source)
        base = self.initialize_git()
        path.write_text(source.replace("== 1", "== 2"), encoding="utf-8")

        working = self.extract_git(base)
        self.git("add", "tests/test_nested_change.py")
        staged = self.extract_git(base, "python", "--staged")
        self.git("commit", "--quiet", "-m", "change nested test")
        head = self.git("rev-parse", "HEAD")
        committed = self.extract_git(base, "python", "--head", head)

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
                self.assertEqual(
                    set(result["diagnostics"][0]),
                    {"code", "path", "line", "message"},
                )

    # @test-value v1
    # kind = "regression"
    # claim = "nested Python testの本文削除を削除anchorからUNSUPPORTED diagnosticへ結合する"
    # oracle = { type = "adr", ref = "ADR-0021" }
    # failure_mode = "未対応宣言内の削除専用hunkを空結果として成功扱いする"
    # scope = "git-diff-selection"
    # lifecycle = "permanent"
    # distinction = "new側rangeが残る置換ではなく本文末尾の削除専用hunkを扱う"
    # @end-test-value
    def test_git_mode_selects_deleted_line_in_nested_python_test(self) -> None:
        source = (
            "def helper():\n"
            "    def test_nested():\n"
            "        assert precondition()\n"
            "        assert removed_condition()\n"
        )
        path = self.write("tests/test_nested_deletion.py", source)
        base = self.initialize_git()
        path.write_text(
            source.replace("        assert removed_condition()\n", ""),
            encoding="utf-8",
        )

        working = self.extract_git(base)
        self.git("add", "tests/test_nested_deletion.py")
        staged = self.extract_git(base, "python", "--staged")
        self.git("commit", "--quiet", "-m", "delete nested test line")
        head = self.git("rev-parse", "HEAD")
        committed = self.extract_git(base, "python", "--head", head)

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
    # claim = "未対応test宣言の全削除で直後の未変更testを選択しない"
    # oracle = { type = "adr", ref = "ADR-0021" }
    # failure_mode = "全削除anchorを隣接legacy testへ結合してmetadata移行を誤要求する"
    # scope = "git-diff-selection"
    # lifecycle = "permanent"
    # distinction = "未対応宣言がsurviveする本文削除ではなく宣言range全体の削除を扱う"
    # @end-test-value
    def test_git_mode_excludes_fully_deleted_unsupported_test(self) -> None:
        source = (
            "def helper():\n"
            "    pass\n"
            "    def test_nested():\n"
            "        assert True\n"
            "def test_survivor():\n"
            "    assert True\n"
        )
        path = self.write("tests/test_unsupported_deletion.py", source)
        base = self.initialize_git()
        path.write_text(
            source.replace(
                "    def test_nested():\n        assert True\n",
                "",
            ),
            encoding="utf-8",
        )

        working = self.extract_git(base)
        self.git("add", "tests/test_unsupported_deletion.py")
        staged = self.extract_git(base, "python", "--staged")
        self.git("commit", "--quiet", "-m", "delete unsupported test")
        head = self.git("rev-parse", "HEAD")
        committed = self.extract_git(base, "python", "--head", head)

        for mode, (result, exit_status, stderr) in {
            "working": working,
            "staged": staged,
            "head": committed,
        }.items():
            with self.subTest(mode=mode):
                self.assertEqual(exit_status, 0, stderr)
                self.assertEqual(result["tests"], [])
                self.assertEqual(result["diagnostics"], [])

    # @test-value v1
    # kind = "regression"
    # claim = "unrelatedなunsupported宣言があってもtest全削除を隣接testへ投影しない"
    # oracle = { type = "adr", ref = "ADR-0021" }
    # failure_mode = "別位置のunsupported diagnosticで未変更legacy testを移行対象にする"
    # scope = "git-diff-selection"
    # lifecycle = "permanent"
    # @end-test-value
    def test_git_mode_localizes_base_unsupported_diagnostic(self) -> None:
        source = (
            VALID_METADATA
            + "def test_removed():\n"
            + "    assert True\n\n"
            + "def test_survivor():\n"
            + "    assert True\n\n"
            + "def helper():\n"
            + "    def test_nested():\n"
            + "        assert True\n"
        )
        path = self.write("tests/test_unsupported.py", source)
        base = self.initialize_git()
        path.write_text(
            "def test_survivor():\n"
            "    assert True\n\n"
            "def helper():\n"
            "    def test_nested():\n"
            "        assert True\n",
            encoding="utf-8",
        )

        working = self.extract_git(base)
        self.git("add", "tests/test_unsupported.py")
        staged = self.extract_git(base, "python", "--staged")
        self.git("commit", "--quiet", "-m", "remove complete test")
        head = self.git("rev-parse", "HEAD")
        committed = self.extract_git(base, "python", "--head", head)

        for mode, (result, exit_status, stderr) in {
            "working": working,
            "staged": staged,
            "head": committed,
        }.items():
            with self.subTest(mode=mode):
                self.assertEqual(exit_status, 0, stderr)
                self.assertEqual(result["tests"], [])
                self.assertEqual(result["diagnostics"], [])

    # @test-value v1
    # kind = "contract"
    # claim = "native adapter failureはtracebackなしのexit 2として返す"
    # oracle = { type = "contract", ref = "output-v1" }
    # failure_mode = "exit 1とJSONなしのtracebackでconsumerが結果解析に失敗する"
    # scope = "git-adapter-failure"
    # lifecycle = "permanent"
    # @end-test-value
    def test_git_mode_maps_native_adapter_failure_to_exit_two(self) -> None:
        metadata = VALID_METADATA.replace("# ", "// ")
        source = metadata + 'test("adapter", () => { expect(true).toBe(true); });\n'
        path = self.write("tests/adapter.test.ts", source)
        base = self.initialize_git()
        path.write_text(source.replace("true).toBe(true", "false).toBe(false"), encoding="utf-8")
        fake_bin = self.root / "fake-bin"
        fake_bin.mkdir()
        if os.name == "nt":
            git_executable = shutil.which("git")
            self.assertIsNotNone(git_executable)
        else:
            fake_node = fake_bin / "node"
            fake_node.write_text("#!/bin/sh\nexit 7\n", encoding="utf-8")
            fake_node.chmod(0o755)
        env = os.environ.copy()
        if os.name == "nt":
            system_root = Path(env.get("SystemRoot", r"C:\Windows"))
            env["PATH"] = os.pathsep.join(
                [str(Path(git_executable).parent), str(system_root / "System32")]
            )
        else:
            env["PATH"] = str(fake_bin) + os.pathsep + env.get("PATH", "")

        result, exit_status, stderr = self.extract_git(
            base,
            "typescript",
            env=env,
        )

        self.assertEqual(exit_status, 2)
        self.assertEqual(result, {})
        self.assertIn("TypeScript adapter", stderr)
        self.assertNotIn("Traceback", stderr)

    # @test-value v1
    # kind = "regression"
    # claim = "Git属性でbinary指定されたsourceもraw text差分からtestを選択する"
    # oracle = { type = "adr", ref = "ADR-0021" }
    # failure_mode = "repositoryのdiff属性により変更testが空結果になる"
    # scope = "git-diff-selection"
    # lifecycle = "permanent"
    # @end-test-value
    def test_git_mode_forces_text_diff_for_supported_source(self) -> None:
        self.write(".gitattributes", "*.py -diff\n")
        source = VALID_METADATA + "def test_binary_attribute():\n    assert value() == 1\n"
        path = self.write("tests/test_attribute.py", source)
        base = self.initialize_git()
        path.write_text(source.replace("== 1", "== 2"), encoding="utf-8")

        working = self.extract_git(base)
        self.git("add", "tests/test_attribute.py")
        staged = self.extract_git(base, "python", "--staged")
        self.git("commit", "--quiet", "-m", "change attributed source")
        head = self.git("rev-parse", "HEAD")
        committed = self.extract_git(base, "python", "--head", head)

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
                    ["test_binary_attribute"],
                )

    # @test-value v1
    # kind = "security"
    # claim = "public CLIはroot外pathをSOURCE_OUTSIDE_ROOTとして内容を抽出しない"
    # oracle = { type = "adr", ref = "ADR-0020" }
    # failure_mode = "repository外sourceを許可対象としてAI入力へ取り込む"
    # scope = "source-root-boundary"
    # lifecycle = "permanent"
    # @end-test-value
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

    # @test-value v1
    # kind = "security"
    # claim = "path modeでもroot外へ解決するsymlinkを拒否して外部test本文を返さない"
    # oracle = { type = "adr", ref = "ADR-0020" }
    # failure_mode = "字句上root内のsymlinkからrepository外情報を漏らす"
    # scope = "source-root-boundary"
    # lifecycle = "permanent"
    # @end-test-value
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
