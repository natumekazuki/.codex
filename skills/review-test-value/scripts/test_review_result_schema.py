import sys
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from build_review_packets import canonical_json, sha256_text  # noqa: E402
from review_routing import build_routing_manifest  # noqa: E402
from validate_review_result import (  # noqa: E402
    ResultValidationError,
    aggregate_record,
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
    manifest = build_routing_manifest(
        [
            {
                **identity,
                "contract_version": "deep-review-v1",
                "metadata": metadata,
                "parent_risk_context": None,
                "metadata_verdict": metadata_verdict,
                "alignment_verdict": alignment_verdict,
                "context_requirements": alignment_review["context_requirements"],
                "audit_percent": 0,
            }
        ]
    )
    sol_result = None
    if sol_verdict is not None:
        sol_result = {
            "review_contract_version": "deep-review-v1",
            "reviews": [
                {
                    **identity,
                    "verdict": sol_verdict,
                    "evidence": ["deep review evidence"],
                    "unverified": [],
                    "context_requirements": [],
                    "next_action": None,
                }
            ],
        }
    return {
        "record": record,
        "alignment_review": alignment_review,
        "routing_manifest": manifest,
        "sol_result": sol_result,
        "retention_basis": retention_basis,
        "artifact_state": artifact_state,
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
        tampered["record"]["metadata"]["kind"] = "contract"
        with self.assertRaisesRegex(ResultValidationError, "metadata_hash"):
            aggregate_record(tampered)

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
            aggregate_record(scalar_input)

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
    def test_aggregate_record_fails_closed_and_preserves_redesign(self):
        base = aggregation_input(kind="security")
        self.assertEqual(
            aggregate_record(base),
            {"status": "NEEDS_CONTEXT", "disposition": "KEEP_PERMANENT", "gate": "BLOCKED"},
        )
        redesigned = aggregation_input(
            metadata_verdict="REDESIGN",
            kind="security",
            sol_verdict="APPROVE",
        )
        self.assertEqual(aggregate_record(redesigned)["status"], "REDESIGN")
        self.assertEqual(aggregate_record(redesigned)["gate"], "CHANGES_REQUIRED")

    # @test-value v1
    # kind = "contract"
    # claim = "保持根拠またはv1 ephemeral削除条件を確定できないACCEPT候補はdisposition null、NEEDS_CONTEXT、BLOCKEDになる"
    # oracle = { type = "adr", ref = "ADR-0022" }
    # failure_mode = "保持先を確定できないtest artifactをPASSとしてBootstrap changeの完了条件に通す"
    # scope = "review-disposition-gate"
    # lifecycle = "permanent"
    # @end-test-value
    def test_aggregate_record_blocks_unresolved_disposition(self):
        record = aggregation_input(
            lifecycle="ephemeral",
            retention_basis="UNRESOLVED",
            artifact_state="TEMPORARY_TEST",
        )

        self.assertEqual(
            aggregate_record(record),
            {"status": "NEEDS_CONTEXT", "disposition": None, "gate": "BLOCKED"},
        )


if __name__ == "__main__":
    unittest.main()
