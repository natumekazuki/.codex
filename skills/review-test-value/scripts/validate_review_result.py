#!/usr/bin/env python3
"""Strictly validate phase results and aggregate record outcomes."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from extract_test_values import validate_metadata
from review_routing import (
    aggregate_gate,
    aggregate_status,
    decide_disposition,
    decide_gate,
    unavailable_result,
    BOUNDARIES,
    validate_routing_manifest,
)


class ResultValidationError(ValueError):
    """Raised when an AI result or final aggregation input is untrusted."""


SOURCE_KEYS = {
    "path",
    "symbol",
    "metadata_start_line",
    "metadata_end_line",
    "declaration_start_line",
    "declaration_end_line",
}
ALIGNMENT_RECORD_KEYS = {
    "record_id",
    "metadata_format_version",
    "metadata",
    "metadata_hash",
    "metadata_review",
    "source",
    "source_text",
    "source_hash",
    "adapter",
    "coverage",
}
DEEP_RECORD_KEYS = ALIGNMENT_RECORD_KEYS | {
    "alignment_review",
    "routing_reasons",
    "risk_tags",
    "audit_selected",
    "context",
    "included_scope",
    "excluded_scope",
}
METADATA_EVIDENCE_KEYS = {"fields", "finding"}
METADATA_EVIDENCE_FINDINGS = {
    "SELF_CONTAINED_CLAIM",
    "CONCRETE_FAULT",
    "COHERENT_BOUNDARY",
    "LIFECYCLE_ALIGNED",
    "ORACLE_DECLARED",
    "CLAIM_NOT_FALSIFIABLE",
    "FAULT_NOT_SPECIFIC",
    "BOUNDARY_INCONSISTENT",
    "ORACLE_CIRCULAR",
}
NEGATIVE_METADATA_FINDINGS = {
    "CLAIM_NOT_FALSIFIABLE",
    "FAULT_NOT_SPECIFIC",
    "BOUNDARY_INCONSISTENT",
    "ORACLE_CIRCULAR",
}

PHASE_SPECS = {
    "metadata": {
        "version": "metadata-review-v2",
        "verdicts": {"VALID", "REDESIGN", "NEEDS_CONTEXT"},
        "keys": {
            "record_id",
            "metadata_hash",
            "verdict",
            "evidence",
            "unverified",
            "next_action",
        },
    },
    "alignment": {
        "version": "alignment-review-v2",
        "verdicts": {"ALIGNED", "MISMATCH", "RECHECK"},
        "keys": {
            "record_id",
            "metadata_hash",
            "source_hash",
            "verdict",
            "actual_boundary",
            "actual_observables",
            "overclaim",
            "evidence",
            "unverified",
            "disposition_candidate",
            "context_requirements",
            "next_action",
        },
    },
    "deep": {
        "version": "deep-review-v2",
        "verdicts": {"APPROVE", "REDESIGN", "NEEDS_CONTEXT"},
        "keys": {
            "record_id",
            "metadata_hash",
            "source_hash",
            "verdict",
            "evidence",
            "unverified",
            "context_requirements",
            "context_resolution",
            "next_action",
        },
    },
}

_SCHEMA_DRAFT = "https://json-schema.org/draft/2020-12/schema"
def phase_result_schema(phase: str) -> dict[str, Any]:
    """Build the codex exec output schema for one v2 review phase.

    This schema describes the result shape and local field constraints. Packet
    identity, review order, hashes, and frozen-result comparisons remain the
    responsibility of ``validate_phase_result``.
    """
    try:
        spec = PHASE_SPECS[phase]
    except KeyError as exc:
        raise ResultValidationError(f"unknown phase: {phase}") from exc

    # Keep this to the Codex Structured Outputs supported subset. Local
    # non-empty, conditional, hash, order, and packet checks stay in the
    # executable validator below.
    string = {"type": "string"}
    string_list = {"type": "array", "items": string}
    hash_string = {"type": "string"}
    review_properties: dict[str, Any] = {
        "record_id": hash_string,
        "metadata_hash": hash_string,
        "verdict": {"type": "string", "enum": sorted(spec["verdicts"])},
        "evidence": string_list,
        "unverified": string_list,
        "next_action": {"type": ["string", "null"]},
    }
    if phase != "metadata":
        review_properties.update(
            {
                "source_hash": hash_string,
                "context_requirements": string_list,
            }
        )
    if phase == "metadata":
        review_properties["evidence"] = {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["fields", "finding"],
                "properties": {
                    "fields": {
                        "type": "array",
                        "items": string,
                    },
                    "finding": {
                        "type": "string",
                        "enum": sorted(METADATA_EVIDENCE_FINDINGS),
                    },
                },
            },
        }
    elif phase == "alignment":
        review_properties.update(
            {
                "actual_boundary": {
                    "type": ["string", "null"],
                    "enum": [*sorted(BOUNDARIES), None],
                },
                "actual_observables": string_list,
                "overclaim": {"type": "boolean"},
                "disposition_candidate": {
                    "type": ["string", "null"],
                    "enum": [
                        "KEEP_PERMANENT",
                        "KEEP_TEMPORARY",
                        "MOVE_TO_POLICY_CHECK",
                        "DROP",
                        None,
                    ],
                },
            }
        )
    elif phase == "deep":
        review_properties["context_resolution"] = {
            "type": ["object", "null"],
            "additionalProperties": False,
            "required": ["actual_boundary", "actual_observables", "context_evidence"],
            "properties": {
                "actual_boundary": {"type": "string", "enum": sorted(BOUNDARIES)},
                "actual_observables": string_list,
                "context_evidence": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["ref", "content_hash"],
                        "properties": {"ref": string, "content_hash": hash_string},
                    },
                },
            },
        }
    review_schema: dict[str, Any] = {
        "type": "object",
        "additionalProperties": False,
        "required": sorted(spec["keys"]),
        "properties": review_properties,
    }
    top_properties: dict[str, Any] = {
        "review_contract_version": {"type": "string", "enum": [spec["version"]]},
        "reviews": {"type": "array", "items": review_schema},
    }
    required = ["review_contract_version", "reviews"]
    if phase == "deep":
        top_properties["input_hash"] = hash_string
        required.append("input_hash")
    return {
        "$schema": _SCHEMA_DRAFT,
        "title": f"{spec['version']} result",
        "type": "object",
        "additionalProperties": False,
        "required": required,
        "properties": top_properties,
    }


def validate_phase_result(
    phase: str,
    result: dict[str, Any],
    expected_records: list[dict[str, Any]],
    expected_input_hash: str | None = None,
) -> dict[str, Any]:
    try:
        spec = PHASE_SPECS[phase]
    except KeyError as exc:
        raise ResultValidationError(f"unknown phase: {phase}") from exc
    top_level_keys = {"review_contract_version", "reviews"}
    if phase == "deep":
        top_level_keys.add("input_hash")
    if set(result) != top_level_keys:
        raise ResultValidationError("result has unexpected top-level keys")
    if result["review_contract_version"] != spec["version"]:
        raise ResultValidationError("result contract version is invalid")
    if phase == "deep":
        if expected_input_hash is None:
            raise ResultValidationError("deep result requires an expected input hash")
        if result["input_hash"] != expected_input_hash:
            raise ResultValidationError("deep result input_hash does not match the packet")
    reviews = result["reviews"]
    if not isinstance(reviews, list):
        raise ResultValidationError("reviews must be an array")
    if not isinstance(expected_records, list) or any(
        not isinstance(record, dict) or "record_id" not in record
        for record in expected_records
    ):
        raise ResultValidationError("expected records are invalid")
    expected_ids = [_string(record["record_id"], "packet.record_id") for record in expected_records]
    if len(expected_ids) != len(set(expected_ids)):
        raise ResultValidationError("packet contains duplicate record_id")
    review_ids = []
    expected_by_id = {record["record_id"]: record for record in expected_records}
    for review in reviews:
        if not isinstance(review, dict) or set(review) != spec["keys"]:
            raise ResultValidationError("review has unexpected keys")
        record_id = _string(review["record_id"], "review.record_id")
        review_ids.append(record_id)
        if review["verdict"] not in spec["verdicts"]:
            raise ResultValidationError("review verdict is invalid")
        if phase == "metadata":
            expected = expected_by_id.get(record_id)
            if expected is None:
                raise ResultValidationError("review contains an unexpected record")
            if review["metadata_hash"] != expected.get("metadata_hash"):
                raise ResultValidationError("metadata_hash does not match the packet")
            _validate_metadata_evidence(review["evidence"], expected.get("metadata"))
        else:
            _string_list(review["evidence"], "review.evidence")
        _string_list(review["unverified"], "review.unverified")
        if review["next_action"] is not None:
            _string(review["next_action"], "review.next_action")
        if phase != "metadata":
            expected = expected_by_id.get(record_id)
            if expected is None:
                raise ResultValidationError("review contains an unexpected record")
            if review["metadata_hash"] != expected["metadata_hash"]:
                raise ResultValidationError("metadata_hash does not match the packet")
            if review["source_hash"] != expected["source_hash"]:
                raise ResultValidationError("source_hash does not match the packet")
            _string_list(review["context_requirements"], "review.context_requirements")
        if phase == "alignment":
            _validate_alignment(review, expected)
        if phase == "metadata" and review["verdict"] == "NEEDS_CONTEXT":
            if not review["unverified"] or review["next_action"] is None:
                raise ResultValidationError("metadata NEEDS_CONTEXT requires unverified and next_action")
        if phase == "metadata" and review["verdict"] in {"VALID", "REDESIGN"}:
            if not review["evidence"]:
                raise ResultValidationError("completed metadata verdict requires evidence")
            findings = {item["finding"] for item in review["evidence"]}
            if review["verdict"] == "VALID" and findings & NEGATIVE_METADATA_FINDINGS:
                raise ResultValidationError("VALID metadata review must not contain negative findings")
            if review["verdict"] == "REDESIGN" and not findings & NEGATIVE_METADATA_FINDINGS:
                raise ResultValidationError("REDESIGN metadata review requires a negative finding")
        if phase == "deep":
            if review["verdict"] in {"APPROVE", "REDESIGN"} and not review["evidence"]:
                raise ResultValidationError("completed deep verdict requires evidence")
            if review["verdict"] == "NEEDS_CONTEXT" and not review["context_requirements"]:
                raise ResultValidationError("deep NEEDS_CONTEXT requires context_requirements")
            _validate_context_resolution(review, expected)
    if review_ids != expected_ids:
        raise ResultValidationError("review record set or order does not match the packet")
    return result


def result_hash(result: dict[str, Any]) -> str:
    return _sha256_text(_canonical_json(result))


def validate_alignment_packet(
    packet: dict[str, Any], metadata_result: dict[str, Any]
) -> list[dict[str, Any]]:
    if not isinstance(packet, dict) or set(packet) != {
        "review_contract_version",
        "metadata_result_hash",
        "records",
    }:
        raise ResultValidationError("alignment packet has unexpected keys")
    if packet["review_contract_version"] != "alignment-review-v2":
        raise ResultValidationError("alignment packet contract version is invalid")
    records = packet["records"]
    if not isinstance(records, list):
        raise ResultValidationError("alignment packet records must be an array")
    metadata_records = []
    for record in records:
        _validate_alignment_record(record)
        metadata_records.append(
            {
                "record_id": record["record_id"],
                "metadata_format_version": record["metadata_format_version"],
                "metadata": record["metadata"],
                "metadata_hash": record["metadata_hash"],
            }
        )
    reviews = validate_phase_result("metadata", metadata_result, metadata_records)["reviews"]
    if packet["metadata_result_hash"] != result_hash(metadata_result):
        raise ResultValidationError("metadata result hash does not match the fixed result")
    if [record["metadata_review"] for record in records] != reviews:
        raise ResultValidationError("embedded metadata review does not match the fixed result")
    return records


def validate_deep_packet(
    packet: dict[str, Any],
    alignment_packet: dict[str, Any],
    alignment_reviews: list[dict[str, Any]],
    routing_entries: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not isinstance(packet, dict) or set(packet) != {
        "review_contract_version",
        "metadata_result_hash",
        "input_hash",
        "records",
    }:
        raise ResultValidationError("deep packet has unexpected keys")
    if packet["review_contract_version"] != "deep-review-v2":
        raise ResultValidationError("deep packet contract version is invalid")
    if packet["metadata_result_hash"] != alignment_packet["metadata_result_hash"]:
        raise ResultValidationError("deep packet metadata_result_hash does not match alignment")
    packet_content = {
        "review_contract_version": packet["review_contract_version"],
        "metadata_result_hash": packet["metadata_result_hash"],
        "records": packet["records"],
    }
    if packet["input_hash"] != result_hash(packet_content):
        raise ResultValidationError("deep packet input_hash does not match packet content")
    records = packet["records"]
    if not isinstance(records, list):
        raise ResultValidationError("deep packet records must be an array")
    for record in records:
        if not isinstance(record, dict) or set(record) != DEEP_RECORD_KEYS:
            raise ResultValidationError("deep packet record has unexpected keys")
    required = [
        (record, review, entry["result"])
        for record, review, entry in zip(
            alignment_packet["records"], alignment_reviews, routing_entries
        )
        if entry["result"]["required"]
    ]
    if [record.get("record_id") for record in records if isinstance(record, dict)] != [
        record["record_id"] for record, _, _ in required
    ]:
        raise ResultValidationError("deep packet record set or order does not match routing")
    for deep_record, (alignment_record, alignment_review, route) in zip(records, required):
        for key in ALIGNMENT_RECORD_KEYS:
            if deep_record[key] != alignment_record[key]:
                raise ResultValidationError(f"deep packet {key} does not match alignment")
        if deep_record["alignment_review"] != alignment_review:
            raise ResultValidationError("deep packet alignment_review does not match fixed result")
        if deep_record["routing_reasons"] != route["reasons"]:
            raise ResultValidationError("deep packet routing_reasons do not match routing")
        if deep_record["risk_tags"] != route["risk_tags"]:
            raise ResultValidationError("deep packet risk_tags do not match routing")
        if deep_record["audit_selected"] != route["audit_selected"]:
            raise ResultValidationError("deep packet audit_selected does not match routing")
        contexts = deep_record["context"]
        if not isinstance(contexts, list):
            raise ResultValidationError("deep packet context must be an array")
        refs = []
        for context in contexts:
            if not isinstance(context, dict) or set(context) != {
                "kind",
                "ref",
                "content",
                "content_hash",
            }:
                raise ResultValidationError("deep packet context has unexpected keys")
            ref = _string(context["ref"], "deep context.ref")
            _string(context["kind"], "deep context.kind")
            content = _string(context["content"], "deep context.content")
            if context["content_hash"] != _sha256_text(content):
                raise ResultValidationError("deep packet context hash does not match content")
            refs.append(ref)
        if deep_record["included_scope"] != refs:
            raise ResultValidationError("deep packet included_scope does not match context")
        if deep_record["excluded_scope"] != ["packet外のrepository source"]:
            raise ResultValidationError("deep packet excluded_scope is invalid")
    return records


def aggregate_results(value: dict[str, Any]) -> dict[str, Any]:
    required = {
        "alignment_packet",
        "metadata_result",
        "deep_packet",
        "alignment_result",
        "workflow_routing_context",
        "routing_manifest",
        "sol_result",
        "retention_records",
    }
    if set(value) != required:
        raise ResultValidationError("aggregation input has unexpected keys")
    try:
        packet = value["alignment_packet"]
        records = validate_alignment_packet(packet, value["metadata_result"])
        alignment_reviews = validate_phase_result(
            "alignment", value["alignment_result"], records
        )["reviews"]
        routing_entries = validate_routing_manifest(
            records,
            alignment_reviews,
            value["routing_manifest"],
            value["workflow_routing_context"],
        )
        required_records = validate_deep_packet(
            value["deep_packet"], packet, alignment_reviews, routing_entries
        )
        sol_result = value["sol_result"]
        sol_by_id: dict[str, dict[str, Any]] = {}
        if sol_result is not None:
            sol_reviews = validate_phase_result(
                "deep",
                sol_result,
                required_records,
                value["deep_packet"]["input_hash"],
            )["reviews"]
            sol_by_id = {review["record_id"]: review for review in sol_reviews}
        retention_by_id = _validate_retention_records(value["retention_records"], records)
        alignment_by_id = {review["record_id"]: review for review in alignment_reviews}
        route_by_id = {entry["record_id"]: entry["result"] for entry in routing_entries}
        final_records = []
        for record in records:
            record_id = record["record_id"]
            route = route_by_id[record_id]
            sol_review = sol_by_id.get(record_id)
            if route["required"] and (
                sol_review is None or sol_review["verdict"] == "NEEDS_CONTEXT"
            ):
                outcome = unavailable_result()
            else:
                metadata = record["metadata"]
                alignment_review = alignment_by_id[record_id]
                status = aggregate_status(
                    record["metadata_review"]["verdict"],
                    alignment_review["verdict"],
                    sol_required=route["required"],
                    sol_verdict=sol_review["verdict"] if sol_review is not None else None,
                )
                retention = retention_by_id[record_id]
                actual_boundary = alignment_review["actual_boundary"]
                if alignment_review["verdict"] == "RECHECK" and sol_review is not None:
                    resolution = sol_review["context_resolution"]
                    if resolution is not None:
                        actual_boundary = resolution["actual_boundary"]
                disposition = decide_disposition(
                    actual_boundary=actual_boundary,
                    lifecycle=metadata["lifecycle"],
                    retention_basis=retention["retention_basis"],
                    expires_on=metadata.get("expires_on"),
                    review_when=metadata.get("review_when"),
                    remove_when=metadata.get("remove_when"),
                )
                if disposition is None:
                    outcome = unavailable_result()
                else:
                    outcome = {
                        "status": status,
                        "disposition": disposition,
                        "gate": decide_gate(status, disposition, retention["artifact_state"]),
                    }
            final_records.append({"record_id": record_id, **outcome})
    except (KeyError, TypeError, ValueError) as exc:
        raise ResultValidationError(str(exc)) from exc
    return {
        "review_contract_version": "review-final-v2",
        "records": final_records,
        "gate": aggregate_gate([record["gate"] for record in final_records]),
    }


def _validate_alignment_record(record: Any) -> None:
    if not isinstance(record, dict) or set(record) != ALIGNMENT_RECORD_KEYS:
        raise ResultValidationError("alignment packet record has unexpected keys")
    source = record["source"]
    if not isinstance(source, dict) or set(source) != SOURCE_KEYS:
        raise ResultValidationError("alignment packet source has unexpected keys")
    metadata = record["metadata"]
    errors = validate_metadata(metadata, 2)
    if errors:
        raise ResultValidationError("record.metadata is invalid: " + "; ".join(errors))
    if record["metadata_format_version"] != 2:
        raise ResultValidationError("metadata_format_version must be 2")
    if record["metadata_hash"] != _sha256_text(_canonical_json(metadata)):
        raise ResultValidationError("alignment packet metadata_hash does not match metadata")
    if record["source_hash"] != _sha256_text(_string(record["source_text"], "record.source_text")):
        raise ResultValidationError("alignment packet source_hash does not match source_text")
    locator = {
        "path": _string(source["path"], "record.source.path"),
        "declaration_start_line": _positive_int(
            source["declaration_start_line"], "record.source.declaration_start_line"
        ),
    }
    current_id = _sha256_text(
        _canonical_json({"locator": locator, "metadata_hash": record["metadata_hash"]})
    )
    deleted_id = _sha256_text(
        _canonical_json(
            {
                "transition": "DELETED",
                "locator": locator,
                "source_hash": record["source_hash"],
                "metadata_hash": record["metadata_hash"],
            }
        )
    )
    if record["record_id"] not in {current_id, deleted_id}:
        raise ResultValidationError(
            "record_id does not match the current or deleted source identity"
        )
    _string(source["symbol"], "record.source.symbol")
    metadata_start = _positive_int(
        source["metadata_start_line"], "record.source.metadata_start_line"
    )
    metadata_end = _positive_int(
        source["metadata_end_line"], "record.source.metadata_end_line"
    )
    declaration_start = _positive_int(
        source["declaration_start_line"], "record.source.declaration_start_line"
    )
    declaration_end = _positive_int(
        source["declaration_end_line"], "record.source.declaration_end_line"
    )
    if not metadata_start <= metadata_end < declaration_start <= declaration_end:
        raise ResultValidationError("source line range is invalid")
    _string(record["adapter"], "record.adapter")
    _string(record["coverage"], "record.coverage")


def _validate_metadata_evidence(value: Any, metadata: Any) -> None:
    if not isinstance(metadata, dict):
        raise ResultValidationError("packet metadata is invalid")
    if not isinstance(value, list):
        raise ResultValidationError("review.evidence must be an array")
    for item in value:
        if not isinstance(item, dict) or set(item) != METADATA_EVIDENCE_KEYS:
            raise ResultValidationError("metadata evidence has unexpected keys")
        fields = _string_list(item["fields"], "metadata evidence.fields")
        if not fields or len(fields) != len(set(fields)):
            raise ResultValidationError("metadata evidence.fields must be unique and non-empty")
        for field in fields:
            root = field.split(".", 1)[0]
            if root not in metadata or field not in set(metadata) | {"oracle.type", "oracle.ref"}:
                raise ResultValidationError("metadata evidence references an unavailable field")
        if item["finding"] not in METADATA_EVIDENCE_FINDINGS:
            raise ResultValidationError("metadata evidence finding is invalid")


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256_text(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _positive_int(value: Any, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ResultValidationError(f"{name} must be a positive integer")
    return value


def _validate_retention_records(
    value: Any, records: list[dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    if not isinstance(value, list):
        raise ResultValidationError("retention_records must be an array")
    expected_ids = [record["record_id"] for record in records]
    actual_ids = []
    by_id = {}
    for item in value:
        if not isinstance(item, dict) or set(item) != {
            "record_id",
            "retention_basis",
            "artifact_state",
        }:
            raise ResultValidationError("retention record has unexpected keys")
        record_id = _string(item["record_id"], "retention.record_id")
        actual_ids.append(record_id)
        if item["retention_basis"] not in {"PRESENT", "ABSENT", "UNRESOLVED"}:
            raise ResultValidationError("retention_basis is invalid")
        if item["artifact_state"] not in {
            "PERMANENT_TEST",
            "TEMPORARY_TEST",
            "TEST_PRESENT",
            "TEST_ABSENT",
        }:
            raise ResultValidationError("artifact_state is invalid")
        by_id[record_id] = item
    if actual_ids != expected_ids:
        raise ResultValidationError("retention record set or order does not match the packet")
    return by_id


def _validate_alignment(review: dict[str, Any], expected: dict[str, Any]) -> None:
    actual_boundary = review["actual_boundary"]
    if actual_boundary is not None and actual_boundary not in BOUNDARIES:
        raise ResultValidationError("actual_boundary is invalid")
    observables = _string_list(review["actual_observables"], "review.actual_observables")
    if not isinstance(review["overclaim"], bool):
        raise ResultValidationError("overclaim must be a boolean")
    if review["verdict"] == "ALIGNED":
        if actual_boundary is None or not observables:
            raise ResultValidationError("ALIGNED review requires a boundary and observables")
        if review["overclaim"]:
            raise ResultValidationError("ALIGNED review must not report overclaim")
        metadata = expected.get("metadata")
        if not isinstance(metadata, dict) or metadata.get("observation_boundary") != actual_boundary:
            raise ResultValidationError(
                "ALIGNED review must match metadata observation_boundary"
            )
    if review["verdict"] == "MISMATCH" and (actual_boundary is None or not observables):
        raise ResultValidationError("MISMATCH review requires a boundary and observables")
    candidates = {"KEEP_PERMANENT", "KEEP_TEMPORARY", "MOVE_TO_POLICY_CHECK", "DROP", None}
    if review["disposition_candidate"] not in candidates:
        raise ResultValidationError("disposition_candidate is invalid")
    if review["verdict"] in {"ALIGNED", "MISMATCH"} and not review["evidence"]:
        raise ResultValidationError("completed alignment verdict requires evidence")
    if review["verdict"] == "RECHECK" and not review["context_requirements"]:
        raise ResultValidationError("RECHECK requires context_requirements")


def _validate_context_resolution(review: dict[str, Any], expected: dict[str, Any]) -> None:
    alignment_review = expected.get("alignment_review")
    if not isinstance(alignment_review, dict):
        raise ResultValidationError("deep packet alignment_review is invalid")
    resolution = review["context_resolution"]
    completed = review["verdict"] in {"APPROVE", "REDESIGN"}
    if alignment_review.get("verdict") != "RECHECK":
        if resolution is not None:
            raise ResultValidationError("non-RECHECK deep review must not resolve context")
        return
    if not completed:
        if resolution is not None:
            raise ResultValidationError("NEEDS_CONTEXT deep review must not resolve context")
        return
    if not isinstance(resolution, dict) or set(resolution) != {
        "actual_boundary",
        "actual_observables",
        "context_evidence",
    }:
        raise ResultValidationError("completed RECHECK deep review requires context_resolution")
    boundary = resolution["actual_boundary"]
    if boundary not in BOUNDARIES:
        raise ResultValidationError("context_resolution actual_boundary is invalid")
    observables = _string_list(
        resolution["actual_observables"], "context_resolution.actual_observables"
    )
    if not observables:
        raise ResultValidationError("context_resolution actual_observables must not be empty")
    evidence = resolution["context_evidence"]
    if not isinstance(evidence, list) or not evidence:
        raise ResultValidationError("context_resolution context_evidence must not be empty")
    available = set()
    for context in expected.get("context", []):
        if isinstance(context, dict):
            available.add((context.get("ref"), context.get("content_hash")))
    for item in evidence:
        if not isinstance(item, dict) or set(item) != {"ref", "content_hash"}:
            raise ResultValidationError("context_resolution evidence has unexpected keys")
        pair = (
            _string(item["ref"], "context_resolution context ref"),
            _string(item["content_hash"], "context_resolution context hash"),
        )
        if pair not in available:
            raise ResultValidationError("context_resolution evidence does not match deep context")
    luna_boundary = alignment_review.get("actual_boundary")
    if review["verdict"] == "APPROVE" and luna_boundary is not None and boundary != luna_boundary:
        raise ResultValidationError("APPROVE context_resolution contradicts known Luna boundary")
    metadata = expected.get("metadata")
    declared_boundary = (
        metadata.get("observation_boundary") if isinstance(metadata, dict) else None
    )
    if review["verdict"] == "APPROVE" and boundary != declared_boundary:
        raise ResultValidationError(
            "APPROVE context_resolution must match metadata observation_boundary"
        )


def _string(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ResultValidationError(f"{name} must be a non-empty string")
    return value


def _string_list(value: Any, name: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
        raise ResultValidationError(f"{name} must be an array of non-empty strings")
    return value


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ResultValidationError(f"{path} must contain a JSON object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", nargs="?", choices=["metadata", "alignment", "deep", "aggregate"])
    parser.add_argument("--input", type=Path)
    parser.add_argument("--packet", type=Path)
    parser.add_argument("--emit-schema", choices=["metadata", "alignment", "deep"])
    args = parser.parse_args()
    try:
        if args.emit_schema is not None:
            if args.phase is not None or args.input is not None or args.packet is not None:
                raise ResultValidationError("--emit-schema cannot be combined with phase, --input, or --packet")
            output = phase_result_schema(args.emit_schema)
            print(json.dumps(output, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
            return 0
        if args.phase is None or args.input is None:
            raise ResultValidationError("phase and --input are required unless --emit-schema is used")
        value = _read_json(args.input)
        if args.phase == "aggregate":
            output = aggregate_results(value)
        else:
            if args.packet is None:
                raise ResultValidationError("--packet is required for phase validation")
            packet = _read_json(args.packet)
            output = validate_phase_result(
                args.phase,
                value,
                packet.get("records", []),
                packet.get("input_hash") if args.phase == "deep" else None,
            )
    except (OSError, json.JSONDecodeError, ResultValidationError) as exc:
        parser.error(str(exc))
    print(json.dumps(output, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
