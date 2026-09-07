#!/usr/bin/env python3
"""Project canonical review packets into model transport and bind results on host.

Canonical packets are host-owned artifacts.  This module deliberately keeps their
identity and hash fields out of the model transport, then reconstructs the
canonical result after validating only per-batch ordinals and semantic fields.
It has no dependency on the native worker so it can be used by worker tests and
by the coordinator without creating an import cycle.
"""

from __future__ import annotations

import copy
from typing import Any

from validate_review_result import (
    ALIGNMENT_RECORD_KEYS,
    DEEP_RECORD_KEYS,
    PHASE_SPECS,
    ResultValidationError,
    phase_result_schema,
    validate_phase_result,
)


class TransportError(ResultValidationError):
    """Raised when a model projection or host binding is not trustworthy."""


# These names are generated and owned by the host.  A nested frozen review may
# contain any of them, so projection removes them recursively.  Semantic text
# values are left unchanged, including user-authored SHA-256-looking strings.
_HOST_IDENTITY_KEYS = {
    "record_id",
    "review_contract_version",
    "metadata_result_hash",
    "input_hash",
    "metadata_hash",
    "source_hash",
    "content_hash",
}

_PHASE_PACKET_KEYS = {
    "metadata": {"review_contract_version", "records"},
    "alignment": {"review_contract_version", "metadata_result_hash", "records"},
    "deep": {
        "review_contract_version",
        "metadata_result_hash",
        "records",
        "input_hash",
    },
}
_PHASE_RECORD_KEYS = {
    "metadata": {"record_id", "metadata_format_version", "metadata", "metadata_hash"},
    "alignment": ALIGNMENT_RECORD_KEYS,
    "deep": DEEP_RECORD_KEYS,
}


def model_packet(phase: str, canonical_packet: dict[str, Any]) -> dict[str, Any]:
    """Return the model-visible projection of one canonical phase packet.

    The returned object contains only ``records``.  Each record has a zero-based
    ``ordinal`` and semantic review input.  Metadata deliberately contains no
    source locator; alignment and deep retain the source/context content needed
    for their respective semantic decisions while removing host identity and
    hash wrappers recursively.
    """

    records = _canonical_records(phase, canonical_packet)
    projected: list[dict[str, Any]] = []
    for ordinal, record in enumerate(records):
        if phase == "metadata":
            projected.append(
                {
                    "ordinal": ordinal,
                    "metadata_format_version": copy.deepcopy(
                        record["metadata_format_version"]
                    ),
                    "metadata": copy.deepcopy(record["metadata"]),
                }
            )
            continue

        item: dict[str, Any] = {
            "ordinal": ordinal,
            "metadata_format_version": copy.deepcopy(record["metadata_format_version"]),
            "metadata": copy.deepcopy(record["metadata"]),
        }
        for key in (
            "metadata_review",
            "source",
            "source_text",
            "adapter",
            "coverage",
        ):
            item[key] = _strip_host_fields(record[key])
        if phase == "deep":
            for key in (
                "alignment_review",
                "routing_reasons",
                "risk_tags",
                "audit_selected",
                "excluded_scope",
            ):
                item[key] = _strip_host_fields(record[key])
            # Context hashes are host bindings. Preserve bounded context kind,
            # ref, and content; result evidence uses a record-local ordinal.
            item["context"] = _project_context(record["context"])
            item["included_scope"] = _strip_host_fields(record["included_scope"])
        projected.append(item)
    return {"records": projected}


