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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    args = parser.parse_args()
    try:
        value = json.loads(args.input.read_text(encoding="utf-8"))
        if not isinstance(value, dict) or set(value) != {"records"}:
            raise RoutingError("input must be a JSON object")
        records = value["records"]
        if not isinstance(records, list):
            raise RoutingError("records must be an array")
        result = {}
        for record in records:
            if not isinstance(record, dict):
                raise RoutingError("routing record must be an object")
            record_id = record.get("record_id")
            if not isinstance(record_id, str) or not record_id:
                raise RoutingError("record_id must be a non-empty string")
            if record_id in result:
                raise RoutingError("routing records contain duplicate record_id")
            result[record_id] = route_record(**record)
    except (OSError, json.JSONDecodeError, TypeError, RoutingError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
