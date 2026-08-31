import sys
import copy
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from build_review_packets import canonical_json, sha256_text  # noqa: E402
from review_routing import build_routing_manifest  # noqa: E402
from validate_review_result import (  # noqa: E402
    ResultValidationError,
    aggregate_results,
    validate_phase_result,
)


def alignment_record():
    return {
        "record_id": "sha256:" + "1" * 64,
        "metadata_hash": "sha256:" + "2" * 64,
        "source_hash": "sha256:" + "3" * 64,
    }


def alignment_result(verdict="ALIGNED"):
    record = alignment_record()
    return {
        "review_contract_version": "alignment-review-v1",
        "reviews": [
            {
                **record,
                "verdict": verdict,
                "declared_boundary": "component-behavior",
                "actual_boundary": "component-behavior",
                "actual_observables": ["final record gate"],
                "overclaim": False,
                "evidence": ["assertionはfinal record gateを読む"],
                "unverified": [],
                "disposition_candidate": "KEEP_PERMANENT",
                "context_requirements": [],
                "next_action": None,
            }
        ],
    }


def aggregation_input(
    *,
    metadata_verdict="VALID",
    alignment_verdict="ALIGNED",
    kind="contract",
    lifecycle="permanent",
    sol_verdict=None,
    retention_basis="PRESENT",
    artifact_state="PERMANENT_TEST",
    parent_risk_tags=None,
):
    metadata = {
        "kind": kind,
        "claim": "final resultは固定済みreview identityから決まる",
        "oracle": {"type": "adr", "ref": "ADR-0022"},
        "failure_mode": "required Solを省略してPASSにする",
        "scope": "review-result-aggregation",
        "lifecycle": lifecycle,
    }
    source_text = "def test_final_result(self):\n    self.assertEqual(result['gate'], 'PASS')\n"
    identity = {
        "record_id": "sha256:" + "1" * 64,
        "metadata_hash": sha256_text(canonical_json(metadata)),
        "source_hash": sha256_text(source_text),
    }
    metadata_review = {
        "record_id": identity["record_id"],
        "verdict": metadata_verdict,
        "evidence": ["metadata verdict evidence"],
        "unverified": [],
        "next_action": None,
    }
    record = {
        **identity,
        "metadata": metadata,
        "metadata_review": metadata_review,
        "source_text": source_text,
    }
    alignment_review = alignment_result(alignment_verdict)["reviews"][0]
    alignment_review.update(
        metadata_hash=identity["metadata_hash"],
        source_hash=identity["source_hash"],
    )
    routing_records = [
        {
            **identity,
            "contract_version": "deep-review-v1",
            "metadata": metadata,
            "metadata_verdict": metadata_verdict,
            "alignment_verdict": alignment_verdict,
            "context_requirements": alignment_review["context_requirements"],
        }
    ]
    workflow_context = {
        "review_contract_version": "review-workflow-context-v1",
        "records": [
            {
                "record_id": identity["record_id"],
                "metadata_hash": identity["metadata_hash"],
                "parent_risk_tags": parent_risk_tags or [],
                "audit_percent": 0,
            }
        ],
    }
    manifest = build_routing_manifest(routing_records, workflow_context)
    sol_result = None
    if sol_verdict is not None:
        needs_context = sol_verdict == "NEEDS_CONTEXT"
        sol_result = {
            "review_contract_version": "deep-review-v1",
            "reviews": [
                {
                    **identity,
                    "verdict": sol_verdict,
                    "evidence": [] if needs_context else ["deep review evidence"],
                    "unverified": [],
                    "context_requirements": ["追加context"] if needs_context else [],
                    "next_action": "追加contextを確認する" if needs_context else None,
                }
            ],
        }
    return {
        "alignment_packet": {
            "review_contract_version": "alignment-review-v1",
            "records": [record],
        },
        "alignment_result": {
            "review_contract_version": "alignment-review-v1",
            "reviews": [alignment_review],
        },
        "workflow_routing_context": workflow_context,
        "routing_manifest": manifest,
        "sol_result": sol_result,
        "retention_records": [
            {
                "record_id": identity["record_id"],
                "retention_basis": retention_basis,
                "artifact_state": artifact_state,
            }
        ],
    }


