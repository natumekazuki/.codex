#!/usr/bin/env python3
"""Build and preflight schema-version-2 Review Briefs."""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Sequence


SCHEMA_VERSION = 2
REVIEW_KINDS = {
    "targeted-review",
    "specialist-review",
    "targeted-closure",
    "holistic-complete-diff-review",
}
ROLES = {"slice_reviewer", "targeted_reviewer", "reviewer"}
HIGH_RISK_TRIGGERS = {
    "public-contract",
    "persistence",
    "migration",
    "external-side-effect",
    "authorization",
    "security",
    "owner-scope",
    "concurrency",
    "resource-limit",
    "coupled-invariant",
    "contract-closure",
}
MISMATCH_DIAGNOSTIC_CODES = {
    "candidate-id-mismatch",
    "candidate-target-mismatch",
    "candidate-repository-mismatch",
    "candidate-mode-fields-invalid",
    "candidate-verification-mismatch",
    "review-role-mismatch",
    "ordinary-slice-high-risk-trigger",
    "scope-outside-review-target",
    "mixed-repository-scope",
    "review-scope-outside-candidate",
    "review-scope-excluded-by-candidate",
    "closure-invariant-candidate-mismatch",
    "closure-invariant-matrix-mismatch",
    "closure-invariant-check-mismatch",
    "executedChecks-candidate-mismatch",
    "full-review-gate-not-run",
    "holistic-input-contamination",
    "assigned-lens-mismatch",
    "holistic-raw-diff-mismatch",
    "holistic-untracked-content-mismatch",
}
PASSED_CHECK_RESULT = "passed"
HOLISTIC_FORBIDDEN_FIELDS = {
    "priorFindings",
    "specialistConclusions",
    "claimedResolution",
    "implementationConclusion",
    "closureMap",
    "reviewInstructions",
}


