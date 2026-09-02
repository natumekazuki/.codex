#!/usr/bin/env python3
"""Build deterministic packets for the two-phase test-value review workflow."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from extract_test_values import validate_metadata
from review_routing import RoutingError, validate_routing_manifest
from validate_review_result import (
    ALIGNMENT_RECORD_KEYS,
    SOURCE_KEYS,
    ResultValidationError,
    result_hash,
    validate_alignment_packet,
    validate_phase_result,
)


class PacketError(ValueError):
    """Raised when extractor or review input cannot form a trusted packet."""


EXTRACTOR_RESULT_KEYS = {
    "schema_version",
    "adapter",
    "coverage",
    "repository_root",
    "tests",
    "diagnostics",
}
EXTRACTOR_RECORD_KEYS = {"source", "metadata", "source_text", "source_hash", "metadata_hash"}
def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_text(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def record_id_for(record: dict[str, Any]) -> str:
    source = _object(record.get("source"), "record.source")
    locator = {
        "path": _string(source.get("path"), "record.source.path"),
        "declaration_start_line": _positive_int(
            source.get("declaration_start_line"),
            "record.source.declaration_start_line",
        ),
    }
    metadata_hash = _hash(record.get("metadata_hash"), "record.metadata_hash")
    return sha256_text(canonical_json({"locator": locator, "metadata_hash": metadata_hash}))


def build_metadata_packet(extractor_result: dict[str, Any]) -> dict[str, Any]:
    records = _extract_records(extractor_result)
    packet_records = []
    for record in records:
        metadata = _object(record.get("metadata"), "record.metadata")
        metadata_errors = validate_metadata(metadata)
        if metadata_errors:
            raise PacketError("record.metadata is invalid: " + "; ".join(metadata_errors))
        metadata_hash = _hash(record.get("metadata_hash"), "record.metadata_hash")
        if sha256_text(canonical_json(metadata)) != metadata_hash:
            raise PacketError("record.metadata_hash does not match canonical metadata")
        packet_records.append(
            {
                "record_id": record_id_for(record),
                "metadata_format_version": 1,
                "metadata": metadata,
                "metadata_hash": metadata_hash,
            }
        )
    _require_unique(packet_records, "record_id")
    return {
        "review_contract_version": "metadata-review-v1",
        "records": packet_records,
    }


def build_alignment_packet(
    extractor_result: dict[str, Any], metadata_result: dict[str, Any]
) -> dict[str, Any]:
    metadata_packet = build_metadata_packet(extractor_result)
    try:
        metadata_reviews = validate_phase_result(
            "metadata", metadata_result, metadata_packet["records"]
        )["reviews"]
    except ResultValidationError as exc:
        raise PacketError(str(exc)) from exc
    review_by_id = {item["record_id"]: item for item in metadata_reviews}
    extractor_records = _extract_records(extractor_result)
    records_by_id = {record_id_for(item): item for item in extractor_records}
    packet_records = []
    for metadata_record in metadata_packet["records"]:
        record_id = metadata_record["record_id"]
        source_record = records_by_id[record_id]
        source_text = _string(source_record.get("source_text"), "record.source_text")
        source_hash = _hash(source_record.get("source_hash"), "record.source_hash")
        if sha256_text(source_text) != source_hash:
            raise PacketError("record.source_hash does not match source_text")
        packet_records.append(
            {
                **metadata_record,
                "metadata_review": review_by_id[record_id],
                "source": _object(source_record.get("source"), "record.source"),
                "source_text": source_text,
                "source_hash": source_hash,
                "adapter": _string(extractor_result.get("adapter"), "extractor.adapter"),
                "coverage": _string(extractor_result.get("coverage"), "extractor.coverage"),
            }
        )
    packet = {
        "review_contract_version": "alignment-review-v1",
        "metadata_result_hash": result_hash(metadata_result),
        "records": packet_records,
    }
    try:
        validate_alignment_packet(packet, metadata_result)
    except ResultValidationError as exc:
        raise PacketError(str(exc)) from exc
    return packet


def build_deep_packet(
    alignment_packet: dict[str, Any],
    metadata_result: dict[str, Any],
    alignment_result: dict[str, Any],
    routing_manifest: dict[str, Any],
    workflow_routing_context: dict[str, Any],
    context_by_record: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    try:
        records = validate_alignment_packet(alignment_packet, metadata_result)
    except ResultValidationError as exc:
        raise PacketError(str(exc)) from exc
    if not isinstance(context_by_record, dict):
        raise PacketError("context_by_record must be an object")
    record_ids = []
    for record in records:
        record_ids.append(_string(record.get("record_id"), "record.record_id"))
    if len(record_ids) != len(set(record_ids)):
        raise PacketError("alignment packet contains duplicate record_id")
    if not set(context_by_record).issubset(set(record_ids)):
        raise PacketError("context contains a record outside the alignment packet")
    try:
        alignment_reviews = validate_phase_result(
            "alignment", alignment_result, records
        )["reviews"]
    except ResultValidationError as exc:
        raise PacketError(str(exc)) from exc
    alignment_by_id = {item["record_id"]: item for item in alignment_reviews}
    try:
        routing_entries = validate_routing_manifest(
            records, alignment_reviews, routing_manifest, workflow_routing_context
        )
    except RoutingError as exc:
        raise PacketError(str(exc)) from exc
    routing_by_id = {item["record_id"]: item for item in routing_entries}
    deep_records = []
    for record in records:
        record_id = record["record_id"]
        route = routing_by_id[record_id]["result"]
        if not route["required"]:
            continue
        contexts = context_by_record.get(record_id, [])
        validated_context = [_validate_context(item) for item in contexts]
        deep_records.append(
            {
                "record_id": record["record_id"],
                "metadata_format_version": record["metadata_format_version"],
                "metadata": record["metadata"],
                "metadata_hash": record["metadata_hash"],
                "metadata_review": record["metadata_review"],
                "source": record["source"],
                "source_text": record["source_text"],
                "source_hash": record["source_hash"],
                "adapter": record["adapter"],
                "coverage": record["coverage"],
                "alignment_review": alignment_by_id[record_id],
                "routing_reasons": route["reasons"],
                "risk_tags": route["risk_tags"],
                "audit_selected": route["audit_selected"],
                "context": validated_context,
                "included_scope": [item["ref"] for item in validated_context],
                "excluded_scope": ["packet外のrepository source"],
            }
        )
    packet = {
        "review_contract_version": "deep-review-v1",
        "metadata_result_hash": alignment_packet["metadata_result_hash"],
        "records": deep_records,
    }
    return {**packet, "input_hash": result_hash(packet)}


def _extract_records(extractor_result: dict[str, Any]) -> list[dict[str, Any]]:
    if set(extractor_result) != EXTRACTOR_RESULT_KEYS:
        raise PacketError("extractor result has unexpected keys")
    if extractor_result.get("schema_version") != 1:
        raise PacketError("extractor schema_version must be 1")
    diagnostics = extractor_result.get("diagnostics")
    if diagnostics != []:
        raise PacketError("extractor result must have no diagnostics")
    records = extractor_result.get("tests")
    if not isinstance(records, list):
        raise PacketError("extractor tests must be an array")
    for record in records:
        if not isinstance(record, dict) or set(record) != EXTRACTOR_RECORD_KEYS:
            raise PacketError("extractor test record has unexpected keys")
    locators = []
    for record in records:
        source = _object(record.get("source"), "record.source")
        if set(source) != SOURCE_KEYS:
            raise PacketError("record.source has unexpected keys")
        locators.append(
            (
                _string(source.get("path"), "record.source.path"),
                _positive_int(
                    source.get("declaration_start_line"),
                    "record.source.declaration_start_line",
                ),
            )
        )
    if len(locators) != len(set(locators)):
        raise PacketError("extractor result contains duplicate record locator")
    return records


def _validate_context(item: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(item, dict) or set(item) != {"kind", "ref", "content", "content_hash"}:
        raise PacketError("deep-review context item has unexpected keys")
    kind = _string(item["kind"], "context.kind")
    ref = _string(item["ref"], "context.ref")
    content = _string(item["content"], "context.content")
    content_hash = _hash(item["content_hash"], "context.content_hash")
    if sha256_text(content) != content_hash:
        raise PacketError(f"context hash does not match content for {ref}")
    return {"kind": kind, "ref": ref, "content": content, "content_hash": content_hash}


def _require_unique(items: list[dict[str, Any]], key: str) -> None:
    values = [item[key] for item in items]
    if len(values) != len(set(values)):
        raise PacketError(f"duplicate {key}")


def _object(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise PacketError(f"{name} must be an object")
    return value


def _string(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise PacketError(f"{name} must be a non-empty string")
    return value


def _positive_int(value: Any, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise PacketError(f"{name} must be a positive integer")
    return value


def _hash(value: Any, name: str) -> str:
    text = _string(value, name)
    if len(text) != 71 or not text.startswith("sha256:"):
        raise PacketError(f"{name} must be a sha256 hash")
    try:
        int(text[7:], 16)
    except ValueError as exc:
        raise PacketError(f"{name} must be a sha256 hash") from exc
    return text


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise PacketError(f"{path} must contain a JSON object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="phase", required=True)
    metadata = subparsers.add_parser("metadata")
    metadata.add_argument("--extractor", type=Path, required=True)
    alignment = subparsers.add_parser("alignment")
    alignment.add_argument("--extractor", type=Path, required=True)
    alignment.add_argument("--metadata-result", type=Path, required=True)
    deep = subparsers.add_parser("deep")
    deep.add_argument("--alignment-packet", type=Path, required=True)
    deep.add_argument("--metadata-result", type=Path, required=True)
    deep.add_argument("--alignment-result", type=Path, required=True)
    deep.add_argument("--routing", type=Path, required=True)
    deep.add_argument("--routing-context", type=Path, required=True)
    deep.add_argument("--context", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.phase == "metadata":
            packet = build_metadata_packet(_read_json(args.extractor))
        elif args.phase == "alignment":
            packet = build_alignment_packet(
                _read_json(args.extractor), _read_json(args.metadata_result)
            )
        else:
            packet = build_deep_packet(
                _read_json(args.alignment_packet),
                _read_json(args.metadata_result),
                _read_json(args.alignment_result),
                _read_json(args.routing),
                _read_json(args.routing_context),
                _read_json(args.context),
            )
    except (OSError, json.JSONDecodeError, PacketError) as exc:
        parser.error(str(exc))
    print(json.dumps(packet, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
