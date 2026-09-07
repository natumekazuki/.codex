import copy
import hashlib
import json
import sys
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from review_transport import (  # noqa: E402
    TransportError,
    canonical_result,
    model_packet,
    model_result_schema,
)
from validate_review_result import PHASE_SPECS, phase_result_schema  # noqa: E402


def canonical_json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha(value):
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def digest(value):
    return sha(canonical_json(value))


def metadata():
    return {
        "kind": "contract",
        "claim": "the gate preserves canonical ordering",
        "oracle": {"type": "adr", "ref": "ADR-0022"},
        "fault": "a reordered result is accepted for a different record",
        "observable": "the canonical result record order",
        "observation_boundary": "component-behavior",
        "scope": "review-transport",
        "lifecycle": "permanent",
    }


def source_record(*, source_path="tests/test_gate.py", line=10, context=False):
    value = "assert gate(record) == PASS\n"
    metadata_value = metadata()
    metadata_hash = digest(metadata_value)
    source = {
        "path": source_path,
        "symbol": "test_gate",
        "metadata_start_line": line - 3,
        "metadata_end_line": line - 1,
        "declaration_start_line": line,
        "declaration_end_line": line + 2,
    }
    record_id = digest(
        {
            "locator": {"path": source_path, "declaration_start_line": line},
            "metadata_hash": metadata_hash,
        }
    )
    record = {
        "record_id": record_id,
        "metadata_format_version": 2,
        "metadata": metadata_value,
        "metadata_hash": metadata_hash,
        "metadata_review": {
            "record_id": record_id,
            "metadata_hash": metadata_hash,
            "verdict": "VALID",
            "evidence": [
                {"fields": ["claim", "fault"], "finding": "COHERENT_BOUNDARY"}
            ],
            "unverified": [],
            "next_action": None,
        },
        "source": source,
        "source_text": value,
        "source_hash": sha(value),
        "adapter": "python",
        "coverage": "full",
    }
    if context:
        context_value = "The accepted contract says the final gate is deterministic."
        record.update(
            {
                "alignment_review": {
                    "record_id": record_id,
                    "metadata_hash": metadata_hash,
                    "source_hash": record["source_hash"],
                    "verdict": "RECHECK",
                    "actual_boundary": None,
                    "actual_observables": [],
                    "overclaim": False,
                    "evidence": [],
                    "unverified": [],
                    "context_requirements": ["accepted contract"],
                    "next_action": None,
                },
                "routing_reasons": ["alignment-context"],
                "risk_tags": [],
                "audit_selected": False,
                "context": [
                    {
                        "kind": "accepted-contract",
                        "ref": "docs/accepted-contract.md#gate",
                        "content": context_value,
                        "content_hash": sha(context_value),
                    }
                ],
                "included_scope": ["docs/accepted-contract.md#gate"],
                "excluded_scope": ["packet外のrepository source"],
            }
        )
    return record


def metadata_packet():
    record = source_record()
    return {
        "review_contract_version": "metadata-review-v3",
        "records": [
            {
                key: record[key]
                for key in ("record_id", "metadata_format_version", "metadata", "metadata_hash")
            }
        ],
    }


def deep_packet():
    record = source_record(context=True)
    packet = {
        "review_contract_version": "deep-review-v3",
        "metadata_result_hash": digest({"fixed": "metadata-result"}),
        "records": [record],
    }
    packet["input_hash"] = digest(
        {
            key: packet[key]
            for key in ("review_contract_version", "metadata_result_hash", "records")
        }
    )
    return packet


