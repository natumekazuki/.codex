"""Deterministic routing, aggregation, disposition, and Bootstrap gate rules."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


RISK_TAGS = {
    "security",
    "authentication",
    "authorization",
    "billing",
    "irreversible-data-loss",
    "privacy",
}
BOUNDARIES = {
    "consumer",
    "public-boundary",
    "component-behavior",
    "declaration",
    "implementation",
}
ROUTING_MANIFEST_VERSION = "review-routing-v1"
WORKFLOW_CONTEXT_VERSION = "review-workflow-context-v1"
ROUTING_INPUT_KEYS = {
    "record_id",
    "metadata_hash",
    "source_hash",
    "contract_version",
    "metadata",
    "metadata_verdict",
    "alignment_verdict",
    "context_requirements",
}
ROUTING_ENTRY_KEYS = {
    "record_id",
    "metadata_hash",
    "source_hash",
    "contract_version",
    "workflow_context_hash",
    "result",
}
WORKFLOW_CONTEXT_ENTRY_KEYS = {
    "record_id",
    "metadata_hash",
    "parent_risk_tags",
    "audit_percent",
}


class RoutingError(ValueError):
    """Raised when routing or aggregation input violates ADR-0022."""


def merge_risk_tags(metadata_tags: Any, parent_tags: Any, *, kind: str) -> list[str]:
    left = _risk_tag_set(metadata_tags, "metadata risk_tags")
    right = _risk_tag_set(parent_tags, "parent risk_tags")
    if kind == "security":
        left.add("security")
    return sorted(left | right)


def deterministic_audit(record_id: str, contract_version: str, audit_percent: int) -> bool:
    if not isinstance(audit_percent, int) or isinstance(audit_percent, bool) or not 0 <= audit_percent <= 100:
        raise RoutingError("audit_percent must be an integer from 0 through 100")
    digest = hashlib.sha256(f"{record_id}\n{contract_version}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") % 100 < audit_percent


def route_record(
    *,
    record_id: str,
    metadata_hash: str,
    contract_version: str,
    metadata: dict[str, Any],
    parent_risk_context: dict[str, Any] | None,
    metadata_verdict: str,
    alignment_verdict: str,
    context_requirements: list[str],
    audit_percent: int,
) -> dict[str, Any]:
    if metadata_verdict not in {"VALID", "REDESIGN", "NEEDS_CONTEXT"}:
        raise RoutingError("metadata_verdict is invalid")
    if alignment_verdict not in {"ALIGNED", "MISMATCH", "RECHECK"}:
        raise RoutingError("alignment_verdict is invalid")
    if not isinstance(context_requirements, list) or any(
        not isinstance(item, str) or not item for item in context_requirements
    ):
        raise RoutingError("context_requirements must be an array of non-empty strings")
    parent_risk_tags: list[str] = []
    if parent_risk_context is not None:
        if not isinstance(parent_risk_context, dict) or set(parent_risk_context) != {
            "record_id",
            "metadata_hash",
            "risk_tags",
        }:
            raise RoutingError("parent_risk_context is invalid")
        if parent_risk_context["record_id"] != record_id:
            raise RoutingError("parent risk record_id does not match")
        if parent_risk_context["metadata_hash"] != metadata_hash:
            raise RoutingError("parent risk metadata_hash does not match")
        parent_risk_tags = parent_risk_context["risk_tags"]
    risk_tags = merge_risk_tags(metadata.get("risk_tags", []), parent_risk_tags, kind=metadata.get("kind", ""))
    audit_selected = deterministic_audit(record_id, contract_version, audit_percent)
    reasons = []
    if metadata_verdict == "NEEDS_CONTEXT":
        reasons.append("metadata-needs-context")
    if alignment_verdict == "RECHECK":
        reasons.append("alignment-recheck")
    if context_requirements:
        reasons.append("bounded-context-required")
    if risk_tags:
        reasons.append("high-risk")
    if audit_selected:
        reasons.append("deterministic-audit")
    required = bool(reasons)
    if (
        not risk_tags
        and not audit_selected
        and metadata_verdict == "REDESIGN"
        and alignment_verdict != "RECHECK"
        and not context_requirements
    ):
        required = False
        reasons = []
    if (
        not risk_tags
        and not audit_selected
        and alignment_verdict == "MISMATCH"
        and metadata_verdict != "NEEDS_CONTEXT"
        and not context_requirements
    ):
        required = False
        reasons = []
    return {
        "required": required,
        "reasons": reasons,
        "risk_tags": risk_tags,
        "audit_selected": audit_selected,
    }


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def workflow_context_hash(entry: dict[str, Any]) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(entry).encode("utf-8")).hexdigest()


def validate_workflow_context(
    records: list[dict[str, Any]], context: dict[str, Any]
) -> list[dict[str, Any]]:
    if not isinstance(context, dict) or set(context) != {"review_contract_version", "records"}:
        raise RoutingError("workflow routing context has unexpected keys")
    if context["review_contract_version"] != WORKFLOW_CONTEXT_VERSION:
        raise RoutingError("workflow routing context version is invalid")
    entries = context["records"]
    if not isinstance(entries, list):
        raise RoutingError("workflow routing context records must be an array")
    expected_ids = [record.get("record_id") for record in records]
    entry_ids = [entry.get("record_id") if isinstance(entry, dict) else None for entry in entries]
    if entry_ids != expected_ids or len(expected_ids) != len(set(expected_ids)):
        raise RoutingError("workflow routing context record set or order does not match records")
    for record, entry in zip(records, entries):
        if not isinstance(entry, dict) or set(entry) != WORKFLOW_CONTEXT_ENTRY_KEYS:
            raise RoutingError("workflow routing context entry has unexpected keys")
        _non_empty_string(entry["record_id"], "workflow record_id")
        _hash_string(entry["metadata_hash"], "workflow metadata_hash")
        if entry["metadata_hash"] != record.get("metadata_hash"):
            raise RoutingError("workflow metadata_hash does not match record")
        _risk_tag_set(entry["parent_risk_tags"], "parent risk_tags")
        deterministic_audit(entry["record_id"], "deep-review-v1", entry["audit_percent"])
    return entries


def build_routing_manifest(
    records: list[dict[str, Any]], workflow_context: dict[str, Any]
) -> dict[str, Any]:
    if not isinstance(records, list):
        raise RoutingError("records must be an array")
    contexts = validate_workflow_context(records, workflow_context)
    entries = []
    seen_ids = set()
    for record, workflow_entry in zip(records, contexts):
        if not isinstance(record, dict) or set(record) != ROUTING_INPUT_KEYS:
            raise RoutingError("routing input record has unexpected keys")
        record_id = _non_empty_string(record["record_id"], "record_id")
        if record_id in seen_ids:
            raise RoutingError("routing records contain duplicate record_id")
        seen_ids.add(record_id)
        metadata_hash = _hash_string(record["metadata_hash"], "metadata_hash")
        source_hash = _hash_string(record["source_hash"], "source_hash")
        if record["contract_version"] != "deep-review-v1":
            raise RoutingError("contract_version must be deep-review-v1")
        if not isinstance(record["metadata"], dict):
            raise RoutingError("metadata must be an object")
        result = route_record(
            record_id=record_id,
            metadata_hash=metadata_hash,
            contract_version=record["contract_version"],
            metadata=record["metadata"],
            parent_risk_context={
                "record_id": workflow_entry["record_id"],
                "metadata_hash": workflow_entry["metadata_hash"],
                "risk_tags": workflow_entry["parent_risk_tags"],
            },
            metadata_verdict=record["metadata_verdict"],
            alignment_verdict=record["alignment_verdict"],
            context_requirements=record["context_requirements"],
            audit_percent=workflow_entry["audit_percent"],
        )
        entries.append(
            {
                "record_id": record_id,
                "metadata_hash": metadata_hash,
                "source_hash": source_hash,
                "contract_version": record["contract_version"],
                "workflow_context_hash": workflow_context_hash(workflow_entry),
                "result": result,
            }
        )
    return {"review_contract_version": ROUTING_MANIFEST_VERSION, "records": entries}


def validate_routing_manifest(
    alignment_records: list[dict[str, Any]],
    alignment_reviews: list[dict[str, Any]],
    manifest: dict[str, Any],
    workflow_context: dict[str, Any],
) -> list[dict[str, Any]]:
    if not isinstance(manifest, dict) or set(manifest) != {
        "review_contract_version",
        "records",
    }:
        raise RoutingError("routing manifest has unexpected keys")
    if manifest["review_contract_version"] != ROUTING_MANIFEST_VERSION:
        raise RoutingError("routing manifest contract version is invalid")
    entries = manifest["records"]
    if not isinstance(entries, list):
        raise RoutingError("routing manifest records must be an array")
    if len(alignment_records) != len(alignment_reviews):
        raise RoutingError("alignment record and review counts do not match")
    contexts = validate_workflow_context(alignment_records, workflow_context)
    expected_ids = [record.get("record_id") for record in alignment_records]
    review_ids = [review.get("record_id") for review in alignment_reviews]
    entry_ids = [entry.get("record_id") if isinstance(entry, dict) else None for entry in entries]
    if review_ids != expected_ids or entry_ids != expected_ids or len(expected_ids) != len(set(expected_ids)):
        raise RoutingError("routing record set or order does not match frozen reviews")
    for record, review, entry, workflow_entry in zip(
        alignment_records, alignment_reviews, entries, contexts
    ):
        if not isinstance(entry, dict) or set(entry) != ROUTING_ENTRY_KEYS:
            raise RoutingError("routing manifest entry has unexpected keys")
        if entry["metadata_hash"] != record.get("metadata_hash"):
            raise RoutingError("routing metadata_hash does not match alignment packet")
        if entry["source_hash"] != record.get("source_hash"):
            raise RoutingError("routing source_hash does not match alignment packet")
        if entry["contract_version"] != "deep-review-v1":
            raise RoutingError("routing contract_version is invalid")
        if entry["workflow_context_hash"] != workflow_context_hash(workflow_entry):
            raise RoutingError("routing workflow context hash does not match fixed input")
        expected_result = route_record(
            record_id=record["record_id"],
            metadata_hash=record["metadata_hash"],
            contract_version=entry["contract_version"],
            metadata=record["metadata"],
            parent_risk_context={
                "record_id": workflow_entry["record_id"],
                "metadata_hash": workflow_entry["metadata_hash"],
                "risk_tags": workflow_entry["parent_risk_tags"],
            },
            metadata_verdict=record["metadata_review"]["verdict"],
            alignment_verdict=review["verdict"],
            context_requirements=review["context_requirements"],
            audit_percent=workflow_entry["audit_percent"],
        )
        if entry["result"] != expected_result:
            raise RoutingError("routing result does not match frozen review inputs")
    return entries


def aggregate_status(
    metadata_verdict: str | None,
    alignment_verdict: str | None,
    *,
    sol_required: bool,
    sol_verdict: str | None,
) -> str:
    if not isinstance(sol_required, bool):
        raise RoutingError("sol_required must be a boolean")
    if metadata_verdict not in {"VALID", "REDESIGN", "NEEDS_CONTEXT"}:
        return "NEEDS_CONTEXT"
    if alignment_verdict not in {"ALIGNED", "MISMATCH", "RECHECK"}:
        return "NEEDS_CONTEXT"
    if metadata_verdict == "NEEDS_CONTEXT" or alignment_verdict == "RECHECK":
        if not sol_required:
            raise RoutingError("uncertain Luna verdict requires Sol")
    if sol_required:
        if sol_verdict not in {"APPROVE", "REDESIGN"}:
            return "NEEDS_CONTEXT"
    elif sol_verdict is not None:
        raise RoutingError("Sol verdict is not allowed when Sol is not required")
    if metadata_verdict == "REDESIGN":
        return "REDESIGN"
    if alignment_verdict == "MISMATCH":
        return "REDESIGN"
    if sol_required and sol_verdict == "REDESIGN":
        return "REDESIGN"
    if metadata_verdict == "VALID" and alignment_verdict == "ALIGNED":
        return "ACCEPT"
    if sol_required and sol_verdict == "APPROVE" and alignment_verdict in {"ALIGNED", "RECHECK"}:
        return "ACCEPT"
    return "NEEDS_CONTEXT"


def decide_disposition(
    *,
    actual_boundary: str | None,
    lifecycle: str,
    retention_basis: str,
    expires_on: str | None = None,
    review_when: str | None = None,
) -> str | None:
    if actual_boundary is None:
        return None
    if actual_boundary not in BOUNDARIES:
        raise RoutingError("actual_boundary is invalid")
    if retention_basis not in {"PRESENT", "ABSENT", "UNRESOLVED"}:
        raise RoutingError("retention_basis is invalid")
    if actual_boundary == "declaration":
        return "MOVE_TO_POLICY_CHECK"
    if lifecycle == "ephemeral":
        return None
    temporary = lifecycle == "characterization" and bool(expires_on or review_when)
    if lifecycle not in {"permanent", "characterization"}:
        raise RoutingError("lifecycle is invalid for Bootstrap")
    if actual_boundary == "implementation":
        return "KEEP_TEMPORARY" if temporary else "DROP"
    if temporary:
        return "KEEP_TEMPORARY"
    if lifecycle == "characterization":
        return "DROP"
    if retention_basis == "UNRESOLVED":
        return None
    return "KEEP_PERMANENT" if retention_basis == "PRESENT" else "DROP"


def decide_gate(status: str, disposition: str | None, artifact_state: str) -> str:
    if status == "NEEDS_CONTEXT":
        return "BLOCKED"
    if status == "REDESIGN":
        return "CHANGES_REQUIRED"
    if status != "ACCEPT" or disposition is None:
        return "BLOCKED"
    if disposition == "KEEP_PERMANENT":
        return "PASS" if artifact_state == "PERMANENT_TEST" else "BLOCKED"
    if disposition == "KEEP_TEMPORARY":
        return "PASS" if artifact_state == "TEMPORARY_TEST" else "BLOCKED"
    if disposition in {"MOVE_TO_POLICY_CHECK", "DROP"}:
        return "CHANGES_REQUIRED" if artifact_state == "TEST_PRESENT" else "BLOCKED"
    raise RoutingError("disposition is invalid")


def aggregate_gate(gates: list[str]) -> str:
    if any(gate == "BLOCKED" for gate in gates):
        return "BLOCKED"
    if any(gate == "CHANGES_REQUIRED" for gate in gates):
        return "CHANGES_REQUIRED"
    if any(gate != "PASS" for gate in gates):
        raise RoutingError("record gate is invalid")
    return "PASS"


def unavailable_result() -> dict[str, Any]:
    return {"status": "NEEDS_CONTEXT", "disposition": None, "gate": "BLOCKED"}


def _risk_tag_set(value: Any, name: str) -> set[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise RoutingError(f"{name} must be an array of strings")
    values = set(value)
    unknown = values - RISK_TAGS
    if unknown:
        raise RoutingError(f"{name} contains unknown values: {sorted(unknown)}")
    return values


def _non_empty_string(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise RoutingError(f"{name} must be a non-empty string")
    return value


def _hash_string(value: Any, name: str) -> str:
    text = _non_empty_string(value, name)
    if len(text) != 71 or not text.startswith("sha256:"):
        raise RoutingError(f"{name} must be a sha256 hash")
    try:
        int(text[7:], 16)
    except ValueError as exc:
        raise RoutingError(f"{name} must be a sha256 hash") from exc
    return text


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    args = parser.parse_args()
    try:
        value = json.loads(args.input.read_text(encoding="utf-8"))
        if not isinstance(value, dict) or set(value) != {"records", "workflow_context"}:
            raise RoutingError("input must be a JSON object")
        records = value["records"]
        if not isinstance(records, list):
            raise RoutingError("records must be an array")
        result = build_routing_manifest(records, value["workflow_context"])
    except (OSError, json.JSONDecodeError, TypeError, RoutingError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
