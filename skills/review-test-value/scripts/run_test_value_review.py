#!/usr/bin/env python3
"""Git selection -> closed inputs -> one call per batch -> host-owned gate."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import math
from pathlib import Path
import threading
from typing import Any, Callable

from build_review_packets import (digest, input_identity, make_batches, model_input,
                                  review_material, selected_records)
from extract_test_values import (ADAPTER_PROFILES, diagnostic, extract_source_text,
                                 public_diagnostic, canonical_json)
from git_diff_selection import changed_files, select_git
from review_resolution import (Target, aggregate_gate, bounded_context, load_state,
                               record_gate, retention_basis, save_state, state_lock,
                               supported_refs)
from validate_review_result import CONTRACT_VERSION, ReviewError, bind_response, parse_json

HOST_VERSION = "test-value-host-v3"
RISK_TAGS = {"security", "authentication", "authorization", "privacy", "billing", "irreversible-data-loss"}
STATE_IDENTITY_KEYS = ("record_id", "source_hash", "metadata_hash", "locator", "adapter", "change_kind")


def extract(target: Target) -> list[dict[str, Any]]:
    results = []
    for profile in ADAPTER_PROFILES:
        try:
            value = select_git(target.root, target.base, profile, extract_source_text,
                               diagnostic, public_diagnostic, target.mode, target.head)
        except (OSError, ValueError, RuntimeError) as exc:
            raise ReviewError("extraction", "EXTRACTION_FAILED") from exc
        if value["diagnostics"]:
            raise ReviewError("extraction", value["diagnostics"][0]["code"])
        results.append(value)
    return selected_records(results)


def selection_hash(records: list[dict[str, Any]]) -> str:
    return digest([{k: r[k] for k in STATE_IDENTITY_KEYS} for r in records])


def evidence_template(records: list[dict[str, Any]], task_id: str, snapshot: str) -> dict[str, Any]:
    return {
        "contract_version": HOST_VERSION, "task_id": task_id,
        "selection_hash": selection_hash(records), "snapshot_hash": snapshot,
        "risk_context": {"tags": [], "summary": "", "context": []},
        "records": [{"record_id": r["record_id"], "context": [],
                     "retention": {"basis": "UNRESOLVED", "reason": "", "evidence_refs": [], "temporal": None},
                     "resolution": None} for r in records],
        "historical_resolutions": [], "supersessions": [],
    }


def build_inputs(target: Target, records: list[dict[str, Any]], raw: Any,
                 task_id: str, snapshot: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    required = {"contract_version", "task_id", "selection_hash", "snapshot_hash", "risk_context",
                "records", "historical_resolutions", "supersessions"}
    if (not isinstance(raw, dict) or set(raw) != required or raw["contract_version"] != HOST_VERSION
            or raw["task_id"] != task_id or raw["selection_hash"] != selection_hash(records)
            or raw["snapshot_hash"] != snapshot):
        raise ReviewError("input", "HOST_INPUT_IDENTITY")
    risk = raw["risk_context"]
    if (not isinstance(risk, dict) or set(risk) != {"tags", "summary", "context"}
            or not isinstance(risk["tags"], list)
            or any(not isinstance(t, str) or t not in RISK_TAGS for t in risk["tags"])
            or not isinstance(risk["summary"], str) or not risk["summary"].strip()):
        raise ReviewError("input", "PARENT_RISK_UNASSESSED")
    shared_context = bounded_context(target, risk["context"])
    if (not isinstance(raw["records"], list)
            or [x.get("record_id") for x in raw["records"] if isinstance(x, dict)]
            != [r["record_id"] for r in records]):
        raise ReviewError("input", "HOST_RECORD_SET")
    hosts = {}
    prepared = []
    for record, entry in zip(records, raw["records"]):
        if set(entry) != {"record_id", "context", "retention", "resolution"}:
            raise ReviewError("input", "HOST_RECORD_SHAPE", record_id=record["record_id"])
        context = [*shared_context, *bounded_context(target, entry["context"])]
        if len({x["ref"] for x in context}) != len(context):
            raise ReviewError("input", "CONTEXT_DUPLICATE", record_id=record["record_id"])
        host = {"context": context, "retention": entry["retention"], "resolution": entry["resolution"]}
        basis = retention_basis(host["retention"], context)
        risk_material = {"tags": sorted(set(risk["tags"]) | set(record["metadata"].get("risk_tags", []))),
                         "summary": risk["summary"]}
        if record["metadata"]["kind"] == "security" and "security" not in risk_material["tags"]:
            risk_material["tags"].append("security")
            risk_material["tags"].sort()
        status = {"state": "ABSENT" if record["change_kind"] == "DELETED" else "PRESENT",
                  "lifecycle": record["metadata"]["lifecycle"], "retention_basis": basis,
                  "retention_reason": host["retention"]["reason"],
                  "temporal_observation": host["retention"]["temporal"],
                  "resolution": ({key: host["resolution"].get(key)
                                  for key in ("action", "reason_kind", "reason")}
                                 if isinstance(host["resolution"], dict) else None)}
        prepared.append({**record, "material": review_material(record, context, risk_material, status)})
        hosts[record["record_id"]] = host
    for name in ("historical_resolutions", "supersessions"):
        if not isinstance(raw[name], list):
            raise ReviewError("input", "HOST_HISTORY_SHAPE")
    return prepared, hosts


def _absent(target: Target, identity: dict[str, Any], current: list[dict[str, Any]]) -> bool:
    # A rename or a rewritten declaration is not evidence of removal.
    if any(r["change_kind"] != "DELETED" and r["source_hash"] == identity["source_hash"] for r in current):
        return False
    relative = identity["locator"]["path"]
    paths = {relative}
    for change in changed_files(target.root, target.base, target.mode, target.head):
        if change.old_path == relative:
            paths.add(change.path)
    profile = next(p for p in ADAPTER_PROFILES if p.adapter == identity["adapter"])
    for path in paths:
        text = target.read(path)
        if text is None:
            continue
        candidates, diagnostics = extract_source_text(text, path, profile)
        if any(d["code"] in {"SOURCE_SYNTAX_ERROR", "TEST_DECLARATION_UNSUPPORTED"} for d in diagnostics):
            return False
        if any(r["source_hash"] == identity["source_hash"] or
               r["source"]["symbol"] == identity["locator"]["symbol"] for r in candidates):
            return False
    return True


def final_result(target: Target, state: dict[str, Any], records: list[dict[str, Any]],
                 hosts: dict[str, Any], raw: dict[str, Any], snapshot: str,
                 calls: int) -> dict[str, Any]:
    today = datetime.now(timezone.utc).date()
    current = {r["lineage_id"]: r for r in records}
    by_id = {r["record_id"]: r for r in records}
    outcomes = []
    for record in records:
        saved = state["records"][record["lineage_id"]]
        review = saved["review"]
        if review is None:
            gate, reason = "BLOCKED", "BATCH_FAILED"
        else:
            gate, reason = record_gate(record, review["verdict"], hosts[record["record_id"]], target, snapshot, today)
        saved["gate"] = gate
        outcomes.append({**saved["identity"], **(review or {}), "gate": gate,
                         "reason_code": reason, "failure": saved["failure"]})
    current_outcomes = {o["record_id"]: o for o in outcomes}
    historical = {e["identity"]["record_id"]: e for key, e in state["records"].items() if key not in current}
    resolutions = {}
    for entry in raw["historical_resolutions"]:
        if (not isinstance(entry, dict) or set(entry) != {"record_id", "context", "retention", "resolution"}
                or entry["record_id"] not in historical or entry["record_id"] in resolutions):
            raise ReviewError("retention_resolution", "HISTORICAL_RESOLUTION_IDENTITY")
        resolutions[entry["record_id"]] = entry
    supersessions = {}
    for entry in raw["supersessions"]:
        if (not isinstance(entry, dict) or set(entry) != {"old_record_id", "current_record_id", "reason", "evidence_refs"}
                or entry["old_record_id"] not in historical or entry["old_record_id"] in supersessions
                or entry["current_record_id"] not in by_id or not isinstance(entry["reason"], str)
                or not entry["reason"].strip()
                or not supported_refs(entry["evidence_refs"], hosts[entry["current_record_id"]]["context"])):
            raise ReviewError("retention_resolution", "SUPERSESSION_UNVERIFIED")
        supersessions[entry["old_record_id"]] = entry["current_record_id"]
    for record_id, saved in historical.items():
        review = saved["review"]
        gate = "BLOCKED"
        reason = "HISTORICAL_REVIEW_REQUIRED"
        replacement = supersessions.get(record_id)
        if replacement is not None and current_outcomes[replacement]["gate"] == "PASS":
            gate, reason = "PASS", None
        elif review is not None and review["verdict"] in {"DROP", "MOVE_TO_POLICY_CHECK"}:
            entry = resolutions.get(record_id)
            if entry is not None and _absent(target, saved["identity"], records):
                host = {**entry, "context": bounded_context(target, entry["context"])}
                gate, reason = record_gate({**saved["identity"], "change_kind": "DELETED"},
                                           review["verdict"], host, target, snapshot, today)
            else:
                gate, reason = "CHANGES_REQUIRED", "RESOLUTION_REQUIRED"
        elif review is not None and review["verdict"] == "REDESIGN":
            gate, reason = "CHANGES_REQUIRED", "HISTORICAL_REDESIGN"
        saved["gate"] = gate
        outcomes.append({**saved["identity"], **(review or {}), "gate": gate,
                         "reason_code": reason, "failure": saved["failure"]})
    return {"contract_version": CONTRACT_VERSION, "snapshot_hash": snapshot,
            "gate": aggregate_gate([x["gate"] for x in outcomes]), "records": outcomes,
            "llm_batch_calls": calls,
            "reason_codes": [] if outcomes else ["EMPTY_SELECTION"]}


def host_implementation_identity() -> str:
    return digest([(p, digest((Path(__file__).parent / p).read_text(encoding="utf-8")))
                   for p in ("build_review_packets.py", "validate_review_result.py",
                             "review_resolution.py", "run_test_value_review.py",
                             "extract_test_values.py", "git_diff_selection.py")])


def run(args: argparse.Namespace, *, worker: Callable | None = None,
        preparer: Callable | None = None) -> dict[str, Any]:
    from review_worker import execute_review, prepare_worker
    worker = worker or execute_review
    preparer = preparer or prepare_worker
    if (type(args.batch_size) is not int or not 1 <= args.batch_size <= 100
            or type(args.max_workers) is not int or not 1 <= args.max_workers <= 8
            or not math.isfinite(args.timeout_seconds) or not 10 <= args.timeout_seconds <= 1800):
        raise ReviewError("input", "EXECUTION_BUDGET_INVALID")
    mode = "staged" if args.staged else "head" if args.head else "working"
    target = Target(args.root, args.changed_from, mode, args.head)
    directory = args.state_dir.resolve(strict=True)
    if directory.is_relative_to(target.root):
        raise ReviewError("input", "STATE_INSIDE_TARGET")
    snapshot = target.snapshot()
    records = extract(target)
    if target.snapshot() != snapshot:
        raise ReviewError("input", "SNAPSHOT_CHANGED")
    if args.prepare:
        return {"contract_version": CONTRACT_VERSION, "gate": "BLOCKED",
                "reason_codes": ["HOST_EVIDENCE_REQUIRED"],
                "selection": [{k: r[k] for k in STATE_IDENTITY_KEYS} for r in records],
                "host_evidence_template": evidence_template(records, args.task_id, snapshot)}
    if args.host_evidence is None:
        raise ReviewError("input", "HOST_EVIDENCE_REQUIRED")
    raw = parse_json(args.host_evidence.read_text(encoding="utf-8"), category="input")
    records, hosts = build_inputs(target, records, raw, args.task_id, snapshot)
    owner = {"task_id": args.task_id, "repository_hash": digest(str(target.root)),
             "base": target.base, "mode": target.mode}
    with state_lock(directory) as lock:
        state = load_state(directory, owner, lock)
        if not records and not state["records"]:
            return {"contract_version": CONTRACT_VERSION, "gate": "BLOCKED",
                    "records": [], "reason_codes": ["EMPTY_SELECTION"], "llm_batch_calls": 0}
        role = Path(__file__).resolve().parents[3] / "agents" / "test_value_luna.toml"
        preparation = preparer(cli=args.cli, role_file=str(role)) if records else None
        worker_hash = preparation["identity"] if preparation else ""
        # Invalidate cached classifications when the host implementation changes.
        implementation = host_implementation_identity()
        pending = []
        for record in records:
            record["input_hash"] = input_identity(record, digest([worker_hash, implementation]))
            old = state["records"].get(record["lineage_id"])
            if old is not None and old["input_hash"] == record["input_hash"]:
                if old["review"] is not None or not args.retry_transport:
                    continue
            pending.append(record)
        batches = make_batches(pending, args.batch_size)
        for record in pending:
            state["records"][record["lineage_id"]] = {
                "identity": {k: record[k] for k in STATE_IDENTITY_KEYS},
                "input_hash": record["input_hash"], "review": None, "gate": "BLOCKED",
                "failure": {"category": "transport", "code": "INTERRUPTED_BATCH"},
            }
        save_state(directory, state)
        cancelled = threading.Event()
        calls = 0
        pool = ThreadPoolExecutor(max_workers=args.max_workers)
        futures = {}
        try:
            for index, batch in enumerate(batches):
                futures[pool.submit(worker, model_input(batch), preparation=preparation,
                                    timeout_seconds=args.timeout_seconds, cancel=cancelled)] = (index, batch)
                calls += 1
            for future in as_completed(futures):
                index, batch = futures[future]
                try:
                    response = future.result()
                    canonical = bind_response(response, batch)
                    for record, review in zip(batch, canonical):
                        state["records"][record["lineage_id"]].update(
                            review={key: review[key] for key in ("verdict", "summary", "findings", "context_request")},
                            failure=None,
                        )
                except ReviewError as exc:
                    failure = {**exc.diagnostic(), "batch_index": index}
                    for record in batch:
                        state["records"][record["lineage_id"]]["failure"] = failure
                except Exception as exc:
                    # An implementation/transport exception is never a semantic verdict.
                    failure = {"category": "transport", "code": "UNEXPECTED_WORKER_FAILURE", "batch_index": index}
                    for record in batch:
                        state["records"][record["lineage_id"]]["failure"] = failure
                save_state(directory, state)
        except BaseException:
            cancelled.set()
            for future in futures:
                future.cancel()
            raise
        finally:
            pool.shutdown(wait=True, cancel_futures=True)
        if target.snapshot() != snapshot:
            raise ReviewError("input", "SNAPSHOT_CHANGED")
        rebuilt, _ = build_inputs(target, records, raw, args.task_id, snapshot)
        if [r["material"] for r in rebuilt] != [r["material"] for r in records]:
            raise ReviewError("input", "CONTEXT_CHANGED")
        if host_implementation_identity() != implementation:
            raise ReviewError("input", "HOST_IMPLEMENTATION_CHANGED")
        result = final_result(target, state, records, hosts, raw, snapshot, calls)
        if target.snapshot() != snapshot:
            raise ReviewError("input", "SNAPSHOT_CHANGED")
        save_state(directory, state)
        return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--changed-from", required=True)
    target = parser.add_mutually_exclusive_group()
    target.add_argument("--head")
    target.add_argument("--staged", action="store_true")
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--cli", required=True)
    parser.add_argument("--host-evidence", type=Path)
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--max-workers", type=int, default=2)
    parser.add_argument("--timeout-seconds", type=float, default=900)
    parser.add_argument("--retry-transport", action="store_true",
                        help="Explicitly retry failed transport only; never rerun an unchanged semantic result")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.prepare and args.host_evidence is not None:
            raise ReviewError("input", "PREPARE_WITH_EVIDENCE")
        result = run(args)
    except ReviewError as exc:
        result = {"contract_version": CONTRACT_VERSION, "gate": "BLOCKED", "failure": exc.diagnostic()}
    except KeyboardInterrupt:
        result = {"contract_version": CONTRACT_VERSION, "gate": "BLOCKED",
                  "failure": {"category": "transport", "code": "CANCELLED"}}
    except (OSError, ValueError, KeyError, TypeError, RuntimeError) as exc:
        result = {"contract_version": CONTRACT_VERSION, "gate": "BLOCKED",
                  "failure": {"category": "input", "code": "INPUT_OR_STATE_INVALID"}}
    print(canonical_json(result))
    return {"PASS": 0, "CHANGES_REQUIRED": 1, "BLOCKED": 2}[result["gate"]]


if __name__ == "__main__":
    raise SystemExit(main())
