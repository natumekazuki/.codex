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

    # @test-value v1
    # kind = "contract"
    # claim = "metadataをdecorated testへ結合しdecoratorから末尾までのsource_textとhashを投影する"
    # oracle = { type = "adr", ref = "ADR-0020" }
    # failure_mode = "metadataを別testへ結合するかdecoratorやassertionをsource_textから欠落させる"
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

    # @test-value v1
    # kind = "regression"
    # claim = "TOML parse errorとschema errorはmetadata nullと対応diagnosticを返す"
    # oracle = { type = "adr", ref = "ADR-0020" }
    # failure_mode = "壊れたpayloadやunknown fieldを有効metadataとして投影する"
    # scope = "test-value-schema"
    # lifecycle = "permanent"
    # @end-test-value
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

    # @test-value v1
    # kind = "regression"
    # claim = "multiline文字列内のdecoyを無視して実際の通常oracle tableを拒否する"
    # oracle = { type = "adr", ref = "ADR-0020" }
    # failure_mode = "claim文字列内のoracle表記を構文根拠にして通常tableを通す"
    # scope = "test-value-schema"
    # lifecycle = "permanent"
    # @end-test-value
    def test_oracle_shape_ignores_inline_table_text_in_multiline_string(self) -> None:
        source = '''# @test-value v1
# kind = "invariant"
# claim = """
# oracle = { type = "contract", ref = "DECOY" }
# claim text
# """
# failure_mode = "誤ったoracle構文を受理する"
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

    # @test-value v1
    # kind = "regression"
    # claim = "field型不一致とreview条件なしcharacterizationをSCHEMA_ERRORにする"
    # oracle = { type = "adr", ref = "ADR-0020" }
    # failure_mode = "型不正または期限条件のない一時契約を有効metadataとして通す"
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

    # @test-value v1
    # kind = "contract"
    # claim = "review_when付きcharacterizationをdiagnosticなしで投影する"
    # oracle = { type = "adr", ref = "ADR-0020" }
    # failure_mode = "見直し条件を持つ有効なcharacterizationを誤拒否する"
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

    # @test-value v1
    # kind = "contract"
    # claim = "内容を変えないrenameはtest価値の再審査対象にしない"
    # oracle = { type = "adr", ref = "ADR-0021" }
    # failure_mode = "pure renameを新規testと誤認して不要な審査を要求する"
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

    # @test-value v1
    # kind = "regression"
    # claim = "部分削除はsurviving testを選びtest全体の削除は隣接testを選ばない"
    # oracle = { type = "adr", ref = "ADR-0021" }
    # failure_mode = "部分削除を見落とすか全削除を隣接testの変更と誤認する"
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

    # @test-value v1
    # kind = "regression"
    # claim = "metadata結合を壊す変更もbase側recordから対応testへ投影する"
    # oracle = { type = "adr", ref = "ADR-0021" }
    # failure_mode = "開始markerの破損でmetadata欠落diagnosticとtest recordが審査から消える"
    # scope = "git-diff-selection"
    # lifecycle = "permanent"
    # @end-test-value
    def test_git_mode_selects_broken_metadata_binding(self) -> None:
        source = VALID_METADATA + "def test_broken_binding():\n    assert True\n"
        path = self.write("tests/test_binding.py", source)
        base = self.initialize_git()
        path.write_text(
            source.replace("@test-value v1", "@test-values v1"),
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
            "\n"
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
