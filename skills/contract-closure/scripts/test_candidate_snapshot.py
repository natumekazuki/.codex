from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPT = Path(__file__).with_name("candidate_snapshot.py")
SPEC = importlib.util.spec_from_file_location("candidate_snapshot", SCRIPT)
assert SPEC and SPEC.loader
SNAPSHOT = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = SNAPSHOT
SPEC.loader.exec_module(SNAPSHOT)


class CandidateSnapshotTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.repository = self.root / "repository"
        self.artifacts = self.root / "artifacts"
        self.repository.mkdir()
        self.artifacts.mkdir()
        self.git("init")
        self.git("config", "user.name", "Candidate Test")
        self.git("config", "user.email", "candidate@example.invalid")
        (self.repository / "tracked.txt").write_bytes(b"base\n")
        self.git("add", "tracked.txt")
        self.git("commit", "-m", "base")

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

    def args(self, **overrides) -> argparse.Namespace:
        values = {
            "candidate_id": "candidate-1",
            "target": self.repository,
            "base_ref": "HEAD",
            "include": [],
            "exclude": [],
            "mode": None,
            "creator_tree_reason": None,
            "allow_manifest_fallback": False,
            "git_object_write_authorized": False,
            "writable_scope": [],
            "artifact_dir": self.artifacts,
            "output": None,
        }
        values.update(overrides)
        return argparse.Namespace(**values)

    def creator_args(self, **overrides) -> argparse.Namespace:
        common_dir = Path(self.git("rev-parse", "--git-common-dir"))
        if not common_dir.is_absolute():
            common_dir = (self.repository / common_dir).resolve()
        values = {
            "mode": "creator-tree",
            "creator_tree_reason": "review must continue after live worktree changes",
            "git_object_write_authorized": True,
            "writable_scope": [common_dir],
        }
        values.update(overrides)
        return self.args(**values)

    def manifest_paths(self, result: dict) -> dict[str, dict]:
        return {
            record["pathText"]: record
            for record in result["candidateSourceIdentity"]["manifest"]["records"]
        }

    def test_unspecified_mode_uses_manifest_without_creator_preflight(self) -> None:
        with mock.patch.object(
            SNAPSHOT, "creator_preflight", side_effect=AssertionError("must not explore")
        ):
            result = SNAPSHOT.create_candidate(self.args())

        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["creation"]["selectedMode"], "manifest-digest")
        self.assertFalse(result["creation"]["authority"]["capabilityExplored"])

    def test_creator_tree_requires_an_explicit_reason(self) -> None:
        result = SNAPSHOT.create_candidate(self.args(mode="creator-tree"))

        self.assertEqual(result["status"], "invalid")
        self.assertEqual(result["diagnostics"][0]["code"], "creator-tree-reason-required")

    def test_creator_tree_captures_tracked_untracked_and_deleted_paths(self) -> None:
        (self.repository / "tracked.txt").write_bytes(b"changed\n")
        (self.repository / "untracked.bin").write_bytes(b"\x00candidate\xff")
        (self.repository / "deleted.txt").write_text("delete me", encoding="utf-8")
        self.git("add", "deleted.txt")
        self.git("commit", "-m", "add deletion target")
        (self.repository / "deleted.txt").unlink()

        result = SNAPSHOT.create_candidate(self.creator_args())

        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["creation"]["selectedMode"], "creator-tree")
        paths = self.manifest_paths(result)
        self.assertEqual(paths["tracked.txt"]["objectType"], "blob")
        self.assertEqual(paths["untracked.bin"]["objectType"], "blob")
        self.assertTrue(paths["deleted.txt"]["deletionMarker"])
        self.assertTrue(result["creation"]["cleanup"]["succeeded"])
        self.assertTrue(result["creation"]["normalIndexPostcondition"]["verified"])

    def test_creator_tree_rejects_temporary_index_inside_target_before_write(self) -> None:
        inside = self.repository / ".candidate-artifacts"
        with mock.patch.object(SNAPSHOT, "index_tree", side_effect=AssertionError("write started")):
            result = SNAPSHOT.create_candidate(
                self.creator_args(artifact_dir=inside, allow_manifest_fallback=False)
            )

        self.assertEqual(result["status"], "validation-gap")
        self.assertEqual(result["diagnostics"][0]["code"], "temporary-index-unavailable")

    def test_inside_target_temporary_index_can_fallback_before_write(self) -> None:
        inside = self.repository / ".candidate-artifacts"
        with mock.patch.object(SNAPSHOT, "index_tree", side_effect=AssertionError("write started")):
            result = SNAPSHOT.create_candidate(
                self.creator_args(artifact_dir=inside, allow_manifest_fallback=True)
            )

        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["creation"]["selectedMode"], "manifest-digest")
        self.assertEqual(result["creation"]["fallbackReason"], "temporary-index-unavailable")

    def test_creator_tree_verification_is_independent_of_live_worktree(self) -> None:
        (self.repository / "tracked.txt").write_bytes(b"candidate\n")
        result = SNAPSHOT.create_candidate(self.creator_args())
        self.assertEqual(result["status"], "ready")

        (self.repository / "tracked.txt").write_bytes(b"later work\n")
        verification = SNAPSHOT.verify_candidate(result)

        self.assertEqual(verification["status"], "verified")

    def test_successful_creator_verification_runs_only_read_only_git_commands(self) -> None:
        (self.repository / "tracked.txt").write_bytes(b"candidate\n")
        result = SNAPSHOT.create_candidate(self.creator_args())
        commands: list[list[str]] = []
        original = SNAPSHOT.Git.run

        def recording_run(instance, args, **kwargs):
            commands.append(list(args))
            return original(instance, args, **kwargs)

        with mock.patch.object(SNAPSHOT.Git, "run", new=recording_run):
            verification = SNAPSHOT.verify_candidate(result)

        self.assertEqual(verification["status"], "verified")
        prohibited = {"read-tree", "write-tree", "hash-object", "update-index", "add"}
        self.assertFalse(any(command and command[0] in prohibited for command in commands))

    def test_manifest_verification_detects_live_worktree_change(self) -> None:
        (self.repository / "tracked.txt").write_bytes(b"candidate\n")
        result = SNAPSHOT.create_candidate(self.args())
        self.assertEqual(result["status"], "ready")

        (self.repository / "tracked.txt").write_bytes(b"later work\n")
        verification = SNAPSHOT.verify_candidate(result)

        self.assertEqual(verification["status"], "mismatch")
        self.assertEqual(verification["diagnostics"][0]["code"], "candidate-source-mismatch")

    def test_ambient_git_config_does_not_change_identity_recipe(self) -> None:
        (self.repository / "tracked.txt").write_bytes(b"candidate\n")
        result = SNAPSHOT.create_candidate(self.args())
        hostile = {
            "GIT_CONFIG_COUNT": "2",
            "GIT_CONFIG_KEY_0": "core.abbrev",
            "GIT_CONFIG_VALUE_0": "12",
            "GIT_CONFIG_KEY_1": "diff.noprefix",
            "GIT_CONFIG_VALUE_1": "true",
        }

        with mock.patch.dict(os.environ, hostile):
            verification = SNAPSHOT.verify_candidate(result)

        self.assertEqual(verification["status"], "verified")

    def test_missing_write_authority_falls_back_only_when_allowed(self) -> None:
        denied = self.creator_args(
            git_object_write_authorized=False,
            writable_scope=[],
            allow_manifest_fallback=False,
        )
        gap = SNAPSHOT.create_candidate(denied)
        fallback = SNAPSHOT.create_candidate(
            self.creator_args(
                git_object_write_authorized=False,
                writable_scope=[],
                allow_manifest_fallback=True,
            )
        )

        self.assertEqual(gap["status"], "validation-gap")
        self.assertIsNone(gap["candidateSourceIdentity"])
        self.assertEqual(gap["diagnostics"][0]["code"], "git-object-write-not-authorized")
        self.assertEqual(fallback["status"], "ready")
        self.assertEqual(fallback["creation"]["selectedMode"], "manifest-digest")
        self.assertEqual(fallback["creation"]["fallbackReason"], "git-object-write-not-authorized")

    def test_missing_base_object_is_not_treated_as_a_fallback_reason(self) -> None:
        result = SNAPSHOT.create_candidate(
            self.creator_args(base_ref="refs/heads/does-not-exist", allow_manifest_fallback=True)
        )

        self.assertEqual(result["status"], "validation-gap")
        self.assertEqual(result["creation"]["fallbackReason"], "none")
        self.assertEqual(result["diagnostics"][0]["code"], "git-command-failed")

    def test_common_dir_outside_writable_scope_does_not_start_writes(self) -> None:
        with mock.patch.object(SNAPSHOT, "index_tree", side_effect=AssertionError("write started")):
            result = SNAPSHOT.create_candidate(
                self.creator_args(writable_scope=[self.artifacts])
            )

        self.assertEqual(result["status"], "validation-gap")
        self.assertEqual(result["diagnostics"][0]["code"], "git-common-dir-outside-writable-scope")

    def test_unconfirmed_object_database_capability_does_not_start_git_write(self) -> None:
        with (
            mock.patch.object(SNAPSHOT.os, "access", return_value=False),
            mock.patch.object(SNAPSHOT, "index_tree", side_effect=AssertionError("write started")),
        ):
            result = SNAPSHOT.create_candidate(self.creator_args())

        self.assertEqual(result["status"], "validation-gap")
        self.assertEqual(result["diagnostics"][0]["code"], "creator-tree-capability-unconfirmed")

    def test_temporary_index_unavailable_can_fallback_before_git_write(self) -> None:
        with (
            mock.patch.object(SNAPSHOT.tempfile, "mkstemp", side_effect=OSError("denied")),
            mock.patch.object(SNAPSHOT, "index_tree", side_effect=AssertionError("write started")),
        ):
            result = SNAPSHOT.create_candidate(
                self.creator_args(allow_manifest_fallback=True)
            )

        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["creation"]["fallbackReason"], "temporary-index-unavailable")

    def test_status_preflight_failure_never_attempts_a_git_write(self) -> None:
        with (
            mock.patch.object(SNAPSHOT, "status_snapshot", side_effect=SNAPSHOT.SnapshotError("status-failed", "injected")),
            mock.patch.object(SNAPSHOT, "index_tree", side_effect=AssertionError("write started")),
        ):
            result = SNAPSHOT.create_candidate(self.creator_args())

        self.assertEqual(result["status"], "validation-gap")
        self.assertEqual(result["diagnostics"][0]["code"], "creator-tree-capability-unconfirmed")
        self.assertFalse(result["creation"]["authority"].get("writeStarted", False))

    def test_failure_after_write_start_never_falls_back(self) -> None:
        original = SNAPSHOT.Git.run

        def fail_read_tree(instance, args, **kwargs):
            if args and args[0] == "read-tree":
                raise SNAPSHOT.SnapshotError("injected-tree-failure", "injected")
            return original(instance, args, **kwargs)

        with mock.patch.object(SNAPSHOT.Git, "run", new=fail_read_tree):
            result = SNAPSHOT.create_candidate(
                self.creator_args(allow_manifest_fallback=True)
            )

        self.assertEqual(result["status"], "validation-gap")
        self.assertIsNone(result["candidateSourceIdentity"])
        self.assertEqual(result["creation"]["selectedMode"], "none")
        self.assertEqual(result["creation"]["fallbackReason"], "none")
        self.assertTrue(result["creation"]["authority"]["writeStarted"])

    def test_cleanup_failure_prevents_candidate_issue(self) -> None:
        with mock.patch.object(
            SNAPSHOT,
            "cleanup_index",
            return_value={"attempted": True, "succeeded": False, "failures": ["injected"]},
        ):
            result = SNAPSHOT.create_candidate(self.creator_args())

        self.assertEqual(result["status"], "validation-gap")
        self.assertIsNone(result["candidateSourceIdentity"])
        self.assertEqual(result["diagnostics"][0]["code"], "temporary-index-cleanup-failed")

    def test_normal_index_postcondition_mismatch_prevents_candidate_issue(self) -> None:
        with mock.patch.object(
            SNAPSHOT,
            "creator_postcondition",
            return_value={"verified": False, "diagnostic": "injected"},
        ):
            result = SNAPSHOT.create_candidate(self.creator_args())

        self.assertEqual(result["status"], "validation-gap")
        self.assertIsNone(result["candidateSourceIdentity"])
        self.assertEqual(result["diagnostics"][0]["code"], "normal-index-postcondition-mismatch")

    def test_inherited_git_index_redirect_cannot_replace_the_normal_index(self) -> None:
        redirected = self.artifacts / "caller-index"
        with mock.patch.dict(os.environ, {"GIT_INDEX_FILE": str(redirected)}):
            result = SNAPSHOT.create_candidate(self.creator_args())

        self.assertEqual(result["status"], "ready")
        postcondition = result["creation"]["normalIndexPostcondition"]
        self.assertTrue(postcondition["verified"])
        self.assertEqual(
            postcondition["before"]["indexTreeOid"],
            self.git("rev-parse", "HEAD^{tree}"),
        )
        self.assertFalse(redirected.exists())

    def test_scope_cleanliness_reports_changes_outside_declared_scope(self) -> None:
        (self.repository / "tracked.txt").write_bytes(b"candidate\n")
        (self.repository / "outside.txt").write_bytes(b"outside\n")

        result = SNAPSHOT.create_candidate(self.args(include=["tracked.txt"]))

        self.assertEqual(set(self.manifest_paths(result)), {"tracked.txt"})
        cleanliness = result["supportedScopeCleanliness"]
        self.assertEqual(cleanliness["result"], "outside-scope-changes-present")
        self.assertEqual(cleanliness["outsideScopePaths"][0]["pathText"], "outside.txt")

    def test_absolute_and_drive_qualified_scopes_are_rejected(self) -> None:
        for value in ("/", "/tmp/source", r"C:\source", "C:source", r"\\server\share"):
            with self.subTest(value=value):
                result = SNAPSHOT.create_candidate(self.args(include=[value]))
                self.assertEqual(result["status"], "invalid")
                self.assertEqual(result["diagnostics"][0]["code"], "invalid-source-scope")

    def test_missing_candidate_tree_is_a_validation_gap_without_recreation(self) -> None:
        result = SNAPSHOT.create_candidate(self.creator_args())
        identity = result["candidateSourceIdentity"]
        identity["candidateTreeOid"] = "f" * 40

        with mock.patch.object(SNAPSHOT.Git, "run", wraps=SNAPSHOT.Git.run) as run:
            verification = SNAPSHOT.verify_candidate(result)

        self.assertEqual(verification["status"], "validation-gap")
        write_commands = {"read-tree", "write-tree", "hash-object", "update-index", "add"}
        for call in run.call_args_list:
            command = call.args[1] if len(call.args) > 1 else []
            self.assertFalse(command and command[0] in write_commands)

    def test_declared_raw_diff_recipe_is_part_of_source_identity(self) -> None:
        result = SNAPSHOT.create_candidate(self.args())
        result["candidateSourceIdentity"]["rawDiffCommand"].append("--tampered")

        verification = SNAPSHOT.verify_candidate(result)

        self.assertEqual(verification["status"], "mismatch")
        self.assertFalse(verification["evidence"]["rawDiffCommand"])

    def test_declared_manifest_and_recipes_are_verified(self) -> None:
        (self.repository / "tracked.txt").write_bytes(b"candidate\n")
        result = SNAPSHOT.create_candidate(self.args())
        result["candidateSourceIdentity"]["manifest"]["records"][0]["contentDigest"] = "sha256:" + "0" * 64
        result["creationRecipe"]["builder"] = "tampered"
        result["readOnlyVerificationRecipe"]["writesGitMetadata"] = True
        result["creation"]["authority"]["gitObjectWriteAuthorized"] = True

        verification = SNAPSHOT.verify_candidate(result)

        self.assertEqual(verification["status"], "mismatch")
        self.assertFalse(verification["evidence"]["declaredManifest"])
        self.assertFalse(verification["evidence"]["creationRecipe"])
        self.assertFalse(verification["evidence"]["readOnlyVerificationRecipe"])
        self.assertFalse(verification["evidence"]["sourceIdentity"])

    def test_candidate_safety_fields_are_identity_bound_and_mode_checked(self) -> None:
        creator = SNAPSHOT.create_candidate(self.creator_args())
        self.assertNotIn("targetRoot", creator["creation"])
        self.assertNotIn("repositoryIdentity", creator["creation"])
        self.assertNotIn("supportedScopeCleanliness", creator["creation"])
        mutations = (
            lambda value: value["creation"]["cleanup"].update({"succeeded": False}),
            lambda value: value["creation"]["normalIndexPostcondition"].update({"verified": False}),
            lambda value: value["supportedScopeCleanliness"].update({"result": "tampered"}),
            lambda value: value["repositoryIdentity"].update({"gitCommonDir": "tampered"}),
        )

        for mutate in mutations:
            with self.subTest(mutate=mutate):
                candidate = copy.deepcopy(creator)
                mutate(candidate)
                verification = SNAPSHOT.verify_candidate(candidate)
                self.assertEqual(verification["status"], "mismatch")

        unsafe = copy.deepcopy(creator)
        unsafe["creation"]["cleanup"]["succeeded"] = False
        verification = SNAPSHOT.verify_candidate(unsafe)
        self.assertFalse(verification["evidence"]["creatorSafetyState"])

    def test_declared_verification_recipe_runs_from_its_recorded_working_directory(self) -> None:
        candidate_path = self.artifacts / "verification-candidate.json"
        result = SNAPSHOT.create_candidate(self.args())
        SNAPSHOT.write_result(result, candidate_path)
        recipe = result["readOnlyVerificationRecipe"]
        command = [str(candidate_path) if value == "<candidate-json>" else value for value in recipe["command"]]

        completed = subprocess.run(
            command,
            cwd=recipe["workingDirectory"],
            capture_output=True,
            check=False,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr.decode("utf-8"))
        self.assertEqual(json.loads(completed.stdout.decode("utf-8"))["status"], "verified")

    @unittest.skipIf(os.name == "nt", "executable-bit semantics are not portable on Windows")
    def test_manifest_records_mode_only_change(self) -> None:
        executable = self.repository / "tool.sh"
        executable.write_text("#!/bin/sh\n", encoding="utf-8")
        self.git("add", "tool.sh")
        self.git("commit", "-m", "add tool")
        executable.chmod(executable.stat().st_mode | stat.S_IXUSR)

        result = SNAPSHOT.create_candidate(self.args())

        record = self.manifest_paths(result)["tool.sh"]
        self.assertEqual(record["oldMode"], "100644")
        self.assertEqual(record["newMode"], "100755")

    def test_manifest_records_symlink_target_when_supported(self) -> None:
        link = self.repository / "link"
        try:
            link.symlink_to("tracked.txt")
        except OSError as exc:
            self.skipTest(f"symlink creation unavailable: {exc}")

        result = SNAPSHOT.create_candidate(self.args())

        record = self.manifest_paths(result)["link"]
        self.assertEqual(record["objectType"], "symlink")
        self.assertIn("symlinkTargetDigest", record)

    def test_manifest_uses_git_mode_for_materialized_symlink(self) -> None:
        self.git("config", "core.symlinks", "false")
        oid = subprocess.run(
            ["git", "hash-object", "-w", "--stdin"],
            cwd=self.repository,
            input=b"tracked.txt",
            capture_output=True,
            check=True,
        ).stdout.decode("ascii").strip()
        self.git("update-index", "--add", "--cacheinfo", f"120000,{oid},materialized-link")
        self.git("commit", "-m", "add materialized symlink")
        (self.repository / "materialized-link").write_bytes(b"other-target")

        result = SNAPSHOT.create_candidate(self.args())

        record = self.manifest_paths(result)["materialized-link"]
        self.assertEqual(record["newMode"], "120000")
        self.assertEqual(record["objectType"], "symlink")
        self.assertIn("symlinkTargetDigest", record)

    def test_creator_tree_records_submodule_oid(self) -> None:
        source = self.root / "submodule-source"
        source.mkdir()
        self.git("init", cwd=source)
        self.git("config", "user.name", "Candidate Test", cwd=source)
        self.git("config", "user.email", "candidate@example.invalid", cwd=source)
        (source / "file.txt").write_text("submodule", encoding="utf-8")
        self.git("add", "file.txt", cwd=source)
        self.git("commit", "-m", "submodule base", cwd=source)
        self.git("-c", "protocol.file.allow=always", "submodule", "add", str(source), "vendor/sub")
        self.git("commit", "-m", "add submodule")

        result = SNAPSHOT.create_candidate(self.creator_args(base_ref="HEAD^"))

        record = self.manifest_paths(result)["vendor/sub"]
        self.assertEqual(record["objectType"], "commit")
        self.assertEqual(record["submoduleOid"], self.git("rev-parse", "HEAD:vendor/sub"))

    def test_creator_manifest_declares_and_hashes_git_index_normalization(self) -> None:
        (self.repository / ".gitattributes").write_text("normalized.txt text eol=lf\n", encoding="utf-8")
        self.git("add", ".gitattributes")
        self.git("commit", "-m", "add attributes")
        (self.repository / "normalized.txt").write_bytes(b"line\r\n")

        manifest_result = SNAPSHOT.create_candidate(self.args())
        creator_result = SNAPSHOT.create_candidate(self.creator_args())
        manifest_record = self.manifest_paths(manifest_result)["normalized.txt"]
        creator_record = self.manifest_paths(creator_result)["normalized.txt"]

        self.assertEqual(
            manifest_record["contentDigest"],
            f"sha256:{hashlib.sha256(b'line\r\n').hexdigest()}",
        )
        self.assertEqual(
            creator_record["contentDigest"],
            f"sha256:{hashlib.sha256(b'line\n').hexdigest()}",
        )
        envelope = creator_result["candidateSourceIdentity"]["manifest"]
        self.assertIn("Git index clean filters", envelope["filterApplication"])
        self.assertIn("candidate tree", envelope["newlineNormalization"])

    def test_cli_writes_structured_output_outside_worktree(self) -> None:
        output = self.artifacts / "candidate.json"
        completed = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "create",
                "--candidate-id",
                "cli-candidate",
                "--target",
                str(self.repository),
                "--base-ref",
                "HEAD",
                "--artifact-dir",
                str(self.artifacts),
                "--output",
                str(output),
            ],
            capture_output=True,
            check=False,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr.decode())
        self.assertEqual(json.loads(output.read_text(encoding="utf-8"))["status"], "ready")


if __name__ == "__main__":
    unittest.main()
