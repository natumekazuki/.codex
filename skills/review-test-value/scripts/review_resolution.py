"""Task-local retention evidence and DROP/MOVE resolution ledger.

Supported inputs are strict dictionaries:

* record identity binds a record, metadata, source, and snapshot by hash;
* retention evidence contains bounded content plus a host determination whose
  references must match that evidence;
* the immutable initial manifest contains the initial selection/artifact
  hashes and frozen review outcomes;
* the append-only ledger contains snapshot-bound resolution attempts.

The host owns semantic judgments.  This module validates their identity and
evidence bindings; it does not infer contract meaning from file existence and
never executes commands contained in review output.

Manifest keys: schema_version, task_id, initial_snapshot_hash, selection_hash,
artifact_hashes, aggregation {input,input_hash,result,result_hash}, obligations.
Retention keys: identity, metadata, disposition, evidence, determination,
source_observation, temporal_observation, retention_basis, artifact_state.
Ledger entries: attempt_id, obligation_id, origin_hash, action, state, and a
resolution containing current snapshot, source transition, target, DROP reason,
check receipts, and unresolved reason.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Any

from extract_test_values import validate_metadata
from review_routing import aggregate_gate, canonical_json
from validate_review_result import ResultValidationError, aggregate_results, result_hash


MANIFEST_VERSION = "test-value-resolution-manifest-v1"
LEDGER_VERSION = "test-value-resolution-ledger-v1"
RETENTION_EVIDENCE_KINDS = {
    "accepted-contract",
    "security-safety",
    "approved-compatibility",
    "incident-regression",
    "reference-model",
}
RESOLUTION_ACTIONS = {"MOVE_TO_POLICY_CHECK", "DROP"}


class ResolutionStateError(ValueError):
    """Raised when task-local resolution state cannot be trusted."""

    def __init__(self, reason_code: str, message: str) -> None:
        super().__init__(message)
        self.reason_code = reason_code


def content_hash(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def build_retention_evidence(
    *,
    identity: dict[str, Any],
    metadata: dict[str, Any],
    disposition: str,
    evidence: list[dict[str, Any]],
    determination: dict[str, Any] | None,
    source_observation: dict[str, Any],
    temporal_observation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate bounded host evidence and derive retention/artifact enums."""

    derived = _derive_retention(
        identity=identity,
        metadata=metadata,
        disposition=disposition,
        evidence=evidence,
        determination=determination,
        source_observation=source_observation,
        temporal_observation=temporal_observation,
    )
    result = {
        "identity": derived["identity"],
        "metadata": metadata,
        "disposition": disposition,
        "evidence": derived["evidence"],
        "determination": determination,
        "source_observation": derived["source_observation"],
        "temporal_observation": derived["temporal_observation"],
        "retention_basis": derived["retention_basis"],
        "artifact_state": derived["artifact_state"],
    }
    validate_retention_evidence(result)
    return result


