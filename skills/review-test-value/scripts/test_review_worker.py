from __future__ import annotations

import base64
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import review_worker  # noqa: E402


def _id_token(plan_type: str) -> str:
    payload = {
        "https://api.openai.com/auth": {"chatgpt_plan_type": plan_type},
    }
    encoded = base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":")).encode("utf-8")
    ).decode("ascii").rstrip("=")
    return "header." + encoded + ".signature"


def _packet(record_count: int = 1) -> dict:
    metadata = {
        "claim": "worker isolates the metadata review",
        "fault": "worker sends a packet before isolation is proven",
        "oracle": {"type": "issue", "ref": "#50"},
        "observable": "worker launch sequence",
        "observation_boundary": "public-boundary",
        "scope": "review-worker",
        "kind": "security",
        "lifecycle": "permanent",
    }
    packet = {
        "review_contract_version": "metadata-review-v2",
        "records": [
            {
                "record_id": "sha256:" + "a" * 64,
                "metadata_format_version": 2,
                "metadata": metadata,
                "metadata_hash": review_worker.sha256_text(review_worker.canonical_json(metadata)),
            }
        ],
    }
    if record_count == 2:
        second_metadata = {**metadata, "claim": "worker binds each schema variant to one record"}
        packet["records"].append(
            {
                "record_id": "sha256:" + "b" * 64,
                "metadata_format_version": 2,
                "metadata": second_metadata,
                "metadata_hash": review_worker.sha256_text(
                    review_worker.canonical_json(second_metadata)
                ),
            }
        )
    return packet


def _result(record_count: int = 1) -> dict:
    packet = _packet(record_count)
    return {
        "review_contract_version": "metadata-review-v2",
        "reviews": [
            {
                "record_id": record["record_id"],
                "metadata_hash": record["metadata_hash"],
                "verdict": "VALID",
                "evidence": [
                    {"fields": ["claim", "fault", "scope"], "finding": "COHERENT_BOUNDARY"}
                ],
                "unverified": ["oracle.refの本文"],
                "next_action": None,
            }
            for record in packet["records"]
        ],
    }


def _events(*items: dict) -> str:
    events = [{"type": "thread.started", "thread_id": "synthetic"}]
    events.extend({"type": "item.completed", "item": item} for item in items)
    events.append({"type": "turn.completed", "usage": {}})
    return "\n".join(json.dumps(event) for event in events)


class ReviewWorkerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.cli = root / "codex.exe"
        self.cli.write_bytes(b"synthetic executable")
        codex_home = root / "codex-home"
        codex_home.mkdir()
        self.auth_file = codex_home / "auth.json"
        self.auth_file.write_text(
            json.dumps(
                {
                    "auth_mode": "chatgpt",
                    "tokens": {"id_token": _id_token("pro")},
                }
            ),
            encoding="utf-8",
        )
        self.environment = patch.dict(os.environ, {"CODEX_HOME": str(codex_home)})
        self.environment.start()
        self.created_directories = 0

        def make_temp_directory(*, prefix: str) -> str:
            self.created_directories += 1
            path = root / f"{prefix}{self.created_directories}"
            path.mkdir()
            return str(path)

        self.temp_directory_factory = patch(
            "review_worker.tempfile.mkdtemp", side_effect=make_temp_directory
        )
        self.temp_directory_factory.start()
        agents = root / "agents"
        references = root / "skills" / "review-test-value" / "references"
        agents.mkdir()
        references.mkdir(parents=True)
        self.role = agents / "test_value_luna.toml"
        self.role.write_text(
            """name = \"test_value_luna\"
model = \"gpt-5.6-luna\"
model_reasoning_effort = \"medium\"
developer_instructions = \"Review only the supplied packet.\"
""",
            encoding="utf-8",
        )
        (references / "metadata-review-contract.md").write_text(
            "# Metadata review contract\nReturn metadata-review-v2 JSON.", encoding="utf-8"
        )

    def tearDown(self) -> None:
        self.temp_directory_factory.stop()
        self.environment.stop()
        self.temp.cleanup()

    # @test-value v2
    # kind = "security"
    # claim = "execute_phase sends the real packet only after one denied canary read"
    # oracle = { type = "issue", ref = "https://github.com/natumekazuki/.codex/issues/50" }
    # fault = "the worker sends review metadata before the named permission profile denies the external canary read"
    # observable = "the fake process runner's ordered stdin values, launch arguments, returned result, and removed scratch path"
    # observation_boundary = "component-behavior"
    # scope = "review-test-value review worker"
    # lifecycle = "permanent"
    # risk_tags = ["security", "privacy"]
    # distinction = "covers the full preflight-to-canary-to-packet transition rather than the existing phase result validator in isolation"
    # @end-test-value
    def test_execute_phase_withholds_packet_until_denial_and_validates_output(self) -> None:
        calls: list[tuple[list[str], str, Path]] = []
        if os.name != "nt":
            self.skipTest("full handoff uses real Windows filesystem paths")
        packet = _packet(2)
        expected_result = _result(2)

        def runner(argv: list[str], input_text: str, cwd: Path, timeout: float) -> review_worker.ProcessOutcome:
            calls.append((argv, input_text, cwd))
            if len(calls) == 1:
                packet_text = json.dumps(
                    packet, ensure_ascii=False, sort_keys=True, separators=(",", ":")
                )
                sensitive_values = [packet_text]
                for record in packet["records"]:
                    sensitive_values.extend(
                        [
                            record["record_id"],
                            record["metadata_hash"],
                            review_worker.canonical_json(record["metadata"]),
                        ]
                    )
                for value in sensitive_values:
                    self.assertNotIn(value, input_text)
                    for argument in argv:
                        self.assertNotIn(value, argument)
                    self.assertNotIn(value, "\0".join(argv))
                self.assertFalse((cwd / "result-schema.json").exists())
                self.assertEqual([], [path for path in cwd.rglob("*") if path.is_file()])
                expected_command = input_text.split("tool: ", 1)[1].split(". Do not", 1)[0]
                expected_literal = expected_command.split(" -LiteralPath ", 1)[1]
                expected_path = Path(expected_literal[1:-1].replace("''", "'"))
                sol_command = (
                    '"C:\\\\Program Files\\\\PowerShell\\\\7\\\\pwsh.exe" '
                    '-NoProfile -Command "'
                    + expected_command.replace("\\", "\\\\")
                    + '"'
                )
                self.assertTrue(
                    review_worker._matches_expected_canary_command(sol_command, expected_path)
                )
                quoted_path = Path(r"C:\Temp\O'Brien\canary.txt")
                self.assertTrue(
                    review_worker._matches_expected_canary_command(
                        "Get-Content -Raw -LiteralPath 'C:\\Temp\\O''Brien\\canary.txt'",
                        quoted_path,
                    )
                )
                self.assertFalse(
                    review_worker._matches_expected_canary_command(
                        'Get-Content -Raw -LiteralPath "$env:TEMP\\canary.txt"',
                        Path(r"C:\Temp\canary.txt"),
                    )
                )
                joined = " ".join(argv)
                self.assertIn("default_permissions=\"test-value-review-worker\"", joined)
                self.assertIn('\":minimal\"=\"read\"', joined)
                self.assertNotIn("=\"deny\"", joined)
                self.assertNotIn("--sandbox", argv)
                return review_worker.ProcessOutcome(
                    0,
                    _events(
                        {
                            "id": "command",
                            "type": "command_execution",
                            "command": sol_command,
                            "aggregated_output": "Access is denied.",
                            "exit_code": 1,
                            "status": "failed",
                        },
                        {"id": "message", "type": "agent_message", "text": "CANARY_DENIED"},
                    ),
                    "",
                )
            for record in packet["records"]:
                self.assertIn(record["record_id"], input_text)
                self.assertIn(record["metadata_hash"], input_text)
            self.assertIn("--output-schema", argv)
            self.assertIn("--disable", argv)
            schema_path = Path(argv[argv.index("--output-schema") + 1])
            schema = json.loads(schema_path.read_text(encoding="utf-8"))
            variants = schema["properties"]["reviews"]["items"]["anyOf"]
            bound_pairs = {
                (
                    variant["properties"]["record_id"]["enum"][0],
                    variant["properties"]["metadata_hash"]["enum"][0],
                )
                for variant in variants
            }
            self.assertEqual(
                {(record["record_id"], record["metadata_hash"]) for record in packet["records"]},
                bound_pairs,
            )
            return review_worker.ProcessOutcome(
                0,
                _events(
                    {
                        "id": "message",
                        "type": "agent_message",
                        "text": json.dumps(expected_result),
                    }
                ),
                "",
            )

        with (
            patch("review_worker.platform.system", return_value="Windows"),
            patch("review_worker._managed_config_paths", return_value=[]),
            patch("review_worker._run_version", return_value=(0, "codex-cli 0.153.4", "")),
        ):
            execution = review_worker.execute_phase(
                "metadata",
                packet,
                cli=str(self.cli),
                role_file=str(self.role),
                runner=runner,
            )

        self.assertEqual(expected_result, execution.result)
        self.assertTrue(execution.evidence["result_validated"])
        self.assertEqual("DENIED", execution.evidence["canary"]["status"])
        self.assertEqual(2, len(calls))
        self.assertFalse(calls[0][2].exists())

    # @test-value v2
    # kind = "security"
    # claim = "a local managed Codex config blocks the worker before either canary or packet launch"
    # oracle = { type = "issue", ref = "https://github.com/natumekazuki/.codex/issues/50" }
    # fault = "the launcher treats ProgramData absence checks as advisory and starts a worker with an unverified managed policy"
    # observable = "ReviewWorkerBlocked reason and zero fake-runner calls"
    # observation_boundary = "component-behavior"
    # scope = "review-test-value review worker preflight"
    # lifecycle = "permanent"
    # risk_tags = ["security"]
    # distinction = "exercises the failure timing before synthetic input, while the success test exercises the later denial proof"
    # @end-test-value
    def test_execute_phase_blocks_managed_config_before_launch(self) -> None:
        managed = Path(self.temp.name) / "requirements.toml"
        managed.write_text("default_permissions = \"managed\"", encoding="utf-8")
        calls = 0

        def runner(*args: object) -> review_worker.ProcessOutcome:
            nonlocal calls
            calls += 1
            raise AssertionError("runner must not be called")

        with (
            patch("review_worker.platform.system", return_value="Windows"),
            patch("review_worker._managed_config_paths", return_value=[managed]),
        ):
            with self.assertRaisesRegex(review_worker.ReviewWorkerBlocked, "MANAGED_CONFIG_PRESENT"):
                review_worker.execute_phase(
                    "metadata",
                    _packet(),
                    cli=str(self.cli),
                    role_file=str(self.role),
                    runner=runner,
                )
        self.assertEqual(0, calls)

    # @test-value v2
    # kind = "security"
    # claim = "execute_phase permits packet delivery only when ChatGPT consumer auth makes cloud preferences ineligible"
    # oracle = { type = "issue", ref = "https://github.com/natumekazuki/.codex/issues/50" }
    # fault = "enterprise-eligible auth reaches a worker whose cloud developer instructions, hooks, or MCP inputs were not bounded"
    # observable = "MANAGED_CLOUD_INPUT_UNVERIFIED and zero fake-runner calls"
    # observation_boundary = "component-behavior"
    # scope = "review-test-value review worker managed-input preflight"
    # lifecycle = "permanent"
    # risk_tags = ["security", "privacy"]
    # distinction = "covers the remote managed-config eligibility gate independently from the local ProgramData file gate"
    # @end-test-value
    def test_execute_phase_blocks_cloud_eligible_auth_before_launch(self) -> None:
        self.auth_file.write_text(
            json.dumps(
                {
                    "auth_mode": "chatgpt",
                    "tokens": {"id_token": _id_token("enterprise")},
                }
            ),
            encoding="utf-8",
        )
        calls = 0

        def runner(*args: object) -> review_worker.ProcessOutcome:
            nonlocal calls
            calls += 1
            raise AssertionError("runner must not be called")

        with (
            patch("review_worker.platform.system", return_value="Windows"),
            patch("review_worker._managed_config_paths", return_value=[]),
        ):
            with self.assertRaisesRegex(
                review_worker.ReviewWorkerBlocked, "MANAGED_CLOUD_INPUT_UNVERIFIED"
            ):
                review_worker.execute_phase(
                    "metadata",
                    _packet(),
                    cli=str(self.cli),
                    role_file=str(self.role),
                    runner=runner,
                )
        self.assertEqual(0, calls)

    # @test-value v2
    # kind = "security"
    # claim = "the model-free worker identity becomes unavailable when either local managed config or cloud-eligible auth replaces the observed boundary"
    # oracle = { type = "issue", ref = "https://github.com/natumekazuki/.codex/issues/50" }
    # fault = "the coordinator reuses a stored generation after managed automatic inputs become eligible while CLI and role hashes remain unchanged"
    # observable = "a stable identity for consumer Pro followed by MANAGED_CONFIG_PRESENT and MANAGED_CLOUD_INPUT_UNVERIFIED"
    # observation_boundary = "component-behavior"
    # scope = "review-test-value worker generation reuse identity"
    # lifecycle = "permanent"
    # risk_tags = ["security", "privacy"]
    # distinction = "covers model-free reuse validation, while execute_phase tests cover isolation before a new packet delivery"
    # @end-test-value
    def test_current_worker_identity_blocks_managed_input_boundary_changes(self) -> None:
        with (
            patch("review_worker.platform.system", return_value="Windows"),
            patch("review_worker._managed_config_paths", return_value=[]),
            patch("review_worker._run_version", return_value=(0, "codex-cli 0.153.4", "")),
        ):
            identity = review_worker.current_worker_identity(
                cli=str(self.cli), role_file=str(self.role), phases=["metadata"]
            )
        self.assertEqual("review-worker-identity-v1", identity["schema_version"])
        self.assertEqual(["metadata"], identity["phases"])

        managed = Path(self.temp.name) / "config.toml"
        managed.write_text("developer_instructions = \"managed\"", encoding="utf-8")
        with (
            patch("review_worker.platform.system", return_value="Windows"),
            patch("review_worker._managed_config_paths", return_value=[managed]),
        ):
            with self.assertRaisesRegex(review_worker.ReviewWorkerBlocked, "MANAGED_CONFIG_PRESENT"):
                review_worker.current_worker_identity(
                    cli=str(self.cli), role_file=str(self.role), phases=["metadata"]
                )

        self.auth_file.write_text(
            json.dumps(
                {
                    "auth_mode": "chatgpt",
                    "tokens": {"id_token": _id_token("enterprise")},
                }
            ),
            encoding="utf-8",
        )
        with (
            patch("review_worker.platform.system", return_value="Windows"),
            patch("review_worker._managed_config_paths", return_value=[]),
        ):
            with self.assertRaisesRegex(
                review_worker.ReviewWorkerBlocked, "MANAGED_CLOUD_INPUT_UNVERIFIED"
            ):
                review_worker.current_worker_identity(
                    cli=str(self.cli), role_file=str(self.role), phases=["metadata"]
                )

    # @test-value v2
    # kind = "security"
    # claim = "an access-denied event for any command other than the requested canary read never authorizes packet delivery"
    # oracle = { type = "issue", ref = "https://github.com/natumekazuki/.codex/issues/50" }
    # fault = "the worker accepts an unrelated denied command without proving that the named profile rejected the external canary path"
    # observable = "CANARY_DENIAL_UNVERIFIED for separate wrong-path and wrong-command calls whose stdin excludes the packet record"
    # observation_boundary = "component-behavior"
    # scope = "review-test-value review worker isolation gate"
    # lifecycle = "permanent"
    # risk_tags = ["security", "privacy"]
    # distinction = "negative path binds denial evidence to the requested command and path instead of accepting an arbitrary access-denied string"
    # @end-test-value
    def test_execute_phase_withholds_packet_when_wrong_command_is_denied(self) -> None:
        calls: list[tuple[str, Path]] = []

        def runner(argv: list[str], input_text: str, cwd: Path, timeout: float) -> review_worker.ProcessOutcome:
            calls.append((input_text, cwd))
            expected_command = input_text.split("tool: ", 1)[1].split(". Do not", 1)[0]
            actual_command = (
                "Get-Content -Raw -LiteralPath 'C:\\unrelated.txt'"
                if len(calls) == 1
                else expected_command.replace("Get-Content", "Get-Item", 1)
            )
            return review_worker.ProcessOutcome(
                0,
                _events(
                    {
                        "id": "command",
                        "type": "command_execution",
                        "command": actual_command,
                        "aggregated_output": "Access is denied.",
                        "exit_code": 1,
                        "status": "failed",
                    }
                ),
                "",
            )

        with (
            patch("review_worker.platform.system", return_value="Windows"),
            patch("review_worker._managed_config_paths", return_value=[]),
            patch("review_worker._run_version", return_value=(0, "codex-cli 0.153.4", "")),
        ):
            for _ in range(2):
                with self.assertRaisesRegex(
                    review_worker.ReviewWorkerBlocked, "CANARY_DENIAL_UNVERIFIED"
                ) as blocked:
                    review_worker.execute_phase(
                        "metadata",
                        _packet(),
                        cli=str(self.cli),
                        role_file=str(self.role),
                        runner=runner,
                    )
                self.assertFalse(blocked.exception.evidence["command_matches"])
        self.assertEqual(2, len(calls))
        for input_text, scratch in calls:
            self.assertNotIn("sha256:" + "a" * 64, input_text)
            self.assertFalse(scratch.exists())

    # @test-value v2
    # kind = "invariant"
    # claim = "on Windows, an owned child reaches the terminated state within a bounded native wait after _run_process returns a timeout outcome"
    # oracle = { type = "issue", ref = "https://github.com/natumekazuki/.codex/issues/50" }
    # fault = "_run_process reports a completed timeout while its owned child process remains active"
    # observable = "ProcessOutcome timeout flags and the native wait result for the child PID printed by the owned parent"
    # observation_boundary = "component-behavior"
    # scope = "review-test-value Windows process lifecycle"
    # lifecycle = "permanent"
    # distinction = "covers owned process-tree cancellation rather than review protocol or filesystem isolation"
    # @end-test-value
    @unittest.skipUnless(sys.platform == "win32", "requires Windows Job Objects")
    def test_run_process_timeout_terminates_owned_child_on_windows(self) -> None:
        parent_code = (
            "import subprocess,sys,time;"
            "p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)'],"
            f"creationflags={review_worker.CREATE_NO_WINDOW});"
            "print(p.pid,flush=True);time.sleep(30)"
        )
        outcome = review_worker._run_process(
            [sys.executable, "-u", "-c", parent_code],
            "",
            Path(self.temp.name),
            1.0,
        )
        child_pid = int(outcome.stdout.strip())

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel32.WaitForSingleObject.restype = wintypes.DWORD
        kernel32.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
        kernel32.TerminateProcess.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL

        child_handle = kernel32.OpenProcess(0x00100001, False, child_pid)
        try:
            if child_handle:
                child_wait = kernel32.WaitForSingleObject(child_handle, 5000)
            else:
                self.assertEqual(87, ctypes.get_last_error())
                child_wait = 0x00000000
            self.assertTrue(outcome.timed_out)
            self.assertTrue(outcome.process_tree_terminated)
            self.assertEqual(0x00000000, child_wait)
        finally:
            if child_handle:
                if kernel32.WaitForSingleObject(child_handle, 0) == 0x00000102:
                    kernel32.TerminateProcess(child_handle, 1)
                    kernel32.WaitForSingleObject(child_handle, 5000)
                kernel32.CloseHandle(child_handle)


if __name__ == "__main__":
    unittest.main()