class ReviewTransportTests(unittest.TestCase):
    # @test-value v2
    # kind = "security"
    # claim = "metadata transportは意味審査に必要なmetadataとformat versionとbatch ordinalだけをモデルへ投影し、source locatorとhost identityを渡さない"
    # oracle = { type = "adr", ref = "ADR-0022" }
    # fault = "metadata packetへrecord ID、hash、source locatorを混入するか、作者がmetadataへ書いたSHA literalまで意味内容として除去する"
    # observable = "model_packet(metadata)のrecord fieldと意味文字列の保持"
    # observation_boundary = "component-behavior"
    # scope = "review-transport-metadata-projection"
    # lifecycle = "permanent"
    # @end-test-value
    def test_metadata_projection_contains_only_semantic_input(self):
        packet = metadata_packet()
        projected = model_packet("metadata", packet)
        self.assertEqual(
            projected,
            {
                "records": [
                    {
                        "ordinal": 0,
                        "metadata_format_version": 2,
                        "metadata": packet["records"][0]["metadata"],
                    }
                ]
            },
        )
        serialized = json.dumps(projected, ensure_ascii=False)
        self.assertNotIn("record_id", serialized)
        self.assertNotIn("metadata_hash", serialized)
        self.assertNotIn("declaration_start_line", serialized)
        # A SHA-looking string written by the author remains semantic content.
        packet["records"][0]["metadata"]["claim"] = "accept sha256:" + "a" * 64
        self.assertIn("sha256:" + "a" * 64, json.dumps(model_packet("metadata", packet)))

    # @test-value v2
    # kind = "security"
    # claim = "nested reviewとbounded contextのhost bindingはtransport projectionで除去し、contextの意味的refとcontentは保持する"
    # oracle = { type = "adr", ref = "ADR-0022" }
    # fault = "nested reviewまたはcontextへrecord hash、contract version、content hashを残すかverified refを失う"
    # observable = "model_packet(deep)のreview、context、included scope field"
    # observation_boundary = "component-behavior"
    # scope = "review-transport-recursive-stripping"
    # lifecycle = "permanent"
    # @end-test-value
    def test_nested_reviews_and_context_strip_host_bindings(self):
        packet = deep_packet()
        projected = model_packet("deep", packet)
        record = projected["records"][0]
        serialized = json.dumps(record, ensure_ascii=False)
        for field in (
            "record_id",
            "metadata_hash",
            "source_hash",
            "content_hash",
            "review_contract_version",
            "metadata_result_hash",
            "input_hash",
        ):
            self.assertNotIn(field, serialized)
        self.assertEqual(
            record["context"],
            [
                {
                    "ordinal": 0,
                    "kind": "accepted-contract",
                    "ref": "docs/accepted-contract.md#gate",
                    "content": record["context"][0]["content"],
                }
            ],
        )
        self.assertEqual(record["included_scope"], ["docs/accepted-contract.md#gate"])

    # @test-value v2
    # kind = "security"
    # claim = "model output schemaはbatch ordinalとrecord-bound semantic fieldsだけを許可し、phaseごとのcontext ordinal境界とalignmentの規範field削除を固定する"
    # oracle = { type = "adr", ref = "ADR-0022" }
    # fault = "schemaがopaque ID、hash、contract version、範囲外context ordinal、未使用のdisposition candidateを受理する"
    # observable = "model_result_schemaのproperties、enum、required field"
    # observation_boundary = "component-behavior"
    # scope = "review-transport-output-schema"
    # lifecycle = "permanent"
    # @end-test-value
    def test_schema_binds_ordinal_metadata_fields_and_context_ordinals(self):
        metadata_schema = model_result_schema("metadata", metadata_packet())
        self.assertEqual(set(metadata_schema["properties"]), {"reviews"})
        metadata_item = metadata_schema["properties"]["reviews"]["items"]["anyOf"][0]
        self.assertEqual(metadata_item["properties"]["ordinal"]["enum"], [0])
        self.assertNotIn("record_id", metadata_item["properties"])
        self.assertNotIn("metadata_hash", metadata_item["properties"])
        evidence_fields = metadata_item["properties"]["evidence"]["items"]["properties"]["fields"]["items"]
        self.assertIn("claim", evidence_fields["enum"])
        self.assertIn("oracle.ref", evidence_fields["enum"])

        deep_schema = model_result_schema("deep", deep_packet())
        deep_item = deep_schema["properties"]["reviews"]["items"]["anyOf"][0]
        self.assertNotIn("source_hash", deep_item["properties"])
        context_item = deep_item["properties"]["context_resolution"]["properties"]["context_evidence"]["items"]
        self.assertEqual(context_item["properties"], {"ordinal": {"type": "integer", "enum": [0]}})
        self.assertEqual(context_item["required"], ["ordinal"])

        alignment_record = source_record()
        alignment_packet = {
            "review_contract_version": "alignment-review-v3",
            "metadata_result_hash": digest({"fixed": "result"}),
            "records": [alignment_record],
        }
        alignment_schema = model_result_schema("alignment", alignment_packet)
        alignment_item = alignment_schema["properties"]["reviews"]["items"]["anyOf"][0]
        self.assertNotIn("disposition_candidate", alignment_item["properties"])

    # @test-value v2
    # kind = "security"
    # claim = "hostは検証済みbatch ordinalからcanonical phase resultのidentity、hash、contract versionを付与する"
    # oracle = { type = "adr", ref = "ADR-0022" }
    # fault = "意味判断だけのmodel resultへhost identityを付与せずcanonical artifactを構築するか、ordinalを結果へ残してbindingを二重化する"
    # observable = "canonical_result(metadata)のreview identityとcontract version"
    # observation_boundary = "component-behavior"
    # scope = "review-transport-host-identity"
    # lifecycle = "permanent"
    # @end-test-value
    def test_metadata_canonical_result_attaches_host_identity(self):
        packet = metadata_packet()
        record = packet["records"][0]
        model = {
            "reviews": [
                {
                    "ordinal": 0,
                    "verdict": "VALID",
                    "evidence": [
                        {"fields": ["claim", "fault"], "finding": "COHERENT_BOUNDARY"}
                    ],
                    "unverified": [],
                    "next_action": None,
                }
            ]
        }
        result = canonical_result("metadata", model, packet)
        self.assertEqual(result["review_contract_version"], "metadata-review-v3")
        self.assertEqual(result["reviews"][0]["record_id"], record["record_id"])
        self.assertEqual(result["reviews"][0]["metadata_hash"], record["metadata_hash"])
        self.assertNotIn("ordinal", result["reviews"][0])

    # @test-value v2
    # kind = "security"
    # claim = "transport validatorはmodelが供給したhost identity、hash、重複・範囲外・boolean ordinalをcanonical resultへ受理しない"
    # oracle = { type = "adr", ref = "ADR-0022" }
    # fault = "modelがrecord bindingを差し替えるか同じordinalを重複させても意味結果として受け入れて別recordへ結合する"
    # observable = "canonical_resultのTransportErrorとordinal集合検証"
    # observation_boundary = "component-behavior"
    # scope = "review-transport-ordinal-validation"
    # lifecycle = "permanent"
    # @end-test-value
    def test_model_cannot_supply_identity_or_hash_or_wrong_ordinal(self):
        packet = metadata_packet()
        good = {
            "ordinal": 0,
            "verdict": "VALID",
            "evidence": [{"fields": ["claim"], "finding": "SELF_CONTAINED_CLAIM"}],
            "unverified": [],
            "next_action": None,
        }
        with self.assertRaises(TransportError):
            canonical_result("metadata", {"reviews": [{**good, "record_id": packet["records"][0]["record_id"]}]}, packet)
        with self.assertRaises(TransportError):
            canonical_result("metadata", {"reviews": [{**good, "metadata_hash": packet["records"][0]["metadata_hash"]}]}, packet)
        with self.assertRaises(TransportError):
            canonical_result("metadata", {"reviews": [{**good, "ordinal": True}]}, packet)
        with self.assertRaises(TransportError):
            canonical_result("metadata", {"reviews": [{**good, "ordinal": 1}]}, packet)

        second = source_record(source_path="tests/test_other_gate.py", line=20)
        packet["records"].append(
            {
                key: second[key]
                for key in ("record_id", "metadata_format_version", "metadata", "metadata_hash")
            }
        )
        two_reviews = {"reviews": [{**good, "ordinal": 0}, {**good, "ordinal": 0}]}
        with self.assertRaises(TransportError):
            canonical_result("metadata", two_reviews, packet)

    # @test-value v2
    # kind = "security"
    # claim = "deep context evidenceは検証済みcontext ordinalからhostがrefとcontent hashを結合し、任意のcontext bindingを許可しない"
    # oracle = { type = "adr", ref = "ADR-0022" }
    # fault = "modelがpacket外のrefまたは改変content hashを指定するか範囲外ordinalを使って別contextを証拠にする"
    # observable = "canonical_result(deep)のcontext evidenceとTransportError"
    # observation_boundary = "component-behavior"
    # scope = "review-transport-context-binding"
    # lifecycle = "permanent"
    # @end-test-value
    def test_deep_context_ordinal_is_bound_to_verified_ref_and_hash(self):
        packet = deep_packet()
        model = {
            "reviews": [
                {
                    "ordinal": 0,
                    "verdict": "APPROVE",
                    "evidence": ["bounded contract context"],
                    "unverified": [],
                    "context_requirements": [],
                    "context_resolution": {
                        "actual_boundary": "component-behavior",
                        "actual_observables": ["the final gate"],
                        "context_evidence": [{"ordinal": 0}],
                    },
                    "next_action": None,
                }
            ]
        }
        result = canonical_result("deep", model, packet)
        evidence = result["reviews"][0]["context_resolution"]["context_evidence"]
        context = packet["records"][0]["context"][0]
        self.assertEqual(evidence, [{"ref": context["ref"], "content_hash": context["content_hash"]}])

        invalid = copy.deepcopy(model)
        invalid["reviews"][0]["context_resolution"]["context_evidence"] = [{"ordinal": 1}]
        with self.assertRaises(TransportError):
            canonical_result("deep", invalid, packet)


if __name__ == "__main__":
    unittest.main()
