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

    # @test-value v2
    # kind = "security"
    # claim = "risk routingはmetadataと親workflowのrisk tagをrecord IDとmetadata hashへ固定して和集合にし未知tagを拒否する"
    # oracle = { type = "adr", ref = "ADR-0022" }
    # fault = "metadataの省略で親workflowのauthorization riskを解除するか別hashまたは未知tagのrisk contextを現在のrecordへ適用する"
    # observable = "route_recordのrisk_tagsとRoutingError"
    # observation_boundary = "component-behavior"
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
                contract_version="deep-review-v2",
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
                contract_version="deep-review-v2",
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

    # @test-value v2
    # kind = "contract"
    # claim = "Solは不確定または高リスクrecordへrequiredとなり低リスクの明白なREDESIGNだけではrequiredにならない"
    # oracle = { type = "adr", ref = "ADR-0022" }
    # fault = "追加contextが必要なrecordをLunaだけで閉じるか明白な低リスク欠陥を不要にSolへ送る"
    # observable = "route_recordのrequired、reasons、risk_tags"
    # observation_boundary = "component-behavior"
    # scope = "test-value-sol-routing"
    # lifecycle = "permanent"
    # @end-test-value
    def test_route_record_escalates_only_defined_conditions(self):
        common = {
            "record_id": "sha256:" + "4" * 64,
            "metadata_hash": "sha256:" + "6" * 64,
            "contract_version": "deep-review-v2",
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

    # @test-value v2
    # kind = "invariant"
    # claim = "dispositionとgateはactual boundary、lifecycle、保持根拠、artifact stateのADR-0022対応表に従いUNRESOLVEDは全boundaryで未確定に閉じる"
    # oracle = { type = "adr", ref = "ADR-0022" }
    # fault = "保持根拠がUNRESOLVEDでもboundaryやtemporary lifecycleの分岐を先に適用してartifact actionを確定する"
    # observable = "decide_disposition、decide_gate、aggregate_gateの戻り値"
    # observation_boundary = "component-behavior"
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
        ephemeral = decide_disposition(
            actual_boundary="component-behavior",
            lifecycle="ephemeral",
            retention_basis="PRESENT",
            remove_when="replaced by the integration check",
        )
        no_basis = decide_disposition(
            actual_boundary="component-behavior",
            lifecycle="permanent",
            retention_basis="ABSENT",
        )
        unresolved = [
            decide_disposition(
                actual_boundary=boundary,
                lifecycle="characterization",
                retention_basis="UNRESOLVED",
                expires_on="2026-12-31",
            )
            for boundary in (
                "consumer",
                "public-boundary",
                "component-behavior",
                "declaration",
                "implementation",
            )
        ]

        self.assertEqual(declaration, "MOVE_TO_POLICY_CHECK")
        self.assertEqual(decide_gate("ACCEPT", declaration, "TEST_PRESENT"), "CHANGES_REQUIRED")
        self.assertEqual(behavior, "KEEP_PERMANENT")
        self.assertEqual(decide_gate("ACCEPT", behavior, "PERMANENT_TEST"), "PASS")
        self.assertEqual(implementation, "DROP")
        self.assertEqual(decide_gate("ACCEPT", implementation, "TEST_PRESENT"), "CHANGES_REQUIRED")
        self.assertEqual(temporary, "KEEP_TEMPORARY")
        self.assertEqual(ephemeral, "KEEP_TEMPORARY")
        self.assertEqual(decide_gate("ACCEPT", temporary, "TEMPORARY_TEST"), "PASS")
        self.assertEqual(no_basis, "DROP")
        self.assertEqual(unresolved, [None, None, None, None, None])
        self.assertEqual(aggregate_gate(["PASS", "CHANGES_REQUIRED"]), "CHANGES_REQUIRED")
        self.assertEqual(aggregate_gate(["PASS", "CHANGES_REQUIRED", "BLOCKED"]), "BLOCKED")

    # @test-value v2
    # kind = "contract"
    # claim = "deterministic audit selectionはrecord IDとcontract versionのSHA-256全体を100で割った剰余から再現できる"
    # oracle = { type = "adr", ref = "ADR-0022" }
    # fault = "digestの一部だけでbucketを計算してrouting policy準拠のconsumerと監査対象が食い違う"
    # observable = "deterministic_auditの選択boolean"
    # observation_boundary = "component-behavior"
    # scope = "test-value-deterministic-audit"
    # lifecycle = "permanent"
    # @end-test-value
    def test_deterministic_audit_is_stable_and_respects_extremes(self):
        record_id = "sha256:" + "0" * 64
        selected = deterministic_audit(record_id, "deep-review-v2", 92)

        self.assertTrue(selected)
        self.assertFalse(deterministic_audit(record_id, "deep-review-v2", 91))
        self.assertEqual(selected, deterministic_audit(record_id, "deep-review-v2", 92))
        self.assertFalse(deterministic_audit(record_id, "deep-review-v2", 0))
        self.assertTrue(deterministic_audit(record_id, "deep-review-v2", 100))


if __name__ == "__main__":
    unittest.main()
