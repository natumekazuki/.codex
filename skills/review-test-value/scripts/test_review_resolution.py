from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from review_resolution import (  # noqa: E402
    MANIFEST_VERSION,
    ResolutionStateError,
    append_resolution_attempt,
    build_retention_evidence,
    canonical_json,
    content_hash,
    evaluate_obligation_gate,
    initialize_resolution_state,
    load_resolution_state,
    retention_record_projection,
)
from test_review_result_schema import aggregation_input  # noqa: E402
from validate_review_result import aggregate_results, result_hash  # noqa: E402


def digest(label: str) -> str:
    return content_hash(label)


def record_identity() -> dict:
    return {
        "record_id": "record-1",
        "metadata_hash": digest("metadata"),
        "source_hash": digest("source"),
        "snapshot_hash": digest("initial-snapshot"),
        "locator": {
            "path": "tests/test_service.py",
            "symbol": "test_service",
            "declaration_start_line": 20,
        },
    }


def metadata(*, boundary: str = "implementation", lifecycle: str = "permanent") -> dict:
    value = {
        "kind": "contract",
        "claim": "A retained check detects the declared service fault",
        "oracle": {"type": "issue", "ref": "natumekazuki/.codex#44"},
        "fault": "The service violates the accepted response contract",
        "observable": "The direct check result at the declared boundary",
        "observation_boundary": boundary,
        "scope": "review-resolution-fixture",
        "lifecycle": lifecycle,
    }
    if lifecycle == "characterization":
        value["review_when"] = "service contract is accepted"
    return value


def bounded_evidence(*, supported: bool) -> tuple[list[dict], dict]:
    text = "CONTRACT-1 requires this behavior" if supported else "No accepted behavior requires this check"
    item = {
        "kind": "accepted-contract",
        "ref": "CONTRACT-1",
        "content": text,
        "content_hash": content_hash(text),
        "meaning": "Whether the declared failure remains a retained contract obligation",
    }
    determination = {
        "determination": "SUPPORTED" if supported else "UNSUPPORTED",
        "rationale": "Host classified the bounded contract evidence",
        "evidence_refs": [{"ref": item["ref"], "content_hash": item["content_hash"]}],
    }
    return [item], determination


def source_observation(
    *, determination: str, snapshot_hash: str | None = None, content: str | None = None
) -> dict:
    record = record_identity()
    text = content if content is not None else (
        "source" if determination == "PRESENT" else f"git source transition: {determination}"
    )
    return {
        "determination": determination,
        "record_id": record["record_id"],
        "metadata_hash": record["metadata_hash"],
        "source_hash": record["source_hash"],
        "snapshot_hash": snapshot_hash or record["snapshot_hash"],
        "ref": "git:tests/test_service.py",
        "content": text,
        "content_hash": content_hash(text),
        "meaning": "Presence of the exact hash-bound origin record in the observed snapshot",
    }


def retention(*, action: str, supported: bool) -> dict:
    evidence, determination = bounded_evidence(supported=supported)
    return build_retention_evidence(
        identity=record_identity(),
        metadata=metadata(boundary="declaration" if action == "MOVE_TO_POLICY_CHECK" else "implementation"),
        disposition=action,
        evidence=evidence,
        determination=determination,
        source_observation=source_observation(determination="PRESENT"),
    )


def obligation(*, action: str, supported: bool, aggregate_input: dict) -> dict:
    packet_record = aggregate_input["alignment_packet"]["records"][0]
    identity = record_identity()
    identity.update(
        record_id=packet_record["record_id"],
        metadata_hash=packet_record["metadata_hash"],
        source_hash=packet_record["source_hash"],
    )
    evidence, determination = bounded_evidence(supported=supported)
    observed = source_observation(
        determination="PRESENT", content=packet_record["source_text"]
    )
    observed.update(
        record_id=identity["record_id"],
        metadata_hash=identity["metadata_hash"],
        source_hash=identity["source_hash"],
    )
    detailed_retention = build_retention_evidence(
        identity=identity,
        metadata=packet_record["metadata"],
        disposition=action,
        evidence=evidence,
        determination=determination,
        source_observation=observed,
    )
    origin = {
        "record": identity,
        "retention": detailed_retention,
        "frozen_result": aggregate_results(aggregate_input)["records"][0],
    }
    return {"obligation_id": "obligation-1", "action": action, "origin": origin}


