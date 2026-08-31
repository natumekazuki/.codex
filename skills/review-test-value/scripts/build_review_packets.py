#!/usr/bin/env python3
"""Build deterministic packets for the two-phase test-value review workflow."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from review_routing import RISK_TAGS
from validate_review_result import ResultValidationError, validate_phase_result


class PacketError(ValueError):
    """Raised when extractor or review input cannot form a trusted packet."""


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
    return {
        "review_contract_version": "alignment-review-v1",
        "records": packet_records,
    }


def build_deep_packet(
    alignment_packet: dict[str, Any],
    alignment_result: dict[str, Any],
    routing: dict[str, Any],
    context_by_record: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    if alignment_packet.get("review_contract_version") != "alignment-review-v1":
        raise PacketError("alignment packet contract version is invalid")
    records = alignment_packet.get("records")
    if not isinstance(records, list):
        raise PacketError("alignment packet records must be an array")
    record_ids = [_string(item.get("record_id"), "record.record_id") for item in records]
    if len(record_ids) != len(set(record_ids)):
        raise PacketError("alignment packet contains duplicate record_id")
    if set(routing) != set(record_ids):
        raise PacketError("routing record set does not match the alignment packet")
    if not set(context_by_record).issubset(set(record_ids)):
        raise PacketError("context contains a record outside the alignment packet")
    for record in records:
        metadata = _object(record.get("metadata"), "record.metadata")
        metadata_hash = _hash(record.get("metadata_hash"), "record.metadata_hash")
        source_text = _string(record.get("source_text"), "record.source_text")
        source_hash = _hash(record.get("source_hash"), "record.source_hash")
        if sha256_text(canonical_json(metadata)) != metadata_hash:
            raise PacketError("alignment packet metadata_hash does not match metadata")
        if sha256_text(source_text) != source_hash:
            raise PacketError("alignment packet source_hash does not match source_text")
    try:
        alignment_reviews = validate_phase_result(
            "alignment", alignment_result, records
        )["reviews"]
    except ResultValidationError as exc:
        raise PacketError(str(exc)) from exc
    alignment_by_id = {item["record_id"]: item for item in alignment_reviews}
    deep_records = []
    for record in records:
        record_id = record["record_id"]
        route = routing.get(record_id)
        if route is None:
            raise PacketError(f"routing is missing record {record_id}")
        if not isinstance(route, dict) or set(route) != {
            "required",
            "reasons",
            "risk_tags",
            "audit_selected",
        }:
            raise PacketError(f"routing entry is invalid for record {record_id}")
        if not isinstance(route["required"], bool) or not isinstance(route["audit_selected"], bool):
            raise PacketError(f"routing booleans are invalid for record {record_id}")
        _string_list(route["reasons"], f"routing reasons for {record_id}")
        risk_tags = _string_list(route["risk_tags"], f"routing risk_tags for {record_id}")
        if set(risk_tags) - RISK_TAGS:
            raise PacketError(f"routing risk_tags are invalid for record {record_id}")
        if route["required"] != bool(route["reasons"]):
            raise PacketError(f"routing required flag is inconsistent for record {record_id}")
        if not route["required"]:
            continue
        contexts = context_by_record.get(record_id, [])
        validated_context = [_validate_context(item) for item in contexts]
        deep_records.append(
            {
                **record,
                "alignment_review": alignment_by_id[record_id],
                "routing_reasons": route["reasons"],
                "risk_tags": route["risk_tags"],
                "audit_selected": route["audit_selected"],
                "context": validated_context,
                "included_scope": [item["ref"] for item in validated_context],
                "excluded_scope": ["packet外のrepository source"],
            }
        )
    return {"review_contract_version": "deep-review-v1", "records": deep_records}


def _extract_records(extractor_result: dict[str, Any]) -> list[dict[str, Any]]:
    if extractor_result.get("schema_version") != 1:
        raise PacketError("extractor schema_version must be 1")
    diagnostics = extractor_result.get("diagnostics")
    if diagnostics != []:
        raise PacketError("extractor result must have no diagnostics")
    records = extractor_result.get("tests")
    if not isinstance(records, list):
        raise PacketError("extractor tests must be an array")
    for record in records:
        if not isinstance(record, dict):
            raise PacketError("extractor test record must be an object")
    locators = []
    for record in records:
        source = _object(record.get("source"), "record.source")
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


def _string_list(value: Any, name: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
        raise PacketError(f"{name} must be an array of non-empty strings")
    return value


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
    deep.add_argument("--alignment-result", type=Path, required=True)
    deep.add_argument("--routing", type=Path, required=True)
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
                _read_json(args.alignment_result),
                _read_json(args.routing),
                _read_json(args.context),
            )
    except (OSError, json.JSONDecodeError, PacketError) as exc:
        parser.error(str(exc))
    print(json.dumps(packet, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