def load_snapshot_module() -> Any:
    path = Path(__file__).with_name("candidate_snapshot.py")
    spec = importlib.util.spec_from_file_location("review_brief_candidate_snapshot", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("candidate_snapshot.py could not be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


SNAPSHOT = load_snapshot_module()


class BriefValidation:
    def __init__(self) -> None:
        self.diagnostics: list[dict[str, str]] = []

    def add(self, code: str, message: str) -> None:
        if not any(item["code"] == code and item["message"] == message for item in self.diagnostics):
            self.diagnostics.append({"code": code, "message": message})

    def require(self, value: Any, code: str, message: str) -> bool:
        valid = value is not None and value != "" and value != [] and value != {}
        if not valid:
            self.add(code, message)
        return valid


def text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def string_list(value: Any) -> bool:
    return isinstance(value, list) and bool(value) and all(text(item) for item in value)


def normalize_scope(values: Any, label: str, validation: BriefValidation) -> list[str] | None:
    if not string_list(values):
        validation.add(f"{label}-required", f"{label} must be a non-empty list of review-target-relative paths")
        return None
    normalized: list[str] = []
    for original in values:
        raw_value = original.replace("\\", "/")
        if raw_value.startswith("/") or re.match(r"^[A-Za-z]:", raw_value):
            validation.add("scope-outside-review-target", f"{label} path must stay within reviewTarget: {original}")
            continue
        value = raw_value.rstrip("/") or "."
        path = PurePosixPath(value)
        if (
            path.is_absolute()
            or ".." in path.parts
        ):
            validation.add("scope-outside-review-target", f"{label} path must stay within reviewTarget: {original}")
            continue
        if value not in normalized:
            normalized.append(value)
    return normalized


def within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except (OSError, ValueError):
        return False


def validate_contract_anchors(
    anchors: Any,
    root: Path | None,
    validation: BriefValidation,
) -> list[dict[str, str]]:
    if not isinstance(anchors, list) or not anchors:
        validation.add("accepted-contract-anchors-required", "acceptedContract.anchors must be a non-empty object list")
        return []
    normalized: list[dict[str, str]] = []
    for index, anchor in enumerate(anchors):
        if not isinstance(anchor, dict):
            validation.add("accepted-contract-anchor-invalid", f"acceptedContract.anchors[{index}] must be an object")
            continue
        kind = anchor.get("kind")
        path_value = anchor.get("path")
        if kind == "repository-path":
            if not text(path_value) or root is None:
                validation.add("accepted-contract-anchor-path-required", f"acceptedContract.anchors[{index}].path is required")
                continue
            relative = PurePosixPath(path_value.replace("\\", "/"))
            if relative.is_absolute() or ".." in relative.parts or re.match(r"^[A-Za-z]:", path_value):
                validation.add("accepted-contract-anchor-outside-target", f"repository anchor must stay within reviewTarget: {path_value}")
                continue
            resolved = (root / Path(*relative.parts)).resolve()
            if not within(resolved, root) or not resolved.is_file():
                validation.add("accepted-contract-anchor-unreadable", f"repository anchor is not a readable file: {path_value}")
                continue
            normalized.append({"kind": kind, "path": relative.as_posix()})
        elif kind == "external-file":
            digest = anchor.get("sha256")
            if not text(path_value) or not Path(path_value).is_absolute() or not text(digest):
                validation.add("accepted-contract-anchor-external-invalid", f"external anchor {index} requires an absolute path and sha256")
                continue
            resolved = Path(path_value).resolve()
            if not resolved.is_file():
                validation.add("accepted-contract-anchor-unreadable", f"external anchor is not a readable file: {path_value}")
                continue
            actual = "sha256:" + hashlib.sha256(resolved.read_bytes()).hexdigest()
            if digest.lower() != actual:
                validation.add("accepted-contract-anchor-digest-mismatch", f"external anchor digest does not match: {path_value}")
                continue
            normalized.append({"kind": kind, "path": str(resolved), "sha256": actual})
        else:
            validation.add("accepted-contract-anchor-kind-invalid", f"acceptedContract.anchors[{index}].kind is unsupported")
    return normalized


def validate_canonical_anchors(anchors: Any, root: Path | None, validation: BriefValidation) -> list[str]:
    if not string_list(anchors):
        validation.add("canonical-anchors-invalid", "canonicalAnchors must be a non-empty repository-path list")
        return []
    normalized: list[str] = []
    for anchor in anchors:
        relative = PurePosixPath(anchor.replace("\\", "/"))
        if root is None or relative.is_absolute() or ".." in relative.parts or re.match(r"^[A-Za-z]:", anchor):
            validation.add("canonical-anchor-outside-target", f"canonical anchor must stay within reviewTarget: {anchor}")
            continue
        resolved = (root / Path(*relative.parts)).resolve()
        if not within(resolved, root) or not resolved.is_file():
            validation.add("canonical-anchor-unreadable", f"canonical anchor is not a readable file: {anchor}")
            continue
        normalized.append(relative.as_posix())
    return normalized


def scope_contains(parent: str, child: str) -> bool:
    if parent == ".":
        return True
    parent_parts = PurePosixPath(parent).parts
    child_parts = PurePosixPath(child).parts
    return child_parts[: len(parent_parts)] == parent_parts


def validate_scope_roots(
    root: Path,
    included: Sequence[str],
    excluded: Sequence[str],
    validation: BriefValidation,
) -> None:
    for value in (*included, *excluded):
        candidate = root.joinpath(*PurePosixPath(value).parts)
        if candidate.exists() and not within(candidate, root):
            validation.add("scope-outside-review-target", f"scope resolves outside reviewTarget: {value}")
            continue
        probe = candidate if candidate.is_dir() else candidate.parent
        while not probe.exists() and probe != root:
            probe = probe.parent
        if not within(probe, root):
            validation.add("scope-outside-review-target", f"scope cannot be interpreted from reviewTarget: {value}")
            continue
        try:
            top = Path(os.fsdecode(SNAPSHOT.Git(probe).run(["rev-parse", "--show-toplevel"]).rstrip(b"\r\n"))).resolve()
        except Exception as exc:  # candidate_snapshot owns Git diagnostics
            validation.add("scope-repository-unavailable", f"cannot resolve repository for scope {value}: {exc}")
            continue
        if top != root:
            validation.add(
                "mixed-repository-scope",
                f"scope {value} belongs to a different Git repository; split the Review Brief",
            )


def validate_declared_scope_containment(
    values: Sequence[str],
    parents: Sequence[str],
    label: str,
    validation: BriefValidation,
) -> None:
    for value in values:
        if not any(scope_contains(parent, value) for parent in parents):
            validation.add(f"{label}-outside-supported-scope", f"{label} is outside supportedContractScope: {value}")


def normalize_record_scopes(
    request: dict[str, Any],
    field: str,
    root: Path | None,
    supported: Sequence[str],
    validation: BriefValidation,
    *,
    require_contract_fields: bool,
) -> None:
    values = request.get(field, [])
    if not isinstance(values, list):
        validation.add(f"{field}-invalid", f"{field} must be a list of objects")
        return
    for index, item in enumerate(values):
        if not isinstance(item, dict):
            validation.add(f"{field}-item-invalid", f"{field}[{index}] must be an object")
            continue
        if require_contract_fields:
            identifier = item.get("invariantId") if field == "matrixCells" else item.get("id")
            if field == "executedChecks":
                if not string_list(item.get("invariantIds")):
                    validation.add("executedChecks-invariant-ids-required", f"executedChecks[{index}] requires non-empty invariantIds")
                if not text(item.get("result")):
                    validation.add("executedChecks-result-required", f"executedChecks[{index}].result must be a non-empty string")
            elif not text(identifier):
                validation.add(f"{field}-invariant-id-required", f"{field}[{index}] requires an Invariant ID")
            for required in ("definition", "failureMode", "consumerImpact", "directVerification"):
                if not text(item.get(required)):
                    validation.add(
                        f"{field}-{required}-required",
                        f"{field}[{index}].{required} must be a non-empty string",
                    )
        if "scope" not in item:
            if require_contract_fields:
                validation.add(f"{field}-scope-required", f"{field}[{index}].scope must be a non-empty target-relative list")
            continue
        scope = normalize_scope(item.get("scope"), f"{field}-scope", validation)
        if scope is None:
            continue
        item["scope"] = scope
        if root is not None:
            validate_scope_roots(root, scope, [], validation)
        validate_declared_scope_containment(scope, supported, f"{field}-scope", validation)


def validate_executed_checks(
    value: Any,
    *,
    candidate_bound: bool,
    candidate_id: Any,
    logical_change_id: Any,
    validation: BriefValidation,
) -> set[str]:
    check_ids: set[str] = set()
    if not isinstance(value, list):
        return check_ids
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            continue
        result = item.get("result")
        if not isinstance(result, str) or result != PASSED_CHECK_RESULT:
            validation.add(
                "executedChecks-result-not-passed",
                f"executedChecks[{index}].result must be the exact string {PASSED_CHECK_RESULT} to issue a Review Brief",
            )
        if not candidate_bound:
            continue
        check_logical_change_id = item.get("logicalChangeId")
        if not text(check_logical_change_id):
            validation.add(
                "executedChecks-logical-change-required",
                f"executedChecks[{index}].logicalChangeId must be a non-empty string for Candidate-bound review",
            )
        elif not text(logical_change_id) or check_logical_change_id != logical_change_id:
            validation.add(
                "executedChecks-logical-change-mismatch",
                f"executedChecks[{index}].logicalChangeId must match the Review Brief logicalChangeId",
            )
        check_id = item.get("id")
        if not text(check_id):
            validation.add(
                "executedChecks-id-required",
                f"executedChecks[{index}].id must be a non-empty string for Candidate-bound review",
            )
        elif check_id in check_ids:
            validation.add(
                "executedChecks-id-duplicate",
                f"executedChecks[{index}].id must be task-local unique: {check_id}",
            )
        else:
            check_ids.add(check_id)
        executed_on_candidate_id = item.get("executedOnCandidateId")
        if not text(executed_on_candidate_id):
            validation.add(
                "executedChecks-candidate-required",
                f"executedChecks[{index}].executedOnCandidateId is required for Candidate-bound review",
            )
        elif not text(candidate_id) or executed_on_candidate_id != candidate_id:
            validation.add(
                "executedChecks-candidate-mismatch",
                f"executedChecks[{index}] must have been executed on the current Candidate",
            )
    return check_ids


def parse_deadline(value: Any, now: datetime, validation: BriefValidation) -> str | None:
    if not text(value):
        validation.add("deadline-required", "deadline must be supplied as an absolute ISO 8601 timestamp")
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        validation.add("deadline-invalid", "deadline must be a finite ISO 8601 timestamp with a UTC offset")
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        validation.add("deadline-not-absolute", "deadline must include a UTC offset")
        return None
    if parsed <= now.astimezone(parsed.tzinfo):
        validation.add("deadline-expired", "deadline must be later than the Review Brief build time")
        return None
    return parsed.isoformat()


def validate_review_target(value: Any, validation: BriefValidation) -> tuple[Path | None, Any | None]:
    if not text(value):
        validation.add("review-target-required", "reviewTarget is required; current directory is never used as a fallback")
        return None, None
    root = Path(value)
    if not root.exists() or not root.is_dir():
        validation.add("review-target-unavailable", "reviewTarget must be an existing readable directory")
        return None, None
    if not os.access(root, os.R_OK):
        validation.add("review-target-unreadable", "reviewTarget is not readable")
        return None, None
    try:
        repository, _ = SNAPSHOT.resolve_repository(root)
    except Exception as exc:
        validation.add("review-target-invalid", f"reviewTarget must be a Git worktree root: {exc}")
        return None, None
    return repository.target_root, repository


def expected_role(kind: str, trigger: dict[str, Any]) -> str | None:
    if kind == "targeted-review":
        risk = trigger.get("riskClass")
        if risk == "ordinary-slice":
            return "slice_reviewer"
        if risk == "high-risk-boundary":
            return "targeted_reviewer"
        return None
    if kind == "specialist-review" and trigger.get("riskClass") == "specialist-review":
        return "targeted_reviewer"
    if kind == "targeted-closure" and trigger.get("riskClass") == "targeted-closure":
        return "targeted_reviewer"
    if kind == "holistic-complete-diff-review" and trigger.get("riskClass") == "holistic-complete-diff-review":
        return "reviewer"
    return None


def is_candidate_bound(kind: str, trigger: dict[str, Any]) -> bool:
    return kind != "targeted-review" or trigger.get("riskClass") == "high-risk-boundary"


def build_candidate_definition(snapshot: dict[str, Any], request: dict[str, Any]) -> dict[str, Any]:
    identity = snapshot["candidateSourceIdentity"]
    accepted = request["acceptedContract"]
    contract = request["reviewContract"]
    return {
        "candidateId": snapshot["candidateId"],
        "baseRefLabel": snapshot["baseRefLabel"],
        "resolvedBaseCommitOid": identity["baseCommitOid"],
        "resolvedBaseTreeOid": identity["baseTreeOid"],
        "sourceIdentity": identity,
        "creation": snapshot["creation"],
        "creationRecipe": snapshot["creationRecipe"],
        "readOnlyVerificationRecipe": snapshot["readOnlyVerificationRecipe"],
        "supportedScopeCleanliness": snapshot["supportedScopeCleanliness"],
        "targetRoot": snapshot["targetRoot"],
        "repositoryIdentity": snapshot["repositoryIdentity"],
        "acceptedContractAnchors": accepted["anchors"],
        "acceptedContractMeaning": accepted["meaning"],
        "supportedContractScope": request["supportedContractScope"],
        "reviewContractRevision": contract["revision"],
        "reviewContractRecipe": contract["recipe"],
        "invariants": request.get("invariants", []),
        "matrixCells": request.get("matrixCells", []),
        "triggeredLensScope": request.get("triggeredLensScope", []),
    }


def validate_candidate(
    request: dict[str, Any],
    root: Path | None,
    repository: Any | None,
    included: Sequence[str],
    excluded: Sequence[str],
    supported: Sequence[str],
    validation: BriefValidation,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    local_mismatch = False
    snapshot_schema_invalid = False
    snapshot = request.get("candidateSnapshot")
    if not isinstance(snapshot, dict):
        validation.add("candidate-snapshot-required", "Candidate-bound review requires candidateSnapshot schema version 1")
        return None, {"result": "validation-gap", "evidence": {}, "diagnostics": list(validation.diagnostics)}
    if snapshot.get("schemaVersion") != 1:
        validation.add("candidate-snapshot-schema-unsupported", "candidateSnapshot.schemaVersion must be 1")
    if snapshot.get("status") != "ready":
        validation.add("candidate-snapshot-not-ready", "candidateSnapshot.status must be ready")
    candidate_id = request.get("candidateId")
    snapshot_candidate_id = snapshot.get("candidateId")
    if not text(candidate_id):
        validation.add("candidate-id-invalid", "candidateId must be a non-empty string")
        snapshot_schema_invalid = True
    if not text(snapshot_candidate_id):
        validation.add("candidate-snapshot-id-invalid", "candidateSnapshot.candidateId must be a non-empty string")
        snapshot_schema_invalid = True
    if text(candidate_id) and text(snapshot_candidate_id) and candidate_id != snapshot_candidate_id:
        validation.add("candidate-id-mismatch", "candidateId must match candidateSnapshot.candidateId")
        local_mismatch = True
    snapshot_target = snapshot.get("targetRoot")
    if not text(snapshot_target):
        validation.add("candidate-snapshot-target-invalid", "candidateSnapshot.targetRoot must be a non-empty path string")
        snapshot_schema_invalid = True
    elif root is not None and Path(snapshot_target).resolve() != root:
        validation.add("candidate-target-mismatch", "candidateSnapshot.targetRoot does not match reviewTarget")
        local_mismatch = True
    if repository is not None and snapshot.get("repositoryIdentity") != SNAPSHOT.repository_identity(repository):
        validation.add("candidate-repository-mismatch", "candidateSnapshot.repositoryIdentity does not match reviewTarget")
        local_mismatch = True

    identity = snapshot.get("candidateSourceIdentity")
    if isinstance(identity, dict):
        snapshot_included = identity.get("includedScope")
        snapshot_excluded = identity.get("excludedScope")
        if not isinstance(snapshot_included, list) or not all(text(item) for item in snapshot_included):
            validation.add(
                "candidate-source-included-scope-invalid",
                "candidateSnapshot.candidateSourceIdentity.includedScope must be a string list",
            )
            snapshot_included = []
            snapshot_schema_invalid = True
        if not isinstance(snapshot_excluded, list) or not all(text(item) for item in snapshot_excluded):
            validation.add(
                "candidate-source-excluded-scope-invalid",
                "candidateSnapshot.candidateSourceIdentity.excludedScope must be a string list",
            )
            snapshot_excluded = []
            snapshot_schema_invalid = True
        for label, values in (("includedScope", included), ("supportedContractScope", supported)):
            for value in values:
                if not any(scope_contains(parent, value) for parent in snapshot_included):
                    validation.add("review-scope-outside-candidate", f"{label} is outside Candidate source scope: {value}")
                if any(scope_contains(parent, value) for parent in snapshot_excluded):
                    validation.add("review-scope-excluded-by-candidate", f"{label} is excluded by Candidate source scope: {value}")
        if identity.get("mode") == "manifest-digest" and identity.get("candidateTreeOid") != "not applicable":
            validation.add("candidate-mode-fields-invalid", "manifest-digest requires candidateTreeOid=not applicable")
            local_mismatch = True
        if identity.get("mode") == "creator-tree" and not text(identity.get("candidateTreeOid")):
            validation.add("candidate-mode-fields-invalid", "creator-tree requires candidateTreeOid")
            local_mismatch = True
        manifest = identity.get("manifest")
        if not isinstance(manifest, dict) or not all(text(manifest.get(key)) for key in ("recordFraming", "pathEncoding", "contentIdentity")):
            validation.add("candidate-digest-framing-missing", "Candidate manifest must declare digest framing, path encoding, and content identity")
    else:
        validation.add("candidate-source-identity-required", "candidateSourceIdentity is required")

    if snapshot_schema_invalid:
        verification = {
            "status": "validation-gap",
            "candidateId": snapshot.get("candidateId", "unknown"),
            "reviewScope": "Candidate verification only",
            "writesGitMetadata": False,
            "evidence": {"snapshotSchema": "invalid"},
            "diagnostics": [
                {
                    "code": "candidate-snapshot-invalid",
                    "message": "Candidate snapshot schema is incomplete or malformed",
                }
            ],
        }
    elif local_mismatch:
        verification = {
            "status": "mismatch",
            "candidateId": snapshot.get("candidateId", "unknown"),
            "reviewScope": "Candidate verification only",
            "writesGitMetadata": False,
            "evidence": {"localTargetAndSchemaComparison": "mismatch"},
            "diagnostics": [
                {
                    "code": "candidate-brief-mismatch",
                    "message": "Review Brief target or mode fields do not match the Candidate snapshot",
                }
            ],
        }
    else:
        try:
            verification = SNAPSHOT.verify_candidate(snapshot)
        except (KeyError, TypeError, ValueError, OSError) as exc:
            validation.add(
                "candidate-snapshot-invalid",
                f"candidateSnapshot could not be validated: {type(exc).__name__}: {exc}",
            )
            verification = {
                "status": "validation-gap",
                "candidateId": snapshot.get("candidateId", "unknown"),
                "reviewScope": "Candidate verification only",
                "writesGitMetadata": False,
                "evidence": {"snapshotSchema": "invalid"},
                "diagnostics": [
                    {
                        "code": "candidate-snapshot-invalid",
                        "message": "Candidate snapshot schema is incomplete or malformed",
                    }
                ],
            }
    result = verification.get("status", "validation-gap")
    preflight = {
        "result": result,
        "evidence": {
            "recipe": snapshot.get("readOnlyVerificationRecipe"),
            "verification": verification,
        },
        "diagnostics": verification.get("diagnostics", []),
    }
    if result == "mismatch":
        validation.add("candidate-verification-mismatch", "candidate_snapshot verification reported mismatch")
    elif result != "verified":
        validation.add("candidate-verification-gap", "candidate_snapshot verification could not be completed")
    if validation.diagnostics or result != "verified":
        return None, preflight
    try:
        return build_candidate_definition(snapshot, request), preflight
    except (KeyError, TypeError) as exc:
        validation.add("candidate-definition-incomplete", f"Candidate Definition input is incomplete: {exc}")
        return None, preflight


def invariant_tuple(value: dict[str, Any]) -> tuple[Any, ...]:
    values = []
    for key in ("id", "definition", "scope", "failureMode", "consumerImpact", "directVerification"):
        item = value.get(key)
        values.append(tuple(item) if key == "scope" and isinstance(item, list) else item)
    return tuple(values)


def validate_invariant_inheritance(request: dict[str, Any], validation: BriefValidation) -> None:
    plans = request.get("preImplementationInvariants", [])
    if not plans:
        return
    invariants = {item.get("id"): item for item in request.get("invariants", []) if isinstance(item, dict)}
    cells = request.get("matrixCells", [])
    checks = request.get("executedChecks", [])
    for plan in plans:
        if not isinstance(plan, dict) or not text(plan.get("id")):
            validation.add("closure-invariant-invalid", "each preImplementationInvariant requires an id")
            continue
        expected = invariant_tuple(plan)
        candidate = invariants.get(plan["id"])
        matching_cells = [item for item in cells if isinstance(item, dict) and item.get("invariantId") == plan["id"]]
        matching_checks = [item for item in checks if isinstance(item, dict) and plan["id"] in item.get("invariantIds", [])]
        if candidate is None or invariant_tuple(candidate) != expected:
            validation.add("closure-invariant-candidate-mismatch", f"Invariant {plan['id']} changed meaning in Candidate input")
        if not matching_cells or any(invariant_tuple({**item, "id": item.get("invariantId")}) != expected for item in matching_cells):
            validation.add("closure-invariant-matrix-mismatch", f"Invariant {plan['id']} is missing or changed in matrixCells")
        if not matching_checks or any(invariant_tuple({**item, "id": plan["id"]}) != expected for item in matching_checks):
            validation.add("closure-invariant-check-mismatch", f"Invariant {plan['id']} is missing or changed in executedChecks")


def expected_untracked_content(snapshot: Any) -> list[dict[str, Any]] | None:
    if not isinstance(snapshot, dict):
        return None
    identity = snapshot.get("candidateSourceIdentity")
    manifest = identity.get("manifest") if isinstance(identity, dict) else None
    records = manifest.get("records") if isinstance(manifest, dict) else None
    if not isinstance(records, list):
        return None
    expected: list[dict[str, Any]] = []
    for record in records:
        if not isinstance(record, dict):
            return None
        if record.get("untracked") is True:
            expected.append(
                {
                    "path": record.get("pathText"),
                    "contentDigest": record.get("contentDigest"),
                    "objectType": record.get("objectType"),
                    "mode": record.get("newMode"),
                }
            )
    return sorted(expected, key=lambda item: item["path"] or "")


def normalize_untracked_content(value: Any) -> list[dict[str, Any]] | None:
    if not isinstance(value, list):
        return None
    normalized: list[dict[str, Any]] = []
    allowed_keys = {"path", "contentDigest", "objectType", "mode"}
    for item in value:
        if not isinstance(item, dict) or set(item) != allowed_keys:
            return None
        projected = {
            "path": item.get("path"),
            "contentDigest": item.get("contentDigest"),
            "objectType": item.get("objectType"),
            "mode": item.get("mode"),
        }
        if not all(text(projected[field]) for field in projected):
            return None
        normalized.append(projected)
    if len({item["path"] for item in normalized}) != len(normalized):
        return None
    return sorted(normalized, key=lambda item: item["path"])


def validate_kind_fields(
    request: dict[str, Any],
    root: Path | None,
    included: Sequence[str],
    excluded: Sequence[str],
    supported: Sequence[str],
    validation: BriefValidation,
) -> None:
    kind = request.get("reviewKind")
    if kind == "targeted-review":
        completed = request.get("completedSlice")
        if not isinstance(completed, dict) or completed.get("status") != "completed":
            validation.add("completed-slice-required", "targeted-review requires a completedSlice with status=completed")
        else:
            if not text(completed.get("observableOutcome")):
                validation.add("observable-outcome-required", "completedSlice.observableOutcome must be a non-empty string")
            if not text(completed.get("executableContract")) and not text(completed.get("alternativeCheck")):
                validation.add("executable-contract-required", "targeted-review requires an executableContract or reasoned alternativeCheck")
            if not text(completed.get("targetedCheck")):
                validation.add("targeted-check-required", "completedSlice.targetedCheck must be a non-empty string")
    elif kind == "specialist-review":
        if not text(request.get("assignedLens")):
            validation.add("assigned-lens-required", "specialist-review requires a non-empty assignedLens")
        elif not string_list(request.get("triggeredLensScope")) or request["assignedLens"] not in request["triggeredLensScope"]:
            validation.add("assigned-lens-mismatch", "assignedLens must be declared in triggeredLensScope")
        if not isinstance(request.get("matrixCells"), list) or not request["matrixCells"] or not all(isinstance(item, dict) for item in request["matrixCells"]):
            validation.add("matrix-cells-required", "specialist-review requires a non-empty matrixCells object list")
        if not isinstance(request.get("closureMap"), dict) or not request["closureMap"]:
            validation.add("closure-map-required", "specialist-review requires a Closure Map object")
    elif kind == "targeted-closure":
        finding = request.get("findingFamily")
        if not isinstance(finding, dict):
            validation.add("finding-family-required", "targeted-closure requires findingFamily")
        else:
            for field in ("id", "acceptedContractRelation", "resultingDelta"):
                validation.require(finding.get(field), f"finding-{field}-required", f"findingFamily.{field} is required")
        if not text(request.get("directCheck")):
            validation.add("direct-check-required", "targeted-closure requires a non-empty directCheck")
        sibling_paths = normalize_scope(request.get("includedSiblingPaths"), "sibling-paths", validation)
        if sibling_paths is None:
            validation.add("sibling-paths-required", "targeted-closure requires a non-empty includedSiblingPaths list")
        else:
            request["includedSiblingPaths"] = sibling_paths
            if root is not None:
                validate_scope_roots(root, sibling_paths, [], validation)
            validate_declared_scope_containment(sibling_paths, supported, "sibling-paths", validation)
            for value in sibling_paths:
                if not any(scope_contains(parent, value) for parent in included):
                    validation.add(
                        "sibling-path-outside-included-scope",
                        f"includedSiblingPaths must stay within includedScope: {value}",
                    )
                if any(scope_contains(parent, value) or scope_contains(value, parent) for parent in excluded):
                    validation.add(
                        "sibling-path-overlaps-excluded-scope",
                        f"includedSiblingPaths must not overlap excludedScope: {value}",
                    )
    elif kind == "holistic-complete-diff-review":
        if request.get("fullReviewGate") != "run":
            validation.add("full-review-gate-not-run", "holistic review requires fullReviewGate=run")
        raw_diff = request.get("completeRawDiff")
        snapshot = request.get("candidateSnapshot")
        identity = snapshot.get("candidateSourceIdentity") if isinstance(snapshot, dict) else None
        if not isinstance(raw_diff, dict) or set(raw_diff) != {"command", "digest"}:
            validation.add("complete-raw-diff-required", "holistic review requires completeRawDiff")
        elif not isinstance(identity, dict) or raw_diff.get("command") != identity.get("rawDiffCommand") or raw_diff.get("digest") != identity.get("rawDiffDigest"):
            validation.add("holistic-raw-diff-mismatch", "completeRawDiff must match the Candidate raw diff command and digest")
        untracked = normalize_untracked_content(request.get("verifiedUntrackedContent"))
        expected_untracked = expected_untracked_content(snapshot)
        if "verifiedUntrackedContent" not in request or untracked is None:
            validation.add("verified-untracked-content-required", "holistic review requires a verifiedUntrackedContent list; an empty list is valid")
        elif expected_untracked is None or untracked != expected_untracked:
            validation.add("holistic-untracked-content-mismatch", "verifiedUntrackedContent must exactly match the Candidate untracked manifest records")
        for field in HOLISTIC_FORBIDDEN_FIELDS:
            if field in request:
                validation.add("holistic-input-contamination", f"holistic Review Brief must not include {field}")


def render_review_brief(payload: dict[str, Any]) -> str:
    return "Review Brief\n\n" + json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def build_review_brief(request: dict[str, Any], *, now: datetime | None = None) -> dict[str, Any]:
    request = copy.deepcopy(request)
    validation = BriefValidation()
    now = now or datetime.now(timezone.utc)
    if request.get("schemaVersion") != SCHEMA_VERSION:
        validation.add("schema-version-unsupported", "input schemaVersion must be 2")
    for legacy_field in ("evidenceLedger", "evidenceLedgerNotRequiredReason"):
        if legacy_field in request:
            validation.add(
                "legacy-evidence-ledger-not-supported",
                f"{legacy_field} is not part of Review Brief schema version 2",
            )
    kind = request.get("reviewKind")
    role = request.get("reviewerRole")
    if kind not in REVIEW_KINDS:
        validation.add("review-kind-invalid", f"reviewKind must be one of {sorted(REVIEW_KINDS)}")
    if role not in ROLES:
        validation.add("reviewer-role-invalid", f"reviewerRole must be one of {sorted(ROLES)}")
    trigger = request.get("reviewTrigger")
    if not isinstance(trigger, dict) or not text(trigger.get("reason")):
        validation.add("review-trigger-required", "reviewTrigger.reason and riskClass are required")
        trigger = {}
    expected = expected_role(kind, trigger) if kind in REVIEW_KINDS else None
    if expected is None:
        validation.add("review-trigger-class-invalid", "reviewTrigger.riskClass does not match the review kind")
    elif role != expected:
        validation.add("review-role-mismatch", f"{kind} with this trigger requires reviewerRole={expected}")
    if trigger.get("riskClass") == "ordinary-slice" and trigger.get("boundary") in HIGH_RISK_TRIGGERS:
        validation.add("ordinary-slice-high-risk-trigger", "ordinary slice cannot declare a high-risk boundary")
    candidate_bound = kind in REVIEW_KINDS and is_candidate_bound(kind, trigger)

    for field, code in (
        ("logicalChangeId", "logical-change-id-required"),
        ("goal", "goal-required"),
        ("canonicalAnchors", "canonical-anchors-required"),
        ("supportedContractScope", "supported-contract-scope-required"),
        ("executedChecks", "executed-checks-required"),
    ):
        validation.require(request.get(field), code, f"{field} is required")
    for field, code in (
        ("logicalChangeId", "logical-change-id-invalid"),
        ("goal", "goal-invalid"),
    ):
        if request.get(field) is not None and not text(request.get(field)):
            validation.add(code, f"{field} must be a non-empty string")
    accepted = request.get("acceptedContract")
    if isinstance(accepted, dict):
        if not text(accepted.get("meaning")):
            validation.add("accepted-contract-meaning-required", "acceptedContract.meaning must be a non-empty string")
    else:
        validation.add("accepted-contract-invalid", "acceptedContract must contain anchors and meaning")
    contract = request.get("reviewContract")
    if isinstance(contract, dict):
        if not text(contract.get("revision")):
            validation.add("review-contract-revision-required", "reviewContract.revision must be a non-empty string")
        if not text(contract.get("recipe")):
            validation.add("review-contract-recipe-required", "reviewContract.recipe must be a non-empty string")
    else:
        validation.add("review-contract-invalid", "reviewContract must contain revision and recipe")
    if request.get("supportedContractScope") is not None and not string_list(request.get("supportedContractScope")):
        validation.add("supported-contract-scope-invalid", "supportedContractScope must be a non-empty string list")
    if request.get("executedChecks") is not None and (
        not isinstance(request.get("executedChecks"), list)
        or not request["executedChecks"]
        or not all(isinstance(item, dict) for item in request["executedChecks"])
    ):
        validation.add("executed-checks-invalid", "executedChecks must be a non-empty object list")

    root, repository = validate_review_target(request.get("reviewTarget"), validation)
    if isinstance(accepted, dict):
        accepted["anchors"] = validate_contract_anchors(accepted.get("anchors"), root, validation)
    request["canonicalAnchors"] = validate_canonical_anchors(request.get("canonicalAnchors"), root, validation)
    included = normalize_scope(request.get("includedScope"), "included-scope", validation) or []
    excluded_value = request.get("excludedScope")
    if excluded_value == []:
        excluded: list[str] = []
    else:
        excluded = normalize_scope(excluded_value, "excluded-scope", validation) or []
    supported = normalize_scope(request.get("supportedContractScope"), "supported-contract-scope", validation) or []
    request["supportedContractScope"] = supported
    if any(scope_contains(left, right) or scope_contains(right, left) for left in included for right in excluded):
        validation.add("scope-included-excluded-overlap", "includedScope and excludedScope must not overlap")
    if root is not None:
        validate_scope_roots(root, included, excluded, validation)
        validate_scope_roots(root, supported, [], validation)
    validate_declared_scope_containment(included, supported, "included-scope", validation)
    require_contract_fields = candidate_bound or bool(request.get("preImplementationInvariants"))
    for field in ("invariants", "matrixCells", "preImplementationInvariants", "executedChecks"):
        normalize_record_scopes(
            request,
            field,
            root,
            supported,
            validation,
            require_contract_fields=require_contract_fields,
        )
    validate_executed_checks(
        request.get("executedChecks"),
        candidate_bound=candidate_bound,
        candidate_id=request.get("candidateId"),
        logical_change_id=request.get("logicalChangeId"),
        validation=validation,
    )
    deadline = parse_deadline(request.get("deadline"), now, validation)
    review_entry_id = request.get("reviewEntryId", "unassigned")
    if review_entry_id is None or review_entry_id == "":
        review_entry_id = "unassigned"
    if not text(review_entry_id):
        validation.add("review-entry-id-invalid", "reviewEntryId must be a string or omitted for unassigned")

    validate_kind_fields(request, root, included, excluded, supported, validation)
    validate_invariant_inheritance(request, validation)
    candidate_definition = None
    candidate_preflight = None
    if candidate_bound:
        for field, code in (
            ("invariants", "candidate-invariants-required"),
            ("matrixCells", "candidate-matrix-cells-required"),
            ("triggeredLensScope", "candidate-lens-scope-required"),
        ):
            validation.require(request.get(field), code, f"Candidate-bound review requires {field}")
        candidate_definition, candidate_preflight = validate_candidate(
            request, root, repository, included, excluded, supported, validation
        )
        if candidate_preflight["result"] == "verified" and validation.diagnostics:
            mismatch = any(item["code"] in MISMATCH_DIAGNOSTIC_CODES for item in validation.diagnostics)
            candidate_preflight = {
                **candidate_preflight,
                "result": "mismatch" if mismatch else "validation-gap",
                "diagnostics": list(validation.diagnostics),
            }
            candidate_definition = None
        input_preflight = None
    else:
        if request.get("candidateSnapshot") is not None or request.get("candidateId") is not None:
            validation.add("ordinary-slice-candidate-not-allowed", "ordinary slice review must not add an unnecessary Frozen Candidate")
        input_preflight = {
            "result": "verified" if not validation.diagnostics else "invalid",
            "evidence": {
                "reviewTarget": str(root) if root else request.get("reviewTarget"),
                "includedScope": included,
                "excludedScope": excluded,
                "targetedCheck": (request.get("completedSlice") or {}).get("targetedCheck"),
            },
        }

    if candidate_preflight and candidate_preflight["result"] == "validation-gap":
        status = "validation-gap"
    else:
        status = "invalid" if validation.diagnostics else "ready"
    payload = {
        "logicalChangeId": request.get("logicalChangeId"),
        "reviewKind": kind,
        "reviewerRole": role,
        "reviewTrigger": request.get("reviewTrigger"),
        "reviewTarget": str(root) if root else request.get("reviewTarget"),
        "reviewEntryId": review_entry_id,
        "goal": request.get("goal"),
        "acceptedContract": request.get("acceptedContract"),
        "canonicalAnchors": request.get("canonicalAnchors", []),
        "supportedContractScope": request.get("supportedContractScope"),
        "includedScope": included,
        "excludedScope": excluded,
        "reviewContract": request.get("reviewContract"),
        "executedChecks": request.get("executedChecks"),
        "deadline": deadline,
        "retry": request.get("retry", "none"),
    }
    if kind != "holistic-complete-diff-review":
        payload["reviewInstructions"] = request.get("reviewInstructions", [])
    if candidate_bound:
        payload.update(
            candidateId=request.get("candidateId"),
            candidateDefinition=candidate_definition,
            candidatePreflight=candidate_preflight,
            candidateVerificationInput=request.get("candidateSnapshot"),
        )
    else:
        payload["inputArtifactPreflight"] = input_preflight
    if kind == "targeted-review":
        payload["completedSlice"] = request.get("completedSlice")
    elif kind == "specialist-review":
        payload.update(
            assignedLens=request.get("assignedLens"),
            matrixCells=request.get("matrixCells"),
            closureMap=request.get("closureMap"),
        )
    elif kind == "targeted-closure":
        payload.update(
            findingFamily=request.get("findingFamily"),
            directCheck=request.get("directCheck"),
            includedSiblingPaths=request.get("includedSiblingPaths"),
        )
    elif kind == "holistic-complete-diff-review":
        payload.update(
            fullReviewGate=request.get("fullReviewGate"),
            completeRawDiff=request.get("completeRawDiff"),
            verifiedUntrackedContent=request.get("verifiedUntrackedContent"),
        )
    result = {
        "schemaVersion": SCHEMA_VERSION,
        "status": status,
        "reviewKind": kind,
        "reviewerRole": role,
        "reviewBrief": render_review_brief(payload) if status == "ready" else None,
        "candidateDefinition": candidate_definition,
        "candidatePreflight": candidate_preflight,
        "inputArtifactPreflight": input_preflight,
        "reviewEntryId": review_entry_id,
        "deadline": deadline,
        "diagnostics": validation.diagnostics,
    }
    return result


def write_result(result: dict[str, Any], output: Path | None) -> None:
    data = json.dumps(result, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
    if output is None:
        sys.stdout.buffer.write(data)
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(data)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="input JSON path, or - for stdin")
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    try:
        source = sys.stdin.read() if args.input == "-" else Path(args.input).read_text(encoding="utf-8")
        request = json.loads(source)
        if not isinstance(request, dict):
            raise ValueError("input must be a JSON object")
        result = build_review_brief(request)
        write_result(result, args.output)
        return 0 if result["status"] == "ready" else 2
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
