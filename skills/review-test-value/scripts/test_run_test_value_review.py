from __future__ import annotations

import copy
import contextlib
import io
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import sys
import unittest
from unittest import mock


SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from build_review_packets import (
    build_alignment_packet_multi,
    build_metadata_packet_multi,
    canonical_json,
)
import run_test_value_review as coordinator
import review_worker
from review_resolution import content_hash
from review_routing import build_routing_manifest, decide_gate
from validate_review_result import aggregate_results
from test_review_packets import extractor_result, metadata_result


def language_extractors() -> list[dict]:
    python = extractor_result()
    typescript = copy.deepcopy(python)
    typescript["adapter"] = "typescript-estree-v1"
    typescript["coverage"] = "typescript-source-declarations-v1"
    typescript["tests"][0]["source"]["path"] = "tests/z_packet.test.ts"
    typescript["tests"][0]["source"]["symbol"] = "packet boundary"
    csharp = copy.deepcopy(python)
    csharp["adapter"] = "csharp-roslyn-v1"
    csharp["coverage"] = "csharp-source-declarations-v1"
    csharp["tests"][0]["source"]["path"] = "tests/AReviewTests.cs"
    csharp["tests"][0]["source"]["symbol"] = "ReviewTests.PacketBoundary"
    return [python, typescript, csharp]


def alignment_result(packet: dict, verdict: str = "MISMATCH") -> dict:
    return {
        "review_contract_version": "alignment-review-v2",
        "reviews": [
            {
                "record_id": record["record_id"],
                "metadata_hash": record["metadata_hash"],
                "source_hash": record["source_hash"],
                "verdict": verdict,
                "actual_boundary": "implementation",
                "actual_observables": ["assertion result"],
                "overclaim": verdict == "MISMATCH",
                "evidence": ["the assertion observes implementation state"],
                "unverified": [],
                "disposition_candidate": "DROP",
                "context_requirements": [],
                "next_action": None,
            }
            for record in packet["records"]
        ],
    }


