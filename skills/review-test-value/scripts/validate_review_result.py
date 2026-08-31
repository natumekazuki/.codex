#!/usr/bin/env python3
"""Strictly validate phase results and aggregate Bootstrap record outcomes."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from review_routing import aggregate_status, decide_disposition, decide_gate


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


def aggregate_record(record: dict[str, Any]) -> dict[str, Any]:
    required = {
        "metadata_verdict",
        "alignment_verdict",
        "sol_required",
        "sol_verdict",
        "actual_boundary",
        "metadata",
        "retention_basis",
        "artifact_state",
    }
    if set(record) != required:
        raise ResultValidationError("aggregation input has unexpected keys")
    try:
        status = aggregate_status(
            record["metadata_verdict"],
            record["alignment_verdict"],
            sol_required=record["sol_required"],
            sol_verdict=record["sol_verdict"],
        )
        metadata = record["metadata"]
        disposition = decide_disposition(
            actual_boundary=record["actual_boundary"],
            lifecycle=metadata["lifecycle"],
            retention_basis=record["retention_basis"],
            expires_on=metadata.get("expires_on"),
            review_when=metadata.get("review_when"),
        )
        if disposition is None:
            status = "NEEDS_CONTEXT"
        gate = decide_gate(status, disposition, record["artifact_state"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ResultValidationError(str(exc)) from exc
    return {"status": status, "disposition": disposition, "gate": gate}


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
            output = aggregate_record(value)
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
