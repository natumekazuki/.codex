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

    # @test-value v2
    # kind = "security"
    # claim = "preflightはstdinを閉じたversion照会だけを行い、receiptへpayload未配信とeffective値未確認を明示する"
    # oracle = { type = "adr", ref = "ADR-0022" }
    # fault = "version照会だけのreceiptにpayload配信済みや実効modelを記録する"
    # observable = "subprocess境界のargv・stdin・timeoutと返却receiptのstatus・payload・effective値"
    # observation_boundary = "component-behavior"
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

    # @test-value v2
    # kind = "invariant"
    # claim = "requested modelとeffortはrole正本からreceiptへ反映される"
    # oracle = { type = "adr", ref = "ADR-0022" }
    # fault = "roleのmodelまたはeffortを別の固定値で上書きする"
    # observable = "返却receiptのrequested.modelとrequested.effort"
    # observation_boundary = "component-behavior"
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

    # @test-value v2
    # kind = "security"
    # claim = "native executableでない入力はversion query前にBLOCKEDになる"
    # oracle = { type = "adr", ref = "ADR-0022" }
    # fault = "native executable以外の入力をversion照会へ渡す"
    # observable = "RUNTIME_UNSUPPORTEDのreason codeとversion runnerへの未dispatch"
    # observation_boundary = "component-behavior"
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

    # @test-value v2
    # kind = "security"
    # claim = "対象外roleや文字コードが壊れたroleはversion照会前に構造化した失敗として拒否される"
    # oracle = { type = "issue", ref = "https://github.com/natumekazuki/.codex/issues/42" }
    # fault = "対象外roleやUTF-8不正roleを受理するかdecode例外を外へ漏らす"
    # observable = "BLOCKED receipt・RUNTIME_UNSUPPORTEDとversion runnerへの未dispatch"
    # observation_boundary = "component-behavior"
    # scope = "review-worker-preflight"
    # lifecycle = "permanent"
    # @end-test-value
    def test_invalid_role_is_rejected_before_query(self):
        for invalid in (ROLE.replace("test_value_luna", "unknown_role").encode("utf-8"), b"\xff"):
            with self.subTest(role_bytes=invalid):
                self.role.write_bytes(invalid)
                called = []
                result = run_preflight(
                    str(self.cli), str(self.role), runner=lambda executable, timeout: called.append(executable)
                )
                self.assertEqual(result["status"], "BLOCKED")
                self.assertIn("RUNTIME_UNSUPPORTED", result["reason_codes"])
                self.assertEqual(called, [])

    # @test-value v2
    # kind = "invariant"
    # claim = "native version queryのtimeoutはBLOCKED receiptになり成功扱いされない"
    # oracle = { type = "adr", ref = "ADR-0022" }
    # fault = "version照会timeoutを構造化した失敗へ変換しない"
    # observable = "返却receiptのCLI_VERSION_TIMEOUTとBLOCKED"
    # observation_boundary = "component-behavior"
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

    # @test-value v2
    # kind = "security"
    # claim = "version query中にCLI snapshotが変化した場合はBLOCKEDになる"
    # oracle = { type = "adr", ref = "ADR-0022" }
    # fault = "version照会前後で変更されたbinaryのhashを有効な証拠として返す"
    # observable = "返却receiptのCLI_SNAPSHOT_CHANGEDとnullのcli.sha256"
    # observation_boundary = "component-behavior"
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

    # @test-value v2
    # kind = "security"
    # claim = "symlink executableはnative workerとして受け付けない"
    # oracle = { type = "adr", ref = "ADR-0022" }
    # fault = "symlink executableをversion照会へdispatchする"
    # observable = "返却receiptのRUNTIME_UNSUPPORTEDとversion runnerへの未dispatch"
    # observation_boundary = "component-behavior"
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