def model_result_schema(
    phase: str, canonical_packet: dict[str, Any]
) -> dict[str, Any]:
    """Build a structured-output schema for the projected model result.

    The model returns ``{"reviews": [...]}`` only.  Per-record variants bind
    the ordinal and metadata evidence fields to the corresponding input record;
    deep context evidence is similarly bound to that record's context ordinals.
    """

    records = _canonical_records(phase, canonical_packet)
    base = copy.deepcopy(phase_result_schema(phase))
    base_item = base.get("properties", {}).get("reviews", {}).get("items")
    if not isinstance(base_item, dict):
        raise TransportError("phase result schema has no review item schema")
    base_properties = base_item.get("properties")
    base_required = base_item.get("required")
    if not isinstance(base_properties, dict) or not isinstance(base_required, list):
        raise TransportError("phase result schema review item is invalid")

    # The canonical validator still describes the host-owned identity fields.
    # Remove those properties from the transport schema, then add the ordinal
    # that replaces them as the model's only record binding.
    model_properties = {
        key: value
        for key, value in base_properties.items()
        if key not in _HOST_IDENTITY_KEYS
    }
    model_required = [
        key
        for key in base_required
        if key not in _HOST_IDENTITY_KEYS
    ]
    model_properties["ordinal"] = {"type": "integer"}
    if "ordinal" not in model_required:
        model_required.insert(0, "ordinal")

    generic_item = {
        "type": "object",
        "additionalProperties": False,
        "required": model_required,
        "properties": model_properties,
    }

    variants: list[dict[str, Any]] = []
    for ordinal, record in enumerate(records):
        variant = copy.deepcopy(generic_item)
        variant["properties"]["ordinal"] = {
            "type": "integer",
            "enum": [ordinal],
        }
        if phase == "metadata":
            allowed_fields = _metadata_allowed_fields(record["metadata"])
            evidence = variant["properties"].get("evidence")
            if not isinstance(evidence, dict):
                raise TransportError("metadata schema has no evidence schema")
            evidence_items = evidence.get("items")
            if not isinstance(evidence_items, dict):
                raise TransportError("metadata evidence schema is invalid")
            evidence_properties = evidence_items.get("properties")
            if not isinstance(evidence_properties, dict) or "fields" not in evidence_properties:
                raise TransportError("metadata evidence fields schema is invalid")
            fields_schema = copy.deepcopy(evidence_properties["fields"])
            if not isinstance(fields_schema, dict):
                raise TransportError("metadata evidence fields schema is invalid")
            fields_items = fields_schema.get("items")
            if not isinstance(fields_items, dict):
                raise TransportError("metadata evidence item schema is invalid")
            fields_schema["items"] = {
                "type": "string",
                "enum": sorted(allowed_fields),
            }
            evidence_properties["fields"] = fields_schema
        if phase == "deep":
            _bind_context_schema(variant, record)
        variants.append(variant)

    # Do not expose the canonical contract version or deep input hash to the
    # model.  They are reattached from the frozen packet by canonical_result.
    schema = {
        key: value
        for key, value in base.items()
        if key not in {"title", "required", "properties"}
    }
    schema["title"] = f"{phase} review model result"
    schema["type"] = "object"
    schema["additionalProperties"] = False
    schema["required"] = ["reviews"]
    schema["properties"] = {
        "reviews": {
            "type": "array",
            "items": {"anyOf": variants} if variants else generic_item,
        }
    }
    return schema


def canonical_result(
    phase: str,
    model_result: dict[str, Any],
    canonical_packet: dict[str, Any],
) -> dict[str, Any]:
    """Attach host identity/hash/version bindings and validate the result.

    ``model_result`` must contain exactly one review for every packet record in
    packet order.  Model-supplied identity, hash, contract, and context refs are
    rejected instead of being ignored.  The host then converts deep context
    ordinals to the verified packet ``ref``/``content_hash`` pair and delegates
    all semantic validation to :func:`validate_phase_result`.
    """

    records = _canonical_records(phase, canonical_packet)
    model = _model_result_reviews(phase, model_result, len(records))
    canonical_reviews: list[dict[str, Any]] = []
    for ordinal, (record, review) in enumerate(zip(records, model)):
        bound = _bind_review(phase, record, review)
        canonical_reviews.append(bound)

    result: dict[str, Any] = {
        "review_contract_version": canonical_packet["review_contract_version"],
        "reviews": canonical_reviews,
    }
    if phase == "deep":
        result["input_hash"] = canonical_packet["input_hash"]

    expected_input_hash = canonical_packet.get("input_hash") if phase == "deep" else None
    try:
        validate_phase_result(phase, result, records, expected_input_hash)
    except ResultValidationError as exc:
        raise TransportError(str(exc), getattr(exc, "details", None)) from exc
    return result


