from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock


SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import run_review_diagnostics as diagnostics  # noqa: E402
from run_test_value_review import execution_policy  # noqa: E402


def _state(root: Path) -> dict:
    policy = execution_policy()
    return {
        "schema_version": diagnostics.TASK_STATE_VERSION,
        "execution_policy": policy,
        "execution_policy_hash": diagnostics._canonical_hash(policy),
        "task_id": "task-diagnostic",
        "repository_root": str(root),
        "base_commit_oid": "a" * 40,
        "target_mode": "working",
        "generations": [],
    }


def _generation(records: list[dict], target: dict, *, gate: str = "PASS") -> dict:
    policy = execution_policy()
    toolchain = {"identity": "toolchain", "execution_policy": policy}
    aggregation = {
        "input": {
            "alignment_packet": {"records": records},
            "alignment_result": {"review_contract_version": "alignment-review-v3", "reviews": []},
            "metadata_result": {"review_contract_version": "metadata-review-v3", "reviews": []},
            "routing_manifest": {"records": []},
            "deep_packet": {"records": []},
        },
        "result": {"gate": gate, "records": []},
    }
    aggregation["input_hash"] = diagnostics.result_hash(aggregation["input"])
    aggregation["result_hash"] = diagnostics.result_hash(aggregation["result"])
    return {
        "schema_version": diagnostics.GENERATION_VERSION,
        "generation_id": "g000001",
        "target_snapshot": target,
        "target_snapshot_hash": target["target_snapshot_hash"],
        "selection_hash": "sha256:" + "1" * 64,
        "host_evidence_hash": "sha256:" + "9" * 64,
        "toolchain_identity": toolchain,
        "toolchain_hash": diagnostics._canonical_hash(toolchain),
        "worker_evidence_hash": "sha256:" + "a" * 64,
        "aggregation": aggregation,
    }


def _record(record_id: str) -> dict:
    return {"record_id": record_id, "metadata_review": {"verdict": "VALID"}}


