from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import review_worker  # noqa: E402
from review_worker import main  # noqa: E402


class ReviewIsolationE2ETests(unittest.TestCase):
    # @test-value v2
    # kind = "regression"
    # claim = "隔離E2E入口が無効なCLIとroleをモデル起動前に拒否する"
    # oracle = { type = "contract", ref = "docs/runbooks/activate-test-value-review.md" }
    # fault = "無効な起動設定でprobeが始まるかterminal JSONが返らない"
    # observable = "exit 2とstructured BLOCKED"
    # observation_boundary = "public-boundary"
    # scope = "isolation-e2e-entrypoint"
    # lifecycle = "permanent"
    # @end-test-value
    def test_explicit_entrypoint_returns_structured_blocker(self) -> None:
        # The explicit entrypoint is safe to invoke with invalid paths; it must
        # stop before launching a process and return a structured blocker.
        from contextlib import redirect_stdout
        from io import StringIO

        stream = StringIO()
        with tempfile.TemporaryDirectory() as directory, redirect_stdout(stream):
            code = main(["--isolation-e2e", "--phase", "metadata",
                         "--cli", str(Path(directory) / "missing-codex.exe"),
                         "--role-file", str(Path(directory) / "missing-role.toml")])
        self.assertEqual(review_worker.EXIT_BLOCKED, code)
        result = json.loads(stream.getvalue())
        self.assertEqual("BLOCKED", result["status"])

    # @test-value v2
    # kind = "security"
    # claim = "the opt-in filesystem probe accepts only the exact expected denied read"
    # oracle = { type = "issue", ref = "https://github.com/natumekazuki/.codex/issues/50" }
    # fault = "the isolation E2E treats any failed command or unrelated denial as proof of the named boundary"
    # observable = "DENIED probe result for one exact command and nonzero command exit"
    # observation_boundary = "component-behavior"
    # scope = "review-test-value isolation E2E"
    # lifecycle = "permanent"
    # risk_tags = ["security", "privacy"]
    # distinction = "covers the positive exact-command denial contract while the negative test covers wrong path and hidden diagnostics"
    # @end-test-value
    def test_probe_accepts_exact_expected_denial(self) -> None:
        expected_path = Path(r"C:\Temp\expected-canary.txt")
        command = f"Get-Content -Raw -LiteralPath '{expected_path}'"
        events = [
            {
                "type": "item.completed",
                "item": {
                    "id": "safe-command-id",
                    "type": "command_execution",
                    "command": command,
                    "status": "failed",
                    "exit_code": 1,
                    "aggregated_output": "Access is denied.",
                },
            },
            {"type": "turn.completed"},
        ]
        result = review_worker._verify_canary(
            review_worker.ProcessOutcome(
                0,
                "\n".join(json.dumps(item) for item in events),
                "",
            ),
            "private-token",
            expected_path,
        )
        self.assertEqual(
            {
                "status": "DENIED",
                "command_count": 1,
                "exit_code": 1,
                "process_tree_terminated": False,
            },
            result,
        )

    # @test-value v2
    # kind = "regression"
    # claim = "通常意味審査の起動引数がshellとunified execを無効にする"
    # oracle = { type = "contract", ref = "docs/runbooks/activate-test-value-review.md" }
    # fault = "通常runでpacket外を取得するtoolが有効になる"
    # observable = "model-free invocation validatorとtool enableの不在"
    # observation_boundary = "public-boundary"
    # scope = "model-free-isolation"
    # lifecycle = "permanent"
    # @end-test-value
    def test_normal_worker_invocation_disables_shell_and_unified_exec(self) -> None:
        argv = review_worker._codex_argv(
            "C:\\codex.exe",
            {"model": "model", "model_reasoning_effort": "max"},
            Path(r"C:\scratch"),
            None,
            "contract",
            schema=Path(r"C:\scratch\schema.json"),
            enable_shell=False,
        )
        review_worker._assert_review_invocation_isolated(
            argv,
            scratch=Path(r"C:\scratch"),
            schema=Path(r"C:\scratch\schema.json"),
        )
        self.assertNotIn("--enable", argv)

    # @test-value v2
    # kind = "regression"
    # claim = "別pathの拒否を隔離成功にせず診断を正規化してprivate pathを保存しない"
    # oracle = { type = "contract", ref = "docs/runbooks/activate-test-value-review.md" }
    # fault = "無関係な拒否をPASSにするかraw commandのprivate pathが漏れる"
    # observable = "CANARY_DENIAL_UNVERIFIEDと正規化種別、秘密文字列の不在"
    # observation_boundary = "public-boundary"
    # scope = "isolation-failure-diagnostics"
    # lifecycle = "permanent"
    # @end-test-value
    def test_probe_failure_diagnostics_normalize_command_and_hide_path(self) -> None:
        private_path = r"C:\Users\private\outside-canary.txt"
        events = [
            {
                "type": "item.completed",
                "item": {
                    "id": "private-command-id",
                    "type": "command_execution",
                    "command": f"Get-Content -Raw -LiteralPath '{private_path}'",
                    "status": "failed",
                    "exit_code": 1,
                    "aggregated_output": f"Access is denied: {private_path}",
                },
            },
            {"type": "turn.completed"},
        ]
        with self.assertRaises(review_worker.ReviewWorkerBlocked) as blocked:
            review_worker._verify_canary(
                review_worker.ProcessOutcome(0, "\n".join(json.dumps(item) for item in events), ""),
                "private-token",
                Path(r"C:\Users\private\expected-canary.txt"),
            )
        evidence = blocked.exception.evidence
        self.assertEqual("CANARY_DENIAL_UNVERIFIED", blocked.exception.code)
        self.assertEqual(["other_command"], evidence["command_kinds"])
        self.assertIn("item.completed", evidence["event_types"])
        self.assertIn("access_denied", evidence["denial_reasons"])
        serialized = json.dumps(evidence)
        self.assertNotIn(private_path, serialized)
        self.assertNotIn("private-command-id", serialized)
        self.assertNotIn("commands", evidence)


if __name__ == "__main__":
    unittest.main()