def _canonical_records(phase: str, packet: Any) -> list[dict[str, Any]]:
    if phase not in _PHASE_PACKET_KEYS:
        raise TransportError(f"unknown phase: {phase}")
    if not isinstance(packet, dict) or set(packet) != _PHASE_PACKET_KEYS[phase]:
        raise TransportError(f"{phase} canonical packet has unexpected keys")
    version = _phase_version(phase)
    if packet.get("review_contract_version") != version:
        raise TransportError(f"{phase} canonical packet contract version is invalid")
    records = packet.get("records")
    if not isinstance(records, list):
        raise TransportError("canonical packet records must be an array")
    for record in records:
        if not isinstance(record, dict) or set(record) != _PHASE_RECORD_KEYS[phase]:
            raise TransportError(f"{phase} canonical packet record has unexpected keys")
        if phase == "deep":
            _validate_context_shape(record["context"])
    return records


def _phase_version(phase: str) -> str:
    try:
        version = PHASE_SPECS[phase]["version"]
    except KeyError as exc:
        raise TransportError(f"unknown phase: {phase}") from exc
    if not isinstance(version, str) or not version:
        raise TransportError("phase result contract version is invalid")
    return version


def _validate_context_shape(contexts: Any) -> None:
    if not isinstance(contexts, list):
        raise TransportError("deep context must be an array")
    for context in contexts:
        if not isinstance(context, dict) or set(context) != {
            "kind",
            "ref",
            "content",
            "content_hash",
        }:
            raise TransportError("deep context has unexpected keys")


def _strip_host_fields(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _strip_host_fields(item)
            for key, item in value.items()
            if key not in _HOST_IDENTITY_KEYS
            and not (isinstance(key, str) and key.endswith("_hash"))
        }
    if isinstance(value, list):
        return [_strip_host_fields(item) for item in value]
    return copy.deepcopy(value)


def _project_context(contexts: Any) -> list[dict[str, Any]]:
    if not isinstance(contexts, list):
        raise TransportError("deep context must be an array")
    projected = []
    for ordinal, context in enumerate(contexts):
        if not isinstance(context, dict) or set(context) != {
            "kind",
            "ref",
            "content",
            "content_hash",
        }:
            raise TransportError("deep context has unexpected keys")
        projected.append(
            {
                "ordinal": ordinal,
                "kind": copy.deepcopy(context["kind"]),
                "ref": copy.deepcopy(context["ref"]),
                "content": copy.deepcopy(context["content"]),
            }
        )
    return projected


def _metadata_allowed_fields(metadata: Any) -> set[str]:
    if not isinstance(metadata, dict):
        raise TransportError("metadata must be an object")
    allowed = set(metadata)
    oracle = metadata.get("oracle")
    if isinstance(oracle, dict):
        allowed.update(
            f"oracle.{key}" for key in ("type", "ref") if key in oracle
        )
    return allowed