class ReviewDiagnosticTests(unittest.TestCase):
    def _patch_common(
        self,
        *,
        root: Path,
        state: Path,
        generation: dict,
        routes: dict[str, dict],
        records: list[dict],
        calls: list[str],
    ):
        target = generation["target_snapshot"]

        def fake_batch(
            phase: str,
            packet: dict,
            **_: object,
        ) -> tuple[dict, dict]:
            calls.append(phase)
            return (
                {"phase": phase, "reviews": []},
                {
                    "schema_version": "phase-batch-execution-v1",
                    "phase": phase,
                    "plan": {"plan_hash": "sha256:" + "2" * 64},
                    "batches": [],
                    "merged_result_hash": "sha256:" + "3" * 64,
                },
            )

        patches = [
            mock.patch.object(
                diagnostics,
                "_load_published",
                return_value=(_state(root), generation),
            ),
            mock.patch.object(diagnostics, "_resolve_repository", return_value=root),
            mock.patch.object(
                diagnostics, "snapshot_descriptor", return_value=target
            ),
            mock.patch.object(
                diagnostics, "_toolchain_identity", return_value={"identity": "toolchain"}
            ),
            mock.patch.object(
                diagnostics,
                "_alignment_records",
                return_value=records,
            ),
            mock.patch.object(
                diagnostics,
                "_route_maps",
                return_value=(
                    routes,
                    {
                        record["record_id"]: {"record_id": record["record_id"], "verdict": "ALIGNED"}
                        for record in records
                    },
                    {record["record_id"]: {} for record in records},
                ),
            ),
            mock.patch.object(
                diagnostics,
                "_contexts",
                return_value={record["record_id"]: [] for record in records},
            ),
            mock.patch.object(
                diagnostics,
                "validate_phase_result",
                side_effect=lambda phase, result, expected, *args: {
                    "reviews": [
                        {"record_id": item["record_id"], "verdict": "ALIGNED"}
                        for item in expected
                    ]
                    if phase == "alignment"
                    else result.get("reviews", [])
                },
            ),
            mock.patch.object(
                diagnostics,
                "_metadata_packet",
                side_effect=lambda selected: {
                    "review_contract_version": "metadata-review-v3",
                    "records": copy.deepcopy(selected),
                },
            ),
            mock.patch.object(
                diagnostics,
                "_alignment_packet",
                side_effect=lambda selected, result: {
                    "records": copy.deepcopy(selected),
                    "review_contract_version": "alignment-review-v3",
                    "metadata_result_hash": "sha256:" + "4" * 64,
                },
            ),
            mock.patch.object(
                diagnostics,
                "_metadata_subset",
                return_value={"review_contract_version": "metadata-review-v3", "reviews": []},
            ),
            mock.patch.object(
                diagnostics,
                "_deep_packet",
                side_effect=lambda selected, *_args, **_kwargs: {
                    "review_contract_version": "deep-review-v3",
                    "metadata_result_hash": "sha256:" + "4" * 64,
                    "records": copy.deepcopy(selected),
                    "input_hash": "sha256:" + "5" * 64,
                },
            ),
            mock.patch.object(diagnostics, "_run_batch", side_effect=fake_batch),
        ]
        return patches

    # @test-value v2
    # kind = "security"
    # claim = "診断workerの失敗はVALIDATION_GAPとして記録され、公開済みtask stateのbytesを変更しない"
    # oracle = { type = "contract", ref = "skills/review-test-value/scripts/run_review_diagnostics.py" }
    # fault = "worker failureを成功扱いまたはstate mutationとして処理し、元generationの証跡を壊す"
    # observable = "diagnostic artifactのstatus、reason_codes、worker call数、task-manifest bytes"
    # observation_boundary = "component-behavior"
    # scope = "test-value-review-diagnostic-state-integrity"
    # lifecycle = "permanent"
    # @end-test-value
    def test_diagnostic_failure_keeps_published_state_byte_identical(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root = base / "repo"
            state_dir = base / "state"
            root.mkdir()
            state_dir.mkdir()
            target = {
                "base_commit_oid": "a" * 40,
                "target_mode": "working",
                "head_commit_oid": None,
                "tracked_diff_hash": "sha256:" + "6" * 64,
                "untracked": [],
                "target_snapshot_hash": "sha256:" + "7" * 64,
            }
            records = [_record("sha256:" + "8" * 64)]
            generation = _generation(records, target)
            routes = {
                records[0]["record_id"]: {
                    "audit_selected": True,
                    "required": False,
                    "risk_tags": [],
                }
            }
            state_text = json.dumps({"published": True}, sort_keys=True)
            manifest = state_dir / "task-manifest.json"
            manifest.write_text(state_text, encoding="utf-8")
            before = manifest.read_bytes()
            calls: list[str] = []
            patches = self._patch_common(
                root=root,
                state=state_dir,
                generation=generation,
                routes=routes,
                records=records,
                calls=calls,
            )
            patches[-1] = mock.patch.object(
                diagnostics,
                "_run_batch",
                side_effect=diagnostics.DiagnosticBlocked("WORKER_TIMEOUT"),
            )
            with contextlib_enter(patches):
                result = diagnostics.run(
                    SimpleNamespace(
                        state_dir=state_dir,
                        output_dir=base / "diagnostic-output",
                        generation_id=None,
                        cli="codex.exe",
                        mode="audit",
                    )
                )
            self.assertEqual(result["status"], "VALIDATION_GAP")
            self.assertEqual(result["original_generation_gate"], "PASS")
            self.assertEqual(calls, [])
            self.assertEqual(before, manifest.read_bytes())
            self.assertEqual(
                json.loads((base / "diagnostic-output" / diagnostics.ARTIFACT_FILENAME).read_text()),
                result,
            )

    # @test-value v2
    # kind = "contract"
    # claim = "audit diagnosticはcanonical routingのaudit_selectedかつlow-riskでrequiredでないnon-terminal recordだけを決定論的に選ぶ"
    # oracle = { type = "contract", ref = "skills/review-test-value/scripts/run_review_diagnostics.py" }
    # fault = "required、risk付き、terminal recordをauditへ混入させるか、同じgenerationの再実行でselectionを変える"
    # observable = "2回のdiagnostic artifactにあるselected_record_ids"
    # observation_boundary = "component-behavior"
    # scope = "test-value-review-diagnostic-audit-scope"
    # lifecycle = "permanent"
    # @end-test-value
    def test_audit_scope_is_deterministic_and_excludes_required_risk_and_terminal(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root = base / "repo"
            state_dir = base / "state"
            root.mkdir()
            state_dir.mkdir()
            target = {
                "base_commit_oid": "a" * 40,
                "target_mode": "working",
                "head_commit_oid": None,
                "tracked_diff_hash": "sha256:" + "6" * 64,
                "untracked": [],
                "target_snapshot_hash": "sha256:" + "7" * 64,
            }
            records = [_record("sha256:" + str(i) * 64) for i in range(1, 5)]
            generation = _generation(records, target)
            routes = {
                records[0]["record_id"]: {"audit_selected": True, "required": False, "risk_tags": []},
                records[1]["record_id"]: {"audit_selected": True, "required": True, "risk_tags": []},
                records[2]["record_id"]: {"audit_selected": True, "required": False, "risk_tags": ["privacy"]},
                records[3]["record_id"]: {"audit_selected": True, "required": False, "risk_tags": [], "terminal": True},
            }
            calls: list[str] = []
            patches = self._patch_common(
                root=root,
                state=state_dir,
                generation=generation,
                routes=routes,
                records=records,
                calls=calls,
            )
            with contextlib_enter(patches):
                first = diagnostics.run(
                    SimpleNamespace(
                        state_dir=state_dir,
                        output_dir=base / "one",
                        generation_id=None,
                        cli="codex.exe",
                        mode="audit",
                    )
                )
            calls.clear()
            # A fresh output directory represents a second explicit diagnostic.
            patches = self._patch_common(
                root=root,
                state=state_dir,
                generation=generation,
                routes=routes,
                records=records,
                calls=calls,
            )
            with contextlib_enter(patches):
                second = diagnostics.run(
                    SimpleNamespace(
                        state_dir=state_dir,
                        output_dir=base / "two",
                        generation_id=None,
                        cli="codex.exe",
                        mode="audit",
                    )
                )
            self.assertEqual(first["selected_record_ids"], [records[0]["record_id"]])
            self.assertEqual(first["selected_record_ids"], second["selected_record_ids"])

    # @test-value v2
    # kind = "contract"
    # claim = "all-phases diagnosticはnormal gateでterminalになったrecordも含むcanonical selection全件をmetadata、alignment、deepへ送る"
    # oracle = { type = "contract", ref = "skills/review-test-value/scripts/run_review_diagnostics.py" }
    # fault = "terminal recordをskipするか、診断結果をnormal gateへのoverrideとして扱う"
    # observable = "selected_record_ids、phase call sequence、diagnostic status"
    # observation_boundary = "component-behavior"
    # scope = "test-value-review-diagnostic-all-phases"
    # lifecycle = "permanent"
    # @end-test-value
    def test_all_phases_reviews_every_record_including_terminal_records(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root = base / "repo"
            state_dir = base / "state"
            root.mkdir()
            state_dir.mkdir()
            target = {
                "base_commit_oid": "a" * 40,
                "target_mode": "working",
                "head_commit_oid": None,
                "tracked_diff_hash": "sha256:" + "6" * 64,
                "untracked": [],
                "target_snapshot_hash": "sha256:" + "7" * 64,
            }
            records = [_record("sha256:" + str(i) * 64) for i in range(1, 4)]
            generation = _generation(records, target)
            routes = {
                records[0]["record_id"]: {"audit_selected": False, "required": False, "risk_tags": []},
                records[1]["record_id"]: {"audit_selected": False, "required": False, "risk_tags": [], "terminal": True},
                records[2]["record_id"]: {"audit_selected": False, "required": True, "risk_tags": ["security"]},
            }
            calls: list[str] = []
            patches = self._patch_common(
                root=root,
                state=state_dir,
                generation=generation,
                routes=routes,
                records=records,
                calls=calls,
            )
            with contextlib_enter(patches):
                result = diagnostics.run(
                    SimpleNamespace(
                        state_dir=state_dir,
                        output_dir=base / "all",
                        generation_id=None,
                        cli="codex.exe",
                        mode="all-phases",
                    )
                )
            self.assertEqual(result["status"], "COMPLETED")
            self.assertEqual(result["selected_record_ids"], [item["record_id"] for item in records])
            self.assertEqual(calls, ["metadata", "alignment", "deep"])

    # @test-value v2
    # kind = "security"
    # claim = "published generationのsnapshotとcurrent repository snapshotが異なる場合、diagnosticはworker前に停止する"
    # oracle = { type = "contract", ref = "skills/review-test-value/scripts/run_review_diagnostics.py" }
    # fault = "snapshot mismatchを無視して古いcanonical packetをworkerへ再送するかdiagnostic outputを作成する"
    # observable = "SNAPSHOT_CHANGED reason、worker call数、output directoryの不存在"
    # observation_boundary = "component-behavior"
    # scope = "test-value-review-diagnostic-snapshot-preflight"
    # lifecycle = "permanent"
    # @end-test-value
    def test_snapshot_mismatch_blocks_before_worker_and_output_creation(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root = base / "repo"
            state_dir = base / "state"
            root.mkdir()
            state_dir.mkdir()
            frozen = {
                "base_commit_oid": "a" * 40,
                "target_mode": "working",
                "head_commit_oid": None,
                "tracked_diff_hash": "sha256:" + "6" * 64,
                "untracked": [],
                "target_snapshot_hash": "sha256:" + "7" * 64,
            }
            current = copy.deepcopy(frozen)
            current["tracked_diff_hash"] = "sha256:" + "9" * 64
            generation = _generation([], frozen)
            calls: list[str] = []
            patches = self._patch_common(
                root=root,
                state=state_dir,
                generation=generation,
                routes={},
                records=[],
                calls=calls,
            )
            patches[2] = mock.patch.object(
                diagnostics, "snapshot_descriptor", return_value=current
            )
            with contextlib_enter(patches):
                with self.assertRaises(diagnostics.DiagnosticBlocked) as raised:
                    diagnostics.run(
                        SimpleNamespace(
                            state_dir=state_dir,
                            output_dir=base / "blocked",
                            generation_id=None,
                            cli="codex.exe",
                            mode="audit",
                        )
                    )
            self.assertEqual(raised.exception.reason_code, "SNAPSHOT_CHANGED")
            self.assertEqual(calls, [])
            self.assertFalse((base / "blocked").exists())

    # @test-value v2
    # kind = "security"
    # claim = "published generationのfrozen toolchain identityとcurrent identityが異なる場合、diagnosticはworker前に停止する"
    # oracle = { type = "contract", ref = "skills/review-test-value/scripts/run_review_diagnostics.py" }
    # fault = "CLI、role、contract、execution policyのidentity mismatchを無視して意味審査を起動する"
    # observable = "TOOLCHAIN_CHANGED reason、worker call数、output directoryの不存在"
    # observation_boundary = "component-behavior"
    # scope = "test-value-review-diagnostic-toolchain-preflight"
    # lifecycle = "permanent"
    # @end-test-value
    def test_toolchain_mismatch_blocks_before_worker_and_output_creation(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root = base / "repo"
            state_dir = base / "state"
            root.mkdir()
            state_dir.mkdir()
            target = {
                "base_commit_oid": "a" * 40,
                "target_mode": "working",
                "head_commit_oid": None,
                "tracked_diff_hash": "sha256:" + "6" * 64,
                "untracked": [],
                "target_snapshot_hash": "sha256:" + "7" * 64,
            }
            records = [_record("sha256:" + "c" * 64)]
            generation = _generation(records, target)
            calls: list[str] = []
            patches = self._patch_common(
                root=root,
                state=state_dir,
                generation=generation,
                routes={records[0]["record_id"]: {"audit_selected": True, "required": False, "risk_tags": []}},
                records=records,
                calls=calls,
            )
            patches[3] = mock.patch.object(
                diagnostics, "_toolchain_identity", return_value={"identity": "changed"}
            )
            with contextlib_enter(patches):
                with self.assertRaises(diagnostics.DiagnosticBlocked) as raised:
                    diagnostics.run(
                        SimpleNamespace(
                            state_dir=state_dir,
                            output_dir=base / "blocked",
                            generation_id=None,
                            cli="codex.exe",
                            mode="audit",
                        )
                    )
            self.assertEqual(raised.exception.reason_code, "TOOLCHAIN_CHANGED")
            self.assertEqual(calls, [])
            self.assertFalse((base / "blocked").exists())

    # @test-value v2
    # kind = "contract"
    # claim = "旧task manifest versionはdiagnosticのcanonical inputとして再利用されずworker前に拒否される"
    # oracle = { type = "contract", ref = "skills/review-test-value/scripts/run_review_diagnostics.py" }
    # fault = "旧schemaのtask manifestを新diagnostic contractへ推測変換してworkerを起動する"
    # observable = "STATE_VERSION_MISMATCH reasonとoutput directoryの不存在"
    # observation_boundary = "component-behavior"
    # scope = "test-value-review-diagnostic-state-version"
    # lifecycle = "permanent"
    # @end-test-value
    def test_state_version_mismatch_blocks_before_worker(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            state_dir = base / "state"
            state_dir.mkdir()
            (state_dir / "task-manifest.json").write_text(
                json.dumps({"schema_version": "old"}), encoding="utf-8"
            )
            with self.assertRaises(diagnostics.DiagnosticBlocked) as raised:
                diagnostics.run(
                    SimpleNamespace(
                        state_dir=state_dir,
                        output_dir=base / "blocked",
                        generation_id=None,
                        cli="codex.exe",
                        mode="audit",
                    )
                )
            self.assertEqual(raised.exception.reason_code, "STATE_VERSION_MISMATCH")
            self.assertFalse((base / "blocked").exists())

    # @test-value v2
    # kind = "invariant"
    # claim = "audit deepのREDESIGNはaudit disagreementとrecord IDsをVALIDATION_GAPへ記録しnormal gateを変更しない"
    # oracle = { type = "contract", ref = "skills/review-test-value/scripts/run_review_diagnostics.py" }
    # fault = "auditの追加意味審査をnormal gate判定へ混ぜるかnegative verdictを成功扱いにする"
    # observable = "artifact status、AUDIT_DISAGREEMENT reason、diagnostic_disagreement_record_ids"
    # observation_boundary = "component-behavior"
    # scope = "test-value-review-diagnostic-audit-disagreement"
    # lifecycle = "permanent"
    # @end-test-value
    def test_audit_model_redesign_is_a_validation_gap_without_gate_mutation(self):
        record_id = "sha256:" + "a" * 64
        artifact = {"status": "COMPLETED", "reason_codes": []}
        diagnostics._semantic_diagnostic_status(
            artifact,
            "audit",
            {"reviews": [{"record_id": record_id, "verdict": "REDESIGN"}]},
        )
        self.assertEqual(artifact["status"], "VALIDATION_GAP")
        self.assertEqual(artifact["reason_codes"], ["AUDIT_DISAGREEMENT"])
        self.assertEqual(artifact["diagnostic_disagreement_record_ids"], [record_id])

    # @test-value v2
    # kind = "regression"
    # claim = "audit runでdeep REDESIGNが返っても、例外ではなくsanitized gap artifactへ記録しoriginal generation gateを保持する"
    # oracle = { type = "contract", ref = "skills/review-test-value/scripts/run_review_diagnostics.py" }
    # fault = "validなnegative model resultを未処理例外またはCOMPLETEDへ変換し、元generation gateを上書きする"
    # observable = "diagnostic.jsonのstatus、reason_codes、original_generation_gate、deep call数"
    # observation_boundary = "component-behavior"
    # scope = "test-value-review-diagnostic-negative-result"
    # lifecycle = "permanent"
    # @end-test-value
    def test_audit_model_redesign_run_writes_gap_artifact_without_exception(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root = base / "repo"
            state_dir = base / "state"
            root.mkdir()
            state_dir.mkdir()
            target = {
                "base_commit_oid": "a" * 40,
                "target_mode": "working",
                "head_commit_oid": None,
                "tracked_diff_hash": "sha256:" + "6" * 64,
                "untracked": [],
                "target_snapshot_hash": "sha256:" + "7" * 64,
            }
            records = [_record("sha256:" + "b" * 64)]
            generation = _generation(records, target)
            routes = {
                records[0]["record_id"]: {
                    "audit_selected": True,
                    "required": False,
                    "risk_tags": [],
                }
            }
            calls: list[str] = []
            patches = self._patch_common(
                root=root,
                state=state_dir,
                generation=generation,
                routes=routes,
                records=records,
                calls=calls,
            )

            def negative_deep(_phase: str, _packet: dict, **_: object) -> tuple[dict, dict]:
                calls.append("deep")
                return (
                    {
                        "review_contract_version": "deep-review-v3",
                        "input_hash": "sha256:" + "5" * 64,
                        "reviews": [
                            {
                                "record_id": records[0]["record_id"],
                                "verdict": "REDESIGN",
                            }
                        ],
                    },
                    {
                        "schema_version": "phase-batch-execution-v1",
                        "phase": "deep",
                        "plan": {"plan_hash": "sha256:" + "2" * 64},
                        "batches": [],
                        "merged_result_hash": "sha256:" + "3" * 64,
                    },
                )

            patches[-1] = mock.patch.object(
                diagnostics, "_run_batch", side_effect=negative_deep
            )
            with contextlib_enter(patches):
                result = diagnostics.run(
                    SimpleNamespace(
                        state_dir=state_dir,
                        output_dir=base / "audit-gap",
                        generation_id=None,
                        cli="codex.exe",
                        mode="audit",
                    )
                )
            self.assertEqual(result["status"], "VALIDATION_GAP")
            self.assertEqual(result["reason_codes"], ["AUDIT_DISAGREEMENT"])
            self.assertEqual(calls, ["deep"])
            self.assertEqual(result["original_generation_gate"], "PASS")


class contextlib_enter:
    """Small local context manager to keep patch setup readable."""

    def __init__(self, patches):
        self.patches = patches

    def __enter__(self):
        for patch in self.patches:
            patch.start()
        return self

    def __exit__(self, exc_type, exc, tb):
        for patch in reversed(self.patches):
            patch.stop()
        return False


if __name__ == "__main__":
    unittest.main()
