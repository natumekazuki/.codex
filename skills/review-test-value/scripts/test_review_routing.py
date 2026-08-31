import sys
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from review_routing import (  # noqa: E402
    RoutingError,
    aggregate_gate,
    aggregate_status,
    decide_disposition,
    decide_gate,
    deterministic_audit,
    merge_risk_tags,
    route_record,
    unavailable_result,
)


class ReviewRoutingTests(unittest.TestCase):
    # @test-value v1
    # kind = "invariant"
    # claim = "status aggregationは未完了、required Sol失敗、Luna欠陥、Sol欠陥、承認可能な組合せをADR-0022の優先順で判定する"
    # oracle = { type = "adr", ref = "ADR-0022" }
    # failure_mode = "低優先のAPPROVEで未完了またはREDESIGNを上書きするか有効なLunaとSolの組合せをACCEPTできない"
    # scope = "test-value-status-truth-table"
    # lifecycle = "permanent"
    # @end-test-value
    def test_status_aggregation_follows_the_adr_priority_table(self):
        cases = (
            (None, "ALIGNED", False, None, "NEEDS_CONTEXT"),
            ("VALID", None, False, None, "NEEDS_CONTEXT"),
            ("VALID", "ALIGNED", True, None, "NEEDS_CONTEXT"),
            ("REDESIGN", "ALIGNED", False, None, "REDESIGN"),
            ("VALID", "MISMATCH", False, None, "REDESIGN"),
            ("VALID", "ALIGNED", True, "REDESIGN", "REDESIGN"),
            ("VALID", "ALIGNED", False, None, "ACCEPT"),
            ("VALID", "RECHECK", True, "APPROVE", "ACCEPT"),
            ("NEEDS_CONTEXT", "ALIGNED", True, "APPROVE", "ACCEPT"),
        )
        for metadata, alignment, required, sol, expected in cases:
            with self.subTest(metadata=metadata, alignment=alignment, required=required, sol=sol):
                self.assertEqual(
                    aggregate_status(
                        metadata,
                        alignment,
                        sol_required=required,
                        sol_verdict=sol,
                    ),
                    expected,
                )
        with self.assertRaises(RoutingError):
            aggregate_status("VALID", "RECHECK", sol_required=False, sol_verdict=None)

    # @test-value v1
    # kind = "security"
    # claim = "risk routingはmetadataと親workflowのrisk tagをrecord IDとmetadata hashへ固定して和集合にし未知tagを拒否する"
    # oracle = { type = "adr", ref = "ADR-0022" }
    # failure_mode = "metadataの省略で親workflowのauthorization riskを解除するか別hashまたは未知tagのrisk contextを現在のrecordへ適用する"
    # scope = "test-value-risk-routing"
    # lifecycle = "permanent"
    # @end-test-value
    def test_risk_tags_preserve_parent_context_and_reject_unknown_values(self):
        self.assertEqual(
            merge_risk_tags(["privacy"], ["authorization"], kind="contract"),
            ["authorization", "privacy"],
        )
        with self.assertRaises(RoutingError):
            merge_risk_tags([], ["availability"], kind="contract")
        with self.assertRaisesRegex(RoutingError, "metadata_hash"):
            route_record(
                record_id="sha256:" + "1" * 64,
                metadata_hash="sha256:" + "2" * 64,
                contract_version="deep-review-v1",
                metadata={"kind": "contract"},
                parent_risk_context={
                    "record_id": "sha256:" + "1" * 64,
                    "metadata_hash": "sha256:" + "9" * 64,
                    "risk_tags": ["authorization"],
                },
                metadata_verdict="VALID",
                alignment_verdict="ALIGNED",
                context_requirements=[],
                audit_percent=0,
            )
        with self.assertRaisesRegex(RoutingError, "record_id"):
            route_record(
                record_id="sha256:" + "1" * 64,
                metadata_hash="sha256:" + "2" * 64,
                contract_version="deep-review-v1",
                metadata={"kind": "contract"},
                parent_risk_context={
                    "record_id": "sha256:" + "8" * 64,
                    "metadata_hash": "sha256:" + "2" * 64,
                    "risk_tags": ["authorization"],
                },
                metadata_verdict="VALID",
                alignment_verdict="ALIGNED",
                context_requirements=[],
                audit_percent=0,
            )

    # @test-value v1
    # kind = "contract"
    # claim = "Solは不確定または高リスクrecordへrequiredとなり低リスクの明白なREDESIGNだけではrequiredにならない"
    # oracle = { type = "adr", ref = "ADR-0022" }
    # failure_mode = "追加contextが必要なrecordをLunaだけで閉じるか明白な低リスク欠陥を不要にSolへ送る"
    # scope = "test-value-sol-routing"
    # lifecycle = "permanent"
    # @end-test-value
    def test_route_record_escalates_only_defined_conditions(self):
        common = {
            "record_id": "sha256:" + "4" * 64,
            "metadata_hash": "sha256:" + "6" * 64,
            "contract_version": "deep-review-v1",
            "parent_risk_context": None,
            "context_requirements": [],
            "audit_percent": 0,
        }
        clear_defect = route_record(
            **common,
            metadata={"kind": "contract"},
            metadata_verdict="REDESIGN",
            alignment_verdict="ALIGNED",
        )
        uncertain = route_record(
            **common,
            metadata={"kind": "contract"},
            metadata_verdict="NEEDS_CONTEXT",
            alignment_verdict="RECHECK",
        )
        high_risk = route_record(
            **common,
            metadata={"kind": "security"},
            metadata_verdict="REDESIGN",
            alignment_verdict="MISMATCH",
        )

        self.assertFalse(clear_defect["required"])
        self.assertTrue(uncertain["required"])
        self.assertTrue(high_risk["required"])
        self.assertIn("security", high_risk["risk_tags"])

    # @test-value v1
    # kind = "invariant"
    # claim = "dispositionとgateはactual boundary、permanentまたはtemporary lifecycle、保持根拠、artifact stateのADR-0022対応表に従う"
    # oracle = { type = "adr", ref = "ADR-0022" }
    # failure_mode = "declaration testを永続behavior testとしてPASSにするかDROP対象が残存してもPASSにする"
    # scope = "test-value-disposition-gate"
    # lifecycle = "permanent"
    # @end-test-value
    def test_disposition_and_gate_keep_status_separate_from_artifact_action(self):
        declaration = decide_disposition(
            actual_boundary="declaration",
            lifecycle="permanent",
            retention_basis="PRESENT",
        )
        behavior = decide_disposition(
            actual_boundary="component-behavior",
            lifecycle="permanent",
            retention_basis="PRESENT",
        )
        implementation = decide_disposition(
            actual_boundary="implementation",
            lifecycle="permanent",
            retention_basis="PRESENT",
        )
        temporary = decide_disposition(
            actual_boundary="implementation",
            lifecycle="characterization",
            retention_basis="ABSENT",
            expires_on="2026-12-31",
        )
        no_basis = decide_disposition(
            actual_boundary="component-behavior",
            lifecycle="permanent",
            retention_basis="ABSENT",
        )
        unresolved = decide_disposition(
            actual_boundary="component-behavior",
            lifecycle="permanent",
            retention_basis="UNRESOLVED",
        )

        self.assertEqual(declaration, "MOVE_TO_POLICY_CHECK")
        self.assertEqual(decide_gate("ACCEPT", declaration, "TEST_PRESENT"), "CHANGES_REQUIRED")
        self.assertEqual(behavior, "KEEP_PERMANENT")
        self.assertEqual(decide_gate("ACCEPT", behavior, "PERMANENT_TEST"), "PASS")
        self.assertEqual(implementation, "DROP")
        self.assertEqual(decide_gate("ACCEPT", implementation, "TEST_PRESENT"), "CHANGES_REQUIRED")
        self.assertEqual(temporary, "KEEP_TEMPORARY")
        self.assertEqual(decide_gate("ACCEPT", temporary, "TEMPORARY_TEST"), "PASS")
        self.assertEqual(no_basis, "DROP")
        self.assertIsNone(unresolved)
        self.assertEqual(aggregate_gate(["PASS", "CHANGES_REQUIRED"]), "CHANGES_REQUIRED")
        self.assertEqual(aggregate_gate(["PASS", "CHANGES_REQUIRED", "BLOCKED"]), "BLOCKED")

    # @test-value v1
    # kind = "regression"
    # claim = "required agent unavailableは代替審査せずNEEDS_CONTEXT、disposition null、BLOCKEDへ固定する"
    # oracle = { type = "adr", ref = "ADR-0022" }
    # failure_mode = "LunaまたはSolを起動できない時に親agentの代行結果でreview gateをPASSにする"
    # scope = "test-value-agent-availability"
    # lifecycle = "permanent"
    # @end-test-value
    def test_required_agent_unavailable_is_fail_closed(self):
        self.assertEqual(
            unavailable_result(),
            {"status": "NEEDS_CONTEXT", "disposition": None, "gate": "BLOCKED"},
        )

    # @test-value v1
    # kind = "contract"
    # claim = "deterministic audit selectionは同じrecord ID、contract version、率から常に同じbooleanを返す"
    # oracle = { type = "adr", ref = "ADR-0022" }
    # failure_mode = "実行ごとに監査対象が変わり同じreview inputのSol routingを再現できなくする"
    # scope = "test-value-deterministic-audit"
    # lifecycle = "permanent"
    # @end-test-value
    def test_deterministic_audit_is_stable_and_respects_extremes(self):
        record_id = "sha256:" + "5" * 64
        selected = deterministic_audit(record_id, "deep-review-v1", 37)

        self.assertEqual(selected, deterministic_audit(record_id, "deep-review-v1", 37))
        self.assertFalse(deterministic_audit(record_id, "deep-review-v1", 0))
        self.assertTrue(deterministic_audit(record_id, "deep-review-v1", 100))


if __name__ == "__main__":
    unittest.main()
