import subprocess
from unittest.mock import patch
import tempfile
import unittest
from pathlib import Path
import sys

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from preflight_review_worker import run_preflight  # noqa: E402


ROLE = '''name = "test_value_luna"
description = "fixture"
model = "gpt-5.6-luna"
model_reasoning_effort = "medium"
sandbox_mode = "read-only"
developer_instructions = "read only"
'''


class PreflightReviewWorkerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.cli = root / "codex.exe"
        self.cli.write_bytes(b"native cli")
        self.role = root / "role.toml"
        self.role.write_text(ROLE, encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    # @test-value v1
    # kind = "security"
    # claim = "preflightはstdinを閉じたversion照会だけを行い、receiptへpayload未配信とeffective値未確認を明示する"
    # oracle = { type = "adr", ref = "ADR-0022" }
    # failure_mode = "隔離や実効設定を確認できないままworker実行済みまたはeffective modelありとして扱う"
    # scope = "review-worker-preflight"
    # lifecycle = "permanent"
    # @end-test-value
    def test_receipt_is_blocked_and_never_reports_payload_or_effective_values(self):
        with patch("preflight_review_worker.subprocess.run") as process:
            process.return_value = subprocess.CompletedProcess([], 0, "codex-cli 0.153.4", "")
            result = run_preflight(str(self.cli), str(self.role))
        self.assertEqual(process.call_count, 1)
        self.assertEqual(process.call_args.args[0], [str(self.cli.resolve()), "--version"])
        self.assertEqual(process.call_args.kwargs["stdin"], subprocess.DEVNULL)
        self.assertGreater(process.call_args.kwargs["timeout"], 0)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertFalse(result["payload_delivered"])
        self.assertIsNone(result["effective"]["model"])
        self.assertIsNone(result["model_available"])
        self.assertIn("EFFECTIVE_TOOL_SURFACE_UNVERIFIED", result["reason_codes"])

    # @test-value v1
    # kind = "invariant"
    # claim = "requested modelとeffortはrole正本からreceiptへ反映される"
    # oracle = { type = "adr", ref = "ADR-0022" }
    # failure_mode = "role正本と異なるmodelまたはeffortをreceiptへ記録してrouting設定を取り違える"
    # scope = "review-worker-preflight"
    # lifecycle = "permanent"
    # @end-test-value
    def test_requested_model_and_effort_are_read_from_role(self):
        for role_name, model, effort in (
            ("test_value_luna", "gpt-5.6-luna", "medium"),
            ("test_value_sol", "gpt-5.6-sol", "xhigh"),
        ):
            with self.subTest(role=role_name):
                declaration = ROLE.replace("test_value_luna", role_name).replace(
                    "gpt-5.6-luna", model
                ).replace('"medium"', f'"{effort}"')
                self.role.write_text(declaration, encoding="utf-8")
                result = run_preflight(
                    str(self.cli), str(self.role), runner=lambda *_: (0, "codex-cli 0.153.4", "")
                )
                self.assertEqual(result["requested"], {"model": model, "effort": effort})

    # @test-value v1
    # kind = "security"
    # claim = "native executableでない入力はversion query前にBLOCKEDになる"
    # oracle = { type = "adr", ref = "ADR-0022" }
    # failure_mode = "非native executableをworker入口として実行し、隔離境界を証明できないまま進む"
    # scope = "review-worker-preflight"
    # lifecycle = "permanent"
    # @end-test-value
    def test_invalid_executable_is_blocked_without_query(self):
        called = []
        result = run_preflight(
            str(self.role), str(self.role), runner=lambda executable, timeout: called.append(executable)
        )
        self.assertIn("RUNTIME_UNSUPPORTED", result["reason_codes"])
        self.assertEqual(called, [])

    # @test-value v1
    # kind = "security"
    # claim = "対象外roleはversion照会前に拒否され、実行構成として採用されない"
    # oracle = { type = "issue", ref = "https://github.com/natumekazuki/.codex/issues/42" }
    # failure_mode = "対象外roleを専用審査roleとして受理して誤った要求値を記録する"
    # scope = "review-worker-preflight"
    # lifecycle = "permanent"
    # @end-test-value
    def test_invalid_role_is_rejected_before_query(self):
        self.role.write_text(ROLE.replace('test_value_luna', 'unknown_role'), encoding="utf-8")
        called = []
        result = run_preflight(
            str(self.cli), str(self.role), runner=lambda executable, timeout: called.append(executable)
        )
        self.assertIn("RUNTIME_UNSUPPORTED", result["reason_codes"])
        self.assertEqual(called, [])

    # @test-value v1
    # kind = "invariant"
    # claim = "native version queryのtimeoutはBLOCKED receiptになり成功扱いされない"
    # oracle = { type = "adr", ref = "ADR-0022" }
    # failure_mode = "version query timeout後にpreflightを成功またはworker起動可能として扱う"
    # scope = "review-worker-preflight"
    # lifecycle = "permanent"
    # @end-test-value
    def test_timeout_is_blocked_and_never_success(self):
        def timeout(executable, limit):
            import subprocess
            raise subprocess.TimeoutExpired([executable, "--version"], limit)

        result = run_preflight(str(self.cli), str(self.role), runner=timeout)
        self.assertIn("CLI_VERSION_TIMEOUT", result["reason_codes"])
        self.assertEqual(result["status"], "BLOCKED")

    # @test-value v1
    # kind = "security"
    # claim = "version query中にCLI snapshotが変化した場合はBLOCKEDになる"
    # oracle = { type = "adr", ref = "ADR-0022" }
    # failure_mode = "検証前後で異なるCLIを使ったままreceiptを有効な実行証拠として扱う"
    # scope = "review-worker-preflight"
    # lifecycle = "permanent"
    # @end-test-value
    def test_changed_cli_snapshot_is_blocked(self):
        def mutate(executable, limit):
            Path(executable).write_bytes(b"changed")
            return (0, "codex-cli 0.153.4", "")

        result = run_preflight(str(self.cli), str(self.role), runner=mutate)
        self.assertIn("CLI_SNAPSHOT_CHANGED", result["reason_codes"])
        self.assertIsNone(result["cli"]["sha256"])

    # @test-value v1
    # kind = "security"
    # claim = "symlink executableはnative workerとして受け付けない"
    # oracle = { type = "adr", ref = "ADR-0022" }
    # failure_mode = "リンク経由の実体が変化しうるexecutableを実行候補として採用する"
    # scope = "review-worker-preflight"
    # lifecycle = "permanent"
    # @end-test-value
    def test_symlink_executable_is_rejected(self):
        link = Path(self.temp.name) / "link.exe"
        try:
            link.symlink_to(self.cli)
        except (OSError, NotImplementedError):
            self.skipTest("symlink creation is unavailable")
        result = run_preflight(str(link), str(self.role), runner=lambda *_: self.fail("must not query"))
        self.assertIn("RUNTIME_UNSUPPORTED", result["reason_codes"])


if __name__ == "__main__":
    unittest.main()
