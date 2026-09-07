#!/usr/bin/env python3
"""Run explicit, non-blocking review diagnostics from a published generation."""

from __future__ import annotations

import argparse
import copy
import os
from pathlib import Path
import re
import tempfile
from typing import Any, Sequence

from build_review_packets import PacketError, canonical_json
from review_routing import RoutingError
from run_test_value_review import (
    CoordinatorBlocked,
    GENERATION_VERSION,
    TASK_STATE_VERSION,
    _canonical_hash,
    _execute_batch_round,
    _load_generation,
    _read_json_object,
    _resolve_repository,
    _toolchain_identity,
    execution_policy,
    snapshot_descriptor,
)
from validate_review_result import (
    ALIGNMENT_RECORD_KEYS,
    ResultValidationError,
    result_hash,
    validate_alignment_packet,
    validate_deep_packet,
    validate_phase_result,
)


DIAGNOSTIC_VERSION = "test-value-review-diagnostic-v1"
ARTIFACT_FILENAME = "diagnostic.json"
DIAGNOSTIC_MODES = ("audit", "all-phases")
_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
_SAFE_FIELD = re.compile(r"^[a-z0-9_]{1,64}(?:\.[a-z0-9_]{1,64})?$")
_SAFE_CODE = re.compile(r"^[A-Za-z0-9_-]{1,96}$")
_SAFE_REASON = re.compile(r"^[A-Z0-9_-]{1,96}$")


