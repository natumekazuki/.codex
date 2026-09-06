#!/usr/bin/env python3
"""Run the complete Git-selected test-value review as one bounded workflow."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
from typing import Any, Sequence

from build_review_packets import (
    PacketError,
    build_alignment_packet_multi,
    build_deep_packet,
    build_metadata_packet_multi,
    deleted_record_id_for,
    extractor_record_identities_multi,
    extractor_record_summaries_multi,
    project_deep_batch,
)
from extract_test_values import (
    ADAPTER_PROFILES,
    AdapterError,
    diagnostic,
    extract_source_text,
    public_diagnostic,
)
from git_diff_selection import select_git
from review_resolution import (
    MANIFEST_VERSION,
    ResolutionStateError,
    build_retention_evidence,
    canonical_json,
    content_hash,
    derive_retention_basis,
    evaluate_obligation_gate,
    append_resolution_attempt,
    initialize_resolution_state,
    load_resolution_state,
    retention_record_projection,
    validate_resolution_entry,
)
from review_routing import (
    RoutingError,
    aggregate_gate,
    build_routing_manifest,
    decide_disposition,
)
from validate_review_result import (
    ResultValidationError,
    aggregate_results,
    result_hash,
    validate_phase_result,
)


TASK_STATE_VERSION = "test-value-review-task-v1"
GENERATION_VERSION = "test-value-review-generation-v1"
HOST_EVIDENCE_VERSION = "test-value-host-evidence-v1"
RESULT_VERSION = "test-value-review-run-v1"
AUDIT_PERCENT = 10
DEEP_PROMPT_CHAR_BUDGET = 800_000
LANGUAGES = ("python", "typescript", "csharp")
RISK_TAGS = {
    "security",
    "authentication",
    "authorization",
    "billing",
    "irreversible-data-loss",
    "privacy",
}
EVIDENCE_KINDS = {
    "accepted-contract",
    "security-safety",
    "approved-compatibility",
    "incident-regression",
    "reference-model",
}
HOST_OBSERVED_AUTHORITIES = {
    "explicit-user-requirement",
    "external-contract",
    "issue",
}
TOOLCHAIN_SOURCE_PATHS = (
    "skills/review-test-value/scripts/run_test_value_review.py",
    "skills/review-test-value/scripts/review_worker.py",
    "skills/review-test-value/scripts/preflight_review_worker.py",
    "skills/review-test-value/scripts/extract_test_values.py",
    "skills/review-test-value/scripts/git_diff_selection.py",
    "skills/review-test-value/scripts/build_review_packets.py",
    "skills/review-test-value/scripts/validate_review_result.py",
    "skills/review-test-value/scripts/review_routing.py",
    "skills/review-test-value/scripts/review_resolution.py",
    "skills/review-test-value/scripts/adapters/typescript/extract.mjs",
    "skills/review-test-value/scripts/adapters/typescript/package.json",
    "skills/review-test-value/scripts/adapters/typescript/package-lock.json",
    "skills/review-test-value/scripts/adapters/csharp/Program.cs",
    "skills/review-test-value/scripts/adapters/csharp/DiagnosticProjection.cs",
    "skills/review-test-value/scripts/adapters/csharp/TestValue.CSharpExtractor.csproj",
    "skills/review-test-value/scripts/adapters/csharp/packages.lock.json",
)


class CoordinatorBlocked(RuntimeError):
    """A trusted aggregate could not be completed."""

    def __init__(
        self,
        reason_code: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.reason_code = reason_code
        self.details = details


def _git(root: Path, *args: str, binary: bool = False) -> str | bytes:
    try:
        process = subprocess.run(
            ["git", "--no-pager", *args],
            cwd=root,
            check=False,
            capture_output=True,
            text=not binary,
            encoding=None if binary else "utf-8",
        )
    except OSError as exc:
        raise CoordinatorBlocked("GIT_UNAVAILABLE", str(exc)) from exc
    if process.returncode:
        detail = process.stderr or process.stdout
        if isinstance(detail, bytes):
            detail = detail.decode("utf-8", "replace")
        raise CoordinatorBlocked("GIT_FAILED", str(detail).strip())
    return process.stdout


def _hash_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _canonical_hash(value: Any) -> str:
    return content_hash(canonical_json(value))


def _file_identity(path: Path, label: str) -> dict[str, str]:
    try:
        resolved = path.resolve(strict=True)
        if not resolved.is_file():
            raise OSError(f"{label} is not a file")
        digest = _hash_bytes(resolved.read_bytes())
    except OSError as exc:
        raise CoordinatorBlocked("TOOLCHAIN_UNAVAILABLE", f"{label}: {exc}") from exc
    return {"path": str(path), "realpath": str(resolved), "sha256": digest}


def _toolchain_identity(cli: str, repository_root: Path) -> dict[str, Any]:
    try:
        from review_worker import ReviewWorkerBlocked, current_worker_identity
    except ImportError as exc:
        raise CoordinatorBlocked("WORKER_UNAVAILABLE", str(exc)) from exc
    try:
        workers = {
            "luna": current_worker_identity(
                cli=cli,
                role_file=str(repository_root / "agents" / "test_value_luna.toml"),
                phases=("metadata", "alignment"),
            ),
            "sol": current_worker_identity(
                cli=cli,
                role_file=str(repository_root / "agents" / "test_value_sol.toml"),
                phases=("deep",),
            ),
        }
    except ReviewWorkerBlocked as exc:
        raise CoordinatorBlocked(str(exc.code), str(exc)) from exc
    return {
        "workers": workers,
        "sources": [
            _file_identity(repository_root / relative, relative)
            for relative in TOOLCHAIN_SOURCE_PATHS
        ],
    }


def _resolve_repository(root: Path) -> Path:
    try:
        resolved = root.resolve(strict=True)
    except OSError as exc:
        raise CoordinatorBlocked("ROOT_INVALID", str(exc)) from exc
    top = Path(str(_git(resolved, "rev-parse", "--show-toplevel")).strip()).resolve()
    if top != resolved:
        raise CoordinatorBlocked("ROOT_INVALID", "--root must be the Git repository root")
    return resolved


def _resolve_commit(root: Path, revision: str) -> str:
    return str(_git(root, "rev-parse", "--verify", f"{revision}^{{commit}}")).strip()


def snapshot_descriptor(
    root: Path, base_oid: str, *, mode: str, head_oid: str | None
) -> dict[str, Any]:
    diff_args = [
        "diff",
        "--binary",
        "--full-index",
        "--no-ext-diff",
        "--no-color",
        base_oid,
    ]
    if mode == "staged":
        diff_args.append("--cached")
    elif mode == "head":
        if head_oid is None:
            raise CoordinatorBlocked("HEAD_REQUIRED", "--head is required for head mode")
        diff_args.append(head_oid)
    tracked = bytes(_git(root, *diff_args, binary=True))
    untracked: list[dict[str, str]] = []
    if mode == "working":
        payload = bytes(
            _git(root, "ls-files", "--others", "--exclude-standard", "-z", binary=True)
        )
        for raw in sorted(filter(None, payload.split(b"\0"))):
            relative = raw.decode("utf-8", "surrogateescape").replace("\\", "/")
            try:
                path = (root / relative).resolve(strict=True)
            except OSError as exc:
                raise CoordinatorBlocked("SNAPSHOT_UNAVAILABLE", relative) from exc
            if not path.is_relative_to(root) or not path.is_file():
                raise CoordinatorBlocked(
                    "SNAPSHOT_OUTSIDE_ROOT", f"untracked path is not a local file: {relative}"
                )
            untracked.append({"path": relative, "content_hash": _hash_bytes(path.read_bytes())})
    descriptor = {
        "base_commit_oid": base_oid,
        "target_mode": mode,
        "head_commit_oid": head_oid,
        "tracked_diff_hash": _hash_bytes(tracked),
        "untracked": untracked,
    }
    return {**descriptor, "target_snapshot_hash": _canonical_hash(descriptor)}


def extract_all_languages(
    root: Path, base_oid: str, *, mode: str, head_oid: str | None
) -> list[dict[str, Any]]:
    results = []
    for language in LANGUAGES:
        profile = next(item for item in ADAPTER_PROFILES if item.language == language)
        try:
            result = select_git(
                root,
                base_oid,
                profile,
                extract_source_text,
                diagnostic,
                public_diagnostic,
                mode,
                head_oid,
            )
        except (AdapterError, OSError, ValueError) as exc:
            raise CoordinatorBlocked("EXTRACTION_FAILED", f"{language}: {exc}") from exc
        if result.get("diagnostics"):
            raise CoordinatorBlocked(
                "EXTRACTION_DIAGNOSTICS",
                f"{language}: {canonical_json(result['diagnostics'])}",
            )
        results.append(result)
    return results


def _read_json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CoordinatorBlocked(f"{label}_INVALID", str(exc)) from exc
    if not isinstance(value, dict):
        raise CoordinatorBlocked(f"{label}_INVALID", f"{label} must be a JSON object")
    return value


def _check_keys(value: Any, keys: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        raise CoordinatorBlocked("HOST_EVIDENCE_INVALID", f"{label} has unexpected keys")
    return value


def _nonempty(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise CoordinatorBlocked("HOST_EVIDENCE_INVALID", f"{label} must be non-empty")
    return value


def _hash(value: Any, label: str) -> str:
    text = _nonempty(value, label)
    if len(text) != 71 or not text.startswith("sha256:"):
        raise CoordinatorBlocked("HOST_EVIDENCE_INVALID", f"{label} must be a sha256 hash")
    try:
        int(text[7:], 16)
    except ValueError as exc:
        raise CoordinatorBlocked("HOST_EVIDENCE_INVALID", f"{label} is invalid") from exc
    return text


def _validate_local_content(
    root: Path,
    item: dict[str, Any],
    *,
    meaning: bool,
    mode: str,
    head_oid: str | None,
    require_kind: bool = True,
    require_provenance: bool = True,
) -> dict[str, Any]:
    keys = {"ref", "content", "content_hash"}
    if require_kind:
        keys.add("kind")
    if meaning:
        keys.add("meaning")
    if require_provenance:
        keys.update({"source", "authority"})
    _check_keys(item, keys, "bounded evidence")
    ref = _nonempty(item["ref"], "evidence.ref")
    supplied = _nonempty(item["content"], "evidence.content")
    supplied_hash = _hash(item["content_hash"], "evidence.content_hash")
    actual = supplied
    if require_provenance:
        source = item["source"]
        authority = item["authority"]
        if source == "repository":
            if authority != "repository":
                raise CoordinatorBlocked("HOST_EVIDENCE_INVALID", "repository evidence authority is invalid")
            ref_path = Path(ref)
            if ref_path.is_absolute():
                raise CoordinatorBlocked("EVIDENCE_OUTSIDE_ROOT", ref)
            try:
                if mode == "working":
                    resolved = (root / ref_path).resolve(strict=True)
                    if not resolved.is_relative_to(root) or not resolved.is_file():
                        raise CoordinatorBlocked("EVIDENCE_OUTSIDE_ROOT", ref)
                    actual = resolved.read_text(encoding="utf-8")
                else:
                    normalized = ref.replace("\\", "/")
                    spec = f":{normalized}" if mode == "staged" else f"{head_oid}:{normalized}"
                    actual = bytes(_git(root, "show", spec, binary=True)).decode("utf-8")
            except (OSError, UnicodeDecodeError, CoordinatorBlocked) as exc:
                raise CoordinatorBlocked("EVIDENCE_UNAVAILABLE", ref) from exc
        elif source == "host-observed":
            if authority not in HOST_OBSERVED_AUTHORITIES:
                raise CoordinatorBlocked("HOST_EVIDENCE_INVALID", "host-observed authority is invalid")
        else:
            raise CoordinatorBlocked("HOST_EVIDENCE_INVALID", "evidence source is invalid")
    if supplied != actual or supplied_hash != content_hash(actual):
        raise CoordinatorBlocked("EVIDENCE_HASH_MISMATCH", ref)
    result = {
        "ref": ref.replace("\\", "/"),
        "content": actual,
        "content_hash": supplied_hash,
    }
    if require_kind:
        result["kind"] = _nonempty(item["kind"], "evidence.kind")
    if meaning:
        if require_kind and result["kind"] not in EVIDENCE_KINDS:
            raise CoordinatorBlocked("HOST_EVIDENCE_INVALID", "evidence kind is invalid")
        result["meaning"] = _nonempty(item["meaning"], "evidence.meaning")
    return result


def validate_host_evidence(
    root: Path,
    value: dict[str, Any],
    *,
    snapshot_hash: str,
    selection_hash: str,
    records: list[dict[str, Any]],
    mode: str,
    head_oid: str | None,
) -> dict[str, Any]:
    _check_keys(
        value,
        {
            "schema_version",
            "task_id",
            "target_snapshot_hash",
            "selection_hash",
            "parent_risk_assessment",
            "context_by_record",
            "retry_context_by_record",
            "retention_by_record",
            "resolution_attempts",
            "supersessions",
        },
        "host evidence",
    )
    if value["schema_version"] != HOST_EVIDENCE_VERSION:
        raise CoordinatorBlocked("HOST_EVIDENCE_INVALID", "host evidence version is invalid")
    task_id = _nonempty(value["task_id"], "task_id")
    if value["target_snapshot_hash"] != snapshot_hash or value["selection_hash"] != selection_hash:
        raise CoordinatorBlocked("HOST_EVIDENCE_STALE", "host evidence does not match selection")
    risk = _check_keys(
        value["parent_risk_assessment"],
        {"status", "risk_tags", "rationale", "evidence", "evidence_refs"},
        "parent risk assessment",
    )
    if risk["status"] not in {"ASSESSED", "UNRESOLVED"}:
        raise CoordinatorBlocked("HOST_EVIDENCE_INVALID", "parent risk status is invalid")
    if not isinstance(risk["risk_tags"], list) or any(
        item not in RISK_TAGS for item in risk["risk_tags"]
    ) or len(risk["risk_tags"]) != len(set(risk["risk_tags"])):
        raise CoordinatorBlocked("HOST_EVIDENCE_INVALID", "parent risk tags are invalid")
    risk_evidence = [
        _validate_local_content(root, item, meaning=True, mode=mode, head_oid=head_oid)
        for item in risk["evidence"]
    ] if isinstance(risk["evidence"], list) else []
    if not isinstance(risk["evidence"], list):
        raise CoordinatorBlocked("HOST_EVIDENCE_INVALID", "risk evidence must be an array")
    available = {(item["ref"], item["content_hash"]) for item in risk_evidence}
    refs = risk["evidence_refs"]
    if not isinstance(refs, list) or any(
        not isinstance(item, dict) or set(item) != {"ref", "content_hash"}
        for item in refs
    ):
        raise CoordinatorBlocked("HOST_EVIDENCE_INVALID", "risk evidence_refs are invalid")
    used = [(_nonempty(item["ref"], "risk ref"), _hash(item["content_hash"], "risk hash")) for item in refs]
    if len(used) != len(set(used)) or any(item not in available for item in used):
        raise CoordinatorBlocked("HOST_EVIDENCE_INVALID", "risk evidence_refs do not match evidence")
    if risk["status"] == "UNRESOLVED":
        raise CoordinatorBlocked("PARENT_RISK_UNRESOLVED", "parent risk assessment is unresolved")
    if not _nonempty(risk["rationale"], "risk rationale") or not risk_evidence or not used:
        raise CoordinatorBlocked("HOST_EVIDENCE_INVALID", "assessed parent risk requires evidence")

    by_id = {record["record_id"]: record for record in records}

    def contexts(name: str) -> dict[str, list[dict[str, Any]]]:
        raw = value[name]
        if not isinstance(raw, list):
            raise CoordinatorBlocked("HOST_EVIDENCE_INVALID", f"{name} must be an array")
        result: dict[str, list[dict[str, Any]]] = {}
        for entry in raw:
            _check_keys(entry, {"record_id", "metadata_hash", "source_hash", "items"}, name)
            record_id = _nonempty(entry["record_id"], "context record_id")
            record = by_id.get(record_id)
            if record is None or entry["metadata_hash"] != record["metadata_hash"] or entry["source_hash"] != record["source_hash"]:
                raise CoordinatorBlocked("HOST_EVIDENCE_IDENTITY_MISMATCH", record_id)
            if record_id in result or not isinstance(entry["items"], list) or not entry["items"]:
                raise CoordinatorBlocked("HOST_EVIDENCE_INVALID", f"invalid context entry: {record_id}")
            result[record_id] = [
                _validate_local_content(root, item, meaning=False, mode=mode, head_oid=head_oid)
                for item in entry["items"]
            ]
            identities = [(item["ref"], item["content_hash"]) for item in result[record_id]]
            if len(identities) != len(set(identities)):
                raise CoordinatorBlocked("HOST_EVIDENCE_INVALID", "context items must be unique")
        return result

    context_by_record = contexts("context_by_record")
    retry_context_by_record = contexts("retry_context_by_record")
    if set(context_by_record) & set(retry_context_by_record):
        for record_id in set(context_by_record) & set(retry_context_by_record):
            refs_seen = {item["ref"] for item in context_by_record[record_id]}
            if any(item["ref"] in refs_seen for item in retry_context_by_record[record_id]):
                raise CoordinatorBlocked("HOST_EVIDENCE_INVALID", "retry context duplicates initial context")

    raw_retention = value["retention_by_record"]
    if not isinstance(raw_retention, list):
        raise CoordinatorBlocked("HOST_EVIDENCE_INVALID", "retention_by_record must be an array")
    retention: dict[str, dict[str, Any]] = {}
    for entry in raw_retention:
        _check_keys(
            entry,
            {"record_id", "metadata_hash", "source_hash", "evidence", "determination", "temporal_observation"},
            "retention entry",
        )
        record_id = _nonempty(entry["record_id"], "retention record_id")
        record = by_id.get(record_id)
        if record is None or entry["metadata_hash"] != record["metadata_hash"] or entry["source_hash"] != record["source_hash"]:
            raise CoordinatorBlocked("HOST_EVIDENCE_IDENTITY_MISMATCH", record_id)
        if record_id in retention or not isinstance(entry["evidence"], list):
            raise CoordinatorBlocked("HOST_EVIDENCE_INVALID", "duplicate or invalid retention entry")
        bounded = [
            _validate_local_content(root, item, meaning=True, mode=mode, head_oid=head_oid)
            for item in entry["evidence"]
        ]
        determination = entry["determination"]
        temporal = entry["temporal_observation"]
        if temporal is not None:
            _check_keys(
                temporal,
                {
                    "determination",
                    "source",
                    "authority",
                    "ref",
                    "content",
                    "content_hash",
                    "meaning",
                },
                "temporal observation",
            )
            temporal_determination = temporal["determination"]
            temporal = _validate_local_content(
                root,
                {key: value for key, value in temporal.items() if key != "determination"},
                meaning=True,
                mode=mode,
                head_oid=head_oid,
                require_kind=False,
            )
            temporal["determination"] = temporal_determination
            if temporal["determination"] not in {"ACTIVE", "EXPIRED", "UNRESOLVED"}:
                raise CoordinatorBlocked("HOST_EVIDENCE_INVALID", "temporal determination is invalid")
        retention[record_id] = {
            "evidence": bounded,
            "determination": determination,
            "temporal_observation": temporal,
        }
    if list(retention) != [record["record_id"] for record in records]:
        raise CoordinatorBlocked("HOST_EVIDENCE_INVALID", "retention entries must match canonical record order")
    raw_supersessions = value["supersessions"]
    if not isinstance(raw_supersessions, list):
        raise CoordinatorBlocked("HOST_EVIDENCE_INVALID", "supersessions must be an array")
    supersessions = []
    seen_historical: set[tuple[str, str]] = set()
    for entry in raw_supersessions:
        _check_keys(
            entry,
            {
                "historical_generation_id",
                "historical_record_id",
                "historical_metadata_hash",
                "historical_source_hash",
                "current_record_id",
                "current_metadata_hash",
                "current_source_hash",
                "evidence",
                "determination",
            },
            "supersession",
        )
        historical_key = (
            _nonempty(entry["historical_generation_id"], "historical generation_id"),
            _nonempty(entry["historical_record_id"], "historical record_id"),
        )
        if historical_key in seen_historical:
            raise CoordinatorBlocked("HOST_EVIDENCE_INVALID", "duplicate supersession")
        seen_historical.add(historical_key)
        current_id = _nonempty(entry["current_record_id"], "current record_id")
        current = by_id.get(current_id)
        if (
            current is None
            or entry["current_metadata_hash"] != current["metadata_hash"]
            or entry["current_source_hash"] != current["source_hash"]
        ):
            raise CoordinatorBlocked("HOST_EVIDENCE_IDENTITY_MISMATCH", current_id)
        bounded = [
            _validate_local_content(root, item, meaning=True, mode=mode, head_oid=head_oid)
            for item in entry["evidence"]
        ] if isinstance(entry["evidence"], list) else []
        try:
            if derive_retention_basis(bounded, entry["determination"]) != "PRESENT":
                raise CoordinatorBlocked(
                    "HOST_EVIDENCE_INVALID",
                    "supersession must be supported by bounded evidence",
                )
        except ResolutionStateError as exc:
            raise CoordinatorBlocked(exc.reason_code, str(exc)) from exc
        supersessions.append(
            {
                **{key: entry[key] for key in entry if key not in {"evidence", "determination"}},
                "evidence": bounded,
                "determination": entry["determination"],
            }
        )
    return {
        "task_id": task_id,
        "risk_tags": sorted(risk["risk_tags"]),
        "context_by_record": context_by_record,
        "retry_context_by_record": retry_context_by_record,
        "retention_by_record": retention,
        "resolution_attempts": value["resolution_attempts"],
        "supersessions": supersessions,
    }


def _target_text(
    root: Path, relative: str, *, mode: str, head_oid: str | None
) -> str | None:
    path = Path(relative)
    if path.is_absolute():
        raise CoordinatorBlocked("RESOLUTION_SOURCE_INVALID", relative)
    if mode == "working":
        resolved = (root / path).resolve(strict=False)
        if not resolved.is_relative_to(root):
            raise CoordinatorBlocked("RESOLUTION_SOURCE_INVALID", relative)
        if not resolved.exists():
            return None
        if not resolved.is_file():
            raise CoordinatorBlocked("RESOLUTION_SOURCE_INVALID", relative)
        try:
            return resolved.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise CoordinatorBlocked("RESOLUTION_SOURCE_UNAVAILABLE", relative) from exc
    normalized = relative.replace("\\", "/")
    if mode == "staged":
        listing = str(_git(root, "ls-files", "--stage", "--", normalized))
        spec = f":{normalized}"
    else:
        listing = str(_git(root, "ls-tree", "-z", head_oid or "", "--", normalized))
        spec = f"{head_oid}:{normalized}"
    if not listing:
        return None
    try:
        return bytes(_git(root, "show", spec, binary=True)).decode("utf-8")
    except UnicodeDecodeError as exc:
        raise CoordinatorBlocked("RESOLUTION_SOURCE_UNAVAILABLE", relative) from exc


def _removal_observation(
    root: Path,
    manifest: dict[str, Any],
    obligation: dict[str, Any],
    *,
    snapshot_hash: str,
    mode: str,
    head_oid: str | None,
) -> dict[str, Any]:
    origin_record = obligation["origin"]["record"]
    packet_records = manifest["aggregation"]["input"]["alignment_packet"]["records"]
    origin_packet = next(
        item for item in packet_records if item["record_id"] == origin_record["record_id"]
    )
    current_text = _target_text(
        root,
        origin_record["locator"]["path"],
        mode=mode,
        head_oid=head_oid,
    )
    removed = current_text is None or origin_packet["source_text"] not in current_text
    observation = canonical_json(
        {
            "path": origin_record["locator"]["path"],
            "origin_source_hash": origin_record["source_hash"],
            "current_content_hash": None if current_text is None else content_hash(current_text),
            "target_snapshot_hash": snapshot_hash,
        }
    )
    return {
        "origin": origin_record,
        "determination": "REMOVED" if removed else "PRESENT",
        "current_snapshot_hash": snapshot_hash,
        "ref": f"git-target:{origin_record['locator']['path']}",
        "content": observation,
        "content_hash": content_hash(observation),
        "meaning": "Whether the exact frozen origin source remains in the current Git target",
    }


def _prepare_resolution_attempts(
    root: Path,
    state_dir: Path,
    state: dict[str, Any],
    attempts: Any,
    *,
    snapshot_hash: str,
    mode: str,
    head_oid: str | None,
) -> list[dict[str, Any]]:
    if not isinstance(attempts, list):
        raise CoordinatorBlocked("HOST_EVIDENCE_INVALID", "resolution_attempts must be an array")
    generations = {item["generation_id"]: item for item in state["generations"]}
    seen_attempts: set[str] = set()
    pending: list[dict[str, Any]] = []
    for supplied in attempts:
        _check_keys(
            supplied,
            {
                "attempt_id",
                "generation_id",
                "obligation_id",
                "action",
                "state",
                "target",
                "drop_reason",
                "checks",
                "reason",
            },
            "resolution attempt",
        )
        attempt_id = _nonempty(supplied["attempt_id"], "resolution attempt_id")
        if attempt_id in seen_attempts:
            raise CoordinatorBlocked("HOST_EVIDENCE_INVALID", "resolution attempt_id is duplicated")
        seen_attempts.add(attempt_id)
        generation_id = _nonempty(supplied["generation_id"], "generation_id")
        descriptor = generations.get(generation_id)
        if descriptor is None:
            raise CoordinatorBlocked("RESOLUTION_GENERATION_UNKNOWN", generation_id)
        generation = _load_generation(state_dir, descriptor)
        relative_state = generation["resolution_state"]
        if relative_state is None:
            raise CoordinatorBlocked("RESOLUTION_OBLIGATION_UNKNOWN", generation_id)
        resolution_dir = (state_dir / relative_state).resolve(strict=False)
        try:
            manifest, ledger = load_resolution_state(
                resolution_dir, expected_task_id=state["task_id"]
            )
        except ResolutionStateError as exc:
            raise CoordinatorBlocked(exc.reason_code, str(exc)) from exc
        obligations = {item["obligation_id"]: item for item in manifest["obligations"]}
        obligation_id = _nonempty(supplied["obligation_id"], "obligation_id")
        obligation = obligations.get(obligation_id)
        if obligation is None:
            raise CoordinatorBlocked("RESOLUTION_OBLIGATION_UNKNOWN", obligation_id)
        if supplied["action"] != obligation["action"]:
            raise CoordinatorBlocked("RESOLUTION_ACTION_MISMATCH", obligation_id)
        removal = _removal_observation(
            root,
            manifest,
            obligation,
            snapshot_hash=snapshot_hash,
            mode=mode,
            head_oid=head_oid,
        )
        target = supplied["target"]
        if target is not None:
            _check_keys(target, {"ref", "content", "content_hash", "meaning"}, "resolution target")
            validated = _validate_local_content(
                root,
                {
                    "kind": "resolution-target",
                    "ref": target["ref"],
                    "content": target["content"],
                    "content_hash": target["content_hash"],
                },
                meaning=False,
                mode=mode,
                head_oid=head_oid,
                require_provenance=False,
            )
            target = {
                "snapshot_hash": snapshot_hash,
                "ref": validated["ref"],
                "content": validated["content"],
                "content_hash": validated["content_hash"],
                "meaning": _nonempty(supplied["target"]["meaning"], "target meaning"),
            }
        checks = supplied["checks"]
        if not isinstance(checks, list):
            raise CoordinatorBlocked("HOST_EVIDENCE_INVALID", "resolution checks must be an array")
        normalized_checks = []
        for check in checks:
            _check_keys(
                check,
                {"check_id", "target_ref", "target_hash", "exit_code", "output_hash"},
                "resolution check",
            )
            normalized_checks.append({**check, "snapshot_hash": snapshot_hash})
        entry = {
            "attempt_id": attempt_id,
            "obligation_id": obligation_id,
            "origin_hash": content_hash(canonical_json(obligation["origin"])),
            "action": supplied["action"],
            "state": supplied["state"],
            "resolution": {
                "current_snapshot_hash": snapshot_hash,
                "removal": removal,
                "target": target,
                "drop_reason": supplied["drop_reason"],
                "checks": normalized_checks,
                "reason": supplied["reason"],
            },
        }
        existing = next(
            (item for item in ledger["entries"] if item["attempt_id"] == attempt_id),
            None,
        )
        if existing is not None:
            if existing != entry:
                raise CoordinatorBlocked("DUPLICATE_ATTEMPT", attempt_id)
            continue
        try:
            validate_resolution_entry(entry, manifest)
        except ResolutionStateError as exc:
            raise CoordinatorBlocked(exc.reason_code, str(exc)) from exc
        pending.append(
            {
                "generation_id": generation_id,
                "resolution_dir": resolution_dir,
                "entry": entry,
            }
        )
    return pending


def _commit_resolution_attempts(
    pending: list[dict[str, Any]], *, task_id: str
) -> None:
    for item in pending:
        try:
            append_resolution_attempt(
                item["resolution_dir"],
                expected_task_id=task_id,
                entry=item["entry"],
            )
        except ResolutionStateError as exc:
            raise CoordinatorBlocked(exc.reason_code, str(exc)) from exc


def _execute_phase(
    phase: str, packet: dict[str, Any], *, cli: str, role_file: Path
) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        from review_worker import ReviewWorkerBlocked, execute_phase
    except ImportError as exc:
        raise CoordinatorBlocked("WORKER_UNAVAILABLE", "review_worker.py is unavailable") from exc
    try:
        execution = execute_phase(
            phase,
            packet,
            cli=cli,
            role_file=str(role_file),
            timeout_seconds=900.0 if phase == "deep" else 300.0,
        )
    except ReviewWorkerBlocked as exc:
        code = getattr(exc, "code", "WORKER_BLOCKED")
        details = {"phase": phase}
        worker_evidence = getattr(exc, "evidence", None)
        if isinstance(worker_evidence, dict):
            if isinstance(worker_evidence.get("validator_error"), str):
                details["validator_error"] = worker_evidence["validator_error"]
            canary: dict[str, Any] = {}
            for key in (
                "turn_completed",
                "tool_event_count",
                "command_id_count",
                "command_count",
                "command_matches",
            ):
                value = worker_evidence.get(key)
                if isinstance(value, bool) or (
                    isinstance(value, int) and not isinstance(value, bool) and value >= 0
                ):
                    canary[key] = value
            for key, item_type in (
                ("command_statuses", str),
                ("command_exit_codes", int),
                ("denial_markers", bool),
            ):
                value = worker_evidence.get(key)
                if (
                    isinstance(value, list)
                    and len(value) <= 32
                    and all(
                        item is None
                        or (
                            isinstance(item, item_type)
                            and not (item_type is int and isinstance(item, bool))
                        )
                        for item in value
                    )
                ):
                    canary[key] = value
            if canary:
                details["canary_evidence"] = canary
        raise CoordinatorBlocked(str(code), str(exc), details) from exc
    evidence = execution.evidence
    if (
        not isinstance(evidence, dict)
        or evidence.get("schema_version") != "review-worker-evidence-v1"
        or evidence.get("phase") != phase
    ):
        raise CoordinatorBlocked("WORKER_EVIDENCE_INVALID", phase)
    return execution.result, evidence


def _validate_worker_toolchain(
    phase: str,
    evidence: dict[str, Any],
    expected: dict[str, Any],
) -> None:
    role_name = "sol" if phase == "deep" else "luna"
    identity = expected["workers"][role_name]
    for key in ("realpath", "sha256"):
        if evidence["cli"].get(key) != identity["cli"][key]:
            raise CoordinatorBlocked("TOOLCHAIN_CHANGED", f"{phase} CLI {key} changed")
        if evidence["role"].get(key) != identity["role"][key]:
            raise CoordinatorBlocked("TOOLCHAIN_CHANGED", f"{phase} role {key} changed")
    contract = next(item for item in identity["contracts"] if item["phase"] == phase)
    if evidence["contract"].get("sha256") != contract["sha256"]:
        raise CoordinatorBlocked("TOOLCHAIN_CHANGED", f"{phase} contract sha256 changed")
    if Path(evidence["contract"].get("path", "")).resolve() != Path(contract["realpath"]):
        raise CoordinatorBlocked("TOOLCHAIN_CHANGED", f"{phase} contract path changed")


def plan_deep_batches(
    global_packet: dict[str, Any],
    *,
    prompt_char_budget: int = DEEP_PROMPT_CHAR_BUDGET,
) -> list[dict[str, Any]]:
    """Plan every contiguous deep transport batch before launching Sol."""

    if not isinstance(prompt_char_budget, int) or isinstance(prompt_char_budget, bool) or prompt_char_budget <= 0:
        raise CoordinatorBlocked("DEEP_BATCH_UNAVAILABLE", "deep prompt budget is invalid")
    try:
        from review_worker import review_prompt
    except ImportError as exc:
        raise CoordinatorBlocked("WORKER_UNAVAILABLE", str(exc)) from exc
    records = global_packet.get("records")
    if not isinstance(records, list):
        raise CoordinatorBlocked("DEEP_BATCH_UNAVAILABLE", "global deep records are invalid")
    if not records:
        return []
    batches: list[dict[str, Any]] = []
    current: list[dict[str, Any]] = []
    for record in records:
        candidate_records = [*current, record]
        try:
            candidate = project_deep_batch(global_packet, candidate_records)
        except PacketError as exc:
            raise CoordinatorBlocked("DEEP_BATCH_UNAVAILABLE", str(exc)) from exc
        if len(review_prompt(candidate)) <= prompt_char_budget:
            current = candidate_records
            continue
        if not current:
            raise CoordinatorBlocked(
                "DEEP_BATCH_UNAVAILABLE",
                f"deep record exceeds the {prompt_char_budget} character prompt budget",
            )
        batches.append(project_deep_batch(global_packet, current))
        current = [record]
        singleton = project_deep_batch(global_packet, current)
        if len(review_prompt(singleton)) > prompt_char_budget:
            raise CoordinatorBlocked(
                "DEEP_BATCH_UNAVAILABLE",
                f"deep record exceeds the {prompt_char_budget} character prompt budget",
            )
    if current:
        batches.append(project_deep_batch(global_packet, current))
    return batches


def _execute_deep_round(
    global_packet: dict[str, Any],
    *,
    cli: str,
    role_file: Path,
    toolchain_identity: dict[str, Any],
    prompt_char_budget: int = DEEP_PROMPT_CHAR_BUDGET,
) -> tuple[dict[str, Any], dict[str, Any]]:
    batches = plan_deep_batches(
        global_packet,
        prompt_char_budget=prompt_char_budget,
    )
    if not batches:
        raise CoordinatorBlocked("DEEP_BATCH_UNAVAILABLE", "required deep packet is empty")
    proofs = []
    merged_reviews = []
    for index, packet in enumerate(batches):
        local_result, evidence = _execute_phase(
            "deep",
            packet,
            cli=cli,
            role_file=role_file,
        )
        _validate_worker_toolchain("deep", evidence, toolchain_identity)
        validated = validate_phase_result(
            "deep",
            local_result,
            packet["records"],
            packet["input_hash"],
        )
        merged_reviews.extend(validated["reviews"])
        proofs.append(
            {
                "index": index,
                "record_ids": [item["record_id"] for item in packet["records"]],
                "packet_input_hash": packet["input_hash"],
                "result": validated,
                "result_hash": result_hash(validated),
                "worker_evidence": evidence,
                "worker_evidence_hash": _canonical_hash(evidence),
            }
        )
    merged = {
        "review_contract_version": "deep-review-v2",
        "input_hash": global_packet["input_hash"],
        "reviews": merged_reviews,
    }
    merged = validate_phase_result(
        "deep",
        merged,
        global_packet["records"],
        global_packet["input_hash"],
    )
    if len(proofs) == 1:
        return merged, proofs[0]["worker_evidence"]
    return merged, {
        "schema_version": "deep-batch-execution-v1",
        "phase": "deep",
        "global_input_hash": global_packet["input_hash"],
        "batches": proofs,
        "merged_result_hash": result_hash(merged),
    }


def _routing_inputs(
    alignment_packet: dict[str, Any], alignment_result: dict[str, Any]
) -> list[dict[str, Any]]:
    reviews = validate_phase_result(
        "alignment", alignment_result, alignment_packet["records"]
    )["reviews"]
    return [
        {
            "record_id": record["record_id"],
            "metadata_hash": record["metadata_hash"],
            "source_hash": record["source_hash"],
            "contract_version": "deep-review-v2",
            "metadata": record["metadata"],
            "metadata_verdict": record["metadata_review"]["verdict"],
            "alignment_verdict": review["verdict"],
            "context_requirements": review["context_requirements"],
        }
        for record, review in zip(alignment_packet["records"], reviews)
    ]


def _actual_boundary(
    record_id: str,
    alignment_review: dict[str, Any],
    sol_by_id: dict[str, dict[str, Any]],
) -> str | None:
    boundary = alignment_review["actual_boundary"]
    sol = sol_by_id.get(record_id)
    if alignment_review["verdict"] == "RECHECK" and sol is not None:
        resolution = sol["context_resolution"]
        if resolution is not None:
            boundary = resolution["actual_boundary"]
    return boundary


def _retention_inputs(
    records: list[dict[str, Any]],
    alignment_result: dict[str, Any],
    sol_result: dict[str, Any] | None,
    host: dict[str, Any],
    snapshot_hash: str,
) -> tuple[list[dict[str, str]], dict[str, dict[str, Any]]]:
    alignment_reviews = validate_phase_result("alignment", alignment_result, records)["reviews"]
    sol_by_id = {} if sol_result is None else {
        item["record_id"]: item for item in sol_result["reviews"]
    }
    projections = []
    detailed: dict[str, dict[str, Any]] = {}
    for record, alignment_review in zip(records, alignment_reviews):
        record_id = record["record_id"]
        entry = host["retention_by_record"][record_id]
        try:
            basis = derive_retention_basis(entry["evidence"], entry["determination"])
        except ResolutionStateError as exc:
            raise CoordinatorBlocked(exc.reason_code, str(exc)) from exc
        boundary = _actual_boundary(record_id, alignment_review, sol_by_id)
        disposition = decide_disposition(
            actual_boundary=boundary,
            lifecycle=record["metadata"]["lifecycle"],
            retention_basis=basis,
            expires_on=record["metadata"].get("expires_on"),
            review_when=record["metadata"].get("review_when"),
            remove_when=record["metadata"].get("remove_when"),
        )
        if disposition is None:
            projections.append(
                {"record_id": record_id, "retention_basis": basis, "artifact_state": "TEST_PRESENT"}
            )
            continue
        source = record["source"]
        identity = {
            "record_id": record_id,
            "metadata_hash": record["metadata_hash"],
            "source_hash": record["source_hash"],
            "snapshot_hash": snapshot_hash,
            "locator": {
                "path": source["path"],
                "symbol": source["symbol"],
                "declaration_start_line": source["declaration_start_line"],
            },
        }
        source_observation = {
            "determination": (
                "ABSENT" if deleted_record_id_for(record) == record_id else "PRESENT"
            ),
            "record_id": record_id,
            "metadata_hash": record["metadata_hash"],
            "source_hash": record["source_hash"],
            "snapshot_hash": snapshot_hash,
            "ref": f"git-selection:{source['path']}",
            "content": (
                canonical_json(
                    {
                        "transition": "DELETED",
                        "record_id": record_id,
                        "source_hash": record["source_hash"],
                    }
                )
                if deleted_record_id_for(record) == record_id
                else record["source_text"]
            ),
            "content_hash": "",
            "meaning": "Presence of the exact source in the fixed Git transition target",
        }
        source_observation["content_hash"] = content_hash(source_observation["content"])
        temporal = entry["temporal_observation"]
        if temporal is not None:
            temporal = {**temporal, "snapshot_hash": snapshot_hash}
        try:
            value = build_retention_evidence(
                identity=identity,
                metadata=record["metadata"],
                disposition=disposition,
                evidence=entry["evidence"],
                determination=entry["determination"],
                source_observation=source_observation,
                temporal_observation=temporal,
            )
            projections.append(retention_record_projection(value))
        except ResolutionStateError as exc:
            raise CoordinatorBlocked(exc.reason_code, str(exc)) from exc
        detailed[record_id] = value
    return projections, detailed


def _obligations(
    aggregate_result: dict[str, Any],
    retention_by_id: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    obligations = []
    for outcome in aggregate_result["records"]:
        if outcome["disposition"] not in {"DROP", "MOVE_TO_POLICY_CHECK"} or outcome["gate"] != "CHANGES_REQUIRED":
            continue
        record_id = outcome["record_id"]
        retention = retention_by_id[record_id]
        origin = {
            "record": retention["identity"],
            "retention": retention,
            "frozen_result": outcome,
        }
        obligations.append(
            {
                "obligation_id": _canonical_hash({"record_id": record_id, "origin": origin}),
                "action": outcome["disposition"],
                "origin": origin,
            }
        )
    return obligations


def _atomic_write(path: Path, value: dict[str, Any]) -> None:
    data = (canonical_json(value) + "\n").encode("utf-8")
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile("wb", dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        temporary = None
    except OSError as exc:
        raise CoordinatorBlocked("STATE_WRITE_FAILED", str(exc)) from exc
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _load_or_initialize_task(
    state_dir: Path,
    *,
    task_id: str,
    root: Path,
    base_oid: str,
    mode: str,
) -> dict[str, Any]:
    path = state_dir / "task-manifest.json"
    identity = {
        "task_id": task_id,
        "repository_root": str(root),
        "base_commit_oid": base_oid,
        "target_mode": mode,
    }
    if path.exists():
        state = _read_json_object(path, "STATE")
        if set(state) != {"schema_version", *identity, "generations"} or state.get("schema_version") != TASK_STATE_VERSION:
            raise CoordinatorBlocked("STATE_INVALID", "task manifest has an invalid shape")
        if any(state[key] != value for key, value in identity.items()):
            raise CoordinatorBlocked("STATE_IDENTITY_MISMATCH", "state belongs to another review target")
        if not isinstance(state["generations"], list):
            raise CoordinatorBlocked("STATE_INVALID", "generations must be an array")
        return state
    if any(
        (state_dir / name).exists()
        for name in ("generations", "initial-manifest.json", "resolution-ledger.json")
    ):
        raise CoordinatorBlocked(
            "STATE_MANIFEST_MISSING",
            "review state artifacts exist without task-manifest.json",
        )
    state = {"schema_version": TASK_STATE_VERSION, **identity, "generations": []}
    _atomic_write(path, state)
    return state


def _validate_deep_batch_execution(
    envelope: dict[str, Any],
    global_packet: dict[str, Any],
    sol_result: dict[str, Any],
    toolchain_identity: dict[str, Any],
) -> None:
    if not isinstance(envelope, dict) or set(envelope) != {
        "schema_version",
        "phase",
        "global_input_hash",
        "batches",
        "merged_result_hash",
    }:
        raise CoordinatorBlocked("STATE_INVALID", "deep batch execution has an invalid shape")
    if (
        envelope["schema_version"] != "deep-batch-execution-v1"
        or envelope["phase"] != "deep"
        or envelope["global_input_hash"] != global_packet["input_hash"]
        or not isinstance(envelope["batches"], list)
        or len(envelope["batches"]) < 2
    ):
        raise CoordinatorBlocked("STATE_INVALID", "deep batch execution identity is invalid")
    global_records = global_packet["records"]
    cursor = 0
    merged_reviews = []
    for index, batch in enumerate(envelope["batches"]):
        if not isinstance(batch, dict) or set(batch) != {
            "index",
            "record_ids",
            "packet_input_hash",
            "result",
            "result_hash",
            "worker_evidence",
            "worker_evidence_hash",
        }:
            raise CoordinatorBlocked("STATE_INVALID", "deep batch proof has an invalid shape")
        record_ids = batch["record_ids"]
        if batch["index"] != index or not isinstance(record_ids, list) or not record_ids:
            raise CoordinatorBlocked("STATE_INVALID", "deep batch partition is invalid")
        expected_records = global_records[cursor : cursor + len(record_ids)]
        if record_ids != [item["record_id"] for item in expected_records]:
            raise CoordinatorBlocked("STATE_INVALID", "deep batch partition is not canonical")
        cursor += len(record_ids)
        try:
            packet = project_deep_batch(global_packet, expected_records)
        except PacketError as exc:
            raise CoordinatorBlocked("STATE_INVALID", str(exc)) from exc
        if packet["input_hash"] != batch["packet_input_hash"]:
            raise CoordinatorBlocked("STATE_INVALID", "deep batch packet hash mismatch")
        if batch["result_hash"] != result_hash(batch["result"]):
            raise CoordinatorBlocked("STATE_INVALID", "deep batch result hash mismatch")
        try:
            validated = validate_phase_result(
                "deep",
                batch["result"],
                packet["records"],
                packet["input_hash"],
            )
        except ResultValidationError as exc:
            raise CoordinatorBlocked("STATE_INVALID", str(exc)) from exc
        evidence = batch["worker_evidence"]
        if (
            not isinstance(evidence, dict)
            or evidence.get("schema_version") != "review-worker-evidence-v1"
            or evidence.get("phase") != "deep"
            or batch["worker_evidence_hash"] != _canonical_hash(evidence)
        ):
            raise CoordinatorBlocked("STATE_INVALID", "deep batch worker evidence is invalid")
        _validate_worker_toolchain("deep", evidence, toolchain_identity)
        merged_reviews.extend(validated["reviews"])
    if cursor != len(global_records):
        raise CoordinatorBlocked("STATE_INVALID", "deep batch partition is incomplete")
    merged = {
        "review_contract_version": "deep-review-v2",
        "input_hash": global_packet["input_hash"],
        "reviews": merged_reviews,
    }
    try:
        merged = validate_phase_result(
            "deep",
            merged,
            global_records,
            global_packet["input_hash"],
        )
    except ResultValidationError as exc:
        raise CoordinatorBlocked("STATE_INVALID", str(exc)) from exc
    if merged != sol_result or envelope["merged_result_hash"] != result_hash(merged):
        raise CoordinatorBlocked("STATE_INVALID", "deep batch merged result mismatch")


def _load_generation(state_dir: Path, descriptor: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(descriptor, dict) or set(descriptor) != {
        "generation_id", "generation_path", "target_snapshot_hash", "selection_hash",
        "host_evidence_hash", "toolchain_hash", "worker_evidence_hash"
    }:
        raise CoordinatorBlocked("STATE_INVALID", "generation descriptor is invalid")
    relative = Path(_nonempty(descriptor["generation_path"], "generation_path"))
    path = (state_dir / relative).resolve(strict=False)
    if not path.is_relative_to(state_dir.resolve()) or not path.is_file():
        raise CoordinatorBlocked("STATE_MISSING", str(relative))
    value = _read_json_object(path, "GENERATION")
    if set(value) != {
        "schema_version", "generation_id", "target_snapshot", "target_snapshot_hash", "selection_hash",
        "host_evidence_hash", "toolchain_identity", "toolchain_hash", "aggregation",
        "worker_evidence", "worker_evidence_hash", "resolution_state"
    } or value.get("schema_version") != GENERATION_VERSION:
        raise CoordinatorBlocked("STATE_INVALID", "generation has an invalid shape")
    for key in (
        "generation_id",
        "target_snapshot_hash",
        "selection_hash",
        "host_evidence_hash",
        "toolchain_hash",
        "worker_evidence_hash",
    ):
        if value[key] != descriptor[key]:
            raise CoordinatorBlocked("STATE_INVALID", f"generation {key} mismatch")
    if value["toolchain_hash"] != _canonical_hash(value["toolchain_identity"]):
        raise CoordinatorBlocked("STATE_INVALID", "generation toolchain hash mismatch")
    target_snapshot = value["target_snapshot"]
    if (
        not isinstance(target_snapshot, dict)
        or target_snapshot.get("target_snapshot_hash") != value["target_snapshot_hash"]
        or _canonical_hash(
            {key: item for key, item in target_snapshot.items() if key != "target_snapshot_hash"}
        ) != value["target_snapshot_hash"]
    ):
        raise CoordinatorBlocked("STATE_INVALID", "generation target snapshot is invalid")
    aggregation = value["aggregation"]
    if not isinstance(aggregation, dict) or set(aggregation) != {"input", "input_hash", "result", "result_hash"}:
        raise CoordinatorBlocked("STATE_INVALID", "generation aggregation is invalid")
    if aggregation["input_hash"] != result_hash(aggregation["input"]):
        raise CoordinatorBlocked("STATE_INVALID", "generation input hash mismatch")
    expected = aggregate_results(aggregation["input"])
    if aggregation["result"] != expected or aggregation["result_hash"] != result_hash(expected):
        raise CoordinatorBlocked("STATE_INVALID", "generation aggregate mismatch")
    requires_resolution = any(
        item["disposition"] in {"DROP", "MOVE_TO_POLICY_CHECK"}
        and item["gate"] == "CHANGES_REQUIRED"
        for item in expected["records"]
    )
    expected_resolution_state = (
        f"generations/{value['generation_id']}/resolution"
        if requires_resolution
        else None
    )
    if value["resolution_state"] != expected_resolution_state:
        raise CoordinatorBlocked(
            "STATE_INVALID",
            "generation resolution state does not match canonical obligations",
        )
    worker_evidence = value["worker_evidence"]
    if (
        not isinstance(worker_evidence, list)
        or value["worker_evidence_hash"] != _canonical_hash(worker_evidence)
        or len(worker_evidence) < 2
    ):
        raise CoordinatorBlocked("STATE_INVALID", "generation worker evidence is invalid")
    phase_evidence = worker_evidence[:2]
    if any(
        not isinstance(item, dict)
        or item.get("schema_version") != "review-worker-evidence-v1"
        or item.get("phase") != phase
        for item, phase in zip(phase_evidence, ("metadata", "alignment"))
    ):
        raise CoordinatorBlocked("STATE_INVALID", "generation Luna evidence is incomplete")
    deep_required = any(
        item["result"]["required"]
        for item in aggregation["input"]["routing_manifest"]["records"]
    )
    deep_evidence = worker_evidence[2:]
    try:
        for item in phase_evidence:
            _validate_worker_toolchain(item["phase"], item, value["toolchain_identity"])
        if not deep_required:
            if deep_evidence:
                raise CoordinatorBlocked("STATE_INVALID", "unexpected deep evidence")
        elif (
            len(deep_evidence) == 1
            and isinstance(deep_evidence[0], dict)
            and deep_evidence[0].get("schema_version") == "deep-batch-execution-v1"
        ):
            _validate_deep_batch_execution(
                deep_evidence[0],
                aggregation["input"]["deep_packet"],
                aggregation["input"]["sol_result"],
                value["toolchain_identity"],
            )
        elif len(deep_evidence) in {1, 2} and all(
            isinstance(item, dict)
            and item.get("schema_version") == "review-worker-evidence-v1"
            and item.get("phase") == "deep"
            for item in deep_evidence
        ):
            for item in deep_evidence:
                _validate_worker_toolchain("deep", item, value["toolchain_identity"])
        else:
            raise CoordinatorBlocked("STATE_INVALID", "generation deep evidence is incomplete")
    except (CoordinatorBlocked, KeyError, StopIteration, TypeError, OSError) as exc:
        raise CoordinatorBlocked("STATE_INVALID", "generation worker identity is invalid") from exc
    return value


def _resolution_gate(
    root: Path,
    state_dir: Path,
    generation: dict[str, Any],
    *,
    task_id: str,
    current_snapshot_hash: str,
    mode: str,
    head_oid: str | None,
    pending: list[dict[str, Any]] | None = None,
) -> tuple[str, set[str]]:
    relative = generation["resolution_state"]
    if relative is None:
        return "PASS", set()
    path = (state_dir / Path(relative)).resolve(strict=False)
    if not path.is_relative_to(state_dir.resolve()):
        raise CoordinatorBlocked("STATE_INVALID", "resolution path escapes state directory")
    summary = evaluate_obligation_gate(path, expected_task_id=task_id)
    if summary["obligation_gate"] == "BLOCKED":
        return "BLOCKED", set()
    try:
        manifest, ledger = load_resolution_state(path, expected_task_id=task_id)
    except ResolutionStateError:
        return "BLOCKED", set()
    if manifest["aggregation"] != generation["aggregation"]:
        return "BLOCKED", set()
    latest = {item["obligation_id"]: item for item in ledger["entries"]}
    for item in pending or []:
        if item["generation_id"] == generation["generation_id"]:
            latest[item["entry"]["obligation_id"]] = item["entry"]
    resolved: set[str] = set()
    gate = "PASS"
    for obligation in manifest["obligations"]:
        entry = latest.get(obligation["obligation_id"])
        receipt_current = False
        if entry is not None and entry["state"] == "RESOLVED":
            resolution = entry["resolution"]
            receipt_current = resolution["current_snapshot_hash"] == current_snapshot_hash
            if receipt_current:
                try:
                    receipt_current = resolution["removal"] == _removal_observation(
                        root,
                        manifest,
                        obligation,
                        snapshot_hash=current_snapshot_hash,
                        mode=mode,
                        head_oid=head_oid,
                    )
                    target = resolution["target"]
                    if receipt_current and target is not None:
                        current_target = _target_text(
                            root,
                            target["ref"],
                            mode=mode,
                            head_oid=head_oid,
                        )
                        receipt_current = (
                            target["snapshot_hash"] == current_snapshot_hash
                            and current_target == target["content"]
                            and content_hash(current_target or "") == target["content_hash"]
                        )
                except CoordinatorBlocked:
                    receipt_current = False
        if not receipt_current:
            gate = "CHANGES_REQUIRED"
        else:
            resolved.add(obligation["origin"]["record"]["record_id"])
    return gate, resolved


def _outer_gate(
    root: Path,
    state_dir: Path,
    state: dict[str, Any],
    current: dict[str, Any],
    *,
    current_snapshot_hash: str,
    mode: str,
    head_oid: str | None,
    pending: list[dict[str, Any]] | None = None,
    supersessions: list[dict[str, Any]] | None = None,
) -> str:
    gates = []
    current_resolved: set[str] = set()
    current_outcomes = {
        item["record_id"]: item for item in current["aggregation"]["result"]["records"]
    }
    current_packet_records = current["aggregation"]["input"]["alignment_packet"]["records"]
    current_record_by_id = {item["record_id"]: item for item in current_packet_records}
    supersession_by_old = {
        (item["historical_generation_id"], item["historical_record_id"]): item
        for item in supersessions or []
    }
    used_supersessions: set[tuple[str, str]] = set()
    current_by_locator: dict[
        tuple[str, str, str], list[tuple[dict[str, Any], dict[str, Any]]]
    ] = {}
    for outcome in current_outcomes.values():
        record = current_record_by_id[outcome["record_id"]]
        locator = (record["adapter"], record["source"]["path"], record["source"]["symbol"])
        current_by_locator.setdefault(locator, []).append((outcome, record))
    for descriptor in state["generations"]:
        generation = _load_generation(state_dir, descriptor)
        gate, resolved = _resolution_gate(
            root,
            state_dir,
            generation,
            task_id=state["task_id"],
            current_snapshot_hash=current_snapshot_hash,
            mode=mode,
            head_oid=head_oid,
            pending=pending,
        )
        gates.append(gate)
        if generation["generation_id"] == current["generation_id"]:
            current_resolved = resolved
            continue
        historical_packet = {
            item["record_id"]: item
            for item in generation["aggregation"]["input"]["alignment_packet"]["records"]
        }
        for historical in generation["aggregation"]["result"]["records"]:
            historical_gate = historical["gate"]
            if historical_gate == "PASS":
                continue
            if (
                historical_gate == "CHANGES_REQUIRED"
                and historical["disposition"] in {"DROP", "MOVE_TO_POLICY_CHECK"}
                and historical["record_id"] in resolved
            ):
                continue
            replacement = current_outcomes.get(historical["record_id"])
            supplied = supersession_by_old.get(
                (generation["generation_id"], historical["record_id"])
            )
            if supplied is not None:
                old_record = historical_packet[historical["record_id"]]
                candidate = current_record_by_id.get(supplied["current_record_id"])
                candidate_outcome = current_outcomes.get(supplied["current_record_id"])
                if (
                    supplied["historical_metadata_hash"] != old_record["metadata_hash"]
                    or supplied["historical_source_hash"] != old_record["source_hash"]
                    or candidate is None
                    or supplied["current_metadata_hash"] != candidate["metadata_hash"]
                    or supplied["current_source_hash"] != candidate["source_hash"]
                ):
                    raise CoordinatorBlocked(
                        "HOST_EVIDENCE_IDENTITY_MISMATCH",
                        historical["record_id"],
                    )
                used_supersessions.add(
                    (generation["generation_id"], historical["record_id"])
                )
                if candidate_outcome is not None and candidate_outcome["gate"] == "PASS":
                    continue
            if replacement is None:
                record = historical_packet[historical["record_id"]]
                locator = (
                    record["adapter"],
                    record["source"]["path"],
                    record["source"]["symbol"],
                )
                candidates = [
                    outcome
                    for outcome, candidate in current_by_locator.get(locator, [])
                    if candidate["source_hash"] == record["source_hash"]
                    or candidate["metadata_hash"] == record["metadata_hash"]
                ]
                if len(candidates) == 1:
                    replacement = candidates[0]
            if replacement is not None and replacement["gate"] == "PASS":
                continue
            gates.append(historical_gate)
    for outcome in current["aggregation"]["result"]["records"]:
        gate = outcome["gate"]
        if gate == "CHANGES_REQUIRED" and outcome["disposition"] in {"DROP", "MOVE_TO_POLICY_CHECK"} and outcome["record_id"] in current_resolved:
            gate = "PASS"
        gates.append(gate)
    if used_supersessions != set(supersession_by_old):
        raise CoordinatorBlocked(
            "HOST_EVIDENCE_IDENTITY_MISMATCH",
            "supersession does not identify an unresolved historical record",
        )
    return aggregate_gate(gates)


def _result_details(
    root: Path,
    state_dir: Path,
    state: dict[str, Any],
    generation: dict[str, Any],
    *,
    gate: str,
    current_snapshot_hash: str,
    mode: str,
    head_oid: str | None,
    pending: list[dict[str, Any]],
    supersessions: list[dict[str, Any]],
) -> dict[str, Any]:
    aggregation_input = generation["aggregation"]["input"]
    aggregate_records = generation["aggregation"]["result"]["records"]
    alignment_packet = aggregation_input["alignment_packet"]
    alignment_by_id = {
        item["record_id"]: item for item in aggregation_input["alignment_result"]["reviews"]
    }
    sol_result = aggregation_input["sol_result"]
    sol_by_id = {} if sol_result is None else {
        item["record_id"]: item for item in sol_result["reviews"]
    }
    retention_by_id = {
        item["record_id"]: item for item in aggregation_input["retention_records"]
    }
    packet_by_id = {item["record_id"]: item for item in alignment_packet["records"]}
    supersession_by_old = {
        (item["historical_generation_id"], item["historical_record_id"]): item
        for item in supersessions
    }
    current_by_locator: dict[
        tuple[str, str, str], list[tuple[dict[str, Any], dict[str, Any]]]
    ] = {}
    for outcome in aggregate_records:
        record = packet_by_id[outcome["record_id"]]
        locator = (record["adapter"], record["source"]["path"], record["source"]["symbol"])
        current_by_locator.setdefault(locator, []).append((outcome, record))
    unresolved = []
    for outcome in aggregate_records:
        if outcome["gate"] != "BLOCKED":
            continue
        record_id = outcome["record_id"]
        packet_record = packet_by_id[record_id]
        alignment = alignment_by_id[record_id]
        sol = sol_by_id.get(record_id)
        reasons = []
        requirements = list(alignment["context_requirements"])
        metadata_review = packet_record["metadata_review"]
        if metadata_review["verdict"] == "NEEDS_CONTEXT":
            reasons.append("METADATA_NEEDS_CONTEXT")
            requirements.extend(metadata_review["unverified"])
        if alignment["verdict"] == "RECHECK":
            reasons.append("ALIGNMENT_NEEDS_CONTEXT")
        if sol is not None and sol["verdict"] == "NEEDS_CONTEXT":
            reasons.append("DEEP_NEEDS_CONTEXT")
            requirements.extend(sol["context_requirements"])
        if retention_by_id[record_id]["retention_basis"] == "UNRESOLVED":
            reasons.append("RETENTION_EVIDENCE_REQUIRED")
        if not reasons:
            reasons.append("CANONICAL_RESULT_BLOCKED")
        unresolved.append(
            {
                "record_id": record_id,
                "reason_codes": reasons,
                "context_requirements": list(dict.fromkeys(requirements)),
            }
        )

    obligations = []
    pending_by_id = {
        item["entry"]["attempt_id"]: item["entry"] for item in pending
    }
    for descriptor in state["generations"]:
        historical = _load_generation(state_dir, descriptor)
        _, resolved_record_ids = _resolution_gate(
            root,
            state_dir,
            historical,
            task_id=state["task_id"],
            current_snapshot_hash=current_snapshot_hash,
            mode=mode,
            head_oid=head_oid,
            pending=pending,
        )
        relative = historical["resolution_state"]
        if relative is not None:
            manifest, ledger = load_resolution_state(
                state_dir / relative,
                expected_task_id=state["task_id"],
            )
            entries = [*ledger["entries"]]
            entries.extend(
                item["entry"]
                for item in pending
                if item["generation_id"] == historical["generation_id"]
                and item["entry"]["attempt_id"] in pending_by_id
            )
            latest = {item["obligation_id"]: item for item in entries}
            for obligation in manifest["obligations"]:
                entry = latest.get(obligation["obligation_id"])
                record_id = obligation["origin"]["record"]["record_id"]
                obligations.append(
                    {
                        "generation_id": historical["generation_id"],
                        "resolution_state": relative,
                        "obligation_id": obligation["obligation_id"],
                        "action": obligation["action"],
                        "state": None if entry is None else entry["state"],
                        "verified_current": record_id in resolved_record_ids,
                    }
                )
        if historical["generation_id"] == generation["generation_id"]:
            continue
        historical_packet = {
            item["record_id"]: item
            for item in historical["aggregation"]["input"]["alignment_packet"]["records"]
        }
        current_by_id = {item["record_id"]: item for item in aggregate_records}
        for outcome in historical["aggregation"]["result"]["records"]:
            if outcome["gate"] == "PASS":
                continue
            if (
                outcome["disposition"] in {"DROP", "MOVE_TO_POLICY_CHECK"}
                and outcome["record_id"] in resolved_record_ids
            ):
                continue
            replacement = current_by_id.get(outcome["record_id"])
            supplied = supersession_by_old.get(
                (historical["generation_id"], outcome["record_id"])
            )
            if supplied is not None:
                replacement = current_by_id.get(supplied["current_record_id"])
            if replacement is None:
                record = historical_packet[outcome["record_id"]]
                locator = (
                    record["adapter"],
                    record["source"]["path"],
                    record["source"]["symbol"],
                )
                candidates = [
                    outcome
                    for outcome, candidate in current_by_locator.get(locator, [])
                    if candidate["source_hash"] == record["source_hash"]
                    or candidate["metadata_hash"] == record["metadata_hash"]
                ]
                if len(candidates) == 1:
                    replacement = candidates[0]
            if replacement is not None and replacement["gate"] == "PASS":
                continue
            unresolved.append(
                {
                    "generation_id": historical["generation_id"],
                    "record_id": outcome["record_id"],
                    "reason_codes": [f"HISTORICAL_{outcome['gate']}"],
                    "context_requirements": [],
                }
            )
    reason_codes = []
    if gate == "BLOCKED":
        reason_codes.append("AGGREGATE_BLOCKED")
    if gate == "CHANGES_REQUIRED" and any(
        not item["verified_current"] for item in obligations
    ):
        reason_codes.append("RESOLUTION_REQUIRED")
    elif gate == "CHANGES_REQUIRED":
        reason_codes.append("REVIEW_CHANGES_REQUIRED")
    return {
        "records": aggregate_records,
        "unresolved": unresolved,
        "resolution_obligations": obligations,
        "reason_codes": reason_codes,
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    root = _resolve_repository(args.root)
    try:
        state_dir = args.state_dir.resolve(strict=True)
    except OSError as exc:
        raise CoordinatorBlocked("STATE_DIRECTORY_MISSING", str(exc)) from exc
    if not state_dir.is_dir():
        raise CoordinatorBlocked("STATE_DIRECTORY_MISSING", "--state-dir must be a directory")
    if state_dir.is_relative_to(root):
        raise CoordinatorBlocked("STATE_INSIDE_ROOT", "--state-dir must be outside the repository")
    base_oid = _resolve_commit(root, args.changed_from)
    mode = "staged" if args.staged else "head" if args.head else "working"
    head_oid = _resolve_commit(root, args.head) if args.head else None
    before = snapshot_descriptor(root, base_oid, mode=mode, head_oid=head_oid)
    extractors = extract_all_languages(root, base_oid, mode=mode, head_oid=head_oid)
    after_extract = snapshot_descriptor(root, base_oid, mode=mode, head_oid=head_oid)
    if before != after_extract:
        raise CoordinatorBlocked("SNAPSHOT_CHANGED", "source changed during extraction")
    selection_hash = _canonical_hash(extractors)
    metadata_packet = build_metadata_packet_multi(extractors)
    identity_records = extractor_record_identities_multi(extractors)
    if args.host_evidence is None:
        template = {
            "schema_version": HOST_EVIDENCE_VERSION,
            "task_id": "<task-id>",
            "target_snapshot_hash": before["target_snapshot_hash"],
            "selection_hash": selection_hash,
            "parent_risk_assessment": {
                "status": "UNRESOLVED",
                "risk_tags": [],
                "rationale": "",
                "evidence": [],
                "evidence_refs": [],
            },
            "context_by_record": [],
            "retry_context_by_record": [],
            "retention_by_record": [
                {
                    **record,
                    "evidence": [],
                    "determination": None,
                    "temporal_observation": None,
                }
                for record in identity_records
            ],
            "resolution_attempts": [],
            "supersessions": [],
        }
        return {
            "schema_version": RESULT_VERSION,
            "gate": "BLOCKED",
            "reason_codes": ["HOST_EVIDENCE_REQUIRED"],
            "target_snapshot_hash": before["target_snapshot_hash"],
            "selection_hash": selection_hash,
            "selection_summary": extractor_record_summaries_multi(extractors),
            "host_evidence_template": template,
        }
    host_raw = _read_json_object(args.host_evidence, "HOST_EVIDENCE")
    host_hash = _canonical_hash({**host_raw, "resolution_attempts": []})
    host = validate_host_evidence(
        root,
        host_raw,
        snapshot_hash=before["target_snapshot_hash"],
        selection_hash=selection_hash,
        records=identity_records,
        mode=mode,
        head_oid=head_oid,
    )
    scripts_root = Path(__file__).resolve().parents[3]
    toolchain_identity = _toolchain_identity(args.cli, scripts_root)
    toolchain_hash = _canonical_hash(toolchain_identity)
    state = _load_or_initialize_task(
        state_dir,
        task_id=host["task_id"],
        root=root,
        base_oid=base_oid,
        mode=mode,
    )
    for descriptor in state["generations"]:
        historical = _load_generation(state_dir, descriptor)
        historical_gate, _ = _resolution_gate(
            root,
            state_dir,
            historical,
            task_id=state["task_id"],
            current_snapshot_hash=before["target_snapshot_hash"],
            mode=mode,
            head_oid=head_oid,
        )
        if historical_gate == "BLOCKED":
            raise CoordinatorBlocked(
                "HISTORICAL_STATE_INVALID",
                f"historical generation cannot be trusted: {historical['generation_id']}",
            )
    pending_attempts = _prepare_resolution_attempts(
        root,
        state_dir,
        state,
        host["resolution_attempts"],
        snapshot_hash=before["target_snapshot_hash"],
        mode=mode,
        head_oid=head_oid,
    )
    if snapshot_descriptor(root, base_oid, mode=mode, head_oid=head_oid) != before:
        raise CoordinatorBlocked("SNAPSHOT_CHANGED", "source changed during resolution validation")
    matching = next(
        (
            descriptor for descriptor in reversed(state["generations"])
            if descriptor["target_snapshot_hash"] == before["target_snapshot_hash"]
            and descriptor["selection_hash"] == selection_hash
            and descriptor["host_evidence_hash"] == host_hash
            and descriptor["toolchain_hash"] == toolchain_hash
        ),
        None,
    )
    if matching is not None:
        generation = _load_generation(state_dir, matching)
        gate = _outer_gate(
            root,
            state_dir,
            state,
            generation,
            current_snapshot_hash=before["target_snapshot_hash"],
            mode=mode,
            head_oid=head_oid,
            pending=pending_attempts,
            supersessions=host["supersessions"],
        )
        if snapshot_descriptor(root, base_oid, mode=mode, head_oid=head_oid) != before:
            raise CoordinatorBlocked("SNAPSHOT_CHANGED", "source changed during state validation")
        details = _result_details(
            root,
            state_dir,
            state,
            generation,
            gate=gate,
            current_snapshot_hash=before["target_snapshot_hash"],
            mode=mode,
            head_oid=head_oid,
            pending=pending_attempts,
            supersessions=host["supersessions"],
        )
        if snapshot_descriptor(root, base_oid, mode=mode, head_oid=head_oid) != before:
            raise CoordinatorBlocked("SNAPSHOT_CHANGED", "source changed before resolution commit")
        if _toolchain_identity(args.cli, scripts_root) != toolchain_identity:
            raise CoordinatorBlocked("TOOLCHAIN_CHANGED", "review toolchain changed before reuse")
        result = {
            "schema_version": RESULT_VERSION,
            "task_id": host["task_id"],
            "target_snapshot_hash": before["target_snapshot_hash"],
            "selection_hash": selection_hash,
            "generation_id": generation["generation_id"],
            "gate": gate,
            "worker_evidence_hashes": [
                _canonical_hash(item) for item in generation["worker_evidence"]
            ],
            **details,
        }
        _commit_resolution_attempts(pending_attempts, task_id=state["task_id"])
        return result

    luna_role = scripts_root / "agents" / "test_value_luna.toml"
    sol_role = scripts_root / "agents" / "test_value_sol.toml"
    worker_evidence = []
    metadata_result, evidence = _execute_phase(
        "metadata", metadata_packet, cli=args.cli, role_file=luna_role
    )
    _validate_worker_toolchain("metadata", evidence, toolchain_identity)
    worker_evidence.append(evidence)
    validate_phase_result("metadata", metadata_result, metadata_packet["records"])
    alignment_packet = build_alignment_packet_multi(extractors, metadata_result)
    alignment_result, evidence = _execute_phase(
        "alignment", alignment_packet, cli=args.cli, role_file=luna_role
    )
    _validate_worker_toolchain("alignment", evidence, toolchain_identity)
    worker_evidence.append(evidence)
    alignment_reviews = validate_phase_result(
        "alignment", alignment_result, alignment_packet["records"]
    )["reviews"]
    routing_inputs = _routing_inputs(alignment_packet, alignment_result)
    workflow_context = {
        "review_contract_version": "review-workflow-context-v1",
        "records": [
            {
                "record_id": item["record_id"],
                "metadata_hash": item["metadata_hash"],
                "parent_risk_tags": host["risk_tags"],
                "audit_percent": AUDIT_PERCENT,
            }
            for item in alignment_packet["records"]
        ],
    }
    routing_manifest = build_routing_manifest(routing_inputs, workflow_context)
    required = {
        item["record_id"]
        for item in routing_manifest["records"]
        if item["result"]["required"]
    }
    supplied_context = set(host["context_by_record"]) | set(host["retry_context_by_record"])
    if not supplied_context.issubset(required):
        raise CoordinatorBlocked("UNREQUESTED_CONTEXT", "context supplied for a non-Sol record")
    deep_packet = build_deep_packet(
        alignment_packet,
        metadata_result,
        alignment_result,
        routing_manifest,
        workflow_context,
        host["context_by_record"],
    )
    sol_result = None
    if required:
        sol_result, evidence = _execute_deep_round(
            deep_packet,
            cli=args.cli,
            role_file=sol_role,
            toolchain_identity=toolchain_identity,
        )
        worker_evidence.append(evidence)
        reviews = validate_phase_result(
            "deep", sol_result, deep_packet["records"], deep_packet["input_hash"]
        )["reviews"]
        unresolved = {item["record_id"] for item in reviews if item["verdict"] == "NEEDS_CONTEXT"}
        retry = host["retry_context_by_record"]
        if unresolved and set(retry) & unresolved:
            combined = {
                record_id: [*host["context_by_record"].get(record_id, []), *retry.get(record_id, [])]
                for record_id in required
                if host["context_by_record"].get(record_id) or retry.get(record_id)
            }
            deep_packet = build_deep_packet(
                alignment_packet,
                metadata_result,
                alignment_result,
                routing_manifest,
                workflow_context,
                combined,
            )
            retry_result, retry_evidence = _execute_deep_round(
                deep_packet,
                cli=args.cli,
                role_file=sol_role,
                toolchain_identity=toolchain_identity,
            )
            if (
                evidence.get("schema_version") == "deep-batch-execution-v1"
                or retry_evidence.get("schema_version") == "deep-batch-execution-v1"
            ):
                worker_evidence[-1] = retry_evidence
            else:
                worker_evidence.append(retry_evidence)
            sol_result = retry_result
            validate_phase_result(
                "deep", sol_result, deep_packet["records"], deep_packet["input_hash"]
            )
    retention_records, detailed_retention = _retention_inputs(
        alignment_packet["records"],
        alignment_result,
        sol_result,
        host,
        before["target_snapshot_hash"],
    )
    aggregate_input = {
        "alignment_packet": alignment_packet,
        "metadata_result": metadata_result,
        "deep_packet": deep_packet,
        "alignment_result": alignment_result,
        "workflow_routing_context": workflow_context,
        "routing_manifest": routing_manifest,
        "sol_result": sol_result,
        "retention_records": retention_records,
    }
    aggregate_result = aggregate_results(aggregate_input)
    if _toolchain_identity(args.cli, scripts_root) != toolchain_identity:
        raise CoordinatorBlocked("TOOLCHAIN_CHANGED", "review toolchain changed during execution")
    if snapshot_descriptor(root, base_oid, mode=mode, head_oid=head_oid) != before:
        raise CoordinatorBlocked("SNAPSHOT_CHANGED", "source changed during review")
    generation_number = len(state["generations"]) + 1
    while (state_dir / "generations" / f"g{generation_number:06d}").exists():
        generation_number += 1
    generation_id = f"g{generation_number:06d}"
    generation_dir = state_dir / "generations" / generation_id
    try:
        generation_dir.mkdir(parents=True, exist_ok=False)
    except OSError as exc:
        raise CoordinatorBlocked("STATE_WRITE_FAILED", str(exc)) from exc
    aggregation = {
        "input": aggregate_input,
        "input_hash": result_hash(aggregate_input),
        "result": aggregate_result,
        "result_hash": result_hash(aggregate_result),
    }
    obligations = _obligations(aggregate_result, detailed_retention)
    resolution_state = None
    if obligations:
        resolution_dir = generation_dir / "resolution"
        resolution_dir.mkdir()
        manifest = {
            "schema_version": MANIFEST_VERSION,
            "task_id": host["task_id"],
            "initial_snapshot_hash": before["target_snapshot_hash"],
            "selection_hash": selection_hash,
            "artifact_hashes": [aggregation["input_hash"], aggregation["result_hash"]],
            "aggregation": aggregation,
            "obligations": obligations,
        }
        try:
            initialize_resolution_state(resolution_dir, manifest)
        except ResolutionStateError as exc:
            raise CoordinatorBlocked(exc.reason_code, str(exc)) from exc
        resolution_state = f"generations/{generation_id}/resolution"
    generation = {
        "schema_version": GENERATION_VERSION,
        "generation_id": generation_id,
        "target_snapshot": before,
        "target_snapshot_hash": before["target_snapshot_hash"],
        "selection_hash": selection_hash,
        "host_evidence_hash": host_hash,
        "toolchain_identity": toolchain_identity,
        "toolchain_hash": toolchain_hash,
        "aggregation": aggregation,
        "worker_evidence": worker_evidence,
        "worker_evidence_hash": _canonical_hash(worker_evidence),
        "resolution_state": resolution_state,
    }
    generation_path = generation_dir / "generation.json"
    _atomic_write(generation_path, generation)
    descriptor = {
        "generation_id": generation_id,
        "generation_path": f"generations/{generation_id}/generation.json",
        "target_snapshot_hash": before["target_snapshot_hash"],
        "selection_hash": selection_hash,
        "host_evidence_hash": host_hash,
        "toolchain_hash": toolchain_hash,
        "worker_evidence_hash": generation["worker_evidence_hash"],
    }
    state = {**state, "generations": [*state["generations"], descriptor]}
    _atomic_write(state_dir / "task-manifest.json", state)
    gate = _outer_gate(
        root,
        state_dir,
        state,
        generation,
        current_snapshot_hash=before["target_snapshot_hash"],
        mode=mode,
        head_oid=head_oid,
        pending=pending_attempts,
        supersessions=host["supersessions"],
    )
    if snapshot_descriptor(root, base_oid, mode=mode, head_oid=head_oid) != before:
        raise CoordinatorBlocked("SNAPSHOT_CHANGED", "source changed during final resolution gate")
    details = _result_details(
        root,
        state_dir,
        state,
        generation,
        gate=gate,
        current_snapshot_hash=before["target_snapshot_hash"],
        mode=mode,
        head_oid=head_oid,
        pending=pending_attempts,
        supersessions=host["supersessions"],
    )
    if snapshot_descriptor(root, base_oid, mode=mode, head_oid=head_oid) != before:
        raise CoordinatorBlocked("SNAPSHOT_CHANGED", "source changed before resolution commit")
    if _toolchain_identity(args.cli, scripts_root) != toolchain_identity:
        raise CoordinatorBlocked("TOOLCHAIN_CHANGED", "review toolchain changed before commit")
    result = {
        "schema_version": RESULT_VERSION,
        "task_id": host["task_id"],
        "target_snapshot_hash": before["target_snapshot_hash"],
        "selection_hash": selection_hash,
        "generation_id": generation_id,
        "gate": gate,
        "worker_evidence_hashes": [_canonical_hash(item) for item in worker_evidence],
        **details,
    }
    _commit_resolution_attempts(pending_attempts, task_id=state["task_id"])
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--changed-from", "--base", dest="changed_from", required=True)
    target = parser.add_mutually_exclusive_group()
    target.add_argument("--head")
    target.add_argument("--staged", action="store_true")
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--cli", required=True)
    parser.add_argument("--host-evidence", type=Path)
    parser.add_argument("--prepare", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.prepare:
        if args.host_evidence is not None:
            print(
                canonical_json(
                    {
                        "schema_version": RESULT_VERSION,
                        "gate": "BLOCKED",
                        "reason_codes": ["CLI_INPUT_INVALID"],
                        "message": "--prepare and --host-evidence are mutually exclusive",
                    }
                )
            )
            return 2
        args.host_evidence = None
    try:
        result = run(args)
    except (
        CoordinatorBlocked,
        PacketError,
        ResultValidationError,
        ResolutionStateError,
        RoutingError,
    ) as exc:
        code = getattr(exc, "reason_code", "COORDINATOR_BLOCKED")
        blocked = {
            "schema_version": RESULT_VERSION,
            "gate": "BLOCKED",
            "reason_codes": [str(code)],
            "message": str(exc),
        }
        details = getattr(exc, "details", None)
        if isinstance(details, dict) and details:
            blocked["details"] = details
        print(canonical_json(blocked))
        return 2
    print(canonical_json(result))
    return {"PASS": 0, "CHANGES_REQUIRED": 1, "BLOCKED": 2}[result["gate"]]


if __name__ == "__main__":
    raise SystemExit(main())
