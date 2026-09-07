"""Deterministic selection identities and a single bounded review input."""
from __future__ import annotations

from typing import Any

from extract_test_values import ADAPTER_PROFILES, canonical_json, sha256_text, validate_metadata
from validate_review_result import CONTRACT_VERSION, ReviewError


def digest(value: Any) -> str:
    return sha256_text(canonical_json(value))


def selected_records(extractors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    expected = {p.adapter: p.coverage for p in ADAPTER_PROFILES}
    if {x.get("adapter") for x in extractors} != set(expected) or len(extractors) != len(expected):
        raise ReviewError("extraction", "ADAPTER_SET")
    records = []
    for result in extractors:
        adapter = result["adapter"]
        if (result.get("schema_version") != 2 or result.get("diagnostics") != []
                or result.get("coverage") != expected[adapter]
                or not isinstance(result.get("transitions"), list)):
            raise ReviewError("extraction", "EXTRACTION_INCOMPLETE")
        afters = []
        for transition in result["transitions"]:
            if set(transition) != {"kind", "before", "after"}:
                raise ReviewError("extraction", "TRANSITION_SHAPE")
            kind, before, after = (transition[k] for k in ("kind", "before", "after"))
            if kind not in {"ADDED", "SURVIVED", "DELETED"}:
                raise ReviewError("extraction", "TRANSITION_KIND")
            if ((kind == "ADDED" and before is not None)
                    or (kind == "DELETED" and after is not None)
                    or (kind == "SURVIVED" and before is None)):
                raise ReviewError("extraction", "TRANSITION_SHAPE")
            source_record = before if kind == "DELETED" else after
            if not isinstance(source_record, dict):
                raise ReviewError("extraction", "RECORD_MISSING")
            metadata = source_record.get("metadata")
            version = source_record.get("metadata_format_version")
            if (version not in ({1, 2} if kind == "DELETED" else {2})
                    or validate_metadata(metadata, version)):
                raise ReviewError("extraction", "METADATA_INVALID")
            source = source_record.get("source")
            text = source_record.get("source_text")
            if (not isinstance(source, dict) or not isinstance(text, str)
                    or source_record.get("source_hash") != sha256_text(text)
                    or source_record.get("metadata_hash") != digest(metadata)):
                raise ReviewError("extraction", "RECORD_HASH_MISMATCH")
            locator = {k: source[k] for k in ("path", "symbol", "declaration_start_line", "declaration_end_line")}
            if (not all(isinstance(locator[k], str) and locator[k] for k in ("path", "symbol"))
                    or type(locator["declaration_start_line"]) is not int
                    or type(locator["declaration_end_line"]) is not int
                    or not 1 <= locator["declaration_start_line"] <= locator["declaration_end_line"]):
                raise ReviewError("extraction", "LOCATOR_INVALID")
            identity = {"adapter": adapter, "locator": locator, "change_kind": kind,
                        "source_hash": source_record["source_hash"],
                        "metadata_hash": source_record["metadata_hash"]}
            # A base record is a stable lineage across a repair and later
            # deletion. Added records have no invented base identity.
            origin = before if before is not None else source_record
            lineage = {"adapter": adapter, "base_record": before is not None,
                       "path": origin["source"]["path"],
                       "symbol": origin["source"]["symbol"],
                       "line": origin["source"]["declaration_start_line"]}
            if before is not None:
                lineage["source_hash"] = before["source_hash"]
                lineage["metadata_hash"] = before["metadata_hash"]
            records.append({**identity, "record_id": digest(identity), "lineage_id": digest(lineage),
                            "metadata_format_version": version, "metadata": metadata,
                            "source_text": text})
            if after is not None:
                afters.append(after)
        if afters != result.get("tests"):
            raise ReviewError("extraction", "SURVIVING_RECORD_SET")
    records.sort(key=lambda r: (r["locator"]["path"], r["locator"]["declaration_start_line"], r["change_kind"]))
    for name in ("record_id", "lineage_id"):
        if len({r[name] for r in records}) != len(records):
            raise ReviewError("extraction", "AMBIGUOUS_RECORD_IDENTITY")
    return records


def review_material(record: dict[str, Any], context: list[dict[str, Any]],
                    risk: dict[str, Any], host_status: dict[str, Any]) -> dict[str, Any]:
    return {
        "metadata": record["metadata"],
        "metadata_format": record["metadata_format_version"],
        "test_source": record["source_text"],
        "locator": record["locator"],
        "change_kind": record["change_kind"],
        "context": [{"kind": x["kind"], "ref": x["ref"], "content": x["content"]} for x in context],
        "risk_context": risk,
        "artifact": host_status,
    }


def make_batches(records: list[dict[str, Any]], batch_size: int,
                 max_chars: int = 800_000) -> list[list[dict[str, Any]]]:
    if type(batch_size) is not int or not 1 <= batch_size <= 100:
        raise ReviewError("input", "INVALID_BATCH_SIZE")
    batches = [records[i:i + batch_size] for i in range(0, len(records), batch_size)]
    for index, batch in enumerate(batches):
        if len(canonical_json(model_input(batch))) > max_chars:
            raise ReviewError("input", "BATCH_INPUT_TOO_LARGE", batch_index=index)
    return batches


def model_input(records: list[dict[str, Any]]) -> dict[str, Any]:
    return {"records": [{"ordinal": i, **record["material"]} for i, record in enumerate(records)]}


def input_identity(record: dict[str, Any], worker_identity: str) -> str:
    return digest({"contract_version": CONTRACT_VERSION, "worker": worker_identity,
                   "material": record["material"]})