class ReviewCoordinatorTests(unittest.TestCase):
    # @test-value v2
    # kind = "contract"
    # claim = "worker失敗はphaseと安全なvalidator/canary診断だけをstructured BLOCKEDとしてCLIへ返す"
    # oracle = { type = "issue", ref = "natumekazuki/.codex#50" }
    # fault = "coordinator wrapperが診断を全廃するかraw command/pathまで公開し、hostが原因を安全に特定できない"
    # observable = "_execute_phaseのwhitelist detailsとmainのJSON output/exit 2"
    # observation_boundary = "public-boundary"
    # scope = "test-value-worker-failure-diagnostic"
    # lifecycle = "permanent"
    # @end-test-value
    def test_worker_validation_failure_reports_phase_and_validator_detail(self):
        worker_failure = review_worker.ReviewWorkerBlocked(
            "REVIEW_RESULT_VALIDATION_FAILED",
            {"validator_error": "review record set or order does not match the packet"},
        )
        with mock.patch.object(
            review_worker,
            "execute_phase",
            side_effect=worker_failure,
        ):
            with self.assertRaises(coordinator.CoordinatorBlocked) as raised:
                coordinator._execute_phase(
                    "alignment",
                    {},
                    cli="C:/codex.exe",
                    role_file=Path("C:/test_value_luna.toml"),
                )

        self.assertEqual(
            raised.exception.details,
            {
                "phase": "alignment",
                "validator_error": "review record set or order does not match the packet",
            },
        )
        canary_events = [
            {
                "type": "item.completed",
                "item": {
                    "id": "canary-command",
                    "type": "command_execution",
                    "command": "Get-Content -Raw -LiteralPath 'C:/test-value/unrelated.txt'",
                    "status": "failed",
                    "exit_code": 1,
                    "aggregated_output": "Access is denied.",
                },
            },
            {"type": "turn.completed"},
        ]
        with self.assertRaises(review_worker.ReviewWorkerBlocked) as produced:
            review_worker._verify_canary(
                review_worker.ProcessOutcome(
                    0, "\n".join(json.dumps(event) for event in canary_events), ""
                ),
                "private-canary-content",
                Path("C:/test-value/expected-canary.txt"),
            )
        canary_failure = produced.exception
        with mock.patch.object(
            review_worker,
            "execute_phase",
            side_effect=canary_failure,
        ):
            with self.assertRaises(coordinator.CoordinatorBlocked) as canary:
                coordinator._execute_phase(
                    "deep",
                    {},
                    cli="C:/codex.exe",
                    role_file=Path("C:/test_value_sol.toml"),
                )
        self.assertEqual(
            canary.exception.details,
            {
                "phase": "deep",
                "canary_evidence": {
                    "turn_completed": True,
                    "tool_event_count": 1,
                    "command_id_count": 1,
                    "command_count": 1,
                    "command_matches": False,
                    "command_statuses": ["failed"],
                    "command_exit_codes": [1],
                    "denial_markers": [True],
                },
            },
        )
        output = io.StringIO()
        with (
            mock.patch.object(coordinator, "run", side_effect=canary.exception),
            contextlib.redirect_stdout(output),
        ):
            exit_code = coordinator.main(
                [
                    "--root",
                    ".",
                    "--changed-from",
                    "base",
                    "--state-dir",
                    ".",
                    "--cli",
                    "C:/codex.exe",
                ]
            )

        result = json.loads(output.getvalue())
        self.assertEqual(exit_code, 2)
        self.assertEqual(result["reason_codes"], ["CANARY_DENIAL_UNVERIFIED"])
        self.assertEqual(result["details"], canary.exception.details)
        self.assertNotIn("commands", result["details"]["canary_evidence"])
        self.assertNotIn("unrelated.txt", output.getvalue())

    # @test-value v2
    # kind = "contract"
    # claim = "review worker moduleが利用不能ならcoordinatorはWORKER_UNAVAILABLEとしてBLOCKED経路へ送る"
    # oracle = { type = "issue", ref = "natumekazuki/.codex#50" }
    # fault = "import失敗時に未束縛例外が発生し、process exit 1をCHANGES_REQUIREDと誤認させる"
    # observable = "_toolchain_identityのCoordinatorBlocked reason code"
    # observation_boundary = "component-behavior"
    # scope = "test-value-worker-availability"
    # lifecycle = "permanent"
    # @end-test-value
    def test_missing_worker_module_is_a_blocked_reason(self):
        with mock.patch.dict(sys.modules, {"review_worker": None}):
            with self.assertRaises(coordinator.CoordinatorBlocked) as raised:
                coordinator._toolchain_identity("C:/codex.exe", Path("C:/toolchain"))

        self.assertEqual(raised.exception.reason_code, "WORKER_UNAVAILABLE")

    # @test-value v2
    # kind = "regression"
    # claim = "過去generationの非DROP/MOVE変更要求は削除や同名別契約では残り、同一locatorでsourceまたはmetadataが一致するcurrent PASSだけが解消する"
    # oracle = { type = "issue", ref = "natumekazuki/.codex#50" }
    # fault = "KEEP_PERMANENTの未解決REDESIGNをtest削除と空selectionだけでPASSへ消す"
    # observable = "historical KEEP outcomeとempty current outcomeを集約したouter gate"
    # observation_boundary = "component-behavior"
    # scope = "test-value-historical-obligation"
    # lifecycle = "permanent"
    # @end-test-value
    def test_historical_non_resolution_change_survives_empty_current_selection(self):
        old_packet_record = {
            "record_id": "old-record",
            "adapter": "python-source-v1",
            "source_hash": content_hash("stable test body"),
            "metadata_hash": content_hash("old metadata"),
            "source": {"path": "tests/test_feature.py", "symbol": "test_feature"},
        }
        historical = {
            "generation_id": "g000001",
            "aggregation": {
                "input": {"alignment_packet": {"records": [old_packet_record]}},
                "result": {
                    "records": [
                        {
                            "record_id": "old-record",
                            "status": "REDESIGN",
                            "disposition": "KEEP_PERMANENT",
                            "gate": "CHANGES_REQUIRED",
                        }
                    ]
                }
            },
        }
        current = {
            "generation_id": "g000002",
            "aggregation": {
                "input": {"alignment_packet": {"records": []}},
                "result": {"records": []},
            },
        }
        state = {
            "task_id": "task-50",
            "generations": [
                {"generation_id": "g000001"},
                {"generation_id": "g000002"},
            ],
        }

        with (
            mock.patch.object(
                coordinator,
                "_load_generation",
                side_effect=[historical, current],
            ),
            mock.patch.object(
                coordinator,
                "_resolution_gate",
                return_value=("PASS", set()),
            ),
        ):
            gate = coordinator._outer_gate(
                Path("state"),
                Path("state"),
                state,
                current,
                current_snapshot_hash=content_hash("snapshot"),
                mode="working",
                head_oid=None,
            )

        self.assertEqual(gate, "CHANGES_REQUIRED")

        moved = copy.deepcopy(old_packet_record)
        moved["record_id"] = "new-record-after-metadata-fix"
        moved["metadata_hash"] = content_hash("fixed metadata")
        current["aggregation"] = {
            "input": {"alignment_packet": {"records": [moved]}},
            "result": {
                "records": [
                    {
                        "record_id": moved["record_id"],
                        "status": "ACCEPT",
                        "disposition": "KEEP_PERMANENT",
                        "gate": "PASS",
                    }
                ]
            },
        }
        with (
            mock.patch.object(
                coordinator,
                "_load_generation",
                side_effect=[historical, current],
            ),
            mock.patch.object(
                coordinator,
                "_resolution_gate",
                return_value=("PASS", set()),
            ),
        ):
            gate = coordinator._outer_gate(
                Path("state"),
                Path("state"),
                state,
                current,
                current_snapshot_hash=content_hash("snapshot"),
                mode="working",
                head_oid=None,
            )

        self.assertEqual(gate, "PASS")

        moved["source_hash"] = content_hash("unrelated replacement body")
        with (
            mock.patch.object(
                coordinator,
                "_load_generation",
                side_effect=[historical, current],
            ),
            mock.patch.object(
                coordinator,
                "_resolution_gate",
                return_value=("PASS", set()),
            ),
        ):
            gate = coordinator._outer_gate(
                Path("state"),
                Path("state"),
                state,
                current,
                current_snapshot_hash=content_hash("snapshot"),
                mode="working",
                head_oid=None,
            )

        self.assertEqual(gate, "CHANGES_REQUIRED")

        supersession = {
            "historical_generation_id": "g000001",
            "historical_record_id": old_packet_record["record_id"],
            "historical_metadata_hash": old_packet_record["metadata_hash"],
            "historical_source_hash": old_packet_record["source_hash"],
            "current_record_id": moved["record_id"],
            "current_metadata_hash": moved["metadata_hash"],
            "current_source_hash": moved["source_hash"],
        }
        with (
            mock.patch.object(
                coordinator,
                "_load_generation",
                side_effect=[historical, current],
            ),
            mock.patch.object(
                coordinator,
                "_resolution_gate",
                return_value=("PASS", set()),
            ),
        ):
            gate = coordinator._outer_gate(
                Path("state"),
                Path("state"),
                state,
                current,
                current_snapshot_hash=content_hash("snapshot"),
                mode="working",
                head_oid=None,
                supersessions=[supersession],
            )

        self.assertEqual(gate, "PASS")

        moved["metadata_hash"] = old_packet_record["metadata_hash"]
        with (
            mock.patch.object(
                coordinator,
                "_load_generation",
                side_effect=[historical, current],
            ),
            mock.patch.object(
                coordinator,
                "_resolution_gate",
                return_value=("PASS", set()),
            ),
        ):
            gate = coordinator._outer_gate(
                Path("state"),
                Path("state"),
                state,
                current,
                current_snapshot_hash=content_hash("snapshot"),
                mode="working",
                head_oid=None,
            )

        self.assertEqual(gate, "PASS")

    # @test-value v2
    # kind = "invariant"
    # claim = "DELETED transitionはTEST_ABSENTとして扱い、KEEP_PERMANENTはBLOCKED、根拠あるDROPもledger解消前はCHANGES_REQUIREDになる"
    # oracle = { type = "issue", ref = "natumekazuki/.codex#50" }
    # fault = "削除前sourceを現snapshotにPRESENTと捏造し、保持すべきtestの削除をPASSにする"
    # observable = "source observationのABSENT、artifactのTEST_ABSENT、KEEP/DROP gate"
    # observation_boundary = "component-behavior"
    # scope = "test-value-deleted-retention"
    # lifecycle = "permanent"
    # @end-test-value
    def test_deleted_record_cannot_pass_as_a_retained_permanent_test(self):
        extracted = extractor_result()
        deleted = copy.deepcopy(extracted["tests"][0])
        extracted["tests"] = []
        extracted["transitions"] = [{"kind": "DELETED", "before": deleted, "after": None}]
        empty_typescript = {**copy.deepcopy(extracted), "adapter": "typescript-estree-v1", "coverage": "typescript-source-declarations-v1", "transitions": []}
        empty_csharp = {**copy.deepcopy(extracted), "adapter": "csharp-roslyn-v1", "coverage": "csharp-source-declarations-v1", "transitions": []}
        extractors = [extracted, empty_typescript, empty_csharp]
        metadata_packet = build_metadata_packet_multi(extractors)
        metadata_reviews = metadata_result(metadata_packet)
        alignment_packet = build_alignment_packet_multi(extractors, metadata_reviews)
        aligned = alignment_result(alignment_packet, verdict="ALIGNED")
        aligned["reviews"][0].update(
            actual_boundary="component-behavior",
            overclaim=False,
            disposition_candidate="KEEP_PERMANENT",
        )
        record = alignment_packet["records"][0]
        evidence = {
            "kind": "accepted-contract",
            "ref": "CONTRACT.md",
            "content": "retained contract",
            "content_hash": content_hash("retained contract"),
            "meaning": "the regression contract remains active",
        }
        host = {
            "retention_by_record": {
                record["record_id"]: {
                    "evidence": [evidence],
                    "determination": {
                        "determination": "SUPPORTED",
                        "rationale": "the accepted contract retains this check",
                        "evidence_refs": [
                            {"ref": evidence["ref"], "content_hash": evidence["content_hash"]}
                        ],
                    },
                    "temporal_observation": None,
                }
            }
        }

        projections, detailed = coordinator._retention_inputs(
            alignment_packet["records"],
            aligned,
            None,
            host,
            content_hash("current snapshot"),
        )

        self.assertEqual(projections[0]["artifact_state"], "TEST_ABSENT")
        self.assertEqual(
            detailed[record["record_id"]]["source_observation"]["determination"],
            "ABSENT",
        )
        self.assertEqual(
            decide_gate("ACCEPT", "KEEP_PERMANENT", projections[0]["artifact_state"]),
            "BLOCKED",
        )
        self.assertEqual(
            decide_gate("ACCEPT", "DROP", projections[0]["artifact_state"]),
            "CHANGES_REQUIRED",
        )

    # @test-value v2
    # kind = "contract"
    # claim = "hostはworkerを起動せず固定snapshotと全record identityを含むhost-evidence templateを同じ入口から取得できる"
    # oracle = { type = "issue", ref = "natumekazuki/.codex#50" }
    # fault = "hostがphase JSONやrecord hashを手作業で組み立てなければ審査を開始できない"
    # observable = "HOST_EVIDENCE_REQUIRED結果、canonical retention identity列、state未作成"
    # observation_boundary = "public-boundary"
    # scope = "test-value-coordinator-prepare"
    # lifecycle = "permanent"
    # @end-test-value
    def test_prepare_returns_snapshot_bound_host_template_without_worker_or_state(self):
        extractors = language_extractors()
        snapshot = {
            "base_commit_oid": "a" * 40,
            "target_mode": "working",
            "head_commit_oid": None,
            "tracked_diff_hash": content_hash("diff"),
            "untracked": [],
        }
        snapshot["target_snapshot_hash"] = content_hash(canonical_json(snapshot))
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            root = base / "repo"
            state = base / "state"
            root.mkdir()
            state.mkdir()
            args = SimpleNamespace(
                root=root,
                changed_from="base",
                head=None,
                staged=False,
                state_dir=state,
                cli="unused.exe",
                host_evidence=None,
            )
            with (
                mock.patch.object(coordinator, "_resolve_repository", return_value=root.resolve()),
                mock.patch.object(coordinator, "_resolve_commit", return_value="a" * 40),
                mock.patch.object(coordinator, "snapshot_descriptor", return_value=snapshot),
                mock.patch.object(coordinator, "extract_all_languages", return_value=extractors),
                mock.patch.object(coordinator, "_execute_phase") as worker,
            ):
                result = coordinator.run(args)

            template = result["host_evidence_template"]
            self.assertEqual(result["reason_codes"], ["HOST_EVIDENCE_REQUIRED"])
            self.assertEqual(len(template["retention_by_record"]), 3)
            self.assertEqual(
                template["target_snapshot_hash"],
                snapshot["target_snapshot_hash"],
            )
            self.assertEqual(
                [
                    {
                        "record_id": item["record_id"],
                        "metadata_hash": item["metadata_hash"],
                        "source_hash": item["source_hash"],
                    }
                    for item in template["retention_by_record"]
                ],
                [
                    {
                        "record_id": "sha256:74b23b959e26503ad8af10a21d4ccc2d6a5aac503f8d3d8c508d66857b98963e",
                        "metadata_hash": "sha256:94f953a86ccad3fefde7cfc1ed4943a00085a0f48b4483730bb6d903df70a2e9",
                        "source_hash": "sha256:f3307b5c9f8d70f5ef6fae1040f7b2e2ebd3426f74a379ce106b68c5b6e41567",
                    },
                    {
                        "record_id": "sha256:9af37966a4f5079d0789ff93751b76b09377ecbea7297e487d37b1b0e8b408fe",
                        "metadata_hash": "sha256:94f953a86ccad3fefde7cfc1ed4943a00085a0f48b4483730bb6d903df70a2e9",
                        "source_hash": "sha256:f3307b5c9f8d70f5ef6fae1040f7b2e2ebd3426f74a379ce106b68c5b6e41567",
                    },
                    {
                        "record_id": "sha256:04d11959d8bd19f4a9e3af60290dc0ae806f7bbe6558c3ccedb8502c1a08da76",
                        "metadata_hash": "sha256:94f953a86ccad3fefde7cfc1ed4943a00085a0f48b4483730bb6d903df70a2e9",
                        "source_hash": "sha256:f3307b5c9f8d70f5ef6fae1040f7b2e2ebd3426f74a379ce106b68c5b6e41567",
                    },
                ],
            )
            self.assertEqual(template["selection_hash"], result["selection_hash"])
            self.assertEqual(len(result["selection_summary"]), 3)
            self.assertTrue(result["selection_summary"][0]["source"]["path"])
            self.assertFalse((state / "task-manifest.json").exists())
            worker.assert_not_called()

    # @test-value v2
    # kind = "invariant"
    # claim = "3言語のextractor recordは一つの決定論的順序へ統合され、各recordのadapter identityと固定済みmetadata verdictをPhase 2へ渡す"
    # oracle = { type = "issue", ref = "natumekazuki/.codex#50" }
    # fault = "言語ごとのpacketを別々に完了扱いするか、global mergeでadapterまたはREDESIGN verdictを欠落させる"
    # observable = "global metadata/alignment packetのpath順、adapter集合、埋込みmetadata verdict"
    # observation_boundary = "component-behavior"
    # scope = "test-value-multilanguage-packet"
    # lifecycle = "permanent"
    # @end-test-value
    def test_multi_language_packets_preserve_every_adapter_and_frozen_verdict(self):
        extractors = language_extractors()
        packet = build_metadata_packet_multi(extractors)
        frozen = metadata_result(packet, verdict="REDESIGN")

        alignment = build_alignment_packet_multi(extractors, frozen)

        self.assertEqual(
            [record["source"]["path"] for record in alignment["records"]],
            sorted(record["source"]["path"] for record in alignment["records"]),
        )
        self.assertEqual(
            {record["adapter"] for record in alignment["records"]},
            {"python-source-v1", "typescript-estree-v1", "csharp-roslyn-v1"},
        )
        self.assertTrue(
            all(record["metadata_review"]["verdict"] == "REDESIGN" for record in alignment["records"])
        )

    # @test-value v2
    # kind = "security"
    # claim = "hostのsemantic evidenceは固定snapshotのrepository内UTF-8 file本文とhashが一致した場合だけ受理される"
    # oracle = { type = "issue", ref = "natumekazuki/.codex#50" }
    # fault = "callerがPRESENT相当の判定と偽のcontent/hashを渡すだけで保持根拠または親riskを確定できる"
    # observable = "validate_host_evidenceのEVIDENCE_HASH_MISMATCH"
    # observation_boundary = "component-behavior"
    # scope = "test-value-host-evidence-binding"
    # lifecycle = "permanent"
    # risk_tags = ["security"]
    # @end-test-value
    def test_host_evidence_rejects_content_not_observed_in_target(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            anchor = root / "CONTRACT.md"
            anchor.write_text("accepted behavior\n", encoding="utf-8")
            forged = "different behavior\n"
            value = {
                "schema_version": coordinator.HOST_EVIDENCE_VERSION,
                "task_id": "task-50",
                "target_snapshot_hash": content_hash("snapshot"),
                "selection_hash": content_hash("selection"),
                "parent_risk_assessment": {
                    "status": "ASSESSED",
                    "risk_tags": [],
                    "rationale": "host assessed the bounded contract",
                    "evidence": [
                        {
                            "source": "repository",
                            "authority": "repository",
                            "kind": "accepted-contract",
                            "ref": "CONTRACT.md",
                            "content": forged,
                            "content_hash": content_hash(forged),
                            "meaning": "accepted behavior",
                        }
                    ],
                    "evidence_refs": [
                        {"ref": "CONTRACT.md", "content_hash": content_hash(forged)}
                    ],
                },
                "context_by_record": [],
                "retry_context_by_record": [],
                "retention_by_record": [],
                "resolution_attempts": [],
                "supersessions": [],
            }

            with self.assertRaisesRegex(coordinator.CoordinatorBlocked, "CONTRACT.md") as raised:
                coordinator.validate_host_evidence(
                    root,
                    value,
                    snapshot_hash=content_hash("snapshot"),
                    selection_hash=content_hash("selection"),
                    records=[],
                    mode="working",
                    head_oid=None,
                )

            self.assertEqual(raised.exception.reason_code, "EVIDENCE_HASH_MISMATCH")

    # @test-value v2
    # kind = "contract"
    # claim = "temporal observationは保持根拠のSUPPORTED/UNSUPPORTED determinationと別の判定として保存される"
    # oracle = { type = "issue", ref = "natumekazuki/.codex#50" }
    # fault = "ACTIVE等のtemporal determinationがsemantic determinationを上書きし、retention判定schemaを壊す"
    # observable = "validated host evidence内のsemantic dictとtemporal string"
    # observation_boundary = "component-behavior"
    # scope = "test-value-host-retention-evidence"
    # lifecycle = "permanent"
    # @end-test-value
    def test_temporal_observation_does_not_replace_semantic_determination(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            content = "accepted behavior\n"
            (root / "CONTRACT.md").write_text(content, encoding="utf-8")
            digest = content_hash(content)
            record = {
                "record_id": "record-1",
                "metadata_hash": content_hash("metadata"),
                "source_hash": content_hash("source"),
            }
            semantic = {
                "determination": "SUPPORTED",
                "rationale": "the accepted contract retains this check",
                "evidence_refs": [{"ref": "CONTRACT.md", "content_hash": digest}],
            }
            bounded = {
                "source": "host-observed",
                "authority": "issue",
                "kind": "accepted-contract",
                "ref": "CONTRACT.md",
                "content": content,
                "content_hash": digest,
                "meaning": "the contract is active",
            }
            value = {
                "schema_version": coordinator.HOST_EVIDENCE_VERSION,
                "task_id": "task-50",
                "target_snapshot_hash": content_hash("snapshot"),
                "selection_hash": content_hash("selection"),
                "parent_risk_assessment": {
                    "status": "ASSESSED",
                    "risk_tags": [],
                    "rationale": "the repository contract was inspected",
                    "evidence": [bounded],
                    "evidence_refs": [{"ref": "CONTRACT.md", "content_hash": digest}],
                },
                "context_by_record": [],
                "retry_context_by_record": [],
                "retention_by_record": [
                    {
                        "record_id": record["record_id"],
                        "metadata_hash": record["metadata_hash"],
                        "source_hash": record["source_hash"],
                        "evidence": [bounded],
                        "determination": semantic,
                        "temporal_observation": {
                            "determination": "ACTIVE",
                            "source": "host-observed",
                            "authority": "issue",
                            "ref": "CONTRACT.md",
                            "content": content,
                            "content_hash": digest,
                            "meaning": "the contract is currently active",
                        },
                    }
                ],
                "resolution_attempts": [],
                "supersessions": [],
            }

            validated = coordinator.validate_host_evidence(
                root,
                value,
                snapshot_hash=content_hash("snapshot"),
                selection_hash=content_hash("selection"),
                records=[record],
                mode="working",
                head_oid=None,
            )

            retention = validated["retention_by_record"][record["record_id"]]
            self.assertEqual(retention["determination"], semantic)
            self.assertEqual(retention["temporal_observation"]["determination"], "ACTIVE")

    # @test-value v2
    # kind = "invariant"
    # claim = "Phase 1がREDESIGNでもPhase 2を実行し、snapshot変化時は解消を保存せず、toolchain変更時は再審査し、state欠損時はBLOCKEDへ戻る"
    # oracle = { type = "issue", ref = "natumekazuki/.codex#50" }
    # fault = "REDESIGNで本文審査を省略するか、削除義務のstate消失後も同じsnapshotをPASSまたはCHANGES_REQUIREDとして信頼する"
    # observable = "worker phase順、失敗run後ledger、再審査回数、CHANGES_REQUIRED→PASS遷移、state欠損reason code"
    # observation_boundary = "component-behavior"
    # scope = "test-value-coordinator-resolution-history"
    # lifecycle = "permanent"
    # @end-test-value
    def test_redesign_runs_alignment_and_missing_historical_ledger_blocks(self):
        extracted = extractor_result()
        empty_typescript = {**copy.deepcopy(extracted), "adapter": "typescript-estree-v1", "coverage": "typescript-source-declarations-v1", "tests": [], "transitions": []}
        empty_csharp = {**copy.deepcopy(extracted), "adapter": "csharp-roslyn-v1", "coverage": "csharp-source-declarations-v1", "tests": [], "transitions": []}
        extractors = [extracted, empty_typescript, empty_csharp]
        snapshot = {
            "base_commit_oid": "a" * 40,
            "target_mode": "working",
            "head_commit_oid": None,
            "tracked_diff_hash": content_hash("diff"),
            "untracked": [],
        }
        snapshot["target_snapshot_hash"] = content_hash(canonical_json(snapshot))
        metadata_packet = build_metadata_packet_multi(extractors)
        record = build_alignment_packet_multi(
            extractors, metadata_result(metadata_packet, verdict="REDESIGN")
        )["records"][0]
        evidence = {
            "kind": "accepted-contract",
            "ref": "CONTRACT.md",
            "content": "no retained contract",
            "content_hash": content_hash("no retained contract"),
            "meaning": "no alternative check is required",
        }
        host = {
            "task_id": "task-50",
            "risk_tags": [],
            "context_by_record": {},
            "retry_context_by_record": {},
            "resolution_attempts": [],
            "supersessions": [],
            "retention_by_record": {
                record["record_id"]: {
                    "evidence": [evidence],
                    "determination": {
                        "determination": "UNSUPPORTED",
                        "rationale": "bounded contract does not retain the test",
                        "evidence_refs": [
                            {"ref": evidence["ref"], "content_hash": evidence["content_hash"]}
                        ],
                    },
                    "temporal_observation": None,
                }
            },
        }
        calls: list[str] = []
        snapshot_values: list[dict] = []
        toolchain = {"identity": "toolchain-1"}

        def current_snapshot(*_: object, **__: object) -> dict:
            return snapshot_values.pop(0) if snapshot_values else snapshot

        def execute(phase: str, packet: dict, **_: object) -> dict:
            calls.append(phase)
            evidence = {
                "schema_version": "review-worker-evidence-v1",
                "phase": phase,
            }
            if phase == "metadata":
                return metadata_result(packet, verdict="REDESIGN"), evidence
            if phase == "alignment":
                return alignment_result(packet), evidence
            self.fail("Sol must not run for an unaudited, low-risk fixed REDESIGN")

        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            root = base / "repo"
            state = base / "state"
            root.mkdir()
            state.mkdir()
            host_path = base / "host.json"
            host_path.write_text(json.dumps({"stable": True}), encoding="utf-8")
            args = SimpleNamespace(
                root=root,
                changed_from="base",
                head=None,
                staged=False,
                state_dir=state,
                cli="codex.exe",
                host_evidence=host_path,
            )
            patches = (
                mock.patch.object(coordinator, "_resolve_repository", return_value=root.resolve()),
                mock.patch.object(coordinator, "_resolve_commit", return_value="a" * 40),
                mock.patch.object(coordinator, "snapshot_descriptor", side_effect=current_snapshot),
                mock.patch.object(coordinator, "extract_all_languages", return_value=extractors),
                mock.patch.object(coordinator, "validate_host_evidence", return_value=host),
                mock.patch.object(
                    coordinator,
                    "_toolchain_identity",
                    side_effect=lambda *_: copy.deepcopy(toolchain),
                ),
                mock.patch.object(coordinator, "_validate_worker_toolchain"),
                mock.patch.object(coordinator, "_execute_phase", side_effect=execute),
            )
            with (
                patches[0],
                patches[1],
                patches[2],
                patches[3],
                patches[4],
                patches[5],
                patches[6],
                patches[7],
            ):
                first = coordinator.run(args)
                self.assertEqual(first["gate"], "CHANGES_REQUIRED")
                self.assertEqual(first["reason_codes"], ["RESOLUTION_REQUIRED"])
                self.assertEqual(calls, ["metadata", "alignment"])

                generation_path = state / "generations" / "g000001" / "generation.json"
                generation_text = generation_path.read_text(encoding="utf-8")
                tampered_generation = json.loads(generation_text)
                tampered_generation["worker_evidence"] = []
                generation_path.write_text(
                    canonical_json(tampered_generation),
                    encoding="utf-8",
                )
                with self.assertRaises(coordinator.CoordinatorBlocked) as tampered:
                    coordinator.run(args)
                self.assertEqual(tampered.exception.reason_code, "STATE_INVALID")
                generation_path.write_text(generation_text, encoding="utf-8")

                resolution_dir = state / "generations" / "g000001" / "resolution"
                manifest = json.loads(
                    (resolution_dir / "initial-manifest.json").read_text(encoding="utf-8")
                )
                obligation = manifest["obligations"][0]
                self.assertEqual(
                    first["resolution_obligations"][0]["obligation_id"],
                    obligation["obligation_id"],
                )
                host["resolution_attempts"] = [
                    {
                        "attempt_id": "attempt-1",
                        "generation_id": "g000001",
                        "obligation_id": obligation["obligation_id"],
                        "action": "DROP",
                        "state": "RESOLVED",
                        "target": None,
                        "drop_reason": {
                            "determination": "NO_ALTERNATIVE_REQUIRED",
                            "rationale": "accepted contract requires no replacement",
                            "evidence_refs": obligation["origin"]["retention"]["determination"]["evidence_refs"],
                        },
                        "checks": [],
                        "reason": None,
                    }
                ]
                changed_snapshot = copy.deepcopy(snapshot)
                changed_snapshot["tracked_diff_hash"] = content_hash("changed diff")
                changed_snapshot["target_snapshot_hash"] = content_hash(
                    canonical_json(
                        {
                            key: value
                            for key, value in changed_snapshot.items()
                            if key != "target_snapshot_hash"
                        }
                    )
                )
                snapshot_values.extend([snapshot, snapshot, changed_snapshot])
                with self.assertRaises(coordinator.CoordinatorBlocked) as changed:
                    coordinator.run(args)
                self.assertEqual(changed.exception.reason_code, "SNAPSHOT_CHANGED")
                ledger_path = resolution_dir / "resolution-ledger.json"
                self.assertEqual(
                    json.loads(ledger_path.read_text(encoding="utf-8"))["entries"],
                    [],
                )

                resolved = coordinator.run(args)
                self.assertEqual(resolved["gate"], "PASS")

                toolchain["identity"] = "toolchain-2"
                reviewed_again = coordinator.run(args)
                self.assertEqual(reviewed_again["generation_id"], "g000002")
                self.assertEqual(reviewed_again["gate"], "CHANGES_REQUIRED")
                self.assertEqual(calls, ["metadata", "alignment", "metadata", "alignment"])

                task_manifest = state / "task-manifest.json"
                task_state = task_manifest.read_text(encoding="utf-8")
                task_manifest.unlink()
                with self.assertRaises(coordinator.CoordinatorBlocked) as missing_manifest:
                    coordinator.run(args)
                self.assertEqual(
                    missing_manifest.exception.reason_code,
                    "STATE_MANIFEST_MISSING",
                )
                task_manifest.write_text(task_state, encoding="utf-8")

                ledger = resolution_dir / "resolution-ledger.json"
                ledger.unlink()
                with self.assertRaises(coordinator.CoordinatorBlocked) as raised:
                    coordinator.run(args)

            self.assertEqual(raised.exception.reason_code, "HISTORICAL_STATE_INVALID")
            self.assertEqual(calls, ["metadata", "alignment", "metadata", "alignment"])

    # @test-value v2
    # kind = "invariant"
    # claim = "global deep packetは連続batchで全recordを一度ずつ審査し、generation loaderが保存済みlocal証拠からglobal結果を再構築検証する"
    # oracle = { type = "issue", ref = "natumekazuki/.codex#50" }
    # fault = "大packetを欠落・重複・hash改変した部分結果や途中成功だけでglobal PASSとして保存または再利用する"
    # observable = "batchの順序/size、global aggregate、deep-batch envelope再検証、破損と途中worker失敗のBLOCKED"
    # observation_boundary = "component-behavior"
    # scope = "test-value-deep-batch-execution"
    # lifecycle = "permanent"
    # risk_tags = ["security"]
    # @end-test-value
    def test_deep_batches_cover_global_packet_and_reject_partial_or_corrupt_proof(self):
        extractors = language_extractors()
        metadata_packet = build_metadata_packet_multi(extractors)
        frozen_metadata = metadata_result(metadata_packet)
        alignment_packet = build_alignment_packet_multi(extractors, frozen_metadata)
        aligned = alignment_result(alignment_packet)
        routing_inputs = coordinator._routing_inputs(alignment_packet, aligned)
        workflow_context = {
            "review_contract_version": "review-workflow-context-v1",
            "records": [
                {
                    "record_id": record["record_id"],
                    "metadata_hash": record["metadata_hash"],
                    "parent_risk_tags": ["security"],
                    "audit_percent": 10,
                }
                for record in alignment_packet["records"]
            ],
        }
        routing = build_routing_manifest(routing_inputs, workflow_context)
        global_packet = coordinator.build_deep_packet(
            alignment_packet,
            frozen_metadata,
            aligned,
            routing,
            workflow_context,
            {},
        )
        singleton_sizes = [
            len(
                review_worker.review_prompt(
                    coordinator.project_deep_batch(global_packet, [record])
                )
            )
            for record in global_packet["records"]
        ]
        budget = max(singleton_sizes)
        self.assertTrue(
            all(
                len(
                    review_worker.review_prompt(
                        coordinator.project_deep_batch(
                            global_packet,
                            global_packet["records"][index : index + 2],
                        )
                    )
                )
                > budget
                for index in range(len(global_packet["records"]) - 1)
            )
        )

        def result_for(packet: dict) -> dict:
            return {
                "review_contract_version": "deep-review-v2",
                "input_hash": packet["input_hash"],
                "reviews": [
                    {
                        "record_id": record["record_id"],
                        "metadata_hash": record["metadata_hash"],
                        "source_hash": record["source_hash"],
                        "verdict": "APPROVE",
                        "evidence": ["the supplied contract and assertion agree"],
                        "unverified": [],
                        "context_requirements": [],
                        "context_resolution": None,
                        "next_action": None,
                    }
                    for record in packet["records"]
                ],
            }

        executed_packets: list[dict] = []

        def execute(_phase: str, packet: dict, **_: object) -> tuple[dict, dict]:
            executed_packets.append(packet)
            return result_for(packet), {
                "schema_version": "review-worker-evidence-v1",
                "phase": "deep",
            }

        with (
            mock.patch.object(coordinator, "_execute_phase", side_effect=execute),
            mock.patch.object(coordinator, "_validate_worker_toolchain"),
        ):
            sol_result, proof = coordinator._execute_deep_round(
                global_packet,
                cli="C:/codex.exe",
                role_file=Path("C:/test_value_sol.toml"),
                toolchain_identity={"identity": "toolchain"},
                prompt_char_budget=budget,
            )

        self.assertEqual(len(executed_packets), 3)
        self.assertEqual(
            [record_id for batch in proof["batches"] for record_id in batch["record_ids"]],
            [record["record_id"] for record in global_packet["records"]],
        )
        self.assertTrue(
            all(len(review_worker.review_prompt(packet)) <= budget for packet in executed_packets)
        )
        aggregate_input = {
            "alignment_packet": alignment_packet,
            "metadata_result": frozen_metadata,
            "deep_packet": global_packet,
            "alignment_result": aligned,
            "workflow_routing_context": workflow_context,
            "routing_manifest": routing,
            "sol_result": sol_result,
            "retention_records": [
                {
                    "record_id": record["record_id"],
                    "retention_basis": "PRESENT",
                    "artifact_state": "TEST_PRESENT",
                }
                for record in alignment_packet["records"]
            ],
        }
        aggregate = aggregate_results(aggregate_input)
        self.assertNotEqual(aggregate["gate"], "BLOCKED")
        with mock.patch.object(coordinator, "_validate_worker_toolchain"):
            coordinator._validate_deep_batch_execution(
                proof,
                global_packet,
                sol_result,
                {"identity": "toolchain"},
            )
            corruptions = []
            missing = copy.deepcopy(proof)
            missing["batches"].pop()
            corruptions.append(missing)
            duplicate = copy.deepcopy(proof)
            duplicate["batches"][1]["record_ids"] = duplicate["batches"][0]["record_ids"]
            corruptions.append(duplicate)
            bad_hash = copy.deepcopy(proof)
            bad_hash["batches"][0]["packet_input_hash"] = content_hash("wrong packet")
            corruptions.append(bad_hash)
            for corrupted in corruptions:
                with self.subTest(corruption=corruptions.index(corrupted)):
                    with self.assertRaises(coordinator.CoordinatorBlocked):
                        coordinator._validate_deep_batch_execution(
                            corrupted,
                            global_packet,
                            sol_result,
                            {"identity": "toolchain"},
                        )

        with tempfile.TemporaryDirectory() as temp:
            state_dir = Path(temp)
            generation_dir = state_dir / "generations" / "g000001"
            generation_dir.mkdir(parents=True)
            snapshot = {
                "base_commit_oid": "a" * 40,
                "target_mode": "working",
                "head_commit_oid": None,
                "tracked_diff_hash": content_hash("diff"),
                "untracked": [],
            }
            snapshot["target_snapshot_hash"] = coordinator._canonical_hash(snapshot)
            aggregation = {
                "input": aggregate_input,
                "input_hash": coordinator.result_hash(aggregate_input),
                "result": aggregate,
                "result_hash": coordinator.result_hash(aggregate),
            }
            toolchain_identity = {"identity": "toolchain"}
            worker_evidence = [
                {"schema_version": "review-worker-evidence-v1", "phase": "metadata"},
                {"schema_version": "review-worker-evidence-v1", "phase": "alignment"},
                proof,
            ]
            generation = {
                "schema_version": coordinator.GENERATION_VERSION,
                "generation_id": "g000001",
                "target_snapshot": snapshot,
                "target_snapshot_hash": snapshot["target_snapshot_hash"],
                "selection_hash": content_hash("selection"),
                "host_evidence_hash": content_hash("host evidence"),
                "toolchain_identity": toolchain_identity,
                "toolchain_hash": coordinator._canonical_hash(toolchain_identity),
                "aggregation": aggregation,
                "worker_evidence": worker_evidence,
                "worker_evidence_hash": coordinator._canonical_hash(worker_evidence),
                "resolution_state": "generations/g000001/resolution",
            }
            descriptor = {
                "generation_id": generation["generation_id"],
                "generation_path": "generations/g000001/generation.json",
                "target_snapshot_hash": generation["target_snapshot_hash"],
                "selection_hash": generation["selection_hash"],
                "host_evidence_hash": generation["host_evidence_hash"],
                "toolchain_hash": generation["toolchain_hash"],
                "worker_evidence_hash": generation["worker_evidence_hash"],
            }
            generation_path = generation_dir / "generation.json"

            def write_generation(value: dict) -> dict:
                sealed = copy.deepcopy(value)
                sealed["worker_evidence_hash"] = coordinator._canonical_hash(
                    sealed["worker_evidence"]
                )
                current_descriptor = {
                    **descriptor,
                    "worker_evidence_hash": sealed["worker_evidence_hash"],
                }
                generation_path.write_text(
                    canonical_json(sealed),
                    encoding="utf-8",
                )
                return current_descriptor

            with mock.patch.object(coordinator, "_validate_worker_toolchain"):
                valid_descriptor = write_generation(generation)
                loaded = coordinator._load_generation(state_dir, valid_descriptor)
                self.assertEqual(loaded["aggregation"]["result"], aggregate)

                loader_corruptions = []
                invalid_result = copy.deepcopy(generation)
                invalid_result["worker_evidence"][2]["batches"][0]["result"][
                    "reviews"
                ].clear()
                invalid_result["worker_evidence"][2]["batches"][0][
                    "result_hash"
                ] = coordinator.result_hash(
                    invalid_result["worker_evidence"][2]["batches"][0]["result"]
                )
                loader_corruptions.append(invalid_result)
                invalid_result_hash = copy.deepcopy(generation)
                invalid_result_hash["worker_evidence"][2]["batches"][0][
                    "result_hash"
                ] = content_hash("wrong result")
                loader_corruptions.append(invalid_result_hash)
                invalid_evidence_hash = copy.deepcopy(generation)
                invalid_evidence_hash["worker_evidence"][2]["batches"][0][
                    "worker_evidence_hash"
                ] = content_hash("wrong worker evidence")
                loader_corruptions.append(invalid_evidence_hash)
                invalid_merged_hash = copy.deepcopy(generation)
                invalid_merged_hash["worker_evidence"][2][
                    "merged_result_hash"
                ] = content_hash("wrong merged result")
                loader_corruptions.append(invalid_merged_hash)

                for index, corrupted in enumerate(loader_corruptions):
                    with self.subTest(loader_corruption=index):
                        corrupted_descriptor = write_generation(corrupted)
                        with self.assertRaises(coordinator.CoordinatorBlocked):
                            coordinator._load_generation(
                                state_dir,
                                corrupted_descriptor,
                            )

        partial_calls = 0

        def fail_second(_phase: str, packet: dict, **_: object) -> tuple[dict, dict]:
            nonlocal partial_calls
            partial_calls += 1
            if partial_calls == 2:
                raise coordinator.CoordinatorBlocked("WORKER_BLOCKED", "second batch failed")
            return result_for(packet), {
                "schema_version": "review-worker-evidence-v1",
                "phase": "deep",
            }

        with (
            mock.patch.object(coordinator, "_execute_phase", side_effect=fail_second),
            mock.patch.object(coordinator, "_validate_worker_toolchain"),
        ):
            with self.assertRaises(coordinator.CoordinatorBlocked):
                coordinator._execute_deep_round(
                    global_packet,
                    cli="C:/codex.exe",
                    role_file=Path("C:/test_value_sol.toml"),
                    toolchain_identity={"identity": "toolchain"},
                    prompt_char_budget=budget,
                )
        self.assertEqual(partial_calls, 2)


if __name__ == "__main__":
    unittest.main()
