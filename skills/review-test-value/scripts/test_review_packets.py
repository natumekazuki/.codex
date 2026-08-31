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


def extractor_result():
    metadata = {
        "kind": "contract",
        "claim": "packetがreview phaseの入力境界を保つ",
        "oracle": {"type": "adr", "ref": "ADR-0022"},
        "failure_mode": "metadata phaseへsourceを混入するかalignment phaseでrecordを欠落させる",
        "scope": "review-test-value-packet",
        "lifecycle": "permanent",
    }
    source_text = "def test_packet_boundary(self):\n    self.assertTrue(packet)\n"
    return {
        "schema_version": 1,
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
                "metadata": metadata,
                "source_text": source_text,
                "source_hash": sha256_text(source_text),
                "metadata_hash": sha256_text(canonical_json(metadata)),
            }
        ],
        "diagnostics": [],
    }


def metadata_result(packet, verdict="VALID"):
    return {
        "review_contract_version": "metadata-review-v1",
        "reviews": [
            {
                "record_id": record["record_id"],
                "verdict": verdict,
                "evidence": ["metadataだけでclaimとfailure modeを区別できる"],
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
    # @test-value v1
    # kind = "security"
    # claim = "metadata packetはopaque record IDとmetadataだけを含みtest sourceのlocatorと本文を含まない"
    # oracle = { type = "adr", ref = "ADR-0022" }
    # failure_mode = "Phase 1 packetへsource path、line、symbol、source text、source hashのいずれかが混入しmetadata不足を本文から補完できる"
    # scope = "metadata-review-packet"
    # lifecycle = "permanent"
    # @end-test-value
    def test_metadata_packet_excludes_all_source_material(self):
        packet = build_metadata_packet(extractor_result())

        self.assertEqual(packet["review_contract_version"], "metadata-review-v1")
        self.assertEqual(
            set(packet["records"][0]),
            {"record_id", "metadata_format_version", "metadata", "metadata_hash"},
        )
        self.assertRegex(packet["records"][0]["record_id"], r"^sha256:[0-9a-f]{64}$")
        self.assertNotIn("tests/test_packet.py", canonical_json(packet))

    # @test-value v1
    # kind = "invariant"
    # claim = "alignment packetは固定したPhase 1のrecord集合と順序を変更せず全recordへsourceを対応付ける"
    # oracle = { type = "adr", ref = "ADR-0022" }
    # failure_mode = "Phase 1 resultのrecordを欠落、追加、並べ替えしてもPhase 2 packetを構築し別recordの審査結果を対応付ける"
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

    # @test-value v1
    # kind = "contract"
    # claim = "Phase 1がREDESIGNのrecordもPhase 2 packetへ同じmetadata resultとsource hashを保って含める"
    # oracle = { type = "adr", ref = "ADR-0022" }
    # failure_mode = "REDESIGN recordをPhase 2から省略してactual boundaryと保持先候補を判定できなくする"
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

    # @test-value v1
    # kind = "security"
    # claim = "deep packetはalignment packetと同じrouting record集合およびcontent hashが一致するbounded contextだけから構築できる"
    # oracle = { type = "adr", ref = "ADR-0022" }
    # failure_mode = "別recordのroutingを混入するかcontext contentの改変後も以前のhashを正しい証拠としてSolへ渡す"
    # scope = "deep-review-packet"
    # lifecycle = "permanent"
    # @end-test-value
    def test_deep_packet_rejects_modified_context(self):
        extracted = extractor_result()
        phase1 = build_metadata_packet(extracted)
        alignment = build_alignment_packet(extracted, metadata_result(phase1))
        record = alignment["records"][0]
        alignment_result = {
            "review_contract_version": "alignment-review-v1",
            "reviews": [
                {
                    "record_id": record["record_id"],
                    "metadata_hash": record["metadata_hash"],
                    "source_hash": record["source_hash"],
                    "verdict": "RECHECK",
                    "declared_boundary": None,
                    "actual_boundary": "component-behavior",
                    "actual_observables": ["packet record"],
                    "overclaim": False,
                    "evidence": [],
                    "unverified": [],
                    "disposition_candidate": None,
                    "context_requirements": ["ADR-0022"],
                    "next_action": "ADRを確認する",
                }
            ],
        }
        routing = {
            record["record_id"]: {
                "required": True,
                "reasons": ["alignment-recheck"],
                "risk_tags": [],
                "audit_selected": False,
            }
        }
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
            build_deep_packet(alignment, alignment_result, routing, bad_context)
        extra_routing = copy.deepcopy(routing)
        extra_routing["sha256:" + "9" * 64] = copy.deepcopy(next(iter(routing.values())))
        with self.assertRaisesRegex(PacketError, "routing record set"):
            build_deep_packet(alignment, alignment_result, extra_routing, {})


if __name__ == "__main__":
    unittest.main()
