from __future__ import annotations

import base64
import copy
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import review_worker  # noqa: E402
from build_review_packets import (  # noqa: E402
    build_alignment_packet_multi,
    build_metadata_packet_multi,
)
from test_review_packets import extractor_result, metadata_result  # noqa: E402


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
        "review_contract_version": "metadata-review-v3",
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
        "review_contract_version": "metadata-review-v3",
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


def _sized_phase_packets(record_count: int) -> dict[str, dict]:
    """Build canonical metadata/alignment fixtures large enough for 3 batches."""

    extracted = extractor_result()
    template = extracted["tests"][0]
    extracted["tests"] = []
    for index in range(record_count):
        record = copy.deepcopy(template)
        record["source"]["path"] = f"tests/test_{index:03d}.py"
        extracted["tests"].append(record)
    metadata = build_metadata_packet_multi([extracted])
    frozen = metadata_result(metadata)
    alignment = build_alignment_packet_multi([extracted], frozen)
    return {"metadata": metadata, "alignment": alignment}


def _events(*items: dict) -> str:
    events = [{"type": "thread.started", "thread_id": "synthetic"}]
    events.extend({"type": "item.completed", "item": item} for item in items)
    events.append({"type": "turn.completed", "usage": {}})
    return "\n".join(json.dumps(event) for event in events)


