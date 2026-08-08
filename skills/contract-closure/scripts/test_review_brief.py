from __future__ import annotations

import argparse
import copy
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import contextmanager
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
        self.session_workspace = self.root / "session-workspace"
        self.repository = self.root / "review-target"
        self.artifacts = self.root / "artifacts"
        self.session_workspace.mkdir()
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
            "consumerImpact": "a reviewer could mistake unverified input for review-ready evidence",
            "directVerification": "review brief builder unit tests",
        }

    def common(self, kind: str, role: str, *, risk: str) -> dict:
        invariant = self.invariant()
        return {
            "schemaVersion": 1,
            "logicalChangeId": "REV-BRIEF-PREFLIGHT",
            "reviewKind": kind,
            "reviewerRole": role,
            "reviewTrigger": {"riskClass": risk, "reason": "review contract requires independent challenge"},
            "reviewTarget": str(self.repository),
            "goal": "verify the completed review-brief change",
            "acceptedContract": {
                "anchors": ["skills/contract-closure/SKILL.md"],
                "meaning": "only a verified, kind-correct brief can start substantive review",
            },
            "canonicalAnchors": ["skills/contract-closure/SKILL.md"],
            "supportedContractScope": ["src", "tests"],
            "includedScope": ["src", "tests"],
            "excludedScope": [],
            "reviewContract": {"revision": "1", "recipe": "review-brief-schema-v1"},
            "invariants": [invariant],
            "matrixCells": [{**invariant, "invariantId": invariant["id"], "cellId": "RB-1/target"}],
            "preImplementationInvariants": [invariant],
            "triggeredLensScope": ["review-candidate-evidence-convergence"],
            "executedChecks": [{**invariant, "invariantIds": [invariant["id"]], "result": "passed"}],
            "deadline": (self.now + timedelta(minutes=30)).isoformat(),
        }

    def ordinary(self) -> dict:
        request = self.common("targeted-review", "slice_reviewer", risk="ordinary-slice")
        request["evidenceLedgerNotRequiredReason"] = (
            "Candidate-independent targeted review does not use a Frozen Candidate or Candidate-bound Evidence Ledger "
            "under skills/contract-closure/SKILL.md Review Brief."
        )
        request["completedSlice"] = {
            "status": "completed",
            "observableOutcome": "valid ordinary input renders a bounded brief",
            "executableContract": "test_review_brief.py",
            "targetedCheck": "python -m unittest test_review_brief.py",
        }
        return request

    def candidate_request(self, kind: str, role: str = "targeted_reviewer") -> dict:
        risk = "high-risk-boundary" if kind == "targeted-review" else kind
        request = self.common(kind, role, risk=risk)
        request["candidateId"] = "candidate-1"
        request["candidateSnapshot"] = self.snapshot()
        request["executedChecks"][0]["executedOnCandidateId"] = "candidate-1"
        if kind in {"targeted-review", "specialist-review", "targeted-closure"}:
            request["evidenceLedger"] = {
                "candidateId": "candidate-1",
                "entries": [
                    {
                        "id": "check-1",
                        "kind": "check",
                        "candidateId": "candidate-1",
                        "status": "current",
                        "result": "passed",
                    }
                ],
            }
        if kind == "targeted-review":
            request["completedSlice"] = {
                "status": "completed",
                "observableOutcome": "high-risk input is Candidate-bound",
                "alternativeCheck": "direct CLI smoke verifies the launch boundary",
                "targetedCheck": "python -m unittest test_review_brief.py",
            }
        elif kind == "specialist-review":
            request.update(
                assignedLens="review-candidate-evidence-convergence",
                closureMap={"supportedScope": ["src", "tests"]},
            )
        elif kind == "targeted-closure":
            request.update(
                findingFamily={
                    "id": "F-1",
                    "acceptedContractRelation": "violates RB-1",
                    "resultingDelta": ["src/feature.py"],
                },
                directCheck="python -m unittest test_review_brief.py",
                includedSiblingPaths=["src", "tests"],
            )
        elif kind == "holistic-complete-diff-review":
            identity = request["candidateSnapshot"]["candidateSourceIdentity"]
            untracked = [
                {
                    "path": record["pathText"],
                    "contentDigest": record["contentDigest"],
                    "objectType": record["objectType"],
                    "mode": record["newMode"],
                }
                for record in identity["manifest"]["records"]
                if record.get("untracked") is True
            ]
            request.update(
                evidenceLedgerNotRequiredReason=(
                    "Holistic complete-diff review receives current executed checks but not prior Ledger review evidence "
                    "under skills/contract-closure/SKILL.md Review Brief."
                ),
                fullReviewGate="run",
                completeRawDiff={"command": identity["rawDiffCommand"], "digest": identity["rawDiffDigest"]},
                verifiedUntrackedContent=untracked,
            )
        return request

    @contextmanager
    def chdir(self, path: Path):
        previous = Path.cwd()
        os.chdir(path)
        try:
            yield
        finally:
            os.chdir(previous)

    def build(self, request: dict) -> dict:
        return BRIEF.build_review_brief(request, now=self.now)

    def codes(self, result: dict) -> set[str]:
        return {item["code"] for item in result["diagnostics"]}

    def test_ordinary_slice_is_ready_without_candidate_from_other_workspace(self) -> None:
        (self.session_workspace / "uncommitted.txt").write_text("session only", encoding="utf-8")
        with self.chdir(self.session_workspace):
            result = self.build(self.ordinary())

        self.assertEqual(result["status"], "ready", result)
        self.assertIsNone(result["candidateDefinition"])
        self.assertEqual(result["inputArtifactPreflight"]["result"], "verified")
        self.assertNotIn(str(self.session_workspace), result["reviewBrief"])
        self.assertNotIn('"candidateDefinition"', result["reviewBrief"])

    def test_candidate_definition_can_target_a_different_git_worktree(self) -> None:
        worktree = self.root / "secondary-worktree"
        self.git("worktree", "add", "-b", "review-brief-secondary", str(worktree))
        (worktree / "src" / "feature.py").write_text("VALUE = 5\n", encoding="utf-8")
        request = self.candidate_request("specialist-review")
        request["reviewTarget"] = str(worktree)
        request["candidateSnapshot"] = self.snapshot(target=worktree)
        with self.chdir(self.session_workspace):
            result = self.build(request)
        self.assertEqual(result["status"], "ready", result)
        self.assertEqual(Path(result["candidateDefinition"]["targetRoot"]), worktree.resolve())
        self.assertEqual(result["candidatePreflight"]["result"], "verified")

    def test_each_candidate_bound_review_kind_has_a_minimal_ready_input(self) -> None:
        for kind, role in (
            ("targeted-review", "targeted_reviewer"),
            ("specialist-review", "targeted_reviewer"),
            ("targeted-closure", "targeted_reviewer"),
            ("holistic-complete-diff-review", "reviewer"),
        ):
            with self.subTest(kind=kind):
                result = self.build(self.candidate_request(kind, role))
                self.assertEqual(result["status"], "ready", result)
                self.assertEqual(result["candidatePreflight"]["result"], "verified")
                self.assertIn('"reviewTarget":', result["reviewBrief"])
                rendered = json.loads(result["reviewBrief"].removeprefix("Review Brief\n\n"))
                self.assertEqual(rendered["candidateVerificationInput"], self.candidate_request(kind, role)["candidateSnapshot"])

    def test_non_passing_checks_block_review_brief_issuance(self) -> None:
        for review_scope, request_factory in (
            ("ordinary", self.ordinary),
            ("candidate-bound", lambda: self.candidate_request("specialist-review")),
        ):
            for check_result in ("failed", "unconfirmed", "superseded"):
                with self.subTest(review_scope=review_scope, result=check_result):
                    request = request_factory()
                    request["executedChecks"][0]["result"] = check_result
                    result = self.build(request)
                    self.assertNotEqual(result["status"], "ready")
                    self.assertIn("executedChecks-result-not-passed", self.codes(result))
                    self.assertIsNone(result["reviewBrief"])

    def test_ordinary_checks_require_exact_string_passed_without_invariant_inheritance(self) -> None:
        for label, check_result in (
            ("missing", object()),
            ("null", None),
            ("empty", ""),
            ("integer", 1),
            ("boolean", True),
        ):
            with self.subTest(result=label):
                request = self.ordinary()
                request.pop("preImplementationInvariants")
                if label == "missing":
                    request["executedChecks"][0].pop("result")
                else:
                    request["executedChecks"][0]["result"] = check_result
                result = self.build(request)
                self.assertNotEqual(result["status"], "ready")
                self.assertIn("executedChecks-result-not-passed", self.codes(result))
                self.assertIsNone(result["reviewBrief"])

    def test_candidate_bound_review_kinds_require_and_render_current_passed_ledger(self) -> None:
        for kind in ("targeted-review", "specialist-review", "targeted-closure"):
            with self.subTest(kind=kind, condition="missing"):
                missing = self.candidate_request(kind)
                del missing["evidenceLedger"]
                missing_result = self.build(missing)
                self.assertNotEqual(missing_result["status"], "ready")
                self.assertIn("evidence-ledger-required", self.codes(missing_result))

            with self.subTest(kind=kind, condition="valid-render"):
                request = self.candidate_request(kind)
                result = self.build(request)
                self.assertEqual(result["status"], "ready", result)
                rendered = json.loads(result["reviewBrief"].removeprefix("Review Brief\n\n"))
                self.assertEqual(rendered["evidenceLedger"], request["evidenceLedger"])

    def test_ledger_not_required_reason_is_explicit_and_rendered_for_sibling_kinds(self) -> None:
        for kind, request_factory in (
            ("ordinary-targeted", self.ordinary),
            ("holistic", lambda: self.candidate_request("holistic-complete-diff-review", "reviewer")),
        ):
            with self.subTest(kind=kind, condition="missing"):
                missing = request_factory()
                del missing["evidenceLedgerNotRequiredReason"]
                missing_result = self.build(missing)
                self.assertNotEqual(missing_result["status"], "ready")
                self.assertIn("evidence-ledger-not-required-reason-required", self.codes(missing_result))

            with self.subTest(kind=kind, condition="valid-render"):
                request = request_factory()
                result = self.build(request)
                self.assertEqual(result["status"], "ready", result)
                rendered = json.loads(result["reviewBrief"].removeprefix("Review Brief\n\n"))
                self.assertEqual(
                    rendered["evidenceLedgerNotRequiredReason"],
                    request["evidenceLedgerNotRequiredReason"],
                )

    def test_candidate_ledger_rejects_noncurrent_wrong_candidate_and_nonpassing_entries(self) -> None:
        mutations = {
            "stale": {"status": "stale"},
            "superseded": {"status": "superseded"},
            "wrong-candidate": {"candidateId": "another-candidate"},
            "failed": {"result": "failed"},
        }
        for kind in ("targeted-review", "specialist-review", "targeted-closure"):
            for label, mutation in mutations.items():
                with self.subTest(kind=kind, condition=label):
                    request = self.candidate_request(kind)
                    request["evidenceLedger"]["entries"][0].update(mutation)
                    result = self.build(request)
                    self.assertNotEqual(result["status"], "ready")
                    self.assertIsNone(result["reviewBrief"])

    def test_executed_checks_and_ledger_cannot_disagree_on_passed_semantics(self) -> None:
        request = self.candidate_request("specialist-review")
        self.assertEqual(request["executedChecks"][0]["result"], "passed")
        request["evidenceLedger"]["entries"][0]["result"] = "failed"
        result = self.build(request)
        self.assertNotEqual(result["status"], "ready")
        self.assertIn("evidence-ledger-entry-result-not-passed", self.codes(result))
        self.assertIsNone(result["reviewBrief"])

    def test_candidate_ledger_entry_ids_are_unique_within_the_review_brief(self) -> None:
        for kind in ("targeted-review", "specialist-review", "targeted-closure"):
            with self.subTest(kind=kind):
                request = self.candidate_request(kind)
                request["evidenceLedger"]["entries"].append(
                    {
                        **request["evidenceLedger"]["entries"][0],
                        "kind": "review",
                    }
                )
                result = self.build(request)
                self.assertNotEqual(result["status"], "ready")
                self.assertIn("evidence-ledger-entry-id-duplicate", self.codes(result))
                self.assertIsNone(result["reviewBrief"])

    def test_candidate_bound_checks_require_current_candidate_provenance(self) -> None:
        for kind, role in (
            ("targeted-review", "targeted_reviewer"),
            ("specialist-review", "targeted_reviewer"),
            ("targeted-closure", "targeted_reviewer"),
            ("holistic-complete-diff-review", "reviewer"),
        ):
            with self.subTest(kind=kind, provenance="missing"):
                missing = self.candidate_request(kind, role)
                del missing["executedChecks"][0]["executedOnCandidateId"]
                missing_result = self.build(missing)
                self.assertNotEqual(missing_result["status"], "ready")
                self.assertIn("executedChecks-candidate-required", self.codes(missing_result))
                self.assertIsNone(missing_result["reviewBrief"])

            with self.subTest(kind=kind, provenance="mismatch"):
                mismatched = self.candidate_request(kind, role)
                mismatched["executedChecks"][0]["executedOnCandidateId"] = "another-candidate"
                mismatched_result = self.build(mismatched)
                self.assertNotEqual(mismatched_result["status"], "ready")
                self.assertIn("executedChecks-candidate-mismatch", self.codes(mismatched_result))
                self.assertIsNone(mismatched_result["reviewBrief"])

    def test_ready_render_is_deterministic(self) -> None:
        request = self.ordinary()
        first = self.build(request)
        second = self.build(copy.deepcopy(request))
        self.assertEqual(first["reviewBrief"], second["reviewBrief"])

    def test_missing_review_target_never_falls_back_to_current_directory(self) -> None:
        request = self.ordinary()
        del request["reviewTarget"]
        with self.chdir(self.repository):
            result = self.build(request)
        self.assertEqual(result["status"], "invalid")
        self.assertIn("review-target-required", self.codes(result))
        self.assertIsNone(result["reviewBrief"])

    def test_nonexistent_and_non_root_targets_are_invalid(self) -> None:
        request = self.ordinary()
        request["reviewTarget"] = str(self.root / "missing")
        self.assertIn("review-target-unavailable", self.codes(self.build(request)))
        request["reviewTarget"] = str(self.repository / "src")
        self.assertIn("review-target-invalid", self.codes(self.build(request)))

    def test_scope_escape_is_invalid(self) -> None:
        request = self.ordinary()
        request["includedScope"] = ["../outside"]
        result = self.build(request)
        self.assertEqual(result["status"], "invalid")
        self.assertIn("scope-outside-review-target", self.codes(result))

        root_scope = self.ordinary()
        root_scope["includedScope"] = ["/"]
        root_result = self.build(root_scope)
        self.assertEqual(root_result["status"], "invalid")
        self.assertIn("scope-outside-review-target", self.codes(root_result))

        overlap = self.ordinary()
        overlap["excludedScope"] = ["src"]
        overlap_result = self.build(overlap)
        self.assertEqual(overlap_result["status"], "invalid")
        self.assertIn("scope-included-excluded-overlap", self.codes(overlap_result))

    def test_nested_repository_scope_requires_a_separate_brief(self) -> None:
        nested = self.repository / "nested"
        nested.mkdir()
        self.git("init", cwd=nested)
        request = self.ordinary()
        request["includedScope"] = ["nested"]
        result = self.build(request)
        self.assertIn("mixed-repository-scope", self.codes(result))

    def test_snapshot_target_and_repository_mismatch_block_brief(self) -> None:
        request = self.candidate_request("specialist-review")
        request["candidateSnapshot"]["targetRoot"] = str(self.session_workspace)
        result = self.build(request)
        self.assertEqual(result["status"], "invalid")
        self.assertIn("candidate-target-mismatch", self.codes(result))
        self.assertIsNone(result["reviewBrief"])

    def test_tampered_snapshot_is_mismatch(self) -> None:
        request = self.candidate_request("specialist-review")
        request["candidateSnapshot"]["candidateSourceIdentity"]["rawDiffDigest"] = "sha256:" + "0" * 64
        result = self.build(request)
        self.assertEqual(result["status"], "invalid")
        self.assertEqual(result["candidatePreflight"]["result"], "mismatch")
        self.assertIn("candidate-verification-mismatch", self.codes(result))

    def test_manifest_snapshot_detects_live_source_change(self) -> None:
        request = self.candidate_request("specialist-review")
        (self.repository / "src" / "feature.py").write_text("VALUE = 3\n", encoding="utf-8")
        result = self.build(request)
        self.assertEqual(result["candidatePreflight"]["result"], "mismatch")
        self.assertIsNone(result["reviewBrief"])

    def test_creator_tree_snapshot_survives_live_source_change(self) -> None:
        request = self.candidate_request("specialist-review")
        request["candidateSnapshot"] = self.snapshot(mode="creator-tree")
        (self.repository / "src" / "feature.py").write_text("VALUE = 4\n", encoding="utf-8")
        result = self.build(request)
        self.assertEqual(result["status"], "ready", result)
        self.assertEqual(result["candidatePreflight"]["result"], "verified")

    def test_role_mismatch_is_invalid_for_ordinary_and_high_risk_reviews(self) -> None:
        ordinary = self.ordinary()
        ordinary["reviewerRole"] = "targeted_reviewer"
        self.assertIn("review-role-mismatch", self.codes(self.build(ordinary)))
        high_risk = self.candidate_request("targeted-review")
        high_risk["reviewerRole"] = "slice_reviewer"
        self.assertIn("review-role-mismatch", self.codes(self.build(high_risk)))

    def test_deadline_must_be_present_absolute_and_unexpired(self) -> None:
        for value, code in (
            (None, "deadline-required"),
            ("2030-01-01T00:30:00", "deadline-not-absolute"),
            ((self.now - timedelta(seconds=1)).isoformat(), "deadline-expired"),
        ):
            with self.subTest(value=value):
                request = self.ordinary()
                request["deadline"] = value
                result = self.build(request)
                self.assertIn(code, self.codes(result))
                self.assertIsNone(result["reviewBrief"])

    def test_review_entry_id_defaults_to_unassigned_without_generation(self) -> None:
        result = self.build(self.ordinary())
        self.assertEqual(result["reviewEntryId"], "unassigned")
        self.assertIn('"reviewEntryId": "unassigned"', result["reviewBrief"])

    def test_closure_invariant_meaning_mismatch_is_invalid(self) -> None:
        request = self.candidate_request("specialist-review")
        request["matrixCells"][0]["consumerImpact"] = "different impact"
        result = self.build(request)
        self.assertIn("closure-invariant-matrix-mismatch", self.codes(result))
        self.assertEqual(result["candidatePreflight"]["result"], "mismatch")

    def test_closure_invariant_definition_drift_is_invalid(self) -> None:
        request = self.candidate_request("specialist-review")
        request["invariants"][0] = {
            **request["invariants"][0],
            "definition": "meaning changed after closure planning",
        }
        result = self.build(request)
        self.assertEqual(result["status"], "invalid")
        self.assertIn("closure-invariant-candidate-mismatch", self.codes(result))
        self.assertEqual(result["candidatePreflight"]["result"], "mismatch")

    def test_empty_included_scope_and_escaping_supported_scope_are_rejected(self) -> None:
        empty = self.candidate_request("specialist-review")
        empty["includedScope"] = []
        empty_result = self.build(empty)
        self.assertNotEqual(empty_result["status"], "ready")
        self.assertIn("included-scope-required", self.codes(empty_result))

        escaping = self.candidate_request("specialist-review")
        escaping["supportedContractScope"] = ["../outside"]
        escaping_result = self.build(escaping)
        self.assertNotEqual(escaping_result["status"], "ready")
        self.assertIn("scope-outside-review-target", self.codes(escaping_result))

    def test_invariant_and_check_scopes_must_stay_in_supported_contract_scope(self) -> None:
        request = self.candidate_request("specialist-review")
        request["executedChecks"][0]["scope"] = ["other"]
        result = self.build(request)
        self.assertNotEqual(result["status"], "ready")
        self.assertIn("executedChecks-scope-outside-supported-scope", self.codes(result))

    def test_contract_records_cannot_omit_the_entire_invariant_scope_tuple(self) -> None:
        request = json.loads(json.dumps(self.candidate_request("specialist-review")))
        for field in ("invariants", "matrixCells", "preImplementationInvariants", "executedChecks"):
            request[field][0].pop("scope")
        result = self.build(request)
        self.assertNotEqual(result["status"], "ready")
        for field in ("invariants", "matrixCells", "preImplementationInvariants", "executedChecks"):
            self.assertIn(f"{field}-scope-required", self.codes(result))

    def test_contract_records_require_all_inherited_meaning_fields(self) -> None:
        request = json.loads(json.dumps(self.candidate_request("specialist-review")))
        for field in ("invariants", "matrixCells", "preImplementationInvariants", "executedChecks"):
            request[field][0].pop("failureMode")
        result = self.build(request)
        self.assertNotEqual(result["status"], "ready")
        for field in ("invariants", "matrixCells", "preImplementationInvariants", "executedChecks"):
            self.assertIn(f"{field}-failureMode-required", self.codes(result))

    def test_specialist_fields_require_kind_specific_types(self) -> None:
        request = self.candidate_request("specialist-review")
        request.pop("preImplementationInvariants")
        request["evidenceLedger"] = 1
        request["assignedLens"] = 1
        request["closureMap"] = 1
        result = self.build(request)
        self.assertNotEqual(result["status"], "ready")
        self.assertIn("evidence-ledger-required", self.codes(result))
        self.assertIn("assigned-lens-required", self.codes(result))
        self.assertIn("closure-map-required", self.codes(result))

        wrong_lens = self.candidate_request("specialist-review")
        wrong_lens["assignedLens"] = "untriggered-lens"
        wrong_lens_result = self.build(wrong_lens)
        self.assertIn("assigned-lens-mismatch", self.codes(wrong_lens_result))

    def test_targeted_closure_sibling_paths_share_scope_validation(self) -> None:
        request = self.candidate_request("targeted-closure")
        request["includedSiblingPaths"] = ["../outside"]
        result = self.build(request)
        self.assertNotEqual(result["status"], "ready")
        self.assertIn("scope-outside-review-target", self.codes(result))

        outside_included = self.candidate_request("targeted-closure")
        outside_included["includedScope"] = ["tests"]
        outside_included["includedSiblingPaths"] = ["src"]
        outside_result = self.build(outside_included)
        self.assertIn("sibling-path-outside-included-scope", self.codes(outside_result))

        excluded = self.candidate_request("targeted-closure")
        excluded["includedScope"] = ["tests"]
        excluded["excludedScope"] = ["src"]
        excluded["includedSiblingPaths"] = ["src"]
        excluded_result = self.build(excluded)
        self.assertIn("sibling-path-overlaps-excluded-scope", self.codes(excluded_result))
        self.assertIsNone(excluded_result["reviewBrief"])

    def test_specialist_requires_trigger_class_and_current_candidate_evidence(self) -> None:
        missing_trigger = self.candidate_request("specialist-review")
        del missing_trigger["reviewTrigger"]["riskClass"]
        missing_trigger_result = self.build(missing_trigger)
        self.assertNotEqual(missing_trigger_result["status"], "ready")
        self.assertIn("review-trigger-class-invalid", self.codes(missing_trigger_result))
        self.assertIsNone(missing_trigger_result["reviewBrief"])

        stale_evidence = self.candidate_request("specialist-review")
        stale_evidence["evidenceLedger"]["entries"][0].update(
            candidateId="another-candidate",
            status="superseded",
        )
        stale_evidence_result = self.build(stale_evidence)
        self.assertNotEqual(stale_evidence_result["status"], "ready")
        self.assertIn("evidence-ledger-entry-not-current", self.codes(stale_evidence_result))
        self.assertIn("evidence-ledger-entry-candidate-mismatch", self.codes(stale_evidence_result))
        self.assertIsNone(stale_evidence_result["reviewBrief"])

        conflicting_provenance = self.candidate_request("specialist-review")
        conflicting_provenance["evidenceLedger"]["entries"][0]["executedOnCandidateId"] = "another-candidate"
        conflicting_result = self.build(conflicting_provenance)
        self.assertNotEqual(conflicting_result["status"], "ready")
        self.assertIn("evidence-ledger-entry-candidate-mismatch", self.codes(conflicting_result))
        self.assertIsNone(conflicting_result["reviewBrief"])

    def test_malformed_candidate_snapshot_returns_structured_diagnostics(self) -> None:
        request = self.candidate_request("specialist-review")
        request["candidateSnapshot"]["targetRoot"] = None
        result = self.build(request)
        self.assertEqual(result["status"], "validation-gap")
        self.assertEqual(result["candidatePreflight"]["result"], "validation-gap")
        self.assertIn("candidate-snapshot-target-invalid", self.codes(result))
        self.assertIsNone(result["reviewBrief"])

        input_path = self.root / "malformed-candidate-input.json"
        input_path.write_text(json.dumps(request), encoding="utf-8")
        completed = subprocess.run(
            [sys.executable, str(SCRIPT), "--input", str(input_path)],
            capture_output=True,
            check=False,
        )
        output = json.loads(completed.stdout.decode("utf-8"))
        self.assertEqual(completed.returncode, 2, completed.stderr.decode("utf-8"))
        self.assertEqual(output["status"], "validation-gap")
        self.assertIsNone(output["reviewBrief"])

        malformed_candidate_id = self.candidate_request("specialist-review")
        malformed_candidate_id["candidateId"] = []
        malformed_candidate_id["candidateSnapshot"]["candidateId"] = []
        malformed_candidate_id["evidenceLedger"]["entries"][0]["candidateId"] = []
        malformed_candidate_id_result = self.build(malformed_candidate_id)
        self.assertEqual(malformed_candidate_id_result["status"], "validation-gap")
        self.assertEqual(malformed_candidate_id_result["candidatePreflight"]["result"], "validation-gap")
        self.assertIn("candidate-id-invalid", self.codes(malformed_candidate_id_result))
        self.assertIn("candidate-snapshot-id-invalid", self.codes(malformed_candidate_id_result))
        self.assertIn("evidence-ledger-entry-candidate-mismatch", self.codes(malformed_candidate_id_result))
        self.assertIsNone(malformed_candidate_id_result["reviewBrief"])

        input_path.write_text(json.dumps(malformed_candidate_id), encoding="utf-8")
        completed = subprocess.run(
            [sys.executable, str(SCRIPT), "--input", str(input_path)],
            capture_output=True,
            check=False,
        )
        output = json.loads(completed.stdout.decode("utf-8"))
        self.assertEqual(completed.returncode, 2, completed.stderr.decode("utf-8"))
        self.assertEqual(output["status"], "validation-gap")
        self.assertIsNone(output["reviewBrief"])

        malformed_scope = self.candidate_request("specialist-review")
        malformed_scope["candidateSnapshot"]["candidateSourceIdentity"]["includedScope"] = 1
        malformed_scope_result = self.build(malformed_scope)
        self.assertEqual(malformed_scope_result["status"], "validation-gap")
        self.assertIn("candidate-source-included-scope-invalid", self.codes(malformed_scope_result))
        self.assertIsNone(malformed_scope_result["reviewBrief"])

        input_path.write_text(json.dumps(malformed_scope), encoding="utf-8")
        completed = subprocess.run(
            [sys.executable, str(SCRIPT), "--input", str(input_path)],
            capture_output=True,
            check=False,
        )
        output = json.loads(completed.stdout.decode("utf-8"))
        self.assertEqual(completed.returncode, 2, completed.stderr.decode("utf-8"))
        self.assertEqual(output["status"], "validation-gap")
        self.assertIsNone(output["reviewBrief"])

    def test_kind_specific_missing_field_is_diagnostic(self) -> None:
        request = self.candidate_request("targeted-closure")
        del request["findingFamily"]
        result = self.build(request)
        self.assertIn("finding-family-required", self.codes(result))
        self.assertEqual(result["candidatePreflight"]["result"], "validation-gap")
        self.assertIsNone(result["reviewBrief"])

    def test_holistic_requires_run_and_rejects_prior_review_conclusions(self) -> None:
        request = self.candidate_request("holistic-complete-diff-review", "reviewer")
        request["fullReviewGate"] = "skip"
        request["priorFindings"] = ["do not disclose"]
        result = self.build(request)
        self.assertIn("full-review-gate-not-run", self.codes(result))
        self.assertIn("holistic-input-contamination", self.codes(result))

    def test_holistic_artifacts_must_match_candidate_identity(self) -> None:
        foreign_diff = self.candidate_request("holistic-complete-diff-review", "reviewer")
        foreign_diff["completeRawDiff"]["digest"] = "sha256:" + "0" * 64
        foreign_result = self.build(foreign_diff)
        self.assertIn("holistic-raw-diff-mismatch", self.codes(foreign_result))
        self.assertIsNone(foreign_result["reviewBrief"])

        extra_raw_field = self.candidate_request("holistic-complete-diff-review", "reviewer")
        extra_raw_field["completeRawDiff"]["unverified"] = "value"
        extra_raw_result = self.build(extra_raw_field)
        self.assertIn("complete-raw-diff-required", self.codes(extra_raw_result))
        self.assertIsNone(extra_raw_result["reviewBrief"])

        (self.repository / "tests" / "untracked.txt").write_text("review me\n", encoding="utf-8")
        untracked = self.candidate_request("holistic-complete-diff-review", "reviewer")
        self.assertTrue(untracked["verifiedUntrackedContent"])
        untracked["verifiedUntrackedContent"] = []
        missing_result = self.build(untracked)
        self.assertIn("holistic-untracked-content-mismatch", self.codes(missing_result))
        self.assertIsNone(missing_result["reviewBrief"])

        tampered = self.candidate_request("holistic-complete-diff-review", "reviewer")
        tampered["verifiedUntrackedContent"][0]["contentDigest"] = "sha256:" + "0" * 64
        tampered_result = self.build(tampered)
        self.assertIn("holistic-untracked-content-mismatch", self.codes(tampered_result))
        self.assertIsNone(tampered_result["reviewBrief"])

        extra_untracked_field = self.candidate_request("holistic-complete-diff-review", "reviewer")
        extra_untracked_field["verifiedUntrackedContent"][0]["unverified"] = "value"
        extra_untracked_result = self.build(extra_untracked_field)
        self.assertIn("verified-untracked-content-required", self.codes(extra_untracked_result))
        self.assertIsNone(extra_untracked_result["reviewBrief"])

    def test_schema_meaning_fields_and_check_results_are_typed(self) -> None:
        malformed = self.candidate_request("specialist-review")
        malformed["acceptedContract"]["anchors"] = [1]
        malformed["acceptedContract"]["meaning"] = []
        malformed["reviewContract"]["revision"] = 1
        malformed["reviewContract"]["recipe"] = []
        malformed["executedChecks"][0].pop("result")
        result = self.build(malformed)
        self.assertNotEqual(result["status"], "ready")
        for code in (
            "accepted-contract-anchors-required",
            "accepted-contract-meaning-required",
            "review-contract-revision-required",
            "review-contract-recipe-required",
            "executedChecks-result-required",
        ):
            self.assertIn(code, self.codes(result))
        self.assertIsNone(result["reviewBrief"])

    def test_holistic_ready_brief_omits_prior_review_and_closure_fields(self) -> None:
        result = self.build(self.candidate_request("holistic-complete-diff-review", "reviewer"))
        self.assertEqual(result["status"], "ready", result)
        for field in BRIEF.HOLISTIC_FORBIDDEN_FIELDS:
            self.assertNotIn(f'"{field}"', result["reviewBrief"])

    def test_ordinary_slice_rejects_unnecessary_candidate(self) -> None:
        request = self.ordinary()
        request["candidateId"] = "candidate-1"
        request["candidateSnapshot"] = self.snapshot()
        result = self.build(request)
        self.assertIn("ordinary-slice-candidate-not-allowed", self.codes(result))

    def test_cli_emits_schema_version_one_json_and_nonzero_for_invalid(self) -> None:
        input_path = self.root / "brief-input.json"
        input_path.write_text(json.dumps(self.ordinary()), encoding="utf-8")
        completed = subprocess.run(
            [sys.executable, str(SCRIPT), "--input", str(input_path)],
            capture_output=True,
            check=False,
        )
        output = json.loads(completed.stdout.decode("utf-8"))
        self.assertEqual(completed.returncode, 0, completed.stderr.decode("utf-8"))
        self.assertEqual(output["schemaVersion"], 1)
        self.assertEqual(output["status"], "ready")

    def test_cli_accepts_input_json_from_stdin(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(SCRIPT), "--input", "-"],
            input=json.dumps(self.ordinary()).encode("utf-8"),
            capture_output=True,
            check=False,
        )
        output = json.loads(completed.stdout.decode("utf-8"))
        self.assertEqual(completed.returncode, 0, completed.stderr.decode("utf-8"))
        self.assertEqual(output["status"], "ready")

    def test_reviewer_roles_require_explicit_target_and_refuse_invalid_briefs(self) -> None:
        agents = Path(__file__).parents[3] / "agents"
        for name in ("slice_reviewer.toml", "targeted_reviewer.toml", "reviewer.toml"):
            content = (agents / name).read_text(encoding="utf-8")
            with self.subTest(name=name):
                self.assertIn("review target", content.lower())
                self.assertIn("current directory", content.lower())
                self.assertIn("substantive review", content.lower())

    def test_builder_does_not_own_provider_session_launch(self) -> None:
        skill = Path(__file__).parents[1] / "SKILL.md"
        content = skill.read_text(encoding="utf-8")
        self.assertIn("builderはsession launcher、provider routing、hookを所有せず", content)
        self.assertIn("reviewerが受信入力とCandidateを独立検証", content)
        self.assertNotIn("reviewBrief=null`のままsubagentを起動しない", content)

    def test_review_kind_machine_tokens_are_consistent(self) -> None:
        skill = (Path(__file__).parents[1] / "SKILL.md").read_text(encoding="utf-8")
        reviewer = (Path(__file__).parents[3] / "agents" / "reviewer.toml").read_text(encoding="utf-8")
        expected = "holistic-complete-diff-review"
        self.assertIn(
            "Review kind: targeted-review | specialist-review | targeted-closure | holistic-complete-diff-review",
            skill,
        )
        self.assertIn(f"reviewKind={expected}", reviewer)
        result = self.build(self.candidate_request(expected, "reviewer"))
        self.assertEqual(result["status"], "ready", result)
        rendered = json.loads(result["reviewBrief"].removeprefix("Review Brief\n\n"))
        self.assertEqual(rendered["reviewKind"], expected)


if __name__ == "__main__":
    unittest.main()
