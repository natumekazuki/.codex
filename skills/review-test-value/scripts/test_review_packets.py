import copy
import sys
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from build_review_packets import (  # noqa: E402
    PacketError,
    build_alignment_packet,
    build_deep_packet,
    build_metadata_packet,
    canonical_json,
    sha256_text,
)
from review_routing import build_routing_manifest  # noqa: E402


def extractor_result():
    metadata = {
        "kind": "contract",
        "claim": "packetがreview phaseの入力境界を保つ",
        "oracle": {"type": "adr", "ref": "ADR-0022"},
        "fault": "metadata phaseへsourceを混入するかalignment phaseでrecordを欠落させる",
        "observable": "phase packetのrecord fieldと順序",
        "observation_boundary": "component-behavior",
        "scope": "review-test-value-packet",
        "lifecycle": "permanent",
    }
    source_text = "def test_packet_boundary(self):\n    self.assertTrue(packet)\n"
    return {
        "schema_version": 2,
        "adapter": "python-source-v1",
        "coverage": "python-source-declarations-v1",
        "repository_root": ".",
        "tests": [
            {
                "source": {
                    "path": "tests/test_packet.py",
                    "symbol": "PacketTests.test_packet_boundary",
                    "metadata_start_line": 1,
                    "metadata_end_line": 8,
                    "declaration_start_line": 9,
                    "declaration_end_line": 10,
                },
                "metadata_format_version": 2,
                "metadata": metadata,
                "source_text": source_text,
                "source_hash": sha256_text(source_text),
                "metadata_hash": sha256_text(canonical_json(metadata)),
            }
        ],
        "transitions": None,
        "diagnostics": [],
        "warnings": [],
    }


def metadata_result(packet, verdict="VALID"):
    return {
        "review_contract_version": "metadata-review-v2",
        "reviews": [
            {
                "record_id": record["record_id"],
                "metadata_hash": record["metadata_hash"],
                "verdict": verdict,
                "evidence": [
                    {
                        "fields": ["claim", "fault", "scope"],
                        "finding": (
                            "FAULT_NOT_SPECIFIC"
                            if verdict == "REDESIGN"
                            else "COHERENT_BOUNDARY"
                        ),
                    }
                ],
                "unverified": ["ADR-0022本文"],
                "next_action": None,
            }
            for record in packet["records"]
        ],
    }


def extractor_result_with_two_records():
    result = extractor_result()
    second = copy.deepcopy(result["tests"][0])
    second["source"]["path"] = "tests/test_packet_two.py"
    second["source"]["declaration_start_line"] = 20
    second["source"]["declaration_end_line"] = 21
    second["source_text"] = "def test_second_packet(self):\n    self.assertTrue(packet)\n"
    second["source_hash"] = sha256_text(second["source_text"])
    result["tests"].append(second)
    return result


