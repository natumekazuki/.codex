#!/usr/bin/env python3
"""Strictly validate phase results and aggregate Bootstrap record outcomes."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from review_routing import (
    aggregate_gate,
    aggregate_status,
    decide_disposition,
    decide_gate,
    unavailable_result,
    validate_routing_manifest,
)


class ResultValidationError(ValueError):
    """Raised when an AI result or final aggregation input is untrusted."""


PHASE_SPECS = {
    "metadata": {
        "version": "metadata-review-v1",
        "verdicts": {"VALID", "REDESIGN", "NEEDS_CONTEXT"},
        "keys": {"record_id", "verdict", "evidence", "unverified", "next_action"},
    },
    "alignment": {
        "version": "alignment-review-v1",
        "verdicts": {"ALIGNED", "MISMATCH", "RECHECK"},
        "keys": {
            "record_id",
            "metadata_hash",
            "source_hash",
            "verdict",
            "declared_boundary",
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
        "version": "deep-review-v1",
        "verdicts": {"APPROVE", "REDESIGN", "NEEDS_CONTEXT"},
        "keys": {
            "record_id",
            "metadata_hash",
            "source_hash",
            "verdict",
            "evidence",
            "unverified",
            "context_requirements",
            "next_action",
        },
    },
}


def validate_phase_result(
    phase: str, result: dict[str, Any], expected_records: list[dict[str, Any]]
) -> dict[str, Any]:
    try:
        spec = PHASE_SPECS[phase]
    except KeyError as exc:
        raise ResultValidationError(f"unknown phase: {phase}") from exc
    if set(result) != {"review_contract_version", "reviews"}:
        raise ResultValidationError("result has unexpected top-level keys")
    if result["review_contract_version"] != spec["version"]:
        raise ResultValidationError("result contract version is invalid")
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
            _validate_alignment(review)
        if phase == "metadata" and review["verdict"] == "NEEDS_CONTEXT":
            if not review["unverified"] or review["next_action"] is None:
                raise ResultValidationError("metadata NEEDS_CONTEXT requires unverified and next_action")
        if phase == "deep":
            if review["verdict"] in {"APPROVE", "REDESIGN"} and not review["evidence"]:
                raise ResultValidationError("completed deep verdict requires evidence")
            if review["verdict"] == "NEEDS_CONTEXT" and not review["context_requirements"]:
                raise ResultValidationError("deep NEEDS_CONTEXT requires context_requirements")
    if review_ids != expected_ids:
        raise ResultValidationError("review record set or order does not match the packet")
    return result


def aggregate_results(value: dict[str, Any]) -> dict[str, Any]:
    required = {
        "alignment_packet",
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
        if not isinstance(packet, dict) or set(packet) != {"review_contract_version", "records"}:
            raise ResultValidationError("alignment packet has unexpected keys")
        if packet["review_contract_version"] != "alignment-review-v1":
            raise ResultValidationError("alignment packet contract version is invalid")
        records = packet["records"]
        if not isinstance(records, list):
            raise ResultValidationError("alignment packet records must be an array")
        for record in records:
            _validate_aggregation_record(record)
        validate_phase_result(
            "metadata",
            {
                "review_contract_version": "metadata-review-v1",
                "reviews": [record["metadata_review"] for record in records],
            },
            records,
        )
        alignment_reviews = validate_phase_result(
            "alignment", value["alignment_result"], records
        )["reviews"]
        routing_entries = validate_routing_manifest(
            records,
            alignment_reviews,
            value["routing_manifest"],
            value["workflow_routing_context"],
        )
        required_records = [
            record
            for record, entry in zip(records, routing_entries)
            if entry["result"]["required"]
        ]
        sol_result = value["sol_result"]
        sol_by_id: dict[str, dict[str, Any]] = {}
        if sol_result is not None:
            sol_reviews = validate_phase_result("deep", sol_result, required_records)["reviews"]
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
                disposition = decide_disposition(
                    actual_boundary=alignment_review["actual_boundary"],
                    lifecycle=metadata["lifecycle"],
                    retention_basis=retention["retention_basis"],
                    expires_on=metadata.get("expires_on"),
                    review_when=metadata.get("review_when"),
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
        "review_contract_version": "review-final-v1",
        "records": final_records,
        "gate": aggregate_gate([record["gate"] for record in final_records]),
    }


def _validate_aggregation_record(record: Any) -> None:
    if not isinstance(record, dict):
        raise ResultValidationError("aggregation record must be an object")
    metadata = record.get("metadata")
    source_text = record.get("source_text")
    if not isinstance(metadata, dict) or not isinstance(source_text, str):
        raise ResultValidationError("aggregation record metadata and source_text are invalid")
    metadata_digest = "sha256:" + hashlib.sha256(
        json.dumps(metadata, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()
    source_digest = "sha256:" + hashlib.sha256(source_text.encode("utf-8")).hexdigest()
    if record.get("metadata_hash") != metadata_digest:
        raise ResultValidationError("aggregation metadata_hash does not match metadata")
    if record.get("source_hash") != source_digest:
        raise ResultValidationError("aggregation source_hash does not match source_text")


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


def _validate_alignment(review: dict[str, Any]) -> None:
    boundaries = {"consumer", "public-boundary", "component-behavior", "declaration", "implementation"}
    if review["actual_boundary"] not in boundaries:
        raise ResultValidationError("actual_boundary is invalid")
    if review["declared_boundary"] is not None and review["declared_boundary"] not in boundaries:
        raise ResultValidationError("declared_boundary is invalid")
    observables = _string_list(review["actual_observables"], "review.actual_observables")
    if not observables:
        raise ResultValidationError("actual_observables must not be empty")
    if not isinstance(review["overclaim"], bool):
        raise ResultValidationError("overclaim must be a boolean")
    candidates = {"KEEP_PERMANENT", "KEEP_TEMPORARY", "MOVE_TO_POLICY_CHECK", "DROP", None}
    if review["disposition_candidate"] not in candidates:
        raise ResultValidationError("disposition_candidate is invalid")
    if review["verdict"] in {"ALIGNED", "MISMATCH"} and not review["evidence"]:
        raise ResultValidationError("completed alignment verdict requires evidence")
    if review["verdict"] == "RECHECK" and not review["context_requirements"]:
        raise ResultValidationError("RECHECK requires context_requirements")


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
    parser.add_argument("phase", choices=["metadata", "alignment", "deep", "aggregate"])
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--packet", type=Path)
    args = parser.parse_args()
    try:
        value = _read_json(args.input)
        if args.phase == "aggregate":
            output = aggregate_results(value)
        else:
            if args.packet is None:
                raise ResultValidationError("--packet is required for phase validation")
            packet = _read_json(args.packet)
            output = validate_phase_result(args.phase, value, packet.get("records", []))
    except (OSError, json.JSONDecodeError, ResultValidationError) as exc:
        parser.error(str(exc))
    print(json.dumps(output, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