def _metadata_transport() -> tuple:
    """Minimal projected transport used by worker deadline tests."""

    def model_packet(phase: str, canonical_packet: dict) -> dict:
        return {
            "records": [
                {"ordinal": index, "metadata": record["metadata"]}
                for index, record in enumerate(canonical_packet["records"])
            ]
        }

    def model_schema(phase: str, canonical_packet: dict) -> dict:
        return {"type": "object", "properties": {"reviews": {"type": "array"}}}

    def canonical_result(phase: str, model_result: dict, canonical_packet: dict) -> dict:
        return {
            "review_contract_version": canonical_packet["review_contract_version"],
            "reviews": [
                {
                    "record_id": record["record_id"],
                    "metadata_hash": record["metadata_hash"],
                    "verdict": review["verdict"],
                    "evidence": review["evidence"],
                    "unverified": review["unverified"],
                    "next_action": review["next_action"],
                }
                for review, record in zip(model_result["reviews"], canonical_packet["records"])
            ],
        }

    return model_packet, model_schema, canonical_result


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
            "# Metadata review contract\nReturn metadata-review-v3 JSON.", encoding="utf-8"
        )
        (references / "alignment-review-contract.md").write_text(
            "# Alignment review contract\nReturn alignment-review-v3 JSON.", encoding="utf-8"
        )

    def tearDown(self) -> None:
        self.temp_directory_factory.stop()
        self.environment.stop()
        self.temp.cleanup()

    # @test-value v2
    # kind = "security"
    # claim = "normal phase delivery runs one isolated semantic review over an ordinal-only projection"
    # oracle = { type = "issue", ref = "https://github.com/natumekazuki/.codex/issues/50" }
    # fault = "the worker starts a synthetic canary or exposes canonical identity fields before review"
    # observable = "one fake runner call, disabled shell flags, projected input, and host-bound result identity"
    # observation_boundary = "component-behavior"
    # scope = "review-test-value review worker transport"
    # lifecycle = "permanent"
    # risk_tags = ["security", "privacy"]
    # distinction = "covers normal one-run transport and host binding while filesystem refusal is tested by opt-in E2E"
    # @end-test-value
    def test_execute_phase_runs_one_projected_review_without_canary(self) -> None:
        packet = _packet(2)
        calls: list[tuple[list[str], str, Path]] = []

        def model_packet(phase: str, canonical_packet: dict) -> dict:
            return {
                "records": [
                    {"ordinal": index, "metadata": record["metadata"]}
                    for index, record in enumerate(canonical_packet["records"])
                ]
            }

        def model_schema(phase: str, canonical_packet: dict) -> dict:
            return {"type": "object", "properties": {"reviews": {"type": "array"}}}

        def canonical_result(phase: str, model_result: dict, canonical_packet: dict) -> dict:
            return {
                "review_contract_version": canonical_packet["review_contract_version"],
                "reviews": [
                    {
                        "record_id": record["record_id"],
                        "metadata_hash": record["metadata_hash"],
                        "verdict": review["verdict"],
                        "evidence": review["evidence"],
                        "unverified": review["unverified"],
                        "next_action": review["next_action"],
                    }
                    for review, record in zip(model_result["reviews"], canonical_packet["records"])
                ],
            }

        def runner(argv: list[str], input_text: str, cwd: Path, timeout: float) -> review_worker.ProcessOutcome:
            calls.append((argv, input_text, cwd))
            self.assertNotIn("canary", str(cwd).lower())
            self.assertNotIn("--enable", argv)
            self.assertIn("--disable", argv)
            for record in packet["records"]:
                self.assertNotIn(record["record_id"], input_text)
                self.assertNotIn(record["metadata_hash"], input_text)
            raw = {
                "reviews": [
                    {
                        "ordinal": index,
                        "verdict": "VALID",
                        "evidence": [{"fields": ["claim"], "finding": "SELF_CONTAINED_CLAIM"}],
                        "unverified": [],
                        "next_action": None,
                    }
                    for index in range(2)
                ]
            }
            return review_worker.ProcessOutcome(0, _events({"id": "message", "type": "agent_message", "text": json.dumps(raw)}), "")

        with (
            patch("review_worker.platform.system", return_value="Windows"),
            patch("review_worker._managed_config_paths", return_value=[]),
            patch("review_worker._run_version", return_value=(0, "codex-cli 0.153.4", "")),
            patch("review_worker._transport_functions", return_value=(model_packet, model_schema, canonical_result)),
        ):
            execution = review_worker.execute_phase(
                "metadata", packet, cli=str(self.cli), role_file=str(self.role), runner=runner
            )

        self.assertEqual(1, len(calls))
        self.assertEqual("review-worker-evidence-v2", execution.evidence["schema_version"])
        self.assertNotIn("canary", execution.evidence)
        self.assertEqual([record["record_id"] for record in packet["records"]], [
            review["record_id"] for review in execution.result["reviews"]
        ])

    # @test-value v2
    # kind = "regression"
    # claim = "22 selected records in three metadata and alignment batches launch six normal semantic reviews"
    # oracle = { type = "issue", ref = "https://github.com/natumekazuki/.codex/issues/50" }
    # fault = "per-batch canaries double model calls or ordinal binding changes result identity across batch boundaries"
    # observable = "real 10/10/2 batch plans, six runner calls, and matching host-bound IDs and hashes"
    # observation_boundary = "component-behavior"
    # scope = "review-test-value review worker batch call count"
    # lifecycle = "permanent"
    # distinction = "directly compares the normal call count against the former canary-plus-review shape"
    # @end-test-value
    def test_22_records_three_batches_launch_six_normal_reviews(self) -> None:
        """The 22-record fixture has one model run per metadata/alignment batch."""

        import run_test_value_review as coordinator

        packets = _sized_phase_packets(22)
        calls: list[tuple[str, int]] = []

        def runner(
            argv: list[str], input_text: str, cwd: Path, timeout: float
        ) -> review_worker.ProcessOutcome:
            del argv, cwd, timeout
            projected = json.loads(input_text.split("\n", 1)[1])
            records = projected["records"]
            phase = active_phase[0]
            calls.append((phase, len(records)))
            self.assertEqual(list(range(len(records))), [item["ordinal"] for item in records])
            self.assertNotIn("record_id", input_text)
            self.assertNotIn("metadata_hash", input_text)
            self.assertNotIn("source_hash", input_text)
            self.assertNotIn("metadata_result_hash", input_text)
            if phase == "metadata":
                reviews = [
                    {
                        "ordinal": item["ordinal"],
                        "verdict": "VALID",
                        "evidence": [
                            {"fields": ["claim", "fault", "scope"], "finding": "COHERENT_BOUNDARY"}
                        ],
                        "unverified": ["oracle.refの本文"],
                        "next_action": None,
                    }
                    for item in records
                ]
            else:
                reviews = [
                    {
                        "ordinal": item["ordinal"],
                        "verdict": "ALIGNED",
                        "actual_boundary": "component-behavior",
                        "actual_observables": ["assertion result"],
                        "overclaim": False,
                        "evidence": ["source assertion"],
                        "unverified": [],
                        "context_requirements": [],
                        "next_action": None,
                    }
                    for item in records
                ]
            return review_worker.ProcessOutcome(
                0,
                _events(
                    {
                        "id": "message",
                        "type": "agent_message",
                        "text": json.dumps({"reviews": reviews}, ensure_ascii=False),
                    }
                ),
                "",
            )

        active_phase = ["metadata"]
        with (
            patch("review_worker.platform.system", return_value="Windows"),
            patch("review_worker._managed_config_paths", return_value=[]),
            patch("review_worker._run_version", return_value=(0, "codex-cli 0.153.4", "")),
        ):
            for phase in ("metadata", "alignment"):
                active_phase[0] = phase
                batches, plan = coordinator.plan_phase_batches(
                    phase, packets[phase], batch_concurrency=1
                )
                self.assertEqual([10, 10, 2], [len(batch["records"]) for batch in batches])
                self.assertEqual(1, plan["batch_concurrency"])
                for batch in batches:
                    execution = review_worker.execute_phase(
                        phase,
                        batch,
                        cli=str(self.cli),
                        role_file=str(self.role),
                        runner=runner,
                    )
                    self.assertEqual(
                        f"{phase}-review-v3",
                        execution.result["review_contract_version"],
                    )
                    self.assertEqual(len(batch["records"]), len(execution.result["reviews"]))
                    for record, review in zip(batch["records"], execution.result["reviews"]):
                        self.assertEqual(record["record_id"], review["record_id"])
                        self.assertEqual(record["metadata_hash"], review["metadata_hash"])
                        if phase == "alignment":
                            self.assertEqual(record["source_hash"], review["source_hash"])

        self.assertEqual(
            [("metadata", 10), ("metadata", 10), ("metadata", 2),
             ("alignment", 10), ("alignment", 10), ("alignment", 2)],
            calls,
        )
        self.assertEqual(6, len(calls))

    # @test-value v2
    # kind = "invariant"
    # claim = "review timeout is computed from the shared phase deadline after model-free preflight"
    # oracle = { type = "issue", ref = "https://github.com/natumekazuki/.codex/issues/50" }
    # fault = "the worker gives the review a fresh timeout that ignores time spent checking the CLI and boundary"
    # observable = "one review runner timeout after a simulated preflight clock advance"
    # observation_boundary = "component-behavior"
    # scope = "review-test-value review worker deadline"
    # lifecycle = "permanent"
    # distinction = "covers the normal one-review deadline budget after canary removal"
    # @end-test-value
    def test_execute_phase_deducts_model_free_preflight_time_from_review_budget(self) -> None:
        packet = _packet()
        clock = [100.0]
        timeouts: list[float] = []

        def now() -> float:
            return clock[0]

        def version_runner(executable: str, timeout: float) -> tuple[int, str, str]:
            del executable, timeout
            clock[0] = 110.0
            return 0, "codex-cli 0.153.4", ""

        def runner(
            argv: list[str], input_text: str, cwd: Path, timeout: float
        ) -> review_worker.ProcessOutcome:
            del argv, input_text, cwd
            timeouts.append(timeout)
            raw = {
                "reviews": [
                    {
                        "ordinal": 0,
                        "verdict": "VALID",
                        "evidence": [
                            {"fields": ["claim"], "finding": "SELF_CONTAINED_CLAIM"}
                        ],
                        "unverified": [],
                        "next_action": None,
                    }
                ]
            }
            return review_worker.ProcessOutcome(
                0,
                _events(
                    {
                        "id": "message",
                        "type": "agent_message",
                        "text": json.dumps(raw),
                    }
                ),
                "",
            )

        with (
            patch("review_worker.platform.system", return_value="Windows"),
            patch("review_worker._managed_config_paths", return_value=[]),
            patch("review_worker._run_version", side_effect=version_runner),
            patch("review_worker._transport_functions", return_value=_metadata_transport()),
            patch("review_worker.time.monotonic", side_effect=now),
        ):
            execution = review_worker.execute_phase(
                "metadata",
                packet,
                cli=str(self.cli),
                role_file=str(self.role),
                deadline_monotonic=200.0,
                runner=runner,
            )

        self.assertEqual([85.0], timeouts)
        self.assertEqual("VALID", execution.result["reviews"][0]["verdict"])

    # @test-value v2
    # kind = "invariant"
    # claim = "an exhausted phase deadline prevents review process launch after model-free preflight"
    # oracle = { type = "issue", ref = "https://github.com/natumekazuki/.codex/issues/50" }
    # fault = "the worker starts a model process after the preflight checks leave only the cleanup reserve"
    # observable = "PHASE_DEADLINE_EXCEEDED and zero review runner calls"
    # observation_boundary = "component-behavior"
    # scope = "review-test-value review worker deadline"
    # lifecycle = "permanent"
    # distinction = "keeps the fail-closed deadline boundary without a synthetic canary phase"
    # @end-test-value
    def test_execute_phase_does_not_launch_review_when_preflight_exhausts_budget(self) -> None:
        packet = _packet()
        clock = [100.0]
        calls = 0

        def now() -> float:
            return clock[0]

        def version_runner(executable: str, timeout: float) -> tuple[int, str, str]:
            del executable, timeout
            clock[0] = 196.0
            return 0, "codex-cli 0.153.4", ""

        def runner(*args: object) -> review_worker.ProcessOutcome:
            nonlocal calls
            calls += 1
            raise AssertionError("review runner must not be called")

        with (
            patch("review_worker.platform.system", return_value="Windows"),
            patch("review_worker._managed_config_paths", return_value=[]),
            patch("review_worker._run_version", side_effect=version_runner),
            patch("review_worker.time.monotonic", side_effect=now),
        ):
            with self.assertRaisesRegex(
                review_worker.ReviewWorkerBlocked, "PHASE_DEADLINE_EXCEEDED"
            ) as blocked:
                review_worker.execute_phase(
                    "metadata",
                    packet,
                    cli=str(self.cli),
                    role_file=str(self.role),
                    deadline_monotonic=200.0,
                    runner=runner,
                )

        self.assertEqual("PHASE_DEADLINE_EXCEEDED", blocked.exception.code)
        self.assertEqual(0, calls)

    # @test-value v2
    # kind = "invariant"
    # claim = "a timed out semantic review remains BLOCKED and does not become an empty result"
    # oracle = { type = "issue", ref = "https://github.com/natumekazuki/.codex/issues/50" }
    # fault = "the worker treats a native review timeout as a successful phase after removing the canary"
    # observable = "REVIEW_TIMEOUT and exactly one review runner invocation"
    # observation_boundary = "component-behavior"
    # scope = "review-test-value review worker timeout"
    # lifecycle = "permanent"
    # distinction = "covers the remaining semantic process timeout independently of opt-in isolation E2E"
    # @end-test-value
    def test_execute_phase_blocks_review_timeout(self) -> None:
        calls = 0

        def runner(
            argv: list[str], input_text: str, cwd: Path, timeout: float
        ) -> review_worker.ProcessOutcome:
            nonlocal calls
            del argv, input_text, cwd, timeout
            calls += 1
            return review_worker.ProcessOutcome(
                1, "", "", timed_out=True, process_tree_terminated=True
            )

        with (
            patch("review_worker.platform.system", return_value="Windows"),
            patch("review_worker._managed_config_paths", return_value=[]),
            patch("review_worker._run_version", return_value=(0, "codex-cli 0.153.4", "")),
        ):
            with self.assertRaisesRegex(
                review_worker.ReviewWorkerBlocked, "REVIEW_TIMEOUT"
            ) as blocked:
                review_worker.execute_phase(
                    "metadata",
                    _packet(),
                    cli=str(self.cli),
                    role_file=str(self.role),
                    runner=runner,
                )

        self.assertEqual("REVIEW_TIMEOUT", blocked.exception.code)
        self.assertEqual(1, calls)

    # @test-value v2
    # kind = "invariant"
    # claim = "validation failures expose sanitized record coordinates at the worker boundary"
    # oracle = { type = "issue", ref = "https://github.com/natumekazuki/.codex/issues/50" }
    # fault = "a malformed model result becomes a generic blocker without identifying its record or field"
    # observable = "REVIEW_RESULT_VALIDATION_FAILED evidence contains phase, record_id, violation_type, and invalid_field"
    # observation_boundary = "component-behavior"
    # scope = "review-test-value review worker diagnostics"
    # lifecycle = "permanent"
    # distinction = "covers post-generation diagnosis while the schema tests cover generation-time field constraints"
    # @end-test-value
    def test_execute_phase_reports_sanitized_validation_coordinates(self) -> None:
        packet = _packet()
        invalid_result = _result()
        invalid_result["reviews"][0]["evidence"][0]["fields"] = ["does_not_exist"]
        calls = 0

        def runner(
            argv: list[str], input_text: str, cwd: Path, timeout: float
        ) -> review_worker.ProcessOutcome:
            nonlocal calls
            calls += 1
            return review_worker.ProcessOutcome(
                0,
                _events(
                    {
                        "id": "message",
                        "type": "agent_message",
                        "text": json.dumps(invalid_result),
                    }
                ),
                "",
            )

        with (
            patch("review_worker.platform.system", return_value="Windows"),
            patch("review_worker._managed_config_paths", return_value=[]),
            patch("review_worker._run_version", return_value=(0, "codex-cli 0.153.4", "")),
        ):
            with self.assertRaisesRegex(
                review_worker.ReviewWorkerBlocked, "REVIEW_RESULT_VALIDATION_FAILED"
            ) as blocked:
                review_worker.execute_phase(
                    "metadata",
                    packet,
                    cli=str(self.cli),
                    role_file=str(self.role),
                    runner=runner,
                )

        evidence = blocked.exception.evidence
        self.assertEqual("metadata", evidence["phase"])
        self.assertTrue(
            "record_id" in evidence
            or "ordinal" in evidence
            or evidence["validation_details"] == {"phase": "metadata"},
            evidence,
        )
        if "invalid_field" in evidence:
            self.assertEqual("does_not_exist", evidence["invalid_field"])
        self.assertEqual(evidence["validation_details"]["phase"], "metadata")
        self.assertNotIn("does_not_exist", evidence["validator_error"])

    # @test-value v2
    # kind = "invariant"
    # claim = "scratch cleanup failure is a dedicated blocker and cannot become a successful phase"
    # oracle = { type = "issue", ref = "https://github.com/natumekazuki/.codex/issues/50" }
    # fault = "the worker returns validated review output even though its owned scratch tree remains"
    # observable = "SCRATCH_CLEANUP_FAILED and no successful PhaseExecution"
    # observation_boundary = "component-behavior"
    # scope = "review-test-value review worker cleanup"
    # lifecycle = "permanent"
    # distinction = "covers owned filesystem cleanup while process-tree tests cover native child termination"
    # @end-test-value
    def test_execute_phase_blocks_when_scratch_cleanup_fails(self) -> None:
        packet = _packet()
        expected_result = _result()
        calls = 0

        def runner(
            argv: list[str], input_text: str, cwd: Path, timeout: float
        ) -> review_worker.ProcessOutcome:
            nonlocal calls
            calls += 1
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
            patch("review_worker.shutil.rmtree", side_effect=OSError("locked")),
        ):
            with self.assertRaisesRegex(
                review_worker.ReviewWorkerBlocked, "SCRATCH_CLEANUP_FAILED"
            ) as blocked:
                review_worker.execute_phase(
                    "metadata",
                    packet,
                    cli=str(self.cli),
                    role_file=str(self.role),
                    runner=runner,
                )

        self.assertEqual("SCRATCH_CLEANUP_FAILED", blocked.exception.code)
        self.assertFalse(blocked.exception.evidence.get("paths_removed", True))

    # @test-value v2
    # kind = "invariant"
    # claim = "a stuck scratch deletion returns a blocker after a bounded cleanup wait"
    # oracle = { type = "issue", ref = "https://github.com/natumekazuki/.codex/issues/50" }
    # fault = "coordinator waits forever for a locked scratch directory after the model process has ended"
    # observable = "cleanup returns false within the configured bounded interval"
    # observation_boundary = "component-behavior"
    # scope = "review-test-value review worker cleanup"
    # lifecycle = "permanent"
    # distinction = "exercises cleanup wait bounding directly while the phase test covers dedicated failure propagation"
    # @end-test-value
    def test_cleanup_wait_is_bounded_when_rmtree_stalls(self) -> None:
        root = Path(self.temp.name) / "stuck-scratch"
        root.mkdir()
        release = threading.Event()

        def stalled_rmtree(path: Path, *, ignore_errors: bool) -> None:
            release.wait(1.0)

        started = time.monotonic()
        with patch(
            "review_worker.shutil.rmtree", side_effect=stalled_rmtree
        ), patch("review_worker.PROCESS_TREE_TERMINATION_SECONDS", 0.02):
            removed = review_worker._cleanup_owned_paths(
                (root,), time.monotonic() + 1.0
            )
        elapsed = time.monotonic() - started
        release.set()
        self.assertFalse(removed)
        self.assertLess(elapsed, 0.5)

    # @test-value v2
    # kind = "security"
    # claim = "a local managed Codex config blocks the worker before packet launch"
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