def validate_retention_evidence(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {
        "identity",
        "metadata",
        "disposition",
        "evidence",
        "determination",
        "source_observation",
        "temporal_observation",
        "retention_basis",
        "artifact_state",
    }:
        raise ResolutionStateError("RETENTION_INPUT_INVALID", "retention evidence has unexpected keys")
    derived = _derive_retention(
        identity=value["identity"],
        metadata=value["metadata"],
        disposition=value["disposition"],
        evidence=value["evidence"],
        determination=value["determination"],
        source_observation=value["source_observation"],
        temporal_observation=value["temporal_observation"],
    )
    if (
        value["retention_basis"] != derived["retention_basis"]
        or value["artifact_state"] != derived["artifact_state"]
    ):
        raise ResolutionStateError(
            "RETENTION_DERIVATION_MISMATCH",
            "retention_basis or artifact_state is not derived from the supplied evidence",
        )
    return value


def _derive_retention(
    *,
    identity: Any,
    metadata: Any,
    disposition: Any,
    evidence: Any,
    determination: Any,
    source_observation: Any,
    temporal_observation: Any,
) -> dict[str, Any]:
    record = _record_identity(identity)
    if not isinstance(metadata, dict):
        raise ResolutionStateError("RETENTION_INPUT_INVALID", "metadata must be an object")
    metadata_errors = validate_metadata(metadata, 2)
    if metadata_errors:
        raise ResolutionStateError(
            "RETENTION_INPUT_INVALID", "metadata is invalid: " + "; ".join(metadata_errors)
        )
    if result_hash(metadata) != record["metadata_hash"]:
        raise ResolutionStateError(
            "RETENTION_IDENTITY_MISMATCH",
            "metadata content does not match the record metadata hash",
        )
    if disposition not in {
        "KEEP_PERMANENT",
        "KEEP_TEMPORARY",
        "MOVE_TO_POLICY_CHECK",
        "DROP",
    }:
        raise ResolutionStateError("RETENTION_INPUT_INVALID", "disposition is invalid")
    bounded = _bounded_evidence(evidence)
    retention_basis = _retention_basis(bounded, determination)
    observed = _source_observation(source_observation, record)
    if observed["snapshot_hash"] != record["snapshot_hash"]:
        raise ResolutionStateError(
            "RETENTION_IDENTITY_MISMATCH",
            "source observation is not bound to the record snapshot",
        )
    temporal = _temporal_observation(temporal_observation, record)
    if observed["determination"] == "UNRESOLVED":
        artifact_state = None
    elif observed["determination"] == "ABSENT":
        artifact_state = "TEST_ABSENT"
    elif disposition in RESOLUTION_ACTIONS:
        artifact_state = "TEST_PRESENT"
    elif metadata["lifecycle"] == "permanent":
        artifact_state = "PERMANENT_TEST"
    elif temporal is None or temporal["determination"] == "UNRESOLVED":
        artifact_state = None
    elif temporal["determination"] == "ACTIVE":
        artifact_state = "TEMPORARY_TEST"
    else:
        artifact_state = "TEST_PRESENT"
    return {
        "identity": record,
        "evidence": bounded,
        "source_observation": observed,
        "temporal_observation": temporal,
        "retention_basis": retention_basis,
        "artifact_state": artifact_state,
    }


def retention_record_projection(value: dict[str, Any]) -> dict[str, str]:
    validated = validate_retention_evidence(value)
    if validated["artifact_state"] is None:
        raise ResolutionStateError("RETENTION_UNRESOLVED", "artifact state is unresolved")
    return {
        "record_id": validated["identity"]["record_id"],
        "retention_basis": validated["retention_basis"],
        "artifact_state": validated["artifact_state"],
    }


def initialize_resolution_state(state_dir: Path, manifest: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Create immutable manifest and empty ledger; never resumes or overwrites."""

    state_dir = Path(state_dir)
    if not state_dir.is_dir():
        raise ResolutionStateError("STATE_DIRECTORY_MISSING", "resolution state directory must already exist")
    manifest_path, ledger_path = _state_paths(state_dir)
    if manifest_path.exists() or ledger_path.exists():
        raise ResolutionStateError("STATE_ALREADY_INITIALIZED", "resolution state already exists; resume it explicitly")
    validated = validate_initial_manifest(manifest)
    manifest_digest = content_hash(canonical_json(validated))
    ledger = {
        "schema_version": LEDGER_VERSION,
        "task_id": validated["task_id"],
        "manifest_hash": manifest_digest,
        "entries": [],
    }
    _atomic_write_json(manifest_path, validated)
    _atomic_write_json(ledger_path, ledger)
    return validated, ledger


def load_resolution_state(
    state_dir: Path, *, expected_task_id: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    manifest_path, ledger_path = _state_paths(Path(state_dir))
    if not manifest_path.is_file() or not ledger_path.is_file():
        raise ResolutionStateError(
            "RESOLUTION_STATE_MISSING",
            "both initial manifest and resolution ledger are required when resuming",
        )
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ResolutionStateError("RESOLUTION_STATE_INVALID", "resolution state cannot be decoded") from exc
    try:
        validate_initial_manifest(manifest)
        validate_ledger(ledger, manifest)
    except ResolutionStateError:
        raise
    except (KeyError, TypeError, ValueError) as exc:
        raise ResolutionStateError(
            "RESOLUTION_STATE_INVALID", "resolution state has an invalid shape"
        ) from exc
    if manifest["task_id"] != expected_task_id:
        raise ResolutionStateError("TASK_ID_MISMATCH", "resolution state belongs to another task")
    return manifest, ledger


def append_resolution_attempt(
    state_dir: Path, *, expected_task_id: str, entry: dict[str, Any]
) -> dict[str, Any]:
    """Append one validated attempt and atomically replace only the ledger."""

    manifest, ledger = load_resolution_state(state_dir, expected_task_id=expected_task_id)
    validate_resolution_entry(entry, manifest)
    if entry["attempt_id"] in {item["attempt_id"] for item in ledger["entries"]}:
        raise ResolutionStateError("DUPLICATE_ATTEMPT", "attempt_id is already present")
    updated = {**ledger, "entries": [*ledger["entries"], entry]}
    validate_ledger(updated, manifest)
    _atomic_write_json(_state_paths(Path(state_dir))[1], updated)
    return updated


def evaluate_obligation_gate(
    state_dir: Path, *, expected_task_id: str
) -> dict[str, Any]:
    """Aggregate only DROP/MOVE obligations; the coordinator owns the final gate."""

    try:
        manifest, ledger = load_resolution_state(state_dir, expected_task_id=expected_task_id)
        gates = []
        latest = {entry["obligation_id"]: entry for entry in ledger["entries"]}
        unresolved: list[str] = []
        for obligation in manifest["obligations"]:
            obligation_id = obligation["obligation_id"]
            attempt = latest.get(obligation_id)
            if attempt is None or attempt["state"] == "UNRESOLVED":
                gates.append("CHANGES_REQUIRED")
                unresolved.append(obligation_id)
            else:
                gates.append("PASS")
        return {
            "obligation_gate": aggregate_gate(gates),
            "unresolved_obligation_ids": unresolved,
            "reason_codes": [],
        }
    except ResolutionStateError as exc:
        return {
            "obligation_gate": "BLOCKED",
            "unresolved_obligation_ids": [],
            "reason_codes": [exc.reason_code],
        }


def validate_initial_manifest(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {
        "schema_version",
        "task_id",
        "initial_snapshot_hash",
        "selection_hash",
        "artifact_hashes",
        "aggregation",
        "obligations",
    }:
        raise ResolutionStateError("MANIFEST_INVALID", "initial manifest has unexpected keys")
    if value["schema_version"] != MANIFEST_VERSION:
        raise ResolutionStateError("MANIFEST_INVALID", "initial manifest version is invalid")
    _nonempty(value["task_id"], "task_id")
    _hash(value["initial_snapshot_hash"], "initial_snapshot_hash")
    _hash(value["selection_hash"], "selection_hash")
    hashes = value["artifact_hashes"]
    if (
        not isinstance(hashes, list)
        or any(not isinstance(item, str) for item in hashes)
        or len(hashes) != len(set(hashes))
    ):
        raise ResolutionStateError("MANIFEST_INVALID", "artifact_hashes must be a unique array")
    for item in hashes:
        _hash(item, "artifact_hash")
    aggregation = value["aggregation"]
    if not isinstance(aggregation, dict) or set(aggregation) != {
        "input",
        "input_hash",
        "result",
        "result_hash",
    }:
        raise ResolutionStateError("MANIFEST_INVALID", "aggregation has unexpected keys")
    if aggregation["input_hash"] != result_hash(aggregation["input"]):
        raise ResolutionStateError("MANIFEST_INVALID", "aggregation input hash does not match")
    try:
        expected_result = aggregate_results(aggregation["input"])
    except (KeyError, TypeError, ResultValidationError) as exc:
        raise ResolutionStateError("MANIFEST_INVALID", "initial aggregation input is invalid") from exc
    if aggregation["result"] != expected_result:
        raise ResolutionStateError("MANIFEST_INVALID", "initial aggregate result does not match its input")
    if aggregation["result_hash"] != result_hash(expected_result):
        raise ResolutionStateError("MANIFEST_INVALID", "initial aggregate result hash does not match")
    if aggregation["input_hash"] not in hashes or aggregation["result_hash"] not in hashes:
        raise ResolutionStateError(
            "MANIFEST_INVALID", "aggregation hashes must be present in initial artifact_hashes"
        )
    packet_records = aggregation["input"]["alignment_packet"]["records"]
    final_by_id = {record["record_id"]: record for record in expected_result["records"]}
    packet_by_id = {record["record_id"]: record for record in packet_records}
    retention_by_id = {
        record["record_id"]: record for record in aggregation["input"]["retention_records"]
    }
    obligations = value["obligations"]
    if not isinstance(obligations, list):
        raise ResolutionStateError("MANIFEST_INVALID", "obligations must be an array")
    ids = []
    for obligation in obligations:
        _validate_obligation(
            obligation,
            value["initial_snapshot_hash"],
            packet_by_id,
            retention_by_id,
            final_by_id,
        )
        ids.append(obligation["obligation_id"])
    if len(ids) != len(set(ids)):
        raise ResolutionStateError("MANIFEST_INVALID", "obligation_id values must be unique")
    expected_obligation_records = [
        record["record_id"]
        for record in expected_result["records"]
        if record["disposition"] in RESOLUTION_ACTIONS
        and record["gate"] == "CHANGES_REQUIRED"
    ]
    actual_obligation_records = [item["origin"]["record"]["record_id"] for item in obligations]
    if actual_obligation_records != expected_obligation_records:
        raise ResolutionStateError(
            "MANIFEST_INVALID",
            "obligations must exactly match the canonical initial DROP/MOVE results",
        )
    return value


def validate_ledger(value: Any, manifest: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {"schema_version", "task_id", "manifest_hash", "entries"}:
        raise ResolutionStateError("LEDGER_INVALID", "resolution ledger has unexpected keys")
    if value["schema_version"] != LEDGER_VERSION or value["task_id"] != manifest["task_id"]:
        raise ResolutionStateError("LEDGER_INVALID", "resolution ledger identity is invalid")
    if value["manifest_hash"] != content_hash(canonical_json(manifest)):
        raise ResolutionStateError("MANIFEST_HASH_MISMATCH", "ledger does not match the immutable manifest")
    entries = value["entries"]
    if not isinstance(entries, list):
        raise ResolutionStateError("LEDGER_INVALID", "ledger entries must be an array")
    attempt_ids = []
    for entry in entries:
        validate_resolution_entry(entry, manifest)
        attempt_ids.append(entry["attempt_id"])
    if len(attempt_ids) != len(set(attempt_ids)):
        raise ResolutionStateError("LEDGER_INVALID", "ledger attempt_id values must be unique")
    return value


def validate_resolution_entry(entry: Any, manifest: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(entry, dict) or set(entry) != {
        "attempt_id",
        "obligation_id",
        "origin_hash",
        "action",
        "state",
        "resolution",
    }:
        raise ResolutionStateError("RESOLUTION_INVALID", "resolution entry has unexpected keys")
    _nonempty(entry["attempt_id"], "attempt_id")
    obligations = {item["obligation_id"]: item for item in manifest["obligations"]}
    obligation = obligations.get(entry["obligation_id"])
    if obligation is None:
        raise ResolutionStateError("RESOLUTION_INVALID", "resolution obligation is not in the initial manifest")
    if entry["origin_hash"] != content_hash(canonical_json(obligation["origin"])):
        raise ResolutionStateError("ORIGIN_HASH_MISMATCH", "resolution does not match the frozen origin")
    if entry["action"] != obligation["action"]:
        raise ResolutionStateError("RESOLUTION_INVALID", "resolution action does not match the obligation")
    if entry["state"] not in {"RESOLVED", "UNRESOLVED"}:
        raise ResolutionStateError("RESOLUTION_INVALID", "resolution state is invalid")
    resolution = _resolution_payload(entry["resolution"], obligation)
    if entry["state"] == "UNRESOLVED":
        if not resolution["reason"]:
            raise ResolutionStateError("RESOLUTION_INVALID", "UNRESOLVED requires a reason")
        return entry
    if resolution["reason"] is not None:
        raise ResolutionStateError("RESOLUTION_INVALID", "RESOLVED must not include an unresolved reason")
    removal = resolution["removal"]
    if removal is None or removal["determination"] != "REMOVED":
        raise ResolutionStateError("REMOVAL_UNVERIFIED", "resolved action requires verified origin removal")
    if entry["action"] == "MOVE_TO_POLICY_CHECK":
        if resolution["target"] is None or resolution["drop_reason"] is not None:
            raise ResolutionStateError("MOVE_INCOMPLETE", "MOVE requires a target and no DROP reason")
        _require_matching_check(resolution)
    else:
        drop_reason = resolution["drop_reason"]
        if drop_reason is None:
            raise ResolutionStateError("DROP_INCOMPLETE", "DROP requires a typed reason")
        retention = obligation["origin"]["retention"]
        if drop_reason["determination"] == "NO_ALTERNATIVE_REQUIRED":
            if retention["retention_basis"] != "ABSENT" or resolution["target"] is not None:
                raise ResolutionStateError("DROP_INCOMPLETE", "no-alternative DROP requires an ABSENT retention basis")
            evidence_by_ref = {
                (item["ref"], item["content_hash"]): item
                for item in retention["evidence"]
            }
            if any(
                evidence_by_ref[(item["ref"], item["content_hash"])]["kind"]
                != "accepted-contract"
                for item in drop_reason["evidence_refs"]
                if (item["ref"], item["content_hash"]) in evidence_by_ref
            ):
                raise ResolutionStateError(
                    "DROP_EVIDENCE_MISMATCH",
                    "no-alternative DROP must be supported by accepted-contract evidence",
                )
        else:
            if retention["retention_basis"] != "PRESENT" or resolution["target"] is None:
                raise ResolutionStateError("DROP_INCOMPLETE", "covered DROP requires a PRESENT basis and canonical target")
            _require_matching_check(resolution)
        available = {
            (item["ref"], item["content_hash"])
            for item in retention["determination"]["evidence_refs"]
        }
        for ref in drop_reason["evidence_refs"]:
            if (ref["ref"], ref["content_hash"]) not in available:
                raise ResolutionStateError("DROP_EVIDENCE_MISMATCH", "DROP reason references evidence outside the frozen origin")
    return entry


def _validate_obligation(
    value: Any,
    manifest_snapshot_hash: str,
    packet_by_id: dict[str, dict[str, Any]],
    retention_by_id: dict[str, dict[str, Any]],
    final_by_id: dict[str, dict[str, Any]],
) -> None:
    if not isinstance(value, dict) or set(value) != {"obligation_id", "action", "origin"}:
        raise ResolutionStateError("MANIFEST_INVALID", "obligation has unexpected keys")
    _nonempty(value["obligation_id"], "obligation_id")
    if value["action"] not in RESOLUTION_ACTIONS:
        raise ResolutionStateError("MANIFEST_INVALID", "obligation action is invalid")
    origin = value["origin"]
    if not isinstance(origin, dict) or set(origin) != {"record", "retention", "frozen_result"}:
        raise ResolutionStateError("MANIFEST_INVALID", "obligation origin has unexpected keys")
    record = _record_identity(origin["record"])
    if record["snapshot_hash"] != manifest_snapshot_hash:
        raise ResolutionStateError("MANIFEST_INVALID", "origin record is not in the initial snapshot")
    retention = validate_retention_evidence(origin["retention"])
    if retention["identity"] != record or retention["disposition"] != value["action"]:
        raise ResolutionStateError("MANIFEST_INVALID", "origin retention does not match the obligation")
    record_id = record["record_id"]
    packet_record = packet_by_id.get(record_id)
    if packet_record is None:
        raise ResolutionStateError("MANIFEST_INVALID", "origin record is absent from canonical aggregation")
    if (
        packet_record["metadata_hash"] != record["metadata_hash"]
        or packet_record["source_hash"] != record["source_hash"]
    ):
        raise ResolutionStateError("MANIFEST_INVALID", "origin record hashes do not match canonical aggregation")
    source = packet_record["source"]
    canonical_locator = {
        "path": source["path"],
        "symbol": source["symbol"],
        "declaration_start_line": source["declaration_start_line"],
    }
    if record["locator"] != canonical_locator:
        raise ResolutionStateError(
            "MANIFEST_INVALID", "origin record locator does not match canonical aggregation"
        )
    if retention_record_projection(retention) != retention_by_id.get(record_id):
        raise ResolutionStateError("MANIFEST_INVALID", "origin retention does not match canonical aggregation")
    frozen = final_by_id.get(record_id)
    if origin["frozen_result"] != frozen:
        raise ResolutionStateError("MANIFEST_INVALID", "frozen result is not canonical")
    if (
        frozen is None
        or frozen["status"] not in {"ACCEPT", "REDESIGN"}
        or frozen["disposition"] != value["action"]
        or frozen["gate"] != "CHANGES_REQUIRED"
    ):
        raise ResolutionStateError(
            "MANIFEST_INVALID", "only complete canonical DROP/MOVE outcomes create obligations"
        )


def _record_identity(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {
        "record_id",
        "metadata_hash",
        "source_hash",
        "snapshot_hash",
        "locator",
    }:
        raise ResolutionStateError("RECORD_IDENTITY_INVALID", "record identity has unexpected keys")
    _nonempty(value["record_id"], "record_id")
    for name in ("metadata_hash", "source_hash", "snapshot_hash"):
        _hash(value[name], name)
    locator = value["locator"]
    if not isinstance(locator, dict) or set(locator) != {"path", "symbol", "declaration_start_line"}:
        raise ResolutionStateError("RECORD_IDENTITY_INVALID", "record locator has unexpected keys")
    _nonempty(locator["path"], "locator.path")
    _nonempty(locator["symbol"], "locator.symbol")
    if not isinstance(locator["declaration_start_line"], int) or isinstance(locator["declaration_start_line"], bool) or locator["declaration_start_line"] < 1:
        raise ResolutionStateError("RECORD_IDENTITY_INVALID", "declaration_start_line must be positive")
    return value


def _bounded_evidence(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise ResolutionStateError("RETENTION_INPUT_INVALID", "evidence must be an array")
    seen = set()
    for item in value:
        if not isinstance(item, dict) or set(item) != {"kind", "ref", "content", "content_hash", "meaning"}:
            raise ResolutionStateError("RETENTION_INPUT_INVALID", "bounded evidence has unexpected keys")
        if item["kind"] not in RETENTION_EVIDENCE_KINDS:
            raise ResolutionStateError("RETENTION_INPUT_INVALID", "bounded evidence kind is invalid")
        for name in ("ref", "content", "meaning"):
            _nonempty(item[name], f"evidence.{name}")
        if item["content_hash"] != content_hash(item["content"]):
            raise ResolutionStateError("RETENTION_EVIDENCE_HASH_MISMATCH", "bounded evidence content hash does not match")
        key = (item["ref"], item["content_hash"])
        if key in seen:
            raise ResolutionStateError("RETENTION_INPUT_INVALID", "bounded evidence references must be unique")
        seen.add(key)
    return value


def _retention_basis(evidence: list[dict[str, Any]], determination: Any) -> str:
    if determination is None:
        return "UNRESOLVED"
    if not isinstance(determination, dict) or set(determination) != {"determination", "rationale", "evidence_refs"}:
        raise ResolutionStateError("RETENTION_INPUT_INVALID", "retention determination has unexpected keys")
    if determination["determination"] not in {"SUPPORTED", "UNSUPPORTED"}:
        raise ResolutionStateError("RETENTION_INPUT_INVALID", "retention determination is invalid")
    _nonempty(determination["rationale"], "retention rationale")
    refs = determination["evidence_refs"]
    if not isinstance(refs, list) or not refs:
        return "UNRESOLVED"
    available = {(item["ref"], item["content_hash"]) for item in evidence}
    used = []
    for item in refs:
        if not isinstance(item, dict) or set(item) != {"ref", "content_hash"}:
            raise ResolutionStateError("RETENTION_INPUT_INVALID", "retention evidence ref has unexpected keys")
        pair = (_nonempty(item["ref"], "evidence ref"), _hash(item["content_hash"], "evidence ref hash"))
        used.append(pair)
    if len(used) != len(set(used)) or any(pair not in available for pair in used):
        return "UNRESOLVED"
    return "PRESENT" if determination["determination"] == "SUPPORTED" else "ABSENT"


def _source_observation(value: Any, record: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {
        "determination",
        "record_id",
        "metadata_hash",
        "source_hash",
        "snapshot_hash",
        "ref",
        "content",
        "content_hash",
        "meaning",
    }:
        raise ResolutionStateError("SOURCE_OBSERVATION_INVALID", "source observation has unexpected keys")
    if value["determination"] not in {"PRESENT", "ABSENT", "UNRESOLVED"}:
        raise ResolutionStateError("SOURCE_OBSERVATION_INVALID", "source determination is invalid")
    for name in ("record_id", "metadata_hash", "source_hash"):
        if value[name] != record[name]:
            raise ResolutionStateError("RETENTION_IDENTITY_MISMATCH", f"source observation {name} does not match")
    _hash(value["snapshot_hash"], "source observation snapshot_hash")
    for name in ("ref", "content", "meaning"):
        _nonempty(value[name], f"source observation {name}")
    if value["content_hash"] != content_hash(value["content"]):
        raise ResolutionStateError("SOURCE_OBSERVATION_INVALID", "source observation content hash does not match")
    if value["determination"] == "PRESENT" and value["content_hash"] != record["source_hash"]:
        raise ResolutionStateError(
            "RETENTION_IDENTITY_MISMATCH",
            "present source observation does not match the record source hash",
        )
    return value


def _temporal_observation(value: Any, record: dict[str, Any]) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) != {
        "determination",
        "snapshot_hash",
        "ref",
        "content",
        "content_hash",
        "meaning",
    }:
        raise ResolutionStateError(
            "TEMPORAL_OBSERVATION_INVALID", "temporal observation has unexpected keys"
        )
    if value["determination"] not in {"ACTIVE", "EXPIRED", "UNRESOLVED"}:
        raise ResolutionStateError(
            "TEMPORAL_OBSERVATION_INVALID", "temporal determination is invalid"
        )
    if value["snapshot_hash"] != record["snapshot_hash"]:
        raise ResolutionStateError(
            "RETENTION_IDENTITY_MISMATCH", "temporal observation snapshot does not match"
        )
    for name in ("ref", "content", "meaning"):
        _nonempty(value[name], f"temporal observation {name}")
    if value["content_hash"] != content_hash(value["content"]):
        raise ResolutionStateError(
            "TEMPORAL_OBSERVATION_INVALID", "temporal observation content hash does not match"
        )
    return value


def _resolution_payload(value: Any, obligation: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {
        "current_snapshot_hash",
        "removal",
        "target",
        "drop_reason",
        "checks",
        "reason",
    }:
        raise ResolutionStateError("RESOLUTION_INVALID", "resolution payload has unexpected keys")
    snapshot_hash = _hash(value["current_snapshot_hash"], "current_snapshot_hash")
    removal = value["removal"]
    if removal is not None:
        if not isinstance(removal, dict) or set(removal) != {
            "origin",
            "determination",
            "current_snapshot_hash",
            "ref",
            "content",
            "content_hash",
            "meaning",
        }:
            raise ResolutionStateError("RESOLUTION_INVALID", "source transition has unexpected keys")
        if _record_identity(removal["origin"]) != obligation["origin"]["record"]:
            raise ResolutionStateError("RESOLUTION_INVALID", "source transition origin does not match")
        if removal["determination"] not in {"REMOVED", "PRESENT", "UNRESOLVED"}:
            raise ResolutionStateError("RESOLUTION_INVALID", "source transition determination is invalid")
        if removal["current_snapshot_hash"] != snapshot_hash:
            raise ResolutionStateError("RESOLUTION_INVALID", "source transition snapshot does not match")
        for name in ("ref", "content", "meaning"):
            _nonempty(removal[name], f"source transition {name}")
        if removal["content_hash"] != content_hash(removal["content"]):
            raise ResolutionStateError("RESOLUTION_INVALID", "source transition content hash does not match")
    target = value["target"]
    if target is not None:
        if not isinstance(target, dict) or set(target) != {"snapshot_hash", "ref", "content", "content_hash", "meaning"}:
            raise ResolutionStateError("RESOLUTION_INVALID", "resolution target has unexpected keys")
        if target["snapshot_hash"] != snapshot_hash:
            raise ResolutionStateError("RESOLUTION_INVALID", "resolution target snapshot does not match")
        for name in ("ref", "content", "meaning"):
            _nonempty(target[name], f"resolution target {name}")
        if target["content_hash"] != content_hash(target["content"]):
            raise ResolutionStateError("RESOLUTION_INVALID", "resolution target content hash does not match")
    drop_reason = value["drop_reason"]
    if drop_reason is not None:
        if not isinstance(drop_reason, dict) or set(drop_reason) != {"determination", "rationale", "evidence_refs"}:
            raise ResolutionStateError("RESOLUTION_INVALID", "DROP reason has unexpected keys")
        if drop_reason["determination"] not in {"NO_ALTERNATIVE_REQUIRED", "COVERED_BY_EXISTING_CHECK"}:
            raise ResolutionStateError("RESOLUTION_INVALID", "DROP determination is invalid")
        _nonempty(drop_reason["rationale"], "DROP rationale")
        refs = drop_reason["evidence_refs"]
        if not isinstance(refs, list) or not refs:
            raise ResolutionStateError("RESOLUTION_INVALID", "DROP reason requires evidence refs")
        for item in refs:
            if not isinstance(item, dict) or set(item) != {"ref", "content_hash"}:
                raise ResolutionStateError("RESOLUTION_INVALID", "DROP evidence ref has unexpected keys")
            _nonempty(item["ref"], "DROP evidence ref")
            _hash(item["content_hash"], "DROP evidence hash")
    checks = value["checks"]
    if not isinstance(checks, list):
        raise ResolutionStateError("RESOLUTION_INVALID", "checks must be an array")
    for check in checks:
        if not isinstance(check, dict) or set(check) != {
            "check_id",
            "snapshot_hash",
            "target_ref",
            "target_hash",
            "exit_code",
            "output_hash",
        }:
            raise ResolutionStateError("RESOLUTION_INVALID", "check receipt has unexpected keys")
        _nonempty(check["check_id"], "check_id")
        if check["snapshot_hash"] != snapshot_hash:
            raise ResolutionStateError("RESOLUTION_INVALID", "check receipt snapshot does not match")
        _nonempty(check["target_ref"], "check target_ref")
        _hash(check["target_hash"], "check target_hash")
        if not isinstance(check["exit_code"], int) or isinstance(check["exit_code"], bool):
            raise ResolutionStateError("RESOLUTION_INVALID", "check exit_code must be an integer")
        _hash(check["output_hash"], "check output_hash")
    if value["reason"] is not None:
        _nonempty(value["reason"], "unresolved reason")
    return value


def _require_matching_check(resolution: dict[str, Any]) -> None:
    target = resolution["target"]
    if not any(
        check["snapshot_hash"] == target["snapshot_hash"]
        and check["target_ref"] == target["ref"]
        and check["target_hash"] == target["content_hash"]
        and check["exit_code"] == 0
        for check in resolution["checks"]
    ):
        raise ResolutionStateError(
            "DIRECT_CHECK_MISSING",
            "resolution requires a successful check bound to the current target and snapshot",
        )


def _state_paths(state_dir: Path) -> tuple[Path, Path]:
    return state_dir / "initial-manifest.json", state_dir / "resolution-ledger.json"


def _atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    data = (canonical_json(value) + "\n").encode("utf-8")
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False
        ) as stream:
            temp_path = Path(stream.name)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_path, path)
        temp_path = None
        if os.name != "nt":
            directory_fd = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
    except OSError as exc:
        raise ResolutionStateError("STATE_WRITE_FAILED", f"failed to persist {path.name}") from exc
    finally:
        if temp_path is not None:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass


def _nonempty(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ResolutionStateError("INPUT_INVALID", f"{name} must be a non-empty string")
    return value


def _hash(value: Any, name: str) -> str:
    text = _nonempty(value, name)
    if len(text) != 71 or not text.startswith("sha256:"):
        raise ResolutionStateError("INPUT_INVALID", f"{name} must be a sha256 hash")
    try:
        int(text[7:], 16)
    except ValueError as exc:
        raise ResolutionStateError("INPUT_INVALID", f"{name} must be a sha256 hash") from exc
    return text
