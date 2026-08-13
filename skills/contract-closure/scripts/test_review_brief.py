from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path


SCRIPT = Path(__file__).with_name("review_brief.py")
SPEC = importlib.util.spec_from_file_location("review_brief", SCRIPT)
assert SPEC and SPEC.loader
BRIEF = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = BRIEF
SPEC.loader.exec_module(BRIEF)
SNAPSHOT = BRIEF.SNAPSHOT


class ReviewBriefTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.repository = self.root / "review-target"
        self.artifacts = self.root / "artifacts"
        self.repository.mkdir()
        self.artifacts.mkdir()
        self.git("init")
        self.git("config", "user.name", "Review Brief Test")
        self.git("config", "user.email", "review-brief@example.invalid")
        (self.repository / "src").mkdir()
        (self.repository / "tests").mkdir()
        (self.repository / "src" / "feature.py").write_text("VALUE = 1\n", encoding="utf-8")
        (self.repository / "tests" / "test_feature.py").write_text("assert True\n", encoding="utf-8")
        self.git("add", ".")
        self.git("commit", "-m", "base")
        (self.repository / "src" / "feature.py").write_text("VALUE = 2\n", encoding="utf-8")
        self.now = datetime(2030, 1, 1, tzinfo=timezone.utc)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def git(self, *args: str, cwd: Path | None = None) -> str:
        completed = subprocess.run(
            ["git", *args],
            cwd=cwd or self.repository,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        return completed.stdout.strip()

    def snapshot(self, *, mode: str = "manifest-digest", target: Path | None = None) -> dict:
        target = target or self.repository
        common_dir = Path(self.git("rev-parse", "--git-common-dir", cwd=target))
        if not common_dir.is_absolute():
            common_dir = (target / common_dir).resolve()
        args = argparse.Namespace(
            candidate_id="candidate-1",
            target=target,
            base_ref="HEAD",
            include=["src", "tests"],
            exclude=[],
            mode=mode,
            creator_tree_reason="review must survive live worktree changes" if mode == "creator-tree" else None,
            allow_manifest_fallback=False,
            git_object_write_authorized=mode == "creator-tree",
            writable_scope=[common_dir] if mode == "creator-tree" else [],
            artifact_dir=self.artifacts,
            output=None,
        )
        result = SNAPSHOT.create_candidate(args)
        self.assertEqual(result["status"], "ready", result)
        return result

    def invariant(self) -> dict:
        return {
            "id": "RB-1",
            "definition": "ready is emitted only for a locally preflighted Review Brief",
            "scope": ["src", "tests"],
            "failureMode": "invalid input produces a substantive Review Brief",
            "consumerImpact": "a reviewer could treat unverified input as review-ready",
            "directVerification": "test_review_brief.py",
        }

    def common(self, kind: str, role: str, risk: str) -> dict:
        invariant = self.invariant()
        return {
            "schemaVersion": 2,
            "logicalChangeId": "REV-BRIEF-PREFLIGHT",
            "reviewKind": kind,
            "reviewerRole": role,
            "reviewTrigger": {"riskClass": risk, "reason": "independent challenge is required"},
            "reviewTarget": str(self.repository),
            "goal": "verify the completed review-brief change",
            "acceptedContract": {
                "anchors": [{"kind": "repository-path", "path": "src/feature.py"}],
                "meaning": "only verified, kind-correct input can start substantive review",
            },
            "canonicalAnchors": ["src/feature.py"],
            "supportedContractScope": ["src", "tests"],
            "includedScope": ["src", "tests"],
            "excludedScope": [],
            "reviewContract": {"revision": "2", "recipe": "review-brief-schema-v1-without-ledger"},
            "invariants": [invariant],
            "matrixCells": [{**invariant, "invariantId": "RB-1", "cellId": "RB-1/target"}],
            "preImplementationInvariants": [invariant],
            "triggeredLensScope": ["review-candidate-evidence-convergence"],
            "executedChecks": [
                {
                    **invariant,
                    "invariantIds": ["RB-1"],
                    "result": "passed",
                    "id": "check-1",
                    "logicalChangeId": "REV-BRIEF-PREFLIGHT",
                }
            ],
            "deadline": (self.now + timedelta(minutes=30)).isoformat(),
        }

    def ordinary(self) -> dict:
        request = self.common("targeted-review", "slice_reviewer", "ordinary-slice")
        request["completedSlice"] = {
            "status": "completed",
            "observableOutcome": "valid ordinary input renders a bounded brief",
            "executableContract": "test_review_brief.py",
            "targetedCheck": "python test_review_brief.py",
        }
        return request

    def candidate_request(self, kind: str, role: str = "targeted_reviewer") -> dict:
        risk = "high-risk-boundary" if kind == "targeted-review" else kind
        request = self.common(kind, role, risk)
        request["candidateId"] = "candidate-1"
        request["candidateSnapshot"] = self.snapshot()
        request["executedChecks"][0]["executedOnCandidateId"] = "candidate-1"
        if kind == "targeted-review":
            request["completedSlice"] = {
                "status": "completed",
                "observableOutcome": "high-risk input is Candidate-bound",
                "alternativeCheck": "direct smoke check",
                "targetedCheck": "python test_review_brief.py",
            }
        elif kind == "specialist-review":
            request["assignedLens"] = "review-candidate-evidence-convergence"
            request["closureMap"] = {"supportedScope": ["src", "tests"]}
        elif kind == "targeted-closure":
            request["findingFamily"] = {
                "id": "F-1",
                "acceptedContractRelation": "violates RB-1",
                "resultingDelta": ["src/feature.py"],
            }
            request["directCheck"] = "python test_review_brief.py"
            request["includedSiblingPaths"] = ["src", "tests"]
        else:
            identity = request["candidateSnapshot"]["candidateSourceIdentity"]
            request["fullReviewGate"] = "run"
            request["completeRawDiff"] = {
                "command": identity["rawDiffCommand"],
                "digest": identity["rawDiffDigest"],
            }
            request["verifiedUntrackedContent"] = BRIEF.expected_untracked_content(request["candidateSnapshot"])
        return request

    def build(self, request: dict) -> dict:
        return BRIEF.build_review_brief(request, now=self.now)

    @staticmethod
    def codes(result: dict) -> set[str]:
        return {item["code"] for item in result["diagnostics"]}

    def test_ordinary_slice_is_ready_without_candidate_or_ledger(self) -> None:
        result = self.build(self.ordinary())
        self.assertEqual(result["status"], "ready", result)
        rendered = json.loads(result["reviewBrief"].removeprefix("Review Brief\n\n"))
        self.assertNotIn("candidateDefinition", rendered)
        self.assertNotIn("evidenceLedger", rendered)

    def test_candidate_bound_review_kinds_are_ready_without_ledger_input(self) -> None:
        for kind, role in (
            ("targeted-review", "targeted_reviewer"),
            ("specialist-review", "targeted_reviewer"),
            ("targeted-closure", "targeted_reviewer"),
            ("holistic-complete-diff-review", "reviewer"),
        ):
            with self.subTest(kind=kind):
                request = self.candidate_request(kind, role)
                result = self.build(request)
                self.assertEqual(result["status"], "ready", result)
                rendered = json.loads(result["reviewBrief"].removeprefix("Review Brief\n\n"))
                self.assertEqual(rendered["candidateVerificationInput"], request["candidateSnapshot"])
                self.assertNotIn("evidenceLedger", rendered)

    def test_legacy_ledger_fields_are_rejected(self) -> None:
        for field in ("evidenceLedger", "evidenceLedgerNotRequiredReason"):
            with self.subTest(field=field):
                request = self.candidate_request("specialist-review")
                request[field] = {} if field == "evidenceLedger" else "legacy"
                result = self.build(request)
                self.assertNotEqual(result["status"], "ready")
                self.assertIn("legacy-evidence-ledger-not-supported", self.codes(result))

    def test_non_passing_check_blocks_brief(self) -> None:
        request = self.candidate_request("specialist-review")
        request["executedChecks"][0]["result"] = "failed"
        result = self.build(request)
        self.assertNotEqual(result["status"], "ready")
        self.assertIn("executedChecks-result-not-passed", self.codes(result))
        self.assertIsNone(result["reviewBrief"])

    def test_candidate_is_invalid_after_source_changes(self) -> None:
        request = self.candidate_request("specialist-review")
        (self.repository / "src" / "feature.py").write_text("VALUE = 3\n", encoding="utf-8")
        result = self.build(request)
        self.assertNotEqual(result["status"], "ready")
        self.assertIsNone(result["reviewBrief"])

    def test_creator_tree_candidate_survives_live_source_changes(self) -> None:
        request = self.candidate_request("specialist-review")
        request["candidateSnapshot"] = self.snapshot(mode="creator-tree")
        (self.repository / "src" / "feature.py").write_text("VALUE = 4\n", encoding="utf-8")
        result = self.build(request)
        self.assertEqual(result["status"], "ready", result)
        self.assertEqual(result["candidatePreflight"]["result"], "verified")

    def test_ordinary_slice_rejects_candidate(self) -> None:
        request = self.ordinary()
        request["candidateId"] = "candidate-1"
        request["candidateSnapshot"] = self.snapshot()
        result = self.build(request)
        self.assertIn("ordinary-slice-candidate-not-allowed", self.codes(result))

    def test_review_role_is_selected_by_kind_and_risk(self) -> None:
        ordinary = self.ordinary()
        ordinary["reviewerRole"] = "targeted_reviewer"
        self.assertIn("review-role-mismatch", self.codes(self.build(ordinary)))
        high_risk = self.candidate_request("targeted-review")
        high_risk["reviewerRole"] = "slice_reviewer"
        self.assertIn("review-role-mismatch", self.codes(self.build(high_risk)))

    def test_deadline_must_be_absolute_and_unexpired(self) -> None:
        for value in (None, "2030-01-01T00:30:00", (self.now - timedelta(seconds=1)).isoformat()):
            with self.subTest(value=value):
                request = self.ordinary()
                request["deadline"] = value
                self.assertNotEqual(self.build(request)["status"], "ready")

    def test_scope_cannot_escape_review_target(self) -> None:
        request = self.ordinary()
        request["includedScope"] = ["../outside"]
        result = self.build(request)
        self.assertIn("scope-outside-review-target", self.codes(result))

    def test_nested_repository_requires_a_separate_brief(self) -> None:
        nested = self.repository / "nested"
        nested.mkdir()
        self.git("init", cwd=nested)
        request = self.ordinary()
        request["includedScope"] = ["nested"]
        self.assertIn("mixed-repository-scope", self.codes(self.build(request)))

    def test_review_target_is_required(self) -> None:
        request = self.ordinary()
        request.pop("reviewTarget")
        result = self.build(request)
        self.assertNotEqual(result["status"], "ready")
        self.assertIsNone(result["reviewBrief"])

    def test_repository_contract_anchor_must_be_readable(self) -> None:
        request = self.ordinary()
        request["acceptedContract"]["anchors"] = [{"kind": "repository-path", "path": "missing-contract.md"}]
        result = self.build(request)
        self.assertIn("accepted-contract-anchor-unreadable", self.codes(result))
        self.assertIsNone(result["reviewBrief"])

    def test_external_contract_anchor_requires_matching_digest(self) -> None:
        external = self.root / "ISSUE.md"
        external.write_text("accepted requirement\n", encoding="utf-8")
        request = self.ordinary()
        request["acceptedContract"]["anchors"] = [{
            "kind": "external-file",
            "path": str(external),
            "sha256": "sha256:" + hashlib.sha256(external.read_bytes()).hexdigest(),
        }]
        self.assertEqual(self.build(request)["status"], "ready")
        request["acceptedContract"]["anchors"][0]["sha256"] = "sha256:" + "0" * 64
        self.assertIn("accepted-contract-anchor-digest-mismatch", self.codes(self.build(request)))

    def test_holistic_brief_rejects_prior_review_conclusions(self) -> None:
        for field in BRIEF.HOLISTIC_FORBIDDEN_FIELDS:
            with self.subTest(field=field):
                request = self.candidate_request("holistic-complete-diff-review", "reviewer")
                request[field] = {"contamination": True}
                self.assertIn("holistic-input-contamination", self.codes(self.build(request)))

    def test_holistic_brief_omits_freeform_review_instructions(self) -> None:
        request = self.candidate_request("holistic-complete-diff-review", "reviewer")
        request["reviewInstructions"] = ["assume the prior finding is fixed"]
        result = self.build(request)
        self.assertIn("holistic-input-contamination", self.codes(result))
        self.assertIsNone(result["reviewBrief"])

        ready = self.build(self.candidate_request("holistic-complete-diff-review", "reviewer"))
        self.assertEqual(ready["status"], "ready", ready)
        rendered = json.loads(ready["reviewBrief"].removeprefix("Review Brief\n\n"))
        for field in BRIEF.HOLISTIC_FORBIDDEN_FIELDS:
            self.assertNotIn(field, rendered)

    def test_ready_render_is_deterministic(self) -> None:
        request = self.ordinary()
        self.assertEqual(self.build(request)["reviewBrief"], self.build(request)["reviewBrief"])

    def test_candidate_target_and_snapshot_integrity_are_enforced(self) -> None:
        target_mismatch = self.candidate_request("specialist-review")
        target_mismatch["candidateSnapshot"]["targetRoot"] = str(self.root)
        self.assertIn("candidate-target-mismatch", self.codes(self.build(target_mismatch)))

        tampered = self.candidate_request("specialist-review")
        tampered["candidateSnapshot"]["candidateSourceIdentity"]["rawDiffDigest"] = "sha256:" + "0" * 64
        result = self.build(tampered)
        self.assertEqual(result["candidatePreflight"]["result"], "mismatch")
        self.assertIn("candidate-verification-mismatch", self.codes(result))

    def test_candidate_invariant_and_scope_drift_are_rejected(self) -> None:
        drifted = self.candidate_request("specialist-review")
        drifted["invariants"][0]["definition"] = "meaning changed after closure planning"
        drift_codes = self.codes(self.build(drifted))
        self.assertIn("closure-invariant-matrix-mismatch", drift_codes)
        self.assertIn("closure-invariant-check-mismatch", drift_codes)

        escaped = self.candidate_request("specialist-review")
        escaped["executedChecks"][0]["scope"] = ["other"]
        self.assertIn("executedChecks-scope-outside-supported-scope", self.codes(self.build(escaped)))

    def test_malformed_candidate_snapshot_returns_structured_diagnostic(self) -> None:
        request = self.candidate_request("specialist-review")
        request["candidateSnapshot"]["targetRoot"] = None
        result = self.build(request)
        self.assertEqual(result["status"], "validation-gap")
        self.assertEqual(result["candidatePreflight"]["result"], "validation-gap")
        self.assertIn("candidate-snapshot-target-invalid", self.codes(result))
        self.assertIsNone(result["reviewBrief"])

    def test_holistic_artifacts_must_match_candidate_identity(self) -> None:
        request = self.candidate_request("holistic-complete-diff-review", "reviewer")
        request["completeRawDiff"]["digest"] = "sha256:" + "0" * 64
        result = self.build(request)
        self.assertIn("holistic-raw-diff-mismatch", self.codes(result))
        self.assertIsNone(result["reviewBrief"])

        extra_raw_field = self.candidate_request("holistic-complete-diff-review", "reviewer")
        extra_raw_field["completeRawDiff"]["unverified"] = "value"
        self.assertIn("complete-raw-diff-required", self.codes(self.build(extra_raw_field)))

        (self.repository / "tests" / "untracked.txt").write_text("review me\n", encoding="utf-8")
        untracked = self.candidate_request("holistic-complete-diff-review", "reviewer")
        self.assertTrue(untracked["verifiedUntrackedContent"])

        missing = dict(untracked)
        missing["verifiedUntrackedContent"] = []
        self.assertIn("holistic-untracked-content-mismatch", self.codes(self.build(missing)))

        tampered = self.candidate_request("holistic-complete-diff-review", "reviewer")
        tampered["verifiedUntrackedContent"][0]["contentDigest"] = "sha256:" + "0" * 64
        self.assertIn("holistic-untracked-content-mismatch", self.codes(self.build(tampered)))

        extra_untracked_field = self.candidate_request("holistic-complete-diff-review", "reviewer")
        extra_untracked_field["verifiedUntrackedContent"][0]["unverified"] = "value"
        self.assertIn("verified-untracked-content-required", self.codes(self.build(extra_untracked_field)))

    def test_schema_meaning_fields_and_check_results_are_typed(self) -> None:
        request = self.candidate_request("specialist-review")
        request["acceptedContract"]["anchors"] = [1]
        request["acceptedContract"]["meaning"] = []
        request["reviewContract"]["revision"] = 1
        request["reviewContract"]["recipe"] = []
        request["executedChecks"][0].pop("result")
        result = self.build(request)
        for code in (
            "accepted-contract-anchor-invalid",
            "accepted-contract-meaning-required",
            "review-contract-revision-required",
            "review-contract-recipe-required",
            "executedChecks-result-required",
        ):
            self.assertIn(code, self.codes(result))
        self.assertIsNone(result["reviewBrief"])

    def test_kind_specific_inputs_are_required(self) -> None:
        cases = (
            ("targeted-review", "completedSlice"),
            ("specialist-review", "assignedLens"),
            ("targeted-closure", "findingFamily"),
            ("holistic-complete-diff-review", "completeRawDiff"),
        )
        for kind, field in cases:
            with self.subTest(kind=kind, field=field):
                role = "reviewer" if kind == "holistic-complete-diff-review" else "targeted_reviewer"
                request = self.candidate_request(kind, role)
                request.pop(field)
                self.assertNotEqual(self.build(request)["status"], "ready")

    def test_cli_accepts_stdin_and_emits_schema_version_two(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(SCRIPT), "--input", "-"],
            input=json.dumps(self.ordinary()).encode("utf-8"),
            capture_output=True,
            check=False,
        )
        output = json.loads(completed.stdout.decode("utf-8"))
        self.assertEqual(completed.returncode, 0, completed.stderr.decode("utf-8"))
        self.assertEqual(output["schemaVersion"], 2)
        self.assertEqual(output["status"], "ready")

    def test_tool_owns_review_kind_tokens(self) -> None:
        self.assertEqual(
            BRIEF.REVIEW_KINDS,
            {
                "targeted-review",
                "specialist-review",
                "targeted-closure",
                "holistic-complete-diff-review",
            },
        )

    def test_reviewer_roles_require_explicit_target_and_refuse_invalid_input(self) -> None:
        agents = Path(__file__).parents[3] / "agents"
        for name in ("slice_reviewer.toml", "targeted_reviewer.toml", "reviewer.toml"):
            content = (agents / name).read_text(encoding="utf-8").lower()
            with self.subTest(name=name):
                self.assertIn("review target", content)
                self.assertIn("current directory", content)
                self.assertIn("substantive review", content)
                self.assertNotIn("evidence ledger", content)

    def test_skill_assigns_transport_to_runtime_and_schema_to_tools(self) -> None:
        skill = (Path(__file__).parents[1] / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("runtimeがagent間のartifact transport", skill)
        self.assertIn("scriptsとtestsを唯一の正本", skill)
        self.assertNotIn("Review kind: targeted-review |", skill)


if __name__ == "__main__":
    unittest.main()