def manifest(*, aggregate_input: dict, obligations: list[dict]) -> dict:
    aggregate_result = aggregate_results(aggregate_input)
    input_hash = result_hash(aggregate_input)
    aggregate_hash = result_hash(aggregate_result)
    return {
        "schema_version": MANIFEST_VERSION,
        "task_id": "task-42-45",
        "initial_snapshot_hash": digest("initial-snapshot"),
        "selection_hash": digest("selection"),
        "artifact_hashes": [input_hash, aggregate_hash],
        "aggregation": {
            "input": aggregate_input,
            "input_hash": input_hash,
            "result": aggregate_result,
            "result_hash": aggregate_hash,
        },
        "obligations": obligations,
    }


def review_input(action: str, *, metadata_verdict: str = "VALID", kind: str = "contract", sol_verdict=None) -> dict:
    move = action == "MOVE_TO_POLICY_CHECK"
    return aggregation_input(
        metadata_verdict=metadata_verdict,
        kind=kind,
        sol_verdict=sol_verdict,
        retention_basis="PRESENT" if move else "ABSENT",
        artifact_state="TEST_PRESENT",
        actual_boundary="declaration" if move else "implementation",
        metadata_boundary="declaration" if move else "implementation",
    )


def removal(origin: dict, current_snapshot_hash: str) -> dict:
    text = "git diff proves the hash-bound origin declaration was removed"
    return {
        "origin": origin,
        "determination": "REMOVED",
        "current_snapshot_hash": current_snapshot_hash,
        "ref": "git-diff:base..current:tests/test_service.py",
        "content": text,
        "content_hash": content_hash(text),
        "meaning": "The original record bytes are absent from the current snapshot",
    }


def target(current_snapshot_hash: str) -> dict:
    text = "policy check that detects the same declared fault"
    return {
        "snapshot_hash": current_snapshot_hash,
        "ref": "policy/checks/service-contract.json",
        "content": text,
        "content_hash": content_hash(text),
        "meaning": "Canonical target that detects the original fault",
    }


def receipt(current_snapshot_hash: str, target_value: dict, *, exit_code: int = 0) -> dict:
    return {
        "check_id": "policy-check",
        "snapshot_hash": current_snapshot_hash,
        "target_ref": target_value["ref"],
        "target_hash": target_value["content_hash"],
        "exit_code": exit_code,
        "output_hash": digest("check-output"),
    }


def attempt(
    obligation_value: dict,
    *,
    state: str,
    action: str,
    resolution: dict,
    attempt_id: str = "attempt-1",
) -> dict:
    return {
        "attempt_id": attempt_id,
        "obligation_id": obligation_value["obligation_id"],
        "origin_hash": content_hash(canonical_json(obligation_value["origin"])),
        "action": action,
        "state": state,
        "resolution": resolution,
    }