class ReviewPacketTests(unittest.TestCase):
    # @test-value v2
    # kind = "invariant"
    # claim = "packet builderはGit transition順にafterまたは削除前beforeをPhase 1へ投影する"
    # oracle = { type = "adr", ref = "ADR-0022" }
    # fault = "削除testをPhase 1から欠落させるか同一locatorの追加testと衝突させる"
    # observable = "metadata packetのrecord集合、順序、record_id"
    # observation_boundary = "component-behavior"
    # scope = "extractor-transition-envelope"
    # lifecycle = "permanent"
    # @end-test-value
    def test_metadata_packet_validates_transition_envelope_and_current_records(self):
        extracted = extractor_result()
        current = copy.deepcopy(extracted["tests"][0])
        extracted["transitions"] = [
            {"kind": "ADDED", "before": None, "after": current}
        ]
        self.assertEqual(len(build_metadata_packet(extracted)["records"]), 1)

        extracted["transitions"] = [
            {"kind": "ADDED", "before": None, "after": current},
            {"kind": "DELETED", "before": copy.deepcopy(current), "after": None},
        ]
        packet = build_metadata_packet(extracted)
        self.assertEqual(len(packet["records"]), 2)
        self.assertNotEqual(packet["records"][0]["record_id"], packet["records"][1]["record_id"])

        deleted = copy.deepcopy(current)
        deleted["source"]["path"] = "tests/test_packet_deleted.py"
        deleted["source"]["declaration_start_line"] = 40
        deleted["source"]["declaration_end_line"] = 41
        extracted["transitions"] = [
            {"kind": "SURVIVED", "before": current, "after": current},
            {"kind": "DELETED", "before": deleted, "after": None},
        ]
        self.assertEqual(len(build_metadata_packet(extracted)["records"]), 2)

        invalid_cases = []
        mismatch = copy.deepcopy(extracted)
        mismatch["transitions"][0]["after"]["source_text"] = "changed"
        invalid_cases.append(mismatch)
        duplicate = copy.deepcopy(extracted)
        duplicate["transitions"].append(copy.deepcopy(duplicate["transitions"][0]))
        invalid_cases.append(duplicate)
        deleted_with_after = copy.deepcopy(extracted)
        deleted_with_after["transitions"] = [
            {"kind": "DELETED", "before": current, "after": current}
        ]
        invalid_cases.append(deleted_with_after)
        unresolved = copy.deepcopy(extracted)
        unresolved["transitions"] = [{"kind": "UNKNOWN", "before": None, "after": current}]
        invalid_cases.append(unresolved)

        for candidate in invalid_cases:
            with self.assertRaises(PacketError):
                build_metadata_packet(candidate)

    # @test-value v2
    # kind = "invariant"
    # claim = "削除だけのGit差分でも削除前metadataを一件のPhase 1 packet recordとして保持する"
    # oracle = { type = "adr", ref = "ADR-0022" }
    # fault = "current testsが空であることを理由に削除testの審査義務を消失させる"
    # observable = "metadata packetのrecord数とmetadata hash"
    # observation_boundary = "component-behavior"
    # scope = "deleted-transition-packet"
    # lifecycle = "permanent"
    # @end-test-value
    def test_deleted_only_transition_yields_one_metadata_record(self):
        extracted = extractor_result()
        deleted = copy.deepcopy(extracted["tests"][0])
        extracted["tests"] = []
        extracted["transitions"] = [
            {"kind": "DELETED", "before": deleted, "after": None}
        ]

        packet = build_metadata_packet(extracted)

        self.assertEqual(len(packet["records"]), 1)
        self.assertEqual(packet["records"][0]["metadata_hash"], deleted["metadata_hash"])

    # @test-value v2
    # kind = "invariant"
    # claim = "同一locatorの追加と削除はtransition状態を含む異なるrecord_idでPhase 1へ渡す"
    # oracle = { type = "adr", ref = "ADR-0022" }
    # fault = "削除前recordを現行追加recordと同一IDへ畳み込み片方の審査を欠落させる"
    # observable = "metadata packetの二件のrecord_idとtransition順"
    # observation_boundary = "component-behavior"
    # scope = "deleted-transition-identity"
    # lifecycle = "permanent"
    # @end-test-value
    def test_same_locator_add_and_delete_have_distinct_packet_ids(self):
        extracted = extractor_result()
        current = copy.deepcopy(extracted["tests"][0])
        extracted["transitions"] = [
            {"kind": "ADDED", "before": None, "after": current},
            {"kind": "DELETED", "before": copy.deepcopy(current), "after": None},
        ]

        records = build_metadata_packet(extracted)["records"]

        self.assertEqual(len(records), 2)
        self.assertNotEqual(records[0]["record_id"], records[1]["record_id"])

    # @test-value v2
    # kind = "contract"
    # claim = "削除前recordはmetadata review結果とsource本文を同じrecord_idでPhase 2へ対応付ける"
    # oracle = { type = "adr", ref = "ADR-0022" }
    # fault = "削除前recordのmetadata審査は通るがalignment packetからsource本文だけが欠落する"
    # observable = "alignment packetの削除record sourceとsource hash"
    # observation_boundary = "component-behavior"
    # scope = "deleted-transition-alignment"
    # lifecycle = "permanent"
    # @end-test-value
    def test_alignment_packet_includes_deleted_source(self):
        extracted = extractor_result()
        deleted = copy.deepcopy(extracted["tests"][0])
        extracted["tests"] = []
        extracted["transitions"] = [
            {"kind": "DELETED", "before": deleted, "after": None}
        ]
        metadata_packet = build_metadata_packet(extracted)
        metadata_reviews = metadata_result(metadata_packet)

        packet = build_alignment_packet(extracted, metadata_reviews)

        self.assertEqual(packet["records"][0]["source"], deleted["source"])
        self.assertEqual(packet["records"][0]["source_text"], deleted["source_text"])
        self.assertEqual(packet["records"][0]["source_hash"], deleted["source_hash"])

    # @test-value v2
    # kind = "security"
    # claim = "packet builderはv1 extractor結果を審査入力へ変換せずv2を要求する"
    # oracle = { type = "adr", ref = "ADR-0022" }
    # fault = "v1 recordをmetadata-review-v2 packetへ混入して旧形式の評価を続行する"
    # observable = "build_metadata_packetが返すPacketError"
    # observation_boundary = "component-behavior"
    # scope = "metadata-review-packet-version"
    # lifecycle = "permanent"
    # @end-test-value
    def test_metadata_packet_rejects_v1_extractor_records(self):
        extracted = extractor_result()
        extracted["schema_version"] = 1
        extracted["tests"][0]["metadata_format_version"] = 1

        with self.assertRaisesRegex(PacketError, "schema_version must be 2"):
            build_metadata_packet(extracted)

    # @test-value v2
    # kind = "security"
    # claim = "metadata packetはopaque record IDとmetadataだけを含みtest sourceのlocatorと本文を含まない"
    # oracle = { type = "adr", ref = "ADR-0022" }
    # fault = "Phase 1 packetへsource path、line、symbol、source text、source hashのいずれかが混入しmetadata不足を本文から補完できる"
    # observable = "metadata packetのfield集合とcanonical JSON"
    # observation_boundary = "component-behavior"
    # scope = "metadata-review-packet"
    # lifecycle = "permanent"
    # @end-test-value
    def test_metadata_packet_excludes_all_source_material(self):
        packet = build_metadata_packet(extractor_result())

        self.assertEqual(packet["review_contract_version"], "metadata-review-v2")
        self.assertEqual(
            set(packet["records"][0]),
            {"record_id", "metadata_format_version", "metadata", "metadata_hash"},
        )
        self.assertRegex(packet["records"][0]["record_id"], r"^sha256:[0-9a-f]{64}$")
        self.assertNotIn("tests/test_packet.py", canonical_json(packet))

    # @test-value v2
    # kind = "security"
    # claim = "metadata packetはv1 schema外fieldをhashが一致していてもAI審査前に拒否する"
    # oracle = { type = "adr", ref = "ADR-0022" }
    # fault = "source_textなどの未知fieldをmetadataへ埋め込みPhase 1へsource evidenceを渡す"
    # observable = "build_metadata_packetが返すPacketError"
    # observation_boundary = "component-behavior"
    # scope = "metadata-review-schema-boundary"
    # lifecycle = "permanent"
    # @end-test-value
    def test_metadata_packet_rejects_unknown_metadata_fields(self):
        extracted = extractor_result()
        metadata = extracted["tests"][0]["metadata"]
        metadata["source_text"] = "assertTrue(packet)"
        extracted["tests"][0]["metadata_hash"] = sha256_text(canonical_json(metadata))

        with self.assertRaisesRegex(PacketError, "unknown fields: source_text"):
            build_metadata_packet(extracted)

    # @test-value v2
    # kind = "invariant"
    # claim = "alignment packetは固定したPhase 1のrecord集合と順序を変更せず全recordへsourceを対応付ける"
    # oracle = { type = "adr", ref = "ADR-0022" }
    # fault = "Phase 1 resultのrecordを欠落、追加、並べ替えしてもPhase 2 packetを構築し別recordの審査結果を対応付ける"
    # observable = "build_alignment_packetが返すPacketError"
    # observation_boundary = "component-behavior"
    # scope = "alignment-review-packet"
    # lifecycle = "permanent"
    # @end-test-value
    def test_alignment_packet_rejects_a_changed_phase1_record_set(self):
        extracted = extractor_result_with_two_records()
        phase1 = build_metadata_packet(extracted)
        valid = metadata_result(phase1)
        changed_results = []
        missing = copy.deepcopy(valid)
        missing["reviews"].pop()
        changed_results.append(missing)
        reordered = copy.deepcopy(valid)
        reordered["reviews"].reverse()
        changed_results.append(reordered)
        additional = copy.deepcopy(valid)
        additional["reviews"].append(copy.deepcopy(additional["reviews"][0]))
        changed_results.append(additional)

        for result in changed_results:
            with self.subTest(record_ids=[item["record_id"] for item in result["reviews"]]):
                with self.assertRaisesRegex(PacketError, "record set or order"):
                    build_alignment_packet(extracted, result)

    # @test-value v2
    # kind = "contract"
    # claim = "Phase 1がREDESIGNのrecordもPhase 2 packetへ同じmetadata resultとsource hashを保って含める"
    # oracle = { type = "adr", ref = "ADR-0022" }
    # fault = "REDESIGN recordをPhase 2から省略してactual boundaryと保持先候補を判定できなくする"
    # observable = "alignment packetのrecord集合とfrozen metadata review"
    # observation_boundary = "component-behavior"
    # scope = "alignment-review-packet"
    # lifecycle = "permanent"
    # @end-test-value
    def test_alignment_packet_keeps_redesign_records_and_frozen_result(self):
        extracted = extractor_result()
        phase1 = build_metadata_packet(extracted)
        frozen = metadata_result(phase1, verdict="REDESIGN")

        packet = build_alignment_packet(extracted, frozen)

        self.assertEqual(len(packet["records"]), 1)
        self.assertEqual(packet["records"][0]["metadata_review"], frozen["reviews"][0])
        self.assertEqual(packet["records"][0]["source_hash"], extracted["tests"][0]["source_hash"])

    # @test-value v2
    # kind = "security"
    # claim = "deep packetはallowlist済みalignment record、固定reviewと一致するrouting manifest、hashが一致するbounded contextだけから構築できる"
    # oracle = { type = "adr", ref = "ADR-0022" }
    # fault = "未知fieldをSolへ転送するかrequired routingを解除するかcontext contentの改変後も以前のhashを正しい証拠としてSolへ渡す"
    # observable = "build_deep_packetが返すPacketErrorとdeep packet input_hash"
    # observation_boundary = "component-behavior"
    # scope = "deep-review-packet"
    # lifecycle = "permanent"
    # @end-test-value
    def test_deep_packet_rejects_modified_context(self):
        extracted = extractor_result()
        phase1 = build_metadata_packet(extracted)
        fixed_metadata_result = metadata_result(phase1)
        alignment = build_alignment_packet(extracted, fixed_metadata_result)
        record = alignment["records"][0]
        alignment_result = {
            "review_contract_version": "alignment-review-v2",
            "reviews": [
                {
                    "record_id": record["record_id"],
                    "metadata_hash": record["metadata_hash"],
                    "source_hash": record["source_hash"],
                    "verdict": "RECHECK",
                    "actual_boundary": None,
                    "actual_observables": [],
                    "overclaim": False,
                    "evidence": [],
                    "unverified": [],
                    "disposition_candidate": None,
                    "context_requirements": ["ADR-0022"],
                    "next_action": "ADRを確認する",
                }
            ],
        }
        workflow_context = {
            "review_contract_version": "review-workflow-context-v1",
            "records": [
                {
                    "record_id": record["record_id"],
                    "metadata_hash": record["metadata_hash"],
                    "parent_risk_tags": ["authorization"],
                    "audit_percent": 0,
                }
            ],
        }
        routing = build_routing_manifest(
            [
                {
                    "record_id": record["record_id"],
                    "metadata_hash": record["metadata_hash"],
                    "source_hash": record["source_hash"],
                    "contract_version": "deep-review-v2",
                    "metadata": record["metadata"],
                    "metadata_verdict": record["metadata_review"]["verdict"],
                    "alignment_verdict": "RECHECK",
                    "context_requirements": ["ADR-0022"],
                }
            ],
            workflow_context,
        )
        bad_context = {
            record["record_id"]: [
                {
                    "kind": "adr",
                    "ref": "ADR-0022",
                    "content": "modified",
                    "content_hash": sha256_text("original"),
                }
            ]
        }

        with self.assertRaisesRegex(PacketError, "context hash"):
            build_deep_packet(
                alignment, fixed_metadata_result, alignment_result, routing, workflow_context, bad_context
            )
        extra_routing = copy.deepcopy(routing)
        extra_entry = copy.deepcopy(extra_routing["records"][0])
        extra_entry["record_id"] = "sha256:" + "9" * 64
        extra_routing["records"].append(extra_entry)
        with self.assertRaisesRegex(PacketError, "record set or order"):
            build_deep_packet(
                alignment, fixed_metadata_result, alignment_result, extra_routing, workflow_context, {}
            )
        downgraded = copy.deepcopy(routing)
        downgraded["records"][0]["result"]["required"] = False
        downgraded["records"][0]["result"]["reasons"] = []
        with self.assertRaisesRegex(PacketError, "routing result"):
            build_deep_packet(
                alignment, fixed_metadata_result, alignment_result, downgraded, workflow_context, {}
            )
        removed_parent_risk = copy.deepcopy(workflow_context)
        removed_parent_risk["records"][0]["parent_risk_tags"] = []
        manifest_without_parent_risk = build_routing_manifest(
            [
                {
                    "record_id": record["record_id"],
                    "metadata_hash": record["metadata_hash"],
                    "source_hash": record["source_hash"],
                    "contract_version": "deep-review-v2",
                    "metadata": record["metadata"],
                    "metadata_verdict": record["metadata_review"]["verdict"],
                    "alignment_verdict": "RECHECK",
                    "context_requirements": ["ADR-0022"],
                }
            ],
            removed_parent_risk,
        )
        with self.assertRaisesRegex(PacketError, "workflow context hash"):
            build_deep_packet(
                alignment,
                fixed_metadata_result,
                alignment_result,
                manifest_without_parent_risk,
                workflow_context,
                {},
            )
        changed_audit = copy.deepcopy(workflow_context)
        changed_audit["records"][0]["audit_percent"] = 100
        manifest_with_changed_audit = build_routing_manifest(
            [
                {
                    "record_id": record["record_id"],
                    "metadata_hash": record["metadata_hash"],
                    "source_hash": record["source_hash"],
                    "contract_version": "deep-review-v2",
                    "metadata": record["metadata"],
                    "metadata_verdict": record["metadata_review"]["verdict"],
                    "alignment_verdict": "RECHECK",
                    "context_requirements": ["ADR-0022"],
                }
            ],
            changed_audit,
        )
        with self.assertRaisesRegex(PacketError, "workflow context hash"):
            build_deep_packet(
                alignment,
                fixed_metadata_result,
                alignment_result,
                manifest_with_changed_audit,
                workflow_context,
                {},
            )
        expanded_alignment = copy.deepcopy(alignment)
        expanded_alignment["records"][0]["unhashed_extra_context"] = "production source"
        with self.assertRaisesRegex(PacketError, "unexpected keys"):
            build_deep_packet(
                expanded_alignment,
                fixed_metadata_result,
                alignment_result,
                routing,
                workflow_context,
                {},
            )
        deep_packet = build_deep_packet(
            alignment,
            fixed_metadata_result,
            alignment_result,
            routing,
            workflow_context,
            {},
        )
        self.assertEqual(
            deep_packet["input_hash"],
            sha256_text(
                canonical_json(
                    {
                        key: deep_packet[key]
                        for key in (
                            "review_contract_version",
                            "metadata_result_hash",
                            "records",
                        )
                    }
                )
            ),
        )

    # @test-value v2
    # kind = "security"
    # claim = "deep packetはalignment packetへ固定されたPhase 1 result全体のhashと埋め込みreviewを元artifactへ照合する"
    # oracle = { type = "adr", ref = "ADR-0022" }
    # fault = "Phase 1のREDESIGNをVALIDへ差し替えてroutingを再生成しrequired reviewを迂回する"
    # observable = "build_deep_packetが返すPacketError"
    # observation_boundary = "component-behavior"
    # scope = "deep-review-phase1-result-binding"
    # lifecycle = "permanent"
    # @end-test-value
    def test_deep_packet_rejects_rewritten_phase1_result(self):
        extracted = extractor_result()
        phase1 = build_metadata_packet(extracted)
        frozen = metadata_result(phase1, verdict="REDESIGN")
        alignment = build_alignment_packet(extracted, frozen)
        rewritten = metadata_result(phase1, verdict="VALID")
        alignment["records"][0]["metadata_review"] = rewritten["reviews"][0]

        with self.assertRaisesRegex(PacketError, "metadata result hash|embedded metadata review"):
            build_deep_packet(alignment, frozen, {}, {}, {}, {})


if __name__ == "__main__":
    unittest.main()