def _bind_context_schema(variant: dict[str, Any], record: dict[str, Any]) -> None:
    resolution = variant.get("properties", {}).get("context_resolution")
    if not isinstance(resolution, dict):
        raise TransportError("deep schema has no context_resolution")
    resolution_properties = resolution.get("properties")
    if not isinstance(resolution_properties, dict):
        raise TransportError("deep context_resolution schema is invalid")
    evidence = resolution_properties.get("context_evidence")
    if not isinstance(evidence, dict) or not isinstance(evidence.get("items"), dict):
        raise TransportError("deep context evidence schema is invalid")
    evidence_item = copy.deepcopy(evidence["items"])
    if not isinstance(evidence_item.get("properties"), dict):
        raise TransportError("deep context evidence item schema is invalid")
    context = record.get("context")
    if not isinstance(context, list):
        raise TransportError("deep context must be an array")
    if not context:
        resolution["type"] = "null"
        resolution.pop("properties", None)
        resolution.pop("required", None)
        return
    evidence_item["properties"] = {"ordinal": {"type": "integer"}}
    evidence_item["required"] = ["ordinal"]
    evidence_item["additionalProperties"] = False
    evidence_item["properties"]["ordinal"] = {
        "type": "integer",
        "enum": list(range(len(context))),
    }
    evidence["items"] = evidence_item


def _model_result_reviews(
    phase: str, model_result: Any, record_count: int
) -> list[dict[str, Any]]:
    if not isinstance(model_result, dict) or set(model_result) != {"reviews"}:
        raise TransportError("model result must contain only reviews")
    reviews = model_result["reviews"]
    if not isinstance(reviews, list) or len(reviews) != record_count:
        raise TransportError("model result review count does not match packet")
    model_keys = _model_review_keys(phase)
    ordinals: list[int] = []
    for review in reviews:
        if not isinstance(review, dict) or set(review) != model_keys:
            raise TransportError("model review has unexpected keys")
        ordinal = review.get("ordinal")
        if type(ordinal) is not int:
            raise TransportError("review ordinal must be a strict integer")
        ordinals.append(ordinal)
    expected = list(range(record_count))
    if ordinals != expected:
        raise TransportError("review ordinals must be complete and in packet order")
    return reviews


def _model_review_keys(phase: str) -> set[str]:
    try:
        keys = set(PHASE_SPECS[phase]["keys"]) - _HOST_IDENTITY_KEYS
    except KeyError as exc:
        raise TransportError(f"unknown phase: {phase}") from exc
    keys.add("ordinal")
    return keys


def _bind_review(
    phase: str, record: dict[str, Any], review: dict[str, Any]
) -> dict[str, Any]:
    bound = copy.deepcopy(review)
    if phase == "metadata":
        host = {
            "record_id": record["record_id"],
            "metadata_hash": record["metadata_hash"],
        }
    else:
        host = {
            "record_id": record["record_id"],
            "metadata_hash": record["metadata_hash"],
            "source_hash": record["source_hash"],
        }
    bound.pop("ordinal", None)
    if phase == "deep":
        resolution = bound.get("context_resolution")
        if resolution is not None:
            if not isinstance(resolution, dict) or set(resolution) != {
                "actual_boundary",
                "actual_observables",
                "context_evidence",
            }:
                raise TransportError("deep context_resolution has unexpected keys")
            contexts = record["context"]
            evidence = resolution["context_evidence"]
            if not isinstance(evidence, list):
                raise TransportError("deep context_evidence must be an array")
            converted = []
            seen: set[int] = set()
            for item in evidence:
                if not isinstance(item, dict) or set(item) != {"ordinal"}:
                    raise TransportError("deep context evidence must contain only ordinal")
                context_ordinal = item["ordinal"]
                if type(context_ordinal) is not int:
                    raise TransportError("context ordinal must be a strict integer")
                if context_ordinal < 0 or context_ordinal >= len(contexts):
                    raise TransportError("context ordinal is outside this record")
                if context_ordinal in seen:
                    raise TransportError("context evidence contains duplicate ordinal")
                seen.add(context_ordinal)
                context = contexts[context_ordinal]
                converted.append(
                    {
                        "ref": context["ref"],
                        "content_hash": context["content_hash"],
                    }
                )
            resolution["context_evidence"] = converted
    return {**host, **bound}


__all__ = [
    "TransportError",
    "canonical_result",
    "model_packet",
    "model_result_schema",
]