class ReviewResolutionTests(unittest.TestCase):
    # @test-value v2
    # kind = "invariant"
    # claim = "retentionのPRESENT/ABSENTとartifact stateは同一recordのhash付き根拠、host判定、source observation、検証済み期限条件からだけ導出される"
    # oracle = { type = "issue", ref = "natumekazuki/.codex#44" }
    # fault = "根拠のないcaller enum、別recordの根拠、またはfile存在だけで保持判定をPASS可能な形へする"
    # observable = "retention projectionまたはUNRESOLVED/identity mismatch"
    # observation_boundary = "component-behavior"
    # scope = "review-resolution-retention"
    # lifecycle = "permanent"
    # @end-test-value
    def test_retention_is_derived_from_bound_evidence_and_source_lifecycle(self):
        value = retention(action="DROP", supported=False)
        self.assertEqual(
            retention_record_projection(value),
            {"record_id": "record-1", "retention_basis": "ABSENT", "artifact_state": "TEST_PRESENT"},
        )

        evidence, unmatched = bounded_evidence(supported=False)
        unmatched["evidence_refs"][0]["content_hash"] = digest("other")
        unresolved = build_retention_evidence(
            identity=record_identity(),
            metadata=metadata(),
            disposition="DROP",
            evidence=evidence,
            determination=unmatched,
            source_observation=source_observation(determination="PRESENT"),
        )
        self.assertEqual(retention_record_projection(unresolved)["retention_basis"], "UNRESOLVED")

        evidence, determination = bounded_evidence(supported=True)
        wrong_record = source_observation(determination="PRESENT")
        wrong_record["record_id"] = "record-2"
        with self.assertRaisesRegex(ResolutionStateError, "record_id does not match"):
            build_retention_evidence(
                identity=record_identity(),
                metadata=metadata(),
                disposition="KEEP_PERMANENT",
                evidence=evidence,
                determination=determination,
                source_observation=wrong_record,
            )

        temporary = build_retention_evidence(
            identity=record_identity(),
            metadata=metadata(lifecycle="characterization"),
            disposition="KEEP_TEMPORARY",
            evidence=evidence,
            determination=determination,
            source_observation=source_observation(determination="PRESENT"),
        )
        with self.assertRaisesRegex(ResolutionStateError, "artifact state is unresolved"):
            retention_record_projection(temporary)

    # @test-value v2
    # kind = "regression"
    # claim = "resume時にmanifestまたはledgerを失ったtask stateは再初期化されずBLOCKEDになる"
    # oracle = { type = "issue", ref = "natumekazuki/.codex#44" }
    # fault = "空selectionで失われたledgerを暗黙に作り直し、以前のresolution義務を消す"
    # observable = "RESOLUTION_STATE_MISSING reasonを持つaggregate BLOCKEDと既存manifestの保持"
    # observation_boundary = "component-behavior"
    # scope = "review-resolution-state"
    # lifecycle = "permanent"
    # @end-test-value
    def test_missing_ledger_blocks_resume_without_reinitializing_manifest(self):
        with tempfile.TemporaryDirectory() as temp:
            state_dir = Path(temp)
            aggregate_input = review_input("DROP")
            initial_obligation = obligation(
                action="DROP", supported=False, aggregate_input=aggregate_input
            )
            initial = manifest(
                aggregate_input=aggregate_input, obligations=[initial_obligation]
            )
            initialize_resolution_state(state_dir, initial)
            (state_dir / "resolution-ledger.json").unlink()

            result = evaluate_obligation_gate(
                state_dir,
                expected_task_id="task-42-45",
            )

            self.assertEqual(result["obligation_gate"], "BLOCKED")
            self.assertEqual(result["reason_codes"], ["RESOLUTION_STATE_MISSING"])
            self.assertTrue((state_dir / "initial-manifest.json").is_file())
            self.assertFalse((state_dir / "resolution-ledger.json").exists())
            with self.assertRaisesRegex(ResolutionStateError, "resume it explicitly"):
                initialize_resolution_state(state_dir, initial)

        with tempfile.TemporaryDirectory() as temp:
            state_dir = Path(temp)
            aggregate_input = aggregation_input()
            initial = manifest(aggregate_input=aggregate_input, obligations=[])
            initialize_resolution_state(state_dir, initial)
            changed = {**initial, "selection_hash": digest("different-selection")}
            (state_dir / "initial-manifest.json").write_text(
                canonical_json(changed) + "\n", encoding="utf-8"
            )
            result = evaluate_obligation_gate(
                state_dir,
                expected_task_id="task-42-45",
            )
            self.assertEqual(result["obligation_gate"], "BLOCKED")
            self.assertEqual(result["reason_codes"], ["MANIFEST_HASH_MISMATCH"])

        with tempfile.TemporaryDirectory() as temp:
            state_dir = Path(temp)
            aggregate_input = aggregation_input()
            initial = manifest(aggregate_input=aggregate_input, obligations=[])
            initialize_resolution_state(state_dir, initial)
            malformed = {**initial, "artifact_hashes": [{}]}
            (state_dir / "initial-manifest.json").write_text(
                canonical_json(malformed) + "\n", encoding="utf-8"
            )
            result = evaluate_obligation_gate(
                state_dir,
                expected_task_id="task-42-45",
            )
            self.assertEqual(result["obligation_gate"], "BLOCKED")
            self.assertEqual(result["reason_codes"], ["MANIFEST_INVALID"])

    # @test-value v2
    # kind = "regression"
    # claim = "MOVE resolutionは元recordのhash付き除去、同一snapshotの移行先content、同じtargetに成功したdirect check receiptが揃う時だけRESOLVEDになる"
    # oracle = { type = "issue", ref = "natumekazuki/.codex#44" }
    # fault = "同名test、移行先sourceだけ、失敗check、別snapshotのreceiptのいずれかでMOVE義務を解消する"
    # observable = "ledger appendの成功またはDIRECT_CHECK_MISSING"
    # observation_boundary = "component-behavior"
    # scope = "review-resolution-move"
    # lifecycle = "permanent"
    # @end-test-value
    def test_move_requires_removal_target_and_matching_successful_check(self):
        current = digest("current-snapshot")
        aggregate_input = review_input("MOVE_TO_POLICY_CHECK")
        obligation_value = obligation(
            action="MOVE_TO_POLICY_CHECK", supported=True, aggregate_input=aggregate_input
        )
        target_value = target(current)
        payload = {
            "current_snapshot_hash": current,
            "removal": removal(obligation_value["origin"]["record"], current),
            "target": target_value,
            "drop_reason": None,
            "checks": [receipt(current, target_value)],
            "reason": None,
        }
        with tempfile.TemporaryDirectory() as temp:
            state_dir = Path(temp)
            initialize_resolution_state(
                state_dir,
                manifest(aggregate_input=aggregate_input, obligations=[obligation_value]),
            )
            append_resolution_attempt(
                state_dir,
                expected_task_id="task-42-45",
                entry=attempt(
                    obligation_value,
                    state="RESOLVED",
                    action="MOVE_TO_POLICY_CHECK",
                    resolution=payload,
                ),
            )
            self.assertEqual(
                evaluate_obligation_gate(state_dir, expected_task_id="task-42-45")["obligation_gate"],
                "PASS",
            )
            _, ledger = load_resolution_state(state_dir, expected_task_id="task-42-45")
            self.assertEqual(ledger["entries"][0]["state"], "RESOLVED")
            self.assertEqual(list(state_dir.glob(".*.tmp")), [])

        failed = {**payload, "checks": [receipt(current, target_value, exit_code=1)]}
        with tempfile.TemporaryDirectory() as temp:
            state_dir = Path(temp)
            initialize_resolution_state(
                state_dir,
                manifest(aggregate_input=aggregate_input, obligations=[obligation_value]),
            )
            with self.assertRaisesRegex(ResolutionStateError, "successful check"):
                append_resolution_attempt(
                    state_dir,
                    expected_task_id="task-42-45",
                    entry=attempt(
                        obligation_value,
                        state="RESOLVED",
                        action="MOVE_TO_POLICY_CHECK",
                        resolution=failed,
                    ),
                )

    # @test-value v2
    # kind = "security"
    # claim = "security recordのrequired Solが未完了ならcanonical aggregateはresolution義務を作れずBLOCKEDを維持する"
    # oracle = { type = "issue", ref = "natumekazuki/.codex#44" }
    # fault = "test削除を理由に未実行Solまたはsecurity欠陥を消し、aggregateをPASSにする"
    # observable = "初期manifest作成の拒否とstate file未作成"
    # observation_boundary = "component-behavior"
    # scope = "review-resolution-blocking-origin"
    # lifecycle = "permanent"
    # risk_tags = ["security"]
    # @end-test-value
    def test_drop_cannot_create_an_obligation_from_security_review_with_missing_sol(self):
        aggregate_input = review_input("DROP", kind="security", sol_verdict=None)
        incomplete = obligation(
            action="DROP", supported=False, aggregate_input=aggregate_input
        )
        with tempfile.TemporaryDirectory() as temp:
            state_dir = Path(temp)
            invalid_manifest = manifest(
                aggregate_input=aggregate_input, obligations=[incomplete]
            )
            with self.assertRaisesRegex(
                ResolutionStateError, "only complete canonical DROP/MOVE outcomes"
            ):
                initialize_resolution_state(state_dir, invalid_manifest)
            self.assertFalse((state_dir / "initial-manifest.json").exists())
            self.assertFalse((state_dir / "resolution-ledger.json").exists())

    # @test-value v2
    # kind = "invariant"
    # claim = "canonical初期aggregateにDROP/MOVE義務がなければobligation gateはPASS、未解決義務はCHANGES_REQUIRED、正規resolution後はPASSになる"
    # oracle = { type = "issue", ref = "natumekazuki/.codex#44" }
    # fault = "未解決DROP義務を集計から落とす、または元REDESIGNを書き換えなければresolution後も閉じられない"
    # observable = "obligation gateのPASS、CHANGES_REQUIRED、PASS遷移とfrozen REDESIGN"
    # observation_boundary = "component-behavior"
    # scope = "review-resolution-aggregate"
    # lifecycle = "permanent"
    # @end-test-value
    def test_obligation_gate_tracks_every_canonical_drop_move_resolution(self):
        with tempfile.TemporaryDirectory() as temp:
            empty_dir = Path(temp) / "empty"
            empty_dir.mkdir()
            no_obligation_input = aggregation_input()
            initialize_resolution_state(
                empty_dir,
                manifest(aggregate_input=no_obligation_input, obligations=[]),
            )
            self.assertEqual(
                evaluate_obligation_gate(empty_dir, expected_task_id="task-42-45")["obligation_gate"],
                "PASS",
            )

            pending_dir = Path(temp) / "pending"
            pending_dir.mkdir()
            pending_input = review_input("DROP", metadata_verdict="REDESIGN")
            pending = obligation(
                action="DROP", supported=False, aggregate_input=pending_input
            )
            initialize_resolution_state(
                pending_dir,
                manifest(aggregate_input=pending_input, obligations=[pending]),
            )
            self.assertEqual(
                evaluate_obligation_gate(pending_dir, expected_task_id="task-42-45")["obligation_gate"],
                "CHANGES_REQUIRED",
            )

            current = digest("current-snapshot")
            evidence_refs = pending["origin"]["retention"]["determination"]["evidence_refs"]
            resolved = {
                "current_snapshot_hash": current,
                "removal": removal(pending["origin"]["record"], current),
                "target": None,
                "drop_reason": {
                    "determination": "NO_ALTERNATIVE_REQUIRED",
                    "rationale": "The bounded accepted-contract evidence requires no replacement",
                    "evidence_refs": evidence_refs,
                },
                "checks": [],
                "reason": None,
            }
            unresolved = {
                "current_snapshot_hash": current,
                "removal": None,
                "target": None,
                "drop_reason": None,
                "checks": [],
                "reason": "origin removal has not yet been verified",
            }
            append_resolution_attempt(
                pending_dir,
                expected_task_id="task-42-45",
                entry=attempt(
                    pending,
                    state="UNRESOLVED",
                    action="DROP",
                    resolution=unresolved,
                ),
            )
            append_resolution_attempt(
                pending_dir,
                expected_task_id="task-42-45",
                entry=attempt(
                    pending,
                    state="RESOLVED",
                    action="DROP",
                    resolution=resolved,
                    attempt_id="attempt-2",
                ),
            )
            self.assertEqual(
                evaluate_obligation_gate(pending_dir, expected_task_id="task-42-45")["obligation_gate"],
                "PASS",
            )
            loaded, ledger = load_resolution_state(pending_dir, expected_task_id="task-42-45")
            self.assertEqual(loaded["obligations"][0]["origin"]["frozen_result"]["status"], "REDESIGN")
            self.assertEqual(
                [entry["state"] for entry in ledger["entries"]],
                ["UNRESOLVED", "RESOLVED"],
            )


if __name__ == "__main__":
    unittest.main()