class ReviewResultSchemaTests(unittest.TestCase):
    # @test-value v1
    # kind = "security"
    # claim = "final aggregatorはmetadataとsourceのhashおよび検証済みrouting manifestからSol requiredを導出しcallerのbooleanを受理しない"
    # oracle = { type = "adr", ref = "ADR-0022" }
    # failure_mode = "security metadataをhash不一致のcontractへ変えるかsol_required=falseを直接入力してrequired Solを省略しPASSにする"
    # scope = "review-final-identity-binding"
    # lifecycle = "permanent"
    # @end-test-value
    def test_aggregate_rejects_identity_tamper_and_caller_routing_boolean(self):
        tampered = aggregation_input(kind="security")
        tampered["alignment_packet"]["records"][0]["metadata"]["kind"] = "contract"
        with self.assertRaisesRegex(ResultValidationError, "metadata_hash"):
            aggregate_results(tampered)
        source_tampered = aggregation_input(kind="security")
        source_tampered["alignment_packet"]["records"][0]["source_text"] += "# changed\n"
        with self.assertRaisesRegex(ResultValidationError, "source_hash"):
            aggregate_results(source_tampered)

        scalar_input = {
            "metadata_verdict": "VALID",
            "alignment_verdict": "ALIGNED",
            "sol_required": False,
            "sol_verdict": None,
            "actual_boundary": "component-behavior",
            "metadata": {"kind": "security", "lifecycle": "permanent"},
            "retention_basis": "PRESENT",
            "artifact_state": "PERMANENT_TEST",
        }
        with self.assertRaisesRegex(ResultValidationError, "unexpected keys"):
            aggregate_results(scalar_input)

    # @test-value v1
    # kind = "contract"
    # claim = "NEEDS_CONTEXT resultはmetadata phaseで未確認事項と次のactionを、deep phaseで必要contextを具体的に示す"
    # oracle = { type = "adr", ref = "ADR-0022" }
    # failure_mode = "追加sourceを特定できないNEEDS_CONTEXTを受理して同じ入力の再実行しか選べないBLOCKED状態にする"
    # scope = "review-result-actionable-context"
    # lifecycle = "permanent"
    # @end-test-value
    def test_needs_context_results_require_actionable_context(self):
        record = alignment_record()
        metadata = {
            "review_contract_version": "metadata-review-v1",
            "reviews": [
                {
                    "record_id": record["record_id"],
                    "verdict": "NEEDS_CONTEXT",
                    "evidence": [],
                    "unverified": [],
                    "next_action": None,
                }
            ],
        }
        deep = {
            "review_contract_version": "deep-review-v1",
            "reviews": [
                {
                    **record,
                    "verdict": "NEEDS_CONTEXT",
                    "evidence": [],
                    "unverified": [],
                    "context_requirements": [],
                    "next_action": "追加sourceを確認する",
                }
            ],
        }

        with self.assertRaises(ResultValidationError):
            validate_phase_result("metadata", metadata, [record])
        with self.assertRaises(ResultValidationError):
            validate_phase_result("deep", deep, [record])

    # @test-value v1
    # kind = "contract"
    # claim = "alignment resultのALIGNEDとMISMATCHはsource根拠を一件以上持ちRECHECKは必要contextを一件以上持つ"
    # oracle = { type = "adr", ref = "ADR-0022" }
    # failure_mode = "根拠のないALIGNEDまたはMISMATCH、必要contextを示さないRECHECKを有効なPhase 2結果として受理する"
    # scope = "alignment-review-result-schema"
    # lifecycle = "permanent"
    # @end-test-value
    def test_alignment_result_requires_verdict_specific_evidence(self):
        for verdict, field in (
            ("ALIGNED", "evidence"),
            ("MISMATCH", "evidence"),
            ("RECHECK", "context_requirements"),
        ):
            with self.subTest(verdict=verdict):
                result = alignment_result(verdict)
                result["reviews"][0][field] = []
                with self.assertRaises(ResultValidationError):
                    validate_phase_result("alignment", result, [alignment_record()])

    # @test-value v1
    # kind = "security"
    # claim = "phase resultはpacketと同じrecord順序、metadata hash、source hashだけを受理する"
    # oracle = { type = "adr", ref = "ADR-0022" }
    # failure_mode = "別recordまたは改変sourceのAI結果を現在のrecordへ対応付けてfinal判定へ混入する"
    # scope = "review-result-identity-validation"
    # lifecycle = "permanent"
    # @end-test-value
    def test_alignment_result_rejects_record_and_hash_changes(self):
        mutations = (
            ("record_id", "sha256:" + "9" * 64),
            ("metadata_hash", "sha256:" + "8" * 64),
            ("source_hash", "sha256:" + "7" * 64),
        )
        for field, value in mutations:
            with self.subTest(field=field):
                result = alignment_result()
                result["reviews"][0][field] = value
                with self.assertRaises(ResultValidationError):
                    validate_phase_result("alignment", result, [alignment_record()])

    # @test-value v1
    # kind = "invariant"
    # claim = "final statusは未完了のrequired SolをNEEDS_CONTEXTにし固定済みREDESIGNをSol APPROVEで救済しない"
    # oracle = { type = "adr", ref = "ADR-0022" }
    # failure_mode = "required agentが未実行でもACCEPTにするかPhase 1 REDESIGNをSol APPROVEでACCEPTへ変更する"
    # scope = "review-status-aggregation"
    # lifecycle = "permanent"
    # @end-test-value
    def test_aggregate_results_fails_closed_and_preserves_redesign(self):
        base = aggregation_input(kind="security")
        self.assertEqual(
            aggregate_results(base)["records"][0],
            {
                "record_id": "sha256:" + "1" * 64,
                "status": "NEEDS_CONTEXT",
                "disposition": None,
                "gate": "BLOCKED",
            },
        )
        redesigned = aggregation_input(
            metadata_verdict="REDESIGN",
            kind="security",
            sol_verdict="APPROVE",
        )
        result = aggregate_results(redesigned)
        self.assertEqual(result["records"][0]["status"], "REDESIGN")
        self.assertEqual(result["records"][0]["gate"], "CHANGES_REQUIRED")
        unresolved_sol = aggregation_input(kind="security", sol_verdict="NEEDS_CONTEXT")
        self.assertEqual(
            aggregate_results(unresolved_sol)["records"][0],
            {
                "record_id": "sha256:" + "1" * 64,
                "status": "NEEDS_CONTEXT",
                "disposition": None,
                "gate": "BLOCKED",
            },
        )

    # @test-value v1
    # kind = "contract"
    # claim = "保持根拠またはv1 ephemeral削除条件を確定できないACCEPT候補はdisposition null、NEEDS_CONTEXT、BLOCKEDになる"
    # oracle = { type = "adr", ref = "ADR-0022" }
    # failure_mode = "保持先を確定できないtest artifactをPASSとしてBootstrap changeの完了条件に通す"
    # scope = "review-disposition-gate"
    # lifecycle = "permanent"
    # @end-test-value
    def test_aggregate_results_blocks_unresolved_disposition(self):
        record = aggregation_input(
            lifecycle="ephemeral",
            retention_basis="UNRESOLVED",
            artifact_state="TEMPORARY_TEST",
        )

        self.assertEqual(
            aggregate_results(record)["records"][0],
            {
                "record_id": "sha256:" + "1" * 64,
                "status": "NEEDS_CONTEXT",
                "disposition": None,
                "gate": "BLOCKED",
            },
        )

    # @test-value v1
    # kind = "security"
    # claim = "final aggregatorはmanifestとは独立した親workflow risk contextとaudit率へrouting結果を固定し改変を拒否する"
    # oracle = { type = "adr", ref = "ADR-0022" }
    # failure_mode = "親workflowのauthorization tagまたはaudit率をmanifest生成時だけ変えてrequired Solを迂回しPASSにする"
    # scope = "review-final-parent-risk-binding"
    # lifecycle = "permanent"
    # @end-test-value
    def test_aggregate_results_rejects_manifest_built_without_fixed_parent_risk(self):
        value = aggregation_input(parent_risk_tags=["authorization"], sol_verdict="APPROVE")
        downgraded_context = copy.deepcopy(value["workflow_routing_context"])
        downgraded_context["records"][0]["parent_risk_tags"] = []
        record = value["alignment_packet"]["records"][0]
        review = value["alignment_result"]["reviews"][0]
        routing_record = {
            "record_id": record["record_id"],
            "metadata_hash": record["metadata_hash"],
            "source_hash": record["source_hash"],
            "contract_version": "deep-review-v1",
            "metadata": record["metadata"],
            "metadata_verdict": record["metadata_review"]["verdict"],
            "alignment_verdict": review["verdict"],
            "context_requirements": review["context_requirements"],
        }
        value["routing_manifest"] = build_routing_manifest(
            [routing_record], downgraded_context
        )

        with self.assertRaisesRegex(ResultValidationError, "workflow context hash"):
            aggregate_results(value)
        value = aggregation_input(parent_risk_tags=["authorization"], sol_verdict="APPROVE")
        changed_audit = copy.deepcopy(value["workflow_routing_context"])
        changed_audit["records"][0]["audit_percent"] = 100
        record = value["alignment_packet"]["records"][0]
        review = value["alignment_result"]["reviews"][0]
        value["routing_manifest"] = build_routing_manifest(
            [
                {
                    "record_id": record["record_id"],
                    "metadata_hash": record["metadata_hash"],
                    "source_hash": record["source_hash"],
                    "contract_version": "deep-review-v1",
                    "metadata": record["metadata"],
                    "metadata_verdict": record["metadata_review"]["verdict"],
                    "alignment_verdict": review["verdict"],
                    "context_requirements": review["context_requirements"],
                }
            ],
            changed_audit,
        )
        with self.assertRaisesRegex(ResultValidationError, "workflow context hash"):
            aggregate_results(value)

    # @test-value v1
    # kind = "contract"
    # claim = "final aggregatorは複数recordの正規alignment、routing、Sol artifactを分割せず同順で一括集約する"
    # oracle = { type = "adr", ref = "ADR-0022" }
    # failure_mode = "複数testの正規artifactを拒否してrecordごとの手作業JSON分割を必要にする"
    # scope = "review-final-record-set-aggregation"
    # lifecycle = "permanent"
    # @end-test-value
    def test_aggregate_results_accepts_complete_multi_record_artifacts(self):
        first = aggregation_input(kind="security", sol_verdict="APPROVE")
        second = aggregation_input(kind="security", sol_verdict="APPROVE")
        second_record = copy.deepcopy(second["alignment_packet"]["records"][0])
        second_record["record_id"] = "sha256:" + "4" * 64
        second_record["metadata_review"]["record_id"] = second_record["record_id"]
        second_review = copy.deepcopy(second["alignment_result"]["reviews"][0])
        second_review["record_id"] = second_record["record_id"]
        first["alignment_packet"]["records"].append(second_record)
        first["alignment_result"]["reviews"].append(second_review)
        second_context = copy.deepcopy(second["workflow_routing_context"]["records"][0])
        second_context["record_id"] = second_record["record_id"]
        first["workflow_routing_context"]["records"].append(second_context)
        routing_records = []
        for record, review in zip(
            first["alignment_packet"]["records"], first["alignment_result"]["reviews"]
        ):
            routing_records.append(
                {
                    "record_id": record["record_id"],
                    "metadata_hash": record["metadata_hash"],
                    "source_hash": record["source_hash"],
                    "contract_version": "deep-review-v1",
                    "metadata": record["metadata"],
                    "metadata_verdict": record["metadata_review"]["verdict"],
                    "alignment_verdict": review["verdict"],
                    "context_requirements": review["context_requirements"],
                }
            )
        first["routing_manifest"] = build_routing_manifest(
            routing_records, first["workflow_routing_context"]
        )
        second_sol_review = copy.deepcopy(second["sol_result"]["reviews"][0])
        second_sol_review["record_id"] = second_record["record_id"]
        first["sol_result"]["reviews"].append(second_sol_review)
        first["retention_records"].append(
            {
                "record_id": second_record["record_id"],
                "retention_basis": "PRESENT",
                "artifact_state": "PERMANENT_TEST",
            }
        )

        result = aggregate_results(first)

        self.assertEqual(
            [record["record_id"] for record in result["records"]],
            ["sha256:" + "1" * 64, "sha256:" + "4" * 64],
        )
        self.assertEqual(result["gate"], "PASS")


if __name__ == "__main__":
    unittest.main()
