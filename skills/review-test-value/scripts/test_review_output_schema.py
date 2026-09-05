"""Tests for the v2 codex exec output schemas."""

from __future__ import annotations

import copy
import json
import subprocess
import unittest
import sys
from pathlib import Path
from jsonschema import ValidationError, validate

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from validate_review_result import phase_result_schema


def _hash(seed: str) -> str:
    return "sha256:" + seed * 64


def _valid_result(phase: str) -> dict:
    review = {
        "record_id": _hash("a"),
        "metadata_hash": _hash("b"),
        "verdict": {"metadata": "VALID", "alignment": "ALIGNED", "deep": "APPROVE"}[phase],
        "evidence": (
            [{"fields": ["claim"], "finding": "SELF_CONTAINED_CLAIM"}]
            if phase == "metadata"
            else ["observable"]
        ),
        "unverified": [],
        "next_action": None,
    }
    if phase != "metadata":
        review.update(
            {
                "source_hash": _hash("c"),
                "context_requirements": [],
            }
        )
    if phase == "alignment":
        review.update(
            {
                "actual_boundary": "consumer",
                "actual_observables": ["result"],
                "overclaim": False,
                "disposition_candidate": None,
            }
        )
    result = {
        "review_contract_version": {
            "metadata": "metadata-review-v2",
            "alignment": "alignment-review-v2",
            "deep": "deep-review-v2",
        }[phase],
        "reviews": [review],
    }
    if phase == "deep":
        result["input_hash"] = _hash("d")
        review["context_resolution"] = None
    return result


class ReviewOutputSchemaTests(unittest.TestCase):
    # @test-value v2
    # kind = "contract"
    # claim = "codex execへ渡す各v2 phase schemaは未知fieldと必須field欠落を拒否し、契約に沿う結果を受理する"
    # oracle = { type = "adr", ref = "ADR-0022" }
    # fault = "workerが未定義fieldを混入または必須値を省略した結果をschema段階で受理し、validator到達前に契約外データを流す"
    # observable = "jsonschemaが返す受理結果またはValidationError"
    # observation_boundary = "component-behavior"
    # scope = "review-result-output-schema"
    # lifecycle = "permanent"
    # @end-test-value
    def test_each_phase_schema_rejects_malformed_and_accepts_valid_result(self):
        for phase in ("metadata", "alignment", "deep"):
            with self.subTest(phase=phase):
                schema = phase_result_schema(phase)
                valid = _valid_result(phase)
                validate(valid, schema)

                malformed = {**valid, "unexpected": True}
                with self.assertRaises(ValidationError):
                    validate(malformed, schema)

                missing = {key: value for key, value in valid.items() if key != "reviews"}
                with self.assertRaises(ValidationError):
                    validate(missing, schema)

                for field, value in (("verdict", "UNKNOWN"), ("metadata_hash", 7), ("extra", True)):
                    malformed = copy.deepcopy(valid)
                    malformed["reviews"][0][field] = value
                    with self.subTest(field=field), self.assertRaises(ValidationError):
                        validate(malformed, schema)
                missing_review_field = copy.deepcopy(valid)
                del missing_review_field["reviews"][0]["next_action"]
                with self.assertRaises(ValidationError):
                    validate(missing_review_field, schema)

    # @test-value v2
    # kind = "contract"
    # claim = "schema出力CLIは指定phaseの結果を受理し別phase版を拒否するJSONだけを返し、検証modeとの混在を拒否する"
    # oracle = { type = "issue", ref = "https://github.com/natumekazuki/.codex/issues/42" }
    # fault = "CLIがphase引数を無視したschemaや余分な文章を返し、workerが誤った出力形式で起動される"
    # observable = "CLIのexit code、stdoutのJSON schema、stderr"
    # observation_boundary = "public-boundary"
    # scope = "review-result-schema-cli"
    # lifecycle = "permanent"
    # distinction = "関数のschema意味検証とは別に公開CLIの引数とJSON出力を観測する"
    # @end-test-value
    def test_cli_emits_requested_schema_and_rejects_mixed_modes(self):
        command = [sys.executable, str(SCRIPTS / "validate_review_result.py")]
        for phase in ("metadata", "alignment", "deep"):
            with self.subTest(phase=phase):
                process = subprocess.run(
                    [*command, "--emit-schema", phase], capture_output=True,
                    text=True, encoding="utf-8", timeout=15,
                )
                self.assertEqual(process.returncode, 0, process.stderr)
                schema = json.loads(process.stdout)
                valid = _valid_result(phase)
                validate(valid, schema)
                valid["review_contract_version"] = "different-review-v2"
                with self.assertRaises(ValidationError):
                    validate(valid, schema)
        mixed = subprocess.run(
            [*command, "metadata", "--emit-schema", "metadata"],
            capture_output=True, text=True, encoding="utf-8", timeout=15,
        )
        self.assertEqual(mixed.returncode, 2)
        self.assertIn("cannot be combined", mixed.stderr)


if __name__ == "__main__":
    unittest.main()
