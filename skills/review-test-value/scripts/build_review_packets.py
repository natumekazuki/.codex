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
    "transitions",
    "diagnostics",
    "warnings",
}
EXTRACTOR_RECORD_KEYS = {
    "source",
    "metadata_format_version",
    "metadata",
    "source_text",
    "source_hash",
    "metadata_hash",
}
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


def deleted_record_id_for(record: dict[str, Any]) -> str:
    source = _object(record.get("source"), "record.source")
    locator = {
        "path": _string(source.get("path"), "record.source.path"),
        "declaration_start_line": _positive_int(
            source.get("declaration_start_line"),
            "record.source.declaration_start_line",
        ),
    }
    source_hash = _hash(record.get("source_hash"), "record.source_hash")
    metadata_hash = _hash(record.get("metadata_hash"), "record.metadata_hash")
    return sha256_text(
        canonical_json(
            {
                "transition": "DELETED",
                "locator": locator,
                "source_hash": source_hash,
                "metadata_hash": metadata_hash,
            }
        )
    )


def build_metadata_packet(extractor_result: dict[str, Any]) -> dict[str, Any]:
    records = _extract_packet_records(extractor_result)
    packet_records = []
    for record, deleted in records:
        metadata = _object(record.get("metadata"), "record.metadata")
        metadata_errors = validate_metadata(metadata, 2)
        if metadata_errors:
            raise PacketError("record.metadata is invalid: " + "; ".join(metadata_errors))
        metadata_hash = _hash(record.get("metadata_hash"), "record.metadata_hash")
        if sha256_text(canonical_json(metadata)) != metadata_hash:
            raise PacketError("record.metadata_hash does not match canonical metadata")
        packet_records.append(
            {
                "record_id": deleted_record_id_for(record) if deleted else record_id_for(record),
                "metadata_format_version": 2,
                "metadata": metadata,
                "metadata_hash": metadata_hash,
            }
        )
    _require_unique(packet_records, "record_id")
    return {
        "review_contract_version": "metadata-review-v2",
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
    extractor_records = _extract_packet_records(extractor_result)
    records_by_id = {
        deleted_record_id_for(item) if deleted else record_id_for(item): item
        for item, deleted in extractor_records
    }
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
        "review_contract_version": "alignment-review-v2",
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
        "review_contract_version": "deep-review-v2",
        "metadata_result_hash": alignment_packet["metadata_result_hash"],
        "records": deep_records,
    }
    return {**packet, "input_hash": result_hash(packet)}


def _extract_packet_records(
    extractor_result: dict[str, Any],
) -> list[tuple[dict[str, Any], bool]]:
    if set(extractor_result) != EXTRACTOR_RESULT_KEYS:
        raise PacketError("extractor result has unexpected keys")
    if extractor_result.get("schema_version") != 2:
        raise PacketError("extractor schema_version must be 2")
    diagnostics = extractor_result.get("diagnostics")
    if diagnostics != []:
        raise PacketError("extractor result must have no diagnostics")
    if not isinstance(extractor_result.get("warnings"), list):
        raise PacketError("extractor warnings must be an array")
    records = extractor_result.get("tests")
    if not isinstance(records, list):
        raise PacketError("extractor tests must be an array")
    for record in records:
        _validate_extractor_record(record, "extractor test record")
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
    transitions = extractor_result.get("transitions")
    if transitions is None:
        return [(record, False) for record in records]
    if not isinstance(transitions, list):
        raise PacketError("extractor transitions must be null or an array")
    before_locators = []
    after_locators = []
    transition_values = []
    packet_records = []
    after_records = []
    for transition in transitions:
        if not isinstance(transition, dict) or set(transition) != {"kind", "before", "after"}:
            raise PacketError("extractor transition has unexpected keys")
        kind = transition["kind"]
        if kind not in {"ADDED", "SURVIVED", "DELETED"}:
            raise PacketError("extractor transition kind is invalid")
        before = transition["before"]
        after = transition["after"]
        if kind == "ADDED":
            if before is not None:
                raise PacketError("ADDED transition before must be null")
            _validate_extractor_record(after, "ADDED transition after")
            packet_records.append((after, False))
            after_records.append(after)
        elif kind == "SURVIVED":
            _validate_extractor_record(before, "SURVIVED transition before")
            _validate_extractor_record(after, "SURVIVED transition after")
            packet_records.append((after, False))
            after_records.append(after)
        else:
            _validate_extractor_record(before, "DELETED transition before")
            packet_records.append((before, True))
            if after is not None:
                raise PacketError("DELETED transition after must be null")
        if before is not None:
            before_locators.append(_record_locator(before, "transition.before"))
        if after is not None:
            after_locators.append(_record_locator(after, "transition.after"))
        transition_values.append(canonical_json(transition))
    if len(before_locators) != len(set(before_locators)):
        raise PacketError("extractor transitions contain duplicate before locator")
    if len(after_locators) != len(set(after_locators)):
        raise PacketError("extractor transitions contain duplicate after locator")
    if len(transition_values) != len(set(transition_values)):
        raise PacketError("extractor transitions contain a duplicate transition")
    if after_records != records:
        raise PacketError("transition after records do not match extractor tests")
    return packet_records


def _validate_extractor_record(record: Any, name: str) -> None:
    if not isinstance(record, dict) or set(record) != EXTRACTOR_RECORD_KEYS:
        raise PacketError(f"{name} has unexpected keys")
    if record["metadata_format_version"] != 2:
        raise PacketError(f"{name} metadata_format_version must be 2")
    source = _object(record.get("source"), f"{name}.source")
    if set(source) != SOURCE_KEYS:
        raise PacketError(f"{name}.source has unexpected keys")
    _string(source.get("path"), f"{name}.source.path")
    _positive_int(source.get("declaration_start_line"), f"{name}.source.declaration_start_line")
    _positive_int(source.get("declaration_end_line"), f"{name}.source.declaration_end_line")
    source_text = _string(record.get("source_text"), f"{name}.source_text")
    source_hash = _hash(record.get("source_hash"), f"{name}.source_hash")
    if sha256_text(source_text) != source_hash:
        raise PacketError(f"{name}.source_hash does not match source_text")
    metadata = _object(record.get("metadata"), f"{name}.metadata")
    metadata_errors = validate_metadata(metadata, 2)
    if metadata_errors:
        raise PacketError(f"{name}.metadata is invalid: " + "; ".join(metadata_errors))
    metadata_hash = _hash(record.get("metadata_hash"), f"{name}.metadata_hash")
    if sha256_text(canonical_json(metadata)) != metadata_hash:
        raise PacketError(f"{name}.metadata_hash does not match canonical metadata")


def _record_locator(record: dict[str, Any], name: str) -> tuple[str, int]:
    source = _object(record.get("source"), f"{name}.source")
    return (
        _string(source.get("path"), f"{name}.source.path"),
        _positive_int(
            source.get("declaration_start_line"),
            f"{name}.source.declaration_start_line",
        ),
    )


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
