"""One flat model response, ordinal binding, and no phase-specific semantics."""
from __future__ import annotations

import json
import math
from typing import Any

VERDICTS = (
    "KEEP_PERMANENT", "KEEP_TEMPORARY", "MOVE_TO_POLICY_CHECK",
    "DROP", "REDESIGN", "NEEDS_CONTEXT",
)
CONTRACT_VERSION = "test-value-review-v3"
PROPERTIES = {
    "ordinal": {"type": "integer"},
    "verdict": {"type": "string", "enum": list(VERDICTS)},
    "summary": {"type": "string"},
    "findings": {"type": "array", "items": {"type": "string"}},
    "context_request": {"type": ["string", "null"]},
}


class ReviewError(ValueError):
    """Safe diagnostics: never include source, a raw response, or private paths."""

    def __init__(self, category: str, code: str, **location: Any) -> None:
        super().__init__(code)
        self.category = category
        self.code = code
        self.location = {k: v for k, v in location.items()
                         if k in {"batch_index", "ordinal", "record_id"}}

    def diagnostic(self) -> dict[str, Any]:
        return {"category": self.category, "code": self.code, **self.location}


def response_schema() -> dict[str, Any]:
    # One schema for every record and verdict; no identity enums or variants.
    return {
        "type": "object", "additionalProperties": False,
        "required": ["reviews"],
        "properties": {"reviews": {
            "type": "array", "items": {
                "type": "object", "additionalProperties": False,
                "required": list(PROPERTIES), "properties": PROPERTIES,
            },
        }},
    }


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def parse_json(text: str, *, category: str = "response_schema") -> Any:
    try:
        return json.loads(text, object_pairs_hook=_pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except (ValueError, TypeError) as exc:
        raise ReviewError(category, "INVALID_JSON") from exc


def validate_response(value: Any, count: int) -> list[dict[str, Any]]:
    if not isinstance(value, dict) or set(value) != {"reviews"}:
        raise ReviewError("response_schema", "RESULT_SHAPE")
    reviews = value["reviews"]
    if not isinstance(reviews, list):
        raise ReviewError("response_schema", "REVIEWS_TYPE")
    by_ordinal: dict[int, dict[str, Any]] = {}
    for item in reviews:
        if not isinstance(item, dict) or set(item) != set(PROPERTIES):
            raise ReviewError("response_schema", "REVIEW_SHAPE")
        # Validate the flat schema's types/enum only. In particular, an empty
        # diagnostic or a null context_request never changes a valid verdict.
        for name, spec in PROPERTIES.items():
            field = item[name]
            kind = spec["type"]
            valid = (
                (kind == "integer" and not isinstance(field, bool)
                 and (isinstance(field, int) or (isinstance(field, float)
                      and math.isfinite(field) and field.is_integer())))
                or (kind == "string" and isinstance(field, str))
                or (kind == "array" and isinstance(field, list)
                    and all(isinstance(x, str) for x in field))
                or (kind == ["string", "null"] and (field is None or isinstance(field, str)))
            )
            if not valid or ("enum" in spec and field not in spec["enum"]):
                raise ReviewError("response_schema", "FIELD_TYPE_OR_ENUM")
        ordinal = int(item["ordinal"])
        if ordinal < 0 or ordinal >= count or ordinal in by_ordinal:
            raise ReviewError("ordinal", "ORDINAL_SET", ordinal=ordinal)
        by_ordinal[ordinal] = {**item, "ordinal": ordinal}
    if set(by_ordinal) != set(range(count)):
        raise ReviewError("ordinal", "ORDINAL_SET")
    return [by_ordinal[i] for i in range(count)]


def bind_response(value: Any, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    reviews = validate_response(value, len(records))
    return [{**{k: record[k] for k in ("record_id", "metadata_hash", "source_hash", "input_hash")},
             **{k: review[k] for k in PROPERTIES if k != "ordinal"}}
            for record, review in zip(records, reviews)]