class DiagnosticBlocked(RuntimeError):
    """A diagnostic could not be trusted or completed."""

    def __init__(
        self,
        reason_code: str,
        message: str = "diagnostic validation failed",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.reason_code = reason_code
        self.details = details or {}


def _safe_reason(value: Any, fallback: str = "DIAGNOSTIC_VALIDATION_FAILED") -> str:
    return value if isinstance(value, str) and _SAFE_REASON.fullmatch(value) else fallback


def _blocked(exc: BaseException, fallback: str) -> DiagnosticBlocked:
    code = getattr(exc, "reason_code", None) or getattr(exc, "code", None)
    code = _safe_reason(code, fallback)
    return DiagnosticBlocked(
        code,
        details=_sanitize_details(getattr(exc, "details", {})),
    )


def _sanitize_details(value: Any) -> dict[str, Any]:
    """Retain only safe coordinates; never expose packet text or raw messages."""

    if not isinstance(value, dict):
        return {}
    safe: dict[str, Any] = {}
    for key in ("phase", "violation_type", "validator_error_code"):
        item = value.get(key)
        if isinstance(item, str) and _SAFE_CODE.fullmatch(item):
            safe[key] = item
    for key in (
        "record_id",
        "record_id_hash",
        "invalid_field_hash",
        "execution_policy_hash",
        "plan_hash",
        "packet_hash",
        "packet_input_hash",
    ):
        item = value.get(key)
        if isinstance(item, str) and _SHA256.fullmatch(item):
            safe[key] = item
    item = value.get("invalid_field")
    if isinstance(item, str) and _SAFE_FIELD.fullmatch(item):
        safe["invalid_field"] = item
    for key in (
        "batch_index",
        "batch_count",
        "completed_batches",
        "batch_seconds",
        "batch_concurrency",
    ):
        item = value.get(key)
        if isinstance(item, int) and not isinstance(item, bool) and 0 <= item <= 100000:
            safe[key] = item
    for key in ("validation_details", "canary_evidence"):
        nested = _sanitize_details(value.get(key))
        if nested:
            safe[key] = nested
    return safe


def _load_published(
    state_dir: Path, generation_id: str | None
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Read and fully validate one published generation without writing state."""

    manifest_path = state_dir / "task-manifest.json"
    if not manifest_path.is_file():
        raise DiagnosticBlocked("STATE_MANIFEST_MISSING")
    try:
        state = _read_json_object(manifest_path, "STATE")
    except CoordinatorBlocked as exc:
        raise _blocked(exc, "STATE_INVALID") from exc
    expected = {
        "schema_version",
        "execution_policy",
        "execution_policy_hash",
        "task_id",
        "repository_root",
        "base_commit_oid",
        "target_mode",
        "generations",
    }
    if set(state) != expected or state.get("schema_version") != TASK_STATE_VERSION:
        raise DiagnosticBlocked("STATE_VERSION_MISMATCH")
    policy = state.get("execution_policy")
    try:
        if state["execution_policy_hash"] != _canonical_hash(policy):
            raise DiagnosticBlocked("STATE_INVALID")
        execution_policy(policy["batch_seconds"], policy.get("batch_concurrency"))
    except DiagnosticBlocked:
        raise
    except (KeyError, TypeError, CoordinatorBlocked) as exc:
        raise DiagnosticBlocked("STATE_INVALID") from exc
    descriptors = state.get("generations")
    if not isinstance(descriptors, list) or not descriptors:
        raise DiagnosticBlocked("GENERATION_MISSING")
    descriptor = (
        descriptors[-1]
        if generation_id is None
        else next(
            (
                item
                for item in descriptors
                if isinstance(item, dict) and item.get("generation_id") == generation_id
            ),
            None,
        )
    )
    if not isinstance(descriptor, dict):
        raise DiagnosticBlocked("GENERATION_UNKNOWN" if generation_id else "STATE_INVALID")
    try:
        generation = _load_generation(state_dir, descriptor)
    except (
        CoordinatorBlocked,
        PacketError,
        ResultValidationError,
        RoutingError,
        OSError,
        KeyError,
        TypeError,
    ) as exc:
        raise _blocked(exc, "STATE_INVALID") from exc
    if generation.get("schema_version") != GENERATION_VERSION:
        raise DiagnosticBlocked("STATE_VERSION_MISMATCH")
    return state, generation


def _preflight(
    state: dict[str, Any],
    generation: dict[str, Any],
    *,
    state_dir: Path,
    cli: str,
    root_override: Path | None = None,
) -> tuple[Path, dict[str, Any]]:
    try:
        manifest_root = Path(state["repository_root"])
    except (TypeError, ValueError) as exc:
        raise DiagnosticBlocked("STATE_INVALID") from exc
    try:
        root = _resolve_repository(root_override or manifest_root)
        if root_override is not None and root != _resolve_repository(manifest_root):
            raise DiagnosticBlocked("STATE_IDENTITY_MISMATCH")
    except DiagnosticBlocked:
        raise
    except CoordinatorBlocked as exc:
        raise _blocked(exc, "ROOT_INVALID") from exc
    if state_dir.resolve().is_relative_to(root.resolve()):
        raise DiagnosticBlocked("STATE_INSIDE_ROOT")

    target = generation.get("target_snapshot")
    if not isinstance(target, dict):
        raise DiagnosticBlocked("STATE_INVALID")
    try:
        current = snapshot_descriptor(
            root,
            target["base_commit_oid"],
            mode=target["target_mode"],
            head_oid=target.get("head_commit_oid"),
        )
    except (CoordinatorBlocked, KeyError, TypeError) as exc:
        raise _blocked(exc, "SNAPSHOT_UNAVAILABLE") from exc
    if current != target:
        raise DiagnosticBlocked("SNAPSHOT_CHANGED")

    frozen = generation.get("toolchain_identity")
    if not isinstance(frozen, dict):
        raise DiagnosticBlocked("STATE_INVALID")
    if frozen.get("execution_policy") != state.get("execution_policy"):
        raise DiagnosticBlocked("TOOLCHAIN_CHANGED")
    try:
        current_identity = _toolchain_identity(cli, Path(__file__).resolve().parents[3])
    except CoordinatorBlocked as exc:
        raise _blocked(exc, "TOOLCHAIN_CHANGED") from exc
    current_identity = {**current_identity, "execution_policy": state["execution_policy"]}
    if current_identity != frozen:
        raise DiagnosticBlocked("TOOLCHAIN_CHANGED")
    return root, current_identity


def _output_dir(path: Path, *, root: Path, state_dir: Path) -> Path:
    try:
        resolved = path.resolve(strict=False)
        if resolved == root.resolve(strict=True) or resolved.is_relative_to(root.resolve(strict=True)):
            raise DiagnosticBlocked("OUTPUT_INSIDE_REPOSITORY")
        if resolved == state_dir.resolve(strict=True) or resolved.is_relative_to(state_dir.resolve(strict=True)):
            raise DiagnosticBlocked("OUTPUT_INSIDE_STATE")
    except DiagnosticBlocked:
        raise
    except OSError as exc:
        raise DiagnosticBlocked("OUTPUT_DIRECTORY_INVALID") from exc
    if resolved.exists():
        raise DiagnosticBlocked("OUTPUT_DIRECTORY_EXISTS")
    return resolved


def _alignment_records(packet: dict[str, Any]) -> list[dict[str, Any]]:
    records = packet.get("records") if isinstance(packet, dict) else None
    if not isinstance(records, list):
        raise DiagnosticBlocked("STATE_INVALID")
    ids = [item.get("record_id") if isinstance(item, dict) else None for item in records]
    if any(not isinstance(item, str) for item in ids) or len(ids) != len(set(ids)):
        raise DiagnosticBlocked("STATE_INVALID")
    return records


def _metadata_packet(records: list[dict[str, Any]]) -> dict[str, Any]:
    try:
        packet_records = [
            {key: copy.deepcopy(record[key]) for key in (
                "record_id", "metadata_format_version", "metadata", "metadata_hash"
            )}
            for record in records
        ]
    except KeyError as exc:
        raise DiagnosticBlocked("STATE_INVALID") from exc
    return {"review_contract_version": "metadata-review-v3", "records": packet_records}


def _metadata_subset(result: dict[str, Any], records: list[dict[str, Any]]) -> dict[str, Any]:
    reviews = result.get("reviews") if isinstance(result, dict) else None
    if (
        result.get("review_contract_version") != "metadata-review-v3"
        or not isinstance(reviews, list)
    ):
        raise DiagnosticBlocked("RESULT_VALIDATION_FAILED")
    by_id: dict[str, dict[str, Any]] = {}
    for review in reviews:
        if not isinstance(review, dict) or not isinstance(review.get("record_id"), str):
            raise DiagnosticBlocked("RESULT_VALIDATION_FAILED")
        if review["record_id"] in by_id:
            raise DiagnosticBlocked("RESULT_VALIDATION_FAILED")
        by_id[review["record_id"]] = review
    try:
        projected = {
            "review_contract_version": result["review_contract_version"],
            "reviews": [copy.deepcopy(by_id[item["record_id"]]) for item in records],
        }
    except KeyError as exc:
        raise DiagnosticBlocked("RESULT_VALIDATION_FAILED") from exc
    try:
        validate_phase_result("metadata", projected, _metadata_packet(records)["records"])
    except ResultValidationError as exc:
        raise _blocked(exc, "RESULT_VALIDATION_FAILED") from exc
    return projected


def _alignment_packet(records: list[dict[str, Any]], metadata: dict[str, Any]) -> dict[str, Any]:
    try:
        metadata_reviews = validate_phase_result(
            "metadata", metadata, _metadata_packet(records)["records"]
        )["reviews"]
    except ResultValidationError as exc:
        raise _blocked(exc, "RESULT_VALIDATION_FAILED") from exc
    reviews = {item["record_id"]: item for item in metadata_reviews}
    packet_records = []
    for record in records:
        if record["record_id"] not in reviews:
            raise DiagnosticBlocked("RESULT_VALIDATION_FAILED")
        item = copy.deepcopy(record)
        item["metadata_review"] = copy.deepcopy(reviews[record["record_id"]])
        packet_records.append(item)
    packet = {
        "review_contract_version": "alignment-review-v3",
        "metadata_result_hash": result_hash(metadata),
        "records": packet_records,
    }
    try:
        validate_alignment_packet(packet, metadata)
    except ResultValidationError as exc:
        raise _blocked(exc, "RESULT_VALIDATION_FAILED") from exc
    return packet


def _route_maps(
    aggregation: dict[str, Any], records: list[dict[str, Any]], alignment_result: dict[str, Any]
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    entries = aggregation["input"]["routing_manifest"].get("records")
    if not isinstance(entries, list):
        raise DiagnosticBlocked("STATE_INVALID")
    routes = {entry["record_id"]: entry["result"] for entry in entries}
    try:
        reviews = validate_phase_result("alignment", alignment_result, records)["reviews"]
    except ResultValidationError as exc:
        raise _blocked(exc, "STATE_INVALID") from exc
    alignments = {item["record_id"]: item for item in reviews}
    final_records = aggregation["result"].get("records")
    if not isinstance(final_records, list):
        raise DiagnosticBlocked("STATE_INVALID")
    finals = {item["record_id"]: item for item in final_records}
    if set(routes) != set(alignments) or not set(routes).issubset(finals):
        raise DiagnosticBlocked("STATE_INVALID")
    return routes, alignments, finals


def _is_terminal(
    record: dict[str, Any], alignment: dict[str, Any], route: dict[str, Any], final: dict[str, Any]
) -> bool:
    # The published aggregate is the authority for whether a record already
    # has a fixed outcome.  A routing marker is accepted when present so the
    # audit scope remains bound to the frozen manifest.
    for source in (route, final):
        if isinstance(source.get("terminal"), bool):
            return source["terminal"]
    if route.get("required") is False and final.get("status") == "REDESIGN":
        return True
    metadata = record.get("metadata_review")
    metadata_verdict = metadata.get("verdict") if isinstance(metadata, dict) else None
    return alignment.get("verdict") != "RECHECK" and (
        metadata_verdict == "REDESIGN" or alignment.get("verdict") == "MISMATCH"
    )


def _contexts(deep_packet: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    records = deep_packet.get("records") if isinstance(deep_packet, dict) else None
    if not isinstance(records, list):
        raise DiagnosticBlocked("STATE_INVALID")
    result = {}
    for record in records:
        if not isinstance(record, dict) or not isinstance(record.get("record_id"), str):
            raise DiagnosticBlocked("STATE_INVALID")
        if not isinstance(record.get("context"), list):
            raise DiagnosticBlocked("STATE_INVALID")
        result[record["record_id"]] = copy.deepcopy(record["context"])
    return result


def _deep_packet(
    records: list[dict[str, Any]],
    metadata: dict[str, Any],
    alignment_result: dict[str, Any],
    routes: dict[str, dict[str, Any]],
    contexts: dict[str, list[dict[str, Any]]],
    reason: str,
) -> dict[str, Any]:
    try:
        metadata_reviews = validate_phase_result(
            "metadata", metadata, _metadata_packet(records)["records"]
        )["reviews"]
    except ResultValidationError as exc:
        raise _blocked(exc, "RESULT_VALIDATION_FAILED") from exc
    metadata_by_id = {item["record_id"]: item for item in metadata_reviews}
    try:
        alignment_reviews = validate_phase_result("alignment", alignment_result, records)["reviews"]
    except ResultValidationError as exc:
        raise _blocked(exc, "RESULT_VALIDATION_FAILED") from exc
    by_id = {item["record_id"]: item for item in alignment_reviews}
    deep_records = []
    for record in records:
        record_id = record["record_id"]
        route = routes.get(record_id)
        if not isinstance(route, dict) or record_id not in by_id:
            raise DiagnosticBlocked("STATE_INVALID")
        context = copy.deepcopy(contexts.get(record_id, []))
        item = {key: copy.deepcopy(record[key]) for key in ALIGNMENT_RECORD_KEYS}
        item["metadata_review"] = copy.deepcopy(metadata_by_id[record_id])
        item.update(
            alignment_review=copy.deepcopy(by_id[record_id]),
            routing_reasons=[reason],
            risk_tags=copy.deepcopy(route.get("risk_tags", [])),
            audit_selected=bool(route.get("audit_selected", False)),
            context=context,
            included_scope=[entry["ref"] for entry in context],
            excluded_scope=["packet外のrepository source"],
        )
        deep_records.append(item)
    packet = {
        "review_contract_version": "deep-review-v3",
        "metadata_result_hash": result_hash(metadata),
        "records": deep_records,
    }
    packet["input_hash"] = result_hash(packet)
    alignment_packet = _alignment_packet(records, metadata)
    synthetic_routes = [
        {
            "result": {
                "required": True,
                "reasons": [reason],
                "risk_tags": routes.get(item["record_id"], {}).get("risk_tags", []),
                "audit_selected": bool(routes.get(item["record_id"], {}).get("audit_selected", False)),
            }
        }
        for item in records
    ]
    try:
        validate_deep_packet(packet, alignment_packet, alignment_reviews, synthetic_routes)
    except (ResultValidationError, KeyError, TypeError) as exc:
        raise _blocked(exc, "RESULT_VALIDATION_FAILED") from exc
    return packet


def _proof_summary(proof: dict[str, Any]) -> dict[str, Any]:
    plan = proof.get("plan") if isinstance(proof, dict) else None
    batches = proof.get("batches") if isinstance(proof, dict) else []
    return {
        "schema_version": proof.get("schema_version") if isinstance(proof, dict) else None,
        "phase": proof.get("phase") if isinstance(proof, dict) else None,
        "plan_hash": plan.get("plan_hash") if isinstance(plan, dict) else None,
        "merged_result_hash": proof.get("merged_result_hash") if isinstance(proof, dict) else None,
        "batches": [
            {
                key: batch[key]
                for key in ("index", "record_ids", "packet_input_hash", "result_hash", "worker_evidence_hash")
                if isinstance(batch, dict) and key in batch
            }
            for batch in batches
            if isinstance(batch, dict)
        ],
        "proof_hash": _canonical_hash(proof),
    }


def _artifact(state: dict[str, Any], generation: dict[str, Any], mode: str, ids: list[str]) -> dict[str, Any]:
    return {
        "schema_version": DIAGNOSTIC_VERSION,
        "mode": mode,
        "generation_id": generation["generation_id"],
        "task_id": state["task_id"],
        "target_snapshot_hash": generation["target_snapshot_hash"],
        "selection_hash": generation["selection_hash"],
        "toolchain_hash": generation["toolchain_hash"],
        "original_generation_gate": generation["aggregation"]["result"].get("gate"),
        "status": "VALIDATION_GAP",
        "reason_codes": [],
        "selected_record_ids": ids,
        "phase_call_counts": {"metadata": 0, "alignment": 0, "deep": 0},
        "results": {},
        "proofs": {},
        "hashes": {},
    }


def _record_phase(artifact: dict[str, Any], phase: str, packet: dict[str, Any], result: dict[str, Any], proof: dict[str, Any]) -> None:
    artifact["phase_call_counts"][phase] = len(proof.get("batches", []))
    artifact["results"][phase] = copy.deepcopy(result)
    artifact["proofs"][phase] = _proof_summary(proof)
    artifact["hashes"][f"{phase}_packet_hash"] = result_hash(packet)
    artifact["hashes"][f"{phase}_result_hash"] = result_hash(result)


def _semantic_diagnostic_status(
    artifact: dict[str, Any],
    mode: str,
    deep_result: dict[str, Any],
    expected_status: dict[str, str] | None = None,
) -> None:
    """Classify semantic disagreement without changing the published gate."""

    reviews = deep_result.get("reviews") if isinstance(deep_result, dict) else []
    if not isinstance(reviews, list):
        artifact["status"] = "VALIDATION_GAP"
        artifact["reason_codes"] = ["DIAGNOSTIC_RESULT_INVALID"]
        return
    unresolved = sorted(
        item["record_id"]
        for item in reviews
        if isinstance(item, dict)
        and item.get("verdict") == "NEEDS_CONTEXT"
        and isinstance(item.get("record_id"), str)
    )
    expected_status = expected_status or {}
    disagreement = sorted(
        item["record_id"]
        for item in reviews
        if isinstance(item, dict)
        and isinstance(item.get("record_id"), str)
        and (
            (item.get("verdict") == "REDESIGN"
             and (mode == "audit" or expected_status.get(item["record_id"]) != "REDESIGN"))
            or (item.get("verdict") == "APPROVE"
                and expected_status.get(item["record_id"]) == "REDESIGN")
        )
    )
    if unresolved:
        artifact["unresolved_record_ids"] = unresolved
    if disagreement:
        artifact["diagnostic_disagreement_record_ids"] = disagreement
    reasons: list[str] = []
    if mode == "audit" and disagreement:
        reasons.append("AUDIT_DISAGREEMENT")
    if mode == "audit" and unresolved:
        reasons.append("AUDIT_NEEDS_CONTEXT")
    if mode == "all-phases" and disagreement:
        reasons.append("DIAGNOSTIC_DISAGREEMENT")
    if mode == "all-phases" and unresolved:
        reasons.append("DIAGNOSTIC_NEEDS_CONTEXT")
    if reasons:
        artifact["status"] = "VALIDATION_GAP"
        artifact["reason_codes"] = reasons


def _write_artifact(output_dir: Path, artifact: dict[str, Any]) -> None:
    try:
        output_dir.mkdir(parents=True, exist_ok=False)
    except FileExistsError as exc:
        raise DiagnosticBlocked("OUTPUT_DIRECTORY_EXISTS") from exc
    except OSError as exc:
        raise DiagnosticBlocked("DIAGNOSTIC_WRITE_FAILED") from exc
    path = output_dir / ARTIFACT_FILENAME
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=output_dir, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(canonical_json(artifact) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        temporary = None
    except OSError as exc:
        raise DiagnosticBlocked("DIAGNOSTIC_WRITE_FAILED") from exc
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _run_batch(phase: str, packet: dict[str, Any], *, cli: str, identity: dict[str, Any], policy: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    scripts_root = Path(__file__).resolve().parents[3]
    role = scripts_root / "agents" / ("test_value_deep.toml" if phase == "deep" else "test_value_luna.toml")
    try:
        return _execute_batch_round(
            phase,
            packet,
            cli=cli,
            role_file=role,
            toolchain_identity=identity,
            state_dir=None,
            batch_seconds=policy["batch_seconds"],
            batch_concurrency=policy.get("batch_concurrency"),
        )
    except (
        CoordinatorBlocked,
        PacketError,
        ResultValidationError,
        RoutingError,
        TimeoutError,
        OSError,
        RuntimeError,
        KeyError,
        TypeError,
    ) as exc:
        raise _blocked(exc, "DIAGNOSTIC_EXECUTION_FAILED") from exc


def run(args: argparse.Namespace) -> dict[str, Any]:
    mode = getattr(args, "mode", None)
    if mode not in DIAGNOSTIC_MODES:
        raise DiagnosticBlocked("CLI_INPUT_INVALID")
    state_arg, output_arg, cli = getattr(args, "state_dir", None), getattr(args, "output_dir", None), getattr(args, "cli", None)
    if not isinstance(state_arg, (str, Path)) or not isinstance(output_arg, (str, Path)) or not isinstance(cli, str) or not cli:
        raise DiagnosticBlocked("CLI_INPUT_INVALID")
    try:
        state_dir = Path(state_arg).resolve(strict=True)
    except OSError as exc:
        raise DiagnosticBlocked("STATE_DIRECTORY_MISSING") from exc
    if not state_dir.is_dir():
        raise DiagnosticBlocked("STATE_DIRECTORY_MISSING")
    state, generation = _load_published(state_dir, getattr(args, "generation_id", None))
    root, identity = _preflight(
        state,
        generation,
        state_dir=state_dir,
        cli=cli,
        root_override=getattr(args, "root", None),
    )
    output_dir = _output_dir(Path(output_arg), root=root, state_dir=state_dir)

    aggregation = generation["aggregation"]
    source = aggregation["input"]
    alignment_packet = copy.deepcopy(source["alignment_packet"])
    reviewed_records = _alignment_records(alignment_packet)
    records = reviewed_records
    alignment_result = copy.deepcopy(source["alignment_result"])
    metadata_result = copy.deepcopy(source["metadata_result"])
    routes, alignments, finals = _route_maps(aggregation, reviewed_records, alignment_result)
    contexts = _contexts(source["deep_packet"])
    selected = []
    for record in reviewed_records:
        route, alignment = routes[record["record_id"]], alignments[record["record_id"]]
        if mode == "all-phases":
            selected.append(record)
        elif (
            route.get("audit_selected") is True
            and route.get("required") is False
            and not route.get("risk_tags")
            and not _is_terminal(record, alignment, route, finals[record["record_id"]])
        ):
            selected.append(record)
    selected_ids = [item["record_id"] for item in selected]
    artifact = _artifact(state, generation, mode, selected_ids)
    artifact["hashes"].update(
        {
            "generation_aggregation_input_hash": generation["aggregation"]["input_hash"],
            "generation_aggregation_result_hash": generation["aggregation"]["result_hash"],
            "generation_host_evidence_hash": generation["host_evidence_hash"],
            "generation_worker_evidence_hash": generation["worker_evidence_hash"],
            "canonical_metadata_result_hash": result_hash(source["metadata_result"]),
            "canonical_alignment_packet_hash": result_hash(source["alignment_packet"]),
            "canonical_alignment_result_hash": result_hash(source["alignment_result"]),
            "canonical_deep_packet_hash": result_hash(source["deep_packet"]),
        }
    )
    if not selected:
        artifact["status"] = "COMPLETED"
        _write_artifact(output_dir, artifact)
        return artifact

    policy = state["execution_policy"]
    try:
        if mode == "all-phases":
            metadata_packet = _metadata_packet(records)
            metadata_result, metadata_proof = _run_batch("metadata", metadata_packet, cli=cli, identity=identity, policy=policy)
            _record_phase(artifact, "metadata", metadata_packet, metadata_result, metadata_proof)
            diagnostic_alignment = _alignment_packet(records, metadata_result)
            alignment_result, alignment_proof = _run_batch("alignment", diagnostic_alignment, cli=cli, identity=identity, policy=policy)
            _record_phase(artifact, "alignment", diagnostic_alignment, alignment_result, alignment_proof)
            deep_records, deep_metadata, deep_alignment = records, metadata_result, alignment_result
        else:
            deep_metadata = _metadata_subset(metadata_result, selected)
            diagnostic_alignment = _alignment_packet(selected, deep_metadata)
            deep_records = selected
            deep_alignment = {
                "review_contract_version": alignment_result["review_contract_version"],
                "reviews": [copy.deepcopy(alignments[item["record_id"]]) for item in selected],
            }
            validate_phase_result("alignment", deep_alignment, selected)
        deep = _deep_packet(
            deep_records,
            deep_metadata,
            deep_alignment,
            routes,
            contexts,
            "diagnostic-all-phases" if mode == "all-phases" else "diagnostic-audit",
        )
        deep_result, deep_proof = _run_batch("deep", deep, cli=cli, identity=identity, policy=policy)
        _record_phase(artifact, "deep", deep, deep_result, deep_proof)
    except (
        DiagnosticBlocked,
        CoordinatorBlocked,
        PacketError,
        ResultValidationError,
        RoutingError,
        TimeoutError,
        OSError,
        RuntimeError,
        KeyError,
        TypeError,
    ) as exc:
        blocked = exc if isinstance(exc, DiagnosticBlocked) else _blocked(exc, "DIAGNOSTIC_EXECUTION_FAILED")
        artifact["reason_codes"] = [_safe_reason(blocked.reason_code, "DIAGNOSTIC_EXECUTION_FAILED")]
        if blocked.details:
            artifact["failure"] = _sanitize_details(blocked.details)
        _write_artifact(output_dir, artifact)
        return artifact
    artifact["status"] = "COMPLETED"
    _semantic_diagnostic_status(
        artifact,
        mode,
        deep_result,
        {record_id: item.get("status") for record_id, item in finals.items()
         if isinstance(item, dict) and isinstance(item.get("status"), str)},
    )
    _write_artifact(output_dir, artifact)
    return artifact


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run an explicit non-blocking review diagnostic.")
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--generation-id")
    parser.add_argument("--cli", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--mode", choices=DIAGNOSTIC_MODES, required=True)
    parser.add_argument("--root", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = run(args)
    except DiagnosticBlocked as exc:
        reason = _safe_reason(exc.reason_code)
        result = {
            "schema_version": DIAGNOSTIC_VERSION,
            "status": "VALIDATION_GAP",
            "reason_codes": [reason],
        }
        details = _sanitize_details(exc.details)
        if details:
            result["failure"] = details
        print(canonical_json(result))
        return 2
    print(canonical_json(result))
    return 0 if result["status"] == "COMPLETED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
