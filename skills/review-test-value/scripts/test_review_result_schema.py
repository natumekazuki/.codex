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
    result_hash,
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
    source_path="tests/test_final_result.py",
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
    source = {
        "path": source_path,
        "symbol": "FinalResultTests.test_final_result",
        "metadata_start_line": 1,
        "metadata_end_line": 8,
        "declaration_start_line": 9,
        "declaration_end_line": 10,
    }
    metadata_hash = sha256_text(canonical_json(metadata))
    record_id = sha256_text(
        canonical_json(
            {
                "locator": {"path": source_path, "declaration_start_line": 9},
                "metadata_hash": metadata_hash,
            }
        )
    )
    identity = {
        "record_id": record_id,
        "metadata_hash": metadata_hash,
        "source_hash": sha256_text(source_text),
    }
    metadata_review = {
        "record_id": identity["record_id"],
        "metadata_hash": identity["metadata_hash"],
        "verdict": metadata_verdict,
        "evidence": [] if metadata_verdict == "NEEDS_CONTEXT" else [
            {
                "fields": ["claim", "failure_mode", "scope"],
                "finding": "COHERENT_BOUNDARY",
            }
        ],
        "unverified": ["oracle.ref"] if metadata_verdict == "NEEDS_CONTEXT" else [],
        "next_action": (
            "oracle.refを確認する" if metadata_verdict == "NEEDS_CONTEXT" else None
        ),
    }
    metadata_result = {
        "review_contract_version": "metadata-review-v1",
        "reviews": [metadata_review],
    }
    record = {
        **identity,
        "metadata_format_version": 1,
        "metadata": metadata,
        "metadata_review": copy.deepcopy(metadata_review),
        "source": source,
        "source_text": source_text,
        "adapter": "python-source-v1",
        "coverage": "python-source-declarations-v1",
    }
    alignment_review = alignment_result(alignment_verdict)["reviews"][0]
    alignment_review.update(
        record_id=identity["record_id"],
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
    alignment_packet = {
        "review_contract_version": "alignment-review-v1",
        "metadata_result_hash": result_hash(metadata_result),
        "records": [record],
    }
    route = manifest["records"][0]["result"]
    deep_records = []
    if route["required"]:
        deep_records.append(
            {
                **copy.deepcopy(record),
                "alignment_review": copy.deepcopy(alignment_review),
                "routing_reasons": route["reasons"],
                "risk_tags": route["risk_tags"],
                "audit_selected": route["audit_selected"],
                "context": [],
                "included_scope": [],
                "excluded_scope": ["packet外のrepository source"],
            }
        )
    deep_packet_content = {
        "review_contract_version": "deep-review-v1",
        "metadata_result_hash": alignment_packet["metadata_result_hash"],
        "records": deep_records,
    }
    deep_packet = {
        **deep_packet_content,
        "input_hash": result_hash(deep_packet_content),
    }
    sol_result = None
    if sol_verdict is not None:
        needs_context = sol_verdict == "NEEDS_CONTEXT"
        sol_result = {
            "review_contract_version": "deep-review-v1",
            "input_hash": deep_packet["input_hash"],
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
        "alignment_packet": alignment_packet,
        "metadata_result": metadata_result,
        "deep_packet": deep_packet,
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
    # claim = "metadata phase evidenceはpacket内metadata fieldと定義済みfindingだけを参照する構造を持つ"
    # oracle = { type = "adr", ref = "ADR-0022" }
    # failure_mode = "source本文を読んだという自由文をPhase 1のVALID根拠として受理する"
    # scope = "metadata-review-evidence-schema"
    # lifecycle = "permanent"
    # @end-test-value
    def test_metadata_result_rejects_free_text_source_evidence(self):
        value = aggregation_input()
        result = copy.deepcopy(value["metadata_result"])
        result["reviews"][0]["evidence"] = [
            "source_textのassertEqualを確認したのでVALID"
        ]
        record = value["alignment_packet"]["records"][0]
        expected = [
            {
                "record_id": record["record_id"],
                "metadata_format_version": 1,
                "metadata": record["metadata"],
                "metadata_hash": record["metadata_hash"],
            }
        ]

        with self.assertRaisesRegex(ResultValidationError, "metadata evidence"):
            validate_phase_result("metadata", result, expected)

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
        extra_field = aggregation_input(kind="security")
        extra_field["alignment_packet"]["records"][0]["unhashed_context"] = "source"
        with self.assertRaisesRegex(ResultValidationError, "unexpected keys"):
            aggregate_results(extra_field)

        reused_phase1 = aggregation_input(kind="security")
        reused_record = reused_phase1["alignment_packet"]["records"][0]
        reused_record["metadata"]["claim"] = "changed claim"
        reused_record["metadata_hash"] = sha256_text(
            canonical_json(reused_record["metadata"])
        )
        reused_record["record_id"] = sha256_text(
            canonical_json(
                {
                    "locator": {
                        "path": reused_record["source"]["path"],
                        "declaration_start_line": reused_record["source"][
                            "declaration_start_line"
                        ],
                    },
                    "metadata_hash": reused_record["metadata_hash"],
                }
            )
        )
        with self.assertRaisesRegex(ResultValidationError, "unexpected record"):
            aggregate_results(reused_phase1)

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
    # kind = "security"
    # claim = "final aggregatorはalignment packetの埋め込みPhase 1 reviewを固定済みPhase 1 result全体へ照合する"
    # oracle = { type = "adr", ref = "ADR-0022" }
    # failure_mode = "REDESIGNをVALIDへ変更してrouting manifestを再生成し最終gateをPASSにする"
    # scope = "review-final-phase1-result-binding"
    # lifecycle = "permanent"
    # @end-test-value
    def test_aggregate_rejects_rewritten_phase1_review(self):
        value = aggregation_input(metadata_verdict="REDESIGN")
        record = value["alignment_packet"]["records"][0]
        record["metadata_review"]["verdict"] = "VALID"
        review = value["alignment_result"]["reviews"][0]
        value["routing_manifest"] = build_routing_manifest(
            [
                {
                    "record_id": record["record_id"],
                    "metadata_hash": record["metadata_hash"],
                    "source_hash": record["source_hash"],
                    "contract_version": "deep-review-v1",
                    "metadata": record["metadata"],
                    "metadata_verdict": "VALID",
                    "alignment_verdict": review["verdict"],
                    "context_requirements": review["context_requirements"],
                }
            ],
            value["workflow_routing_context"],
        )

        with self.assertRaisesRegex(ResultValidationError, "embedded metadata review"):
            aggregate_results(value)

    # @test-value v1
    # kind = "security"
    # claim = "Sol resultはPhase 1、alignment、routing、bounded contextを含むcanonical deep packet全体へ結合される"
    # oracle = { type = "adr", ref = "ADR-0022" }
    # failure_mode = "別のPhase 1 resultで得たSol APPROVEを現在のNEEDS_CONTEXT recordへ再利用してPASSにする"
    # scope = "review-final-deep-input-binding"
    # lifecycle = "permanent"
    # @end-test-value
    def test_aggregate_rejects_sol_result_from_another_phase1_result(self):
        tampered_packet = aggregation_input(
            metadata_verdict="NEEDS_CONTEXT", kind="security", sol_verdict="APPROVE"
        )
        tampered_packet["deep_packet"]["records"][0]["metadata_review"][
            "verdict"
        ] = "VALID"
        with self.assertRaisesRegex(ResultValidationError, "input_hash"):
            aggregate_results(tampered_packet)

        previous = aggregation_input(
            metadata_verdict="VALID", kind="security", sol_verdict="APPROVE"
        )
        current = aggregation_input(
            metadata_verdict="NEEDS_CONTEXT", kind="security", sol_verdict="APPROVE"
        )
        self.assertNotEqual(
            previous["deep_packet"]["metadata_result_hash"],
            current["deep_packet"]["metadata_result_hash"],
        )
        current["sol_result"] = previous["sol_result"]

        with self.assertRaisesRegex(ResultValidationError, "input_hash"):
            aggregate_results(current)

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
            "input_hash": "sha256:" + "4" * 64,
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
            validate_phase_result(
                "deep", deep, [record], "sha256:" + "4" * 64
            )

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
                "record_id": base["alignment_packet"]["records"][0]["record_id"],
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
                "record_id": unresolved_sol["alignment_packet"]["records"][0]["record_id"],
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
                "record_id": record["alignment_packet"]["records"][0]["record_id"],
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
        second = aggregation_input(
            kind="security",
            sol_verdict="APPROVE",
            source_path="tests/test_second_final_result.py",
        )
        second_record = copy.deepcopy(second["alignment_packet"]["records"][0])
        second_review = copy.deepcopy(second["alignment_result"]["reviews"][0])
        first["alignment_packet"]["records"].append(second_record)
        first["metadata_result"]["reviews"].append(
            copy.deepcopy(second["metadata_result"]["reviews"][0])
        )
        first["alignment_packet"]["metadata_result_hash"] = result_hash(
            first["metadata_result"]
        )
        first["deep_packet"]["metadata_result_hash"] = first["alignment_packet"][
            "metadata_result_hash"
        ]
        first["alignment_result"]["reviews"].append(second_review)
        first["deep_packet"]["records"].append(
            copy.deepcopy(second["deep_packet"]["records"][0])
        )
        second_context = copy.deepcopy(second["workflow_routing_context"]["records"][0])
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
        first["sol_result"]["reviews"].append(second_sol_review)
        first["deep_packet"]["input_hash"] = result_hash(
            {
                key: first["deep_packet"][key]
                for key in ("review_contract_version", "metadata_result_hash", "records")
            }
        )
        first["sol_result"]["input_hash"] = first["deep_packet"]["input_hash"]
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
            [
                first["alignment_packet"]["records"][0]["record_id"],
                second_record["record_id"],
            ],
        )
        self.assertEqual(result["gate"], "PASS")


if __name__ == "__main__":
    unittest.main()
