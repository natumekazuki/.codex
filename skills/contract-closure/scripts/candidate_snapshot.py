#!/usr/bin/env python3
"""Build and verify Candidate source identities without touching the normal index."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import secrets
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Sequence


SCHEMA_VERSION = 1
CREATION_RECIPE_VERSION = 1
VERIFICATION_RECIPE_VERSION = 1
HASH_ALGORITHM = "sha256"
SAFE_GIT_OPTIONS = ["--no-optional-locks", "--no-replace-objects", "--no-lazy-fetch"]
FALLBACK_REASONS = {
    "git-object-write-not-authorized",
    "git-common-dir-outside-writable-scope",
    "temporary-index-unavailable",
    "creator-tree-capability-unconfirmed",
}
REPOSITORY_REDIRECT_ENV = {
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_COMMON_DIR",
    "GIT_DIR",
    "GIT_INDEX_FILE",
    "GIT_NAMESPACE",
    "GIT_OBJECT_DIRECTORY",
    "GIT_PREFIX",
    "GIT_WORK_TREE",
}


class SnapshotError(RuntimeError):
    def __init__(self, code: str, message: str, *, status: str = "validation-gap"):
        super().__init__(message)
        self.code = code
        self.status = status


@dataclass(frozen=True)
class Repository:
    target_root: Path
    git_dir: Path
    common_dir: Path
    object_format: str
    oid_length: int


@dataclass(frozen=True)
class Scope:
    included: tuple[str, ...]
    excluded: tuple[str, ...]

    def pathspecs(self) -> list[str]:
        values = [":(top)" if value == "." else f":(top,literal){value}" for value in self.included]
        values.extend(f":(top,exclude,literal){value}" for value in self.excluded)
        return values


class Git:
    def __init__(self, target: Path):
        self.target = target

    def run(
        self,
        args: Sequence[str],
        *,
        env: dict[str, str] | None = None,
        input_bytes: bytes | None = None,
    ) -> bytes:
        command = ["git", *SAFE_GIT_OPTIONS, "-C", str(self.target), *args]
        process_env = os.environ.copy()
        for name in tuple(process_env):
            if name in REPOSITORY_REDIRECT_ENV or name.startswith("GIT_CONFIG_"):
                process_env.pop(name, None)
        if env:
            process_env.update(env)
        completed = subprocess.run(
            command,
            input=input_bytes,
            capture_output=True,
            check=False,
            env=process_env,
        )
        if completed.returncode != 0:
            detail = completed.stderr.decode("utf-8", errors="replace").strip()
            raise SnapshotError(
                "git-command-failed",
                f"Git command failed ({' '.join(args)}): {detail or completed.returncode}",
            )
        return completed.stdout


def sha256(data: bytes) -> str:
    return f"{HASH_ALGORITHM}:{hashlib.sha256(data).hexdigest()}"


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def encode_path(path: bytes) -> dict[str, str | None]:
    try:
        text = path.decode("utf-8")
    except UnicodeDecodeError:
        text = None
    return {
        "pathBytesBase64": base64.b64encode(path).decode("ascii"),
        "pathText": text,
    }


def decode_path(record: dict[str, Any]) -> bytes:
    return base64.b64decode(record["pathBytesBase64"], validate=True)


def normalize_scope(values: Sequence[str], option: str, *, default: tuple[str, ...] = ()) -> tuple[str, ...]:
    normalized: list[str] = []
    for original in values or default:
        untrimmed = original.replace("\\", "/")
        if (
            not untrimmed
            or untrimmed.startswith("/")
            or re.match(r"^[A-Za-z]:", untrimmed)
        ):
            raise SnapshotError("invalid-source-scope", f"{option} must be repository-relative: {original}", status="invalid")
        value = untrimmed.rstrip("/") or "."
        path = PurePosixPath(value)
        if path.is_absolute() or value.startswith("/") or ".." in path.parts:
            raise SnapshotError("invalid-source-scope", f"{option} must be repository-relative: {original}", status="invalid")
        if value not in normalized:
            normalized.append(value)
    return tuple(normalized)


def is_within(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def resolve_repository(target: Path) -> tuple[Repository, Git]:
    target = target.resolve()
    git = Git(target)
    try:
        top = Path(os.fsdecode(git.run(["rev-parse", "--show-toplevel"]).rstrip(b"\r\n"))).resolve()
        git_dir_text = os.fsdecode(git.run(["rev-parse", "--git-dir"]).rstrip(b"\r\n"))
        common_text = os.fsdecode(git.run(["rev-parse", "--git-common-dir"]).rstrip(b"\r\n"))
        object_format = git.run(["rev-parse", "--show-object-format"]).decode("ascii").strip()
    except SnapshotError as exc:
        raise SnapshotError("repository-resolution-failed", str(exc), status="invalid") from exc
    if top != target:
        raise SnapshotError(
            "target-root-not-worktree-root",
            f"target root resolves to {target}, but Git worktree root is {top}",
            status="invalid",
        )
    git_dir = (target / git_dir_text).resolve() if not Path(git_dir_text).is_absolute() else Path(git_dir_text).resolve()
    common_dir = (target / common_text).resolve() if not Path(common_text).is_absolute() else Path(common_text).resolve()
    oid_length = {"sha1": 40, "sha256": 64}.get(object_format, 0)
    if oid_length == 0:
        raise SnapshotError("unsupported-object-format", f"unsupported Git object format: {object_format}")
    return Repository(target, git_dir, common_dir, object_format, oid_length), git


def single_oid(data: bytes, repository: Repository, label: str) -> str:
    text = data.decode("ascii", errors="strict").strip()
    if re.fullmatch(f"[0-9a-f]{{{repository.oid_length}}}", text) is None:
        raise SnapshotError("invalid-object-oid", f"{label} did not resolve to one {repository.object_format} OID")
    return text


def require_object(git: Git, oid: str, expected: str) -> None:
    actual = git.run(["cat-file", "-t", oid]).decode("ascii", errors="strict").strip()
    if actual != expected:
        raise SnapshotError("object-type-mismatch", f"{oid} is {actual}, expected {expected}")


def resolve_base(git: Git, repository: Repository, base_ref: str) -> tuple[str, str]:
    base_commit = single_oid(
        git.run(["rev-parse", "--verify", f"{base_ref}^{{commit}}"]).rstrip(b"\r\n"),
        repository,
        "base commit",
    )
    require_object(git, base_commit, "commit")
    base_tree = single_oid(
        git.run(["rev-parse", f"{base_commit}^{{tree}}"]).rstrip(b"\r\n"),
        repository,
        "base tree",
    )
    require_object(git, base_tree, "tree")
    return base_commit, base_tree


def parse_raw_records(raw: bytes) -> list[dict[str, Any]]:
    fields = raw.split(b"\0")
    records: list[dict[str, Any]] = []
    index = 0
    while index < len(fields) and fields[index]:
        header = fields[index]
        index += 1
        if index >= len(fields):
            raise SnapshotError("raw-diff-parse-failed", "raw diff ended before its path")
        path = fields[index]
        index += 1
        parts = header.split(b" ")
        if len(parts) != 5 or not parts[0].startswith(b":"):
            raise SnapshotError("raw-diff-parse-failed", "unexpected raw diff record")
        status = parts[4].decode("ascii", errors="strict")
        if status.startswith(("R", "C")):
            raise SnapshotError("raw-diff-parse-failed", "rename/copy records are not supported by this recipe")
        records.append(
            {
                **encode_path(path),
                "change": status[0],
                "oldMode": parts[0][1:].decode("ascii"),
                "newMode": parts[1].decode("ascii"),
                "oldOid": parts[2].decode("ascii"),
                "newOid": parts[3].decode("ascii"),
            }
        )
    return records


def read_worktree_identity(root: Path, record: dict[str, Any], git: Git) -> None:
    path_bytes = decode_path(record)
    relative = os.fsdecode(path_bytes)
    absolute = root / relative
    mode = record["newMode"]
    if mode == "000000":
        record.update({"objectType": "deleted", "deletionMarker": True})
        return
    if mode == "160000":
        zero_oid = set(record["newOid"]) <= {"0"}
        if not zero_oid:
            oid = record["newOid"]
        elif absolute.exists():
            oid = git.run(["-C", str(absolute), "rev-parse", "--verify", "HEAD^{commit}"]).decode("ascii").strip()
        else:
            raise SnapshotError("submodule-identity-unavailable", f"cannot resolve submodule identity: {relative}")
        record.update({"objectType": "commit", "submoduleOid": oid})
        return
    if not os.path.lexists(absolute):
        raise SnapshotError("worktree-content-unavailable", f"changed path is missing: {relative}")
    if mode == "120000":
        if absolute.is_symlink():
            target = os.readlink(os.fsencode(absolute))
            target_bytes = target if isinstance(target, bytes) else os.fsencode(target)
        else:
            target_bytes = absolute.read_bytes()
        record.update({"objectType": "symlink", "symlinkTargetDigest": sha256(target_bytes)})
        return
    content = absolute.read_bytes()
    record.update({"objectType": "blob", "contentDigest": sha256(content)})


def read_tree_identity(record: dict[str, Any], git: Git) -> None:
    mode = record["newMode"]
    oid = record["newOid"]
    if mode == "000000":
        record.update({"objectType": "deleted", "deletionMarker": True})
    elif mode == "160000":
        record.update({"objectType": "commit", "submoduleOid": oid})
    else:
        require_object(git, oid, "blob")
        content = git.run(["cat-file", "blob", oid])
        if mode == "120000":
            record.update({"objectType": "symlink", "symlinkTargetDigest": sha256(content)})
        else:
            record.update({"objectType": "blob", "contentDigest": sha256(content)})


def untracked_records(git: Git, repository: Repository, scope: Scope) -> list[dict[str, Any]]:
    raw = git.run(["ls-files", "--others", "--exclude-standard", "-z", "--", *scope.pathspecs()])
    records = []
    for path in sorted(item for item in raw.split(b"\0") if item):
        absolute = git.target / os.fsdecode(path)
        if absolute.is_symlink():
            mode = "120000"
        else:
            executable = os.access(absolute, os.X_OK) and os.name != "nt"
            mode = "100755" if executable else "100644"
        record: dict[str, Any] = {
            **encode_path(path),
            "change": "A",
            "oldMode": "000000",
            "newMode": mode,
            "oldOid": "0" * repository.oid_length,
            "newOid": "0" * repository.oid_length,
            "untracked": True,
        }
        read_worktree_identity(git.target, record, git)
        records.append(record)
    return records


def manifest_envelope(mode: str, records: list[dict[str, Any]]) -> dict[str, Any]:
    records.sort(key=decode_path)
    if mode == "creator-tree":
        content_identity = "sha256 over exact candidate-tree blob or symlink-target bytes"
        filter_application = "Git index clean filters and normalization applied by git add -A"
        newline_normalization = "as stored in the candidate tree after Git index conversion"
    else:
        content_identity = "sha256 over exact worktree regular-file or symlink-target bytes"
        filter_application = "none for manifest content digests"
        newline_normalization = "none for manifest content digests"
    return {
        "schemaVersion": SCHEMA_VERSION,
        "mode": mode,
        "recordFraming": "canonical-json-utf8; records sorted by decoded path bytes",
        "pathEncoding": "raw Git path bytes as RFC 4648 base64; UTF-8 text is informational",
        "contentIdentity": content_identity,
        "filterApplication": filter_application,
        "newlineNormalization": newline_normalization,
        "records": records,
    }


def stable_diff_options(base_oid: str) -> list[str]:
    return [
        "--no-color",
        "--no-ext-diff",
        "--no-textconv",
        "--no-renames",
        "--no-relative",
        "--ignore-submodules=none",
        "--submodule=short",
        "--diff-algorithm=myers",
        "--src-prefix=a/",
        "--dst-prefix=b/",
        f"--abbrev={len(base_oid)}",
    ]


def build_manifest_digest(git: Git, repository: Repository, base_commit: str, scope: Scope) -> tuple[dict[str, Any], bytes]:
    raw_records = git.run(["diff", "--raw", "-z", *stable_diff_options(base_commit), base_commit, "--", *scope.pathspecs()])
    records = parse_raw_records(raw_records)
    tracked_paths = {decode_path(record) for record in records}
    for record in records:
        read_worktree_identity(git.target, record, git)
    for record in untracked_records(git, repository, scope):
        if decode_path(record) not in tracked_paths:
            records.append(record)
    raw_diff = git.run(
        ["diff", *stable_diff_options(base_commit), "--binary", "--full-index", base_commit, "--", *scope.pathspecs()]
    )
    return manifest_envelope("manifest-digest", records), raw_diff


def build_tree_manifest(
    git: Git,
    base_commit: str,
    base_tree: str,
    candidate_tree: str,
    scope: Scope,
) -> tuple[dict[str, Any], bytes]:
    raw_records = git.run(
        ["diff-tree", "-r", "--raw", "-z", *stable_diff_options(base_commit), base_commit, candidate_tree, "--", *scope.pathspecs()]
    )
    records = parse_raw_records(raw_records)
    for record in records:
        read_tree_identity(record, git)
    raw_diff = git.run(
        ["diff", *stable_diff_options(base_commit), "--binary", "--full-index", base_commit, candidate_tree, "--", *scope.pathspecs()]
    )
    return manifest_envelope("creator-tree", records), raw_diff


def changed_paths(git: Git, base_commit: str, scope: Scope | None) -> set[bytes]:
    pathspecs = scope.pathspecs() if scope is not None else []
    suffix = ["--", *pathspecs] if pathspecs else []
    tracked = git.run(["diff", "--name-only", "-z", *stable_diff_options(base_commit), base_commit, *suffix])
    untracked = git.run(
        ["ls-files", "--others", "--exclude-standard", "-z", *suffix]
    )
    return {path for path in (*tracked.split(b"\0"), *untracked.split(b"\0")) if path}


def scope_cleanliness(git: Git, base_commit: str, scope: Scope) -> dict[str, Any]:
    all_paths = changed_paths(git, base_commit, None)
    included_paths = changed_paths(git, base_commit, scope)
    outside = sorted(all_paths - included_paths)
    return {
        "recipe": {
            "tracked": ["git", *SAFE_GIT_OPTIONS, "diff", "--name-only", "-z", base_commit],
            "untracked": ["git", *SAFE_GIT_OPTIONS, "ls-files", "--others", "--exclude-standard", "-z"],
            "comparison": "all changed/untracked paths minus the declared include/exclude pathspec result",
        },
        "result": "clean" if not outside else "outside-scope-changes-present",
        "outsideScopePaths": [encode_path(path) for path in outside],
    }


def identity_value(
    mode: str,
    base_commit: str,
    base_tree: str,
    candidate_tree: str | None,
    scope: Scope,
    manifest: dict[str, Any],
    raw_diff: bytes,
    creation_context: dict[str, Any],
) -> str:
    raw_command = raw_diff_recipe(mode, base_commit, candidate_tree, scope)
    value = {
        "schemaVersion": SCHEMA_VERSION,
        "creationRecipeVersion": CREATION_RECIPE_VERSION,
        "verificationRecipeVersion": VERIFICATION_RECIPE_VERSION,
        "mode": mode,
        "baseCommitOid": base_commit,
        "baseTreeOid": base_tree,
        "candidateTreeOid": candidate_tree,
        "includedScope": scope.included,
        "excludedScope": scope.excluded,
        "manifestDigest": sha256(canonical_bytes(manifest)),
        "rawDiffCommand": raw_command,
        "rawDiffDigest": sha256(raw_diff),
        "creationContextDigest": sha256(canonical_bytes(creation_context)),
        "creationRecipe": creation_recipe(mode, creation_context["targetRoot"]),
        "readOnlyVerificationRecipe": verification_recipe(mode, creation_context["targetRoot"]),
    }
    return sha256(canonical_bytes(value))


def status_snapshot(git: Git) -> dict[str, Any]:
    raw = git.run(["status", "--porcelain=v2", "-z", "--untracked-files=all"])
    return {"digest": sha256(raw), "byteLength": len(raw)}


def index_tree(git: Git, repository: Repository, env: dict[str, str] | None = None) -> str:
    return single_oid(git.run(["write-tree"], env=env).rstrip(b"\r\n"), repository, "index tree")


def creator_preflight(
    repository: Repository,
    artifact_dir: Path,
    authorized: bool,
    writable_scopes: Sequence[Path],
) -> tuple[str | None, dict[str, Any]]:
    authority = {
        "gitObjectWriteAuthorized": authorized,
        "gitCommonDir": str(repository.common_dir),
        "writableScopes": [str(path.resolve()) for path in writable_scopes],
    }
    if not authorized:
        return "git-object-write-not-authorized", authority
    if not writable_scopes:
        return "creator-tree-capability-unconfirmed", authority
    if not any(is_within(repository.common_dir, path) for path in writable_scopes):
        return "git-common-dir-outside-writable-scope", authority
    if is_within(artifact_dir, repository.target_root):
        authority["temporaryIndexLocation"] = "inside-target-worktree"
        return "temporary-index-unavailable", authority
    objects_dir = repository.common_dir / "objects"
    authority["gitObjectDirectory"] = str(objects_dir)
    authority["gitObjectDirectoryWritable"] = objects_dir.is_dir() and os.access(objects_dir, os.W_OK)
    if not authority["gitObjectDirectoryWritable"]:
        return "creator-tree-capability-unconfirmed", authority
    try:
        artifact_dir.mkdir(parents=True, exist_ok=True)
        descriptor, probe = tempfile.mkstemp(prefix="candidate-index-probe-", dir=artifact_dir)
        os.close(descriptor)
        Path(probe).unlink()
    except OSError:
        return "temporary-index-unavailable", authority
    authority["temporaryIndexAvailable"] = True
    authority["capabilityConfirmed"] = True
    return None, authority


def cleanup_index(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {"attempted": False, "succeeded": True}
    failures: list[str] = []
    for target in (path, Path(f"{path}.lock")):
        try:
            target.unlink(missing_ok=True)
        except OSError as exc:
            failures.append(f"{target.name}: {exc}")
    return {"attempted": True, "succeeded": not failures, "failures": failures}


def raw_diff_recipe(mode: str, base: str, tree: str | None, scope: Scope) -> list[str]:
    args = ["git", *SAFE_GIT_OPTIONS, "diff", *stable_diff_options(base), "--binary", "--full-index", base]
    if mode == "creator-tree" and tree is not None:
        args.append(tree)
    args.extend(["--", *scope.pathspecs()])
    return args


def creation_recipe(mode: str, target_root: str) -> dict[str, Any]:
    return {
        "version": CREATION_RECIPE_VERSION,
        "command": [sys.executable, str(Path(__file__).resolve()), "create"],
        "workingDirectory": target_root,
        "mode": mode,
        "normalIndexIsolation": mode == "creator-tree",
        "gitSafetyOptions": SAFE_GIT_OPTIONS,
    }


def verification_recipe(mode: str, target_root: str) -> dict[str, Any]:
    return {
        "version": VERIFICATION_RECIPE_VERSION,
        "command": [sys.executable, str(Path(__file__).resolve()), "verify", "--candidate", "<candidate-json>"],
        "workingDirectory": target_root,
        "mode": mode,
        "writesGitMetadata": False,
        "usesRecordedBaseOid": True,
        "usesLiveWorktree": mode == "manifest-digest",
    }


def creation_context(
    target_root: str,
    repository_identity: dict[str, Any],
    requested_mode: str,
    selected_mode: str,
    fallback_allowed: bool,
    creator_reason: str | None,
    fallback_reason: str | None,
    authority: dict[str, Any],
    cleanup: dict[str, Any],
    postcondition: dict[str, Any],
    cleanliness: dict[str, Any],
) -> dict[str, Any]:
    return {
        "targetRoot": target_root,
        "repositoryIdentity": repository_identity,
        "requestedMode": requested_mode,
        "selectedMode": selected_mode,
        "manifestFallbackAllowed": fallback_allowed,
        "creatorTreeReason": creator_reason or "not applicable",
        "fallbackReason": fallback_reason or "none",
        "authority": authority,
        "cleanup": cleanup,
        "normalIndexPostcondition": postcondition,
        "supportedScopeCleanliness": cleanliness,
    }


def repository_identity(repository: Repository) -> dict[str, Any]:
    return {
        "gitDir": str(repository.git_dir),
        "gitCommonDir": str(repository.common_dir),
        "objectFormat": repository.object_format,
    }


def creator_safety_state(candidate: dict[str, Any], mode: str) -> bool:
    creation = candidate["creation"]
    cleanup = creation["cleanup"]
    postcondition = creation["normalIndexPostcondition"]
    if mode == "manifest-digest":
        return (
            cleanup.get("attempted") is False
            and cleanup.get("succeeded") is True
            and postcondition.get("required") is False
            and postcondition.get("verified") is True
        )
    before = postcondition.get("before")
    after = postcondition.get("after")
    return (
        creation["authority"].get("writeStarted") is True
        and cleanup.get("attempted") is True
        and cleanup.get("succeeded") is True
        and not cleanup.get("failures")
        and postcondition.get("verified") is True
        and isinstance(before, dict)
        and before == after
    )


def build_ready_result(
    candidate_id: str,
    repository: Repository,
    base_ref: str,
    base_commit: str,
    base_tree: str,
    requested_mode: str,
    selected_mode: str,
    fallback_allowed: bool,
    creator_reason: str | None,
    fallback_reason: str | None,
    authority: dict[str, Any],
    candidate_tree: str | None,
    scope: Scope,
    manifest: dict[str, Any],
    raw_diff: bytes,
    cleanliness: dict[str, Any],
    cleanup: dict[str, Any],
    postcondition: dict[str, Any],
) -> dict[str, Any]:
    repo_identity = repository_identity(repository)
    context = creation_context(
        str(repository.target_root),
        repo_identity,
        requested_mode,
        selected_mode,
        fallback_allowed,
        creator_reason,
        fallback_reason,
        authority,
        cleanup,
        postcondition,
        cleanliness,
    )
    value = identity_value(
        selected_mode,
        base_commit,
        base_tree,
        candidate_tree,
        scope,
        manifest,
        raw_diff,
        context,
    )
    return {
        "schemaVersion": SCHEMA_VERSION,
        "status": "ready",
        "candidateId": candidate_id,
        "targetRoot": str(repository.target_root),
        "repositoryIdentity": repo_identity,
        "baseRefLabel": base_ref,
        "candidateSourceIdentity": {
            "mode": selected_mode,
            "value": value,
            "baseCommitOid": base_commit,
            "baseTreeOid": base_tree,
            "candidateTreeOid": candidate_tree or "not applicable",
            "includedScope": list(scope.included),
            "excludedScope": list(scope.excluded),
            "manifest": manifest,
            "manifestDigest": sha256(canonical_bytes(manifest)),
            "rawDiffCommand": raw_diff_recipe(selected_mode, base_commit, candidate_tree, scope),
            "rawDiffDigest": sha256(raw_diff),
            "creationRecipeVersion": CREATION_RECIPE_VERSION,
            "verificationRecipeVersion": VERIFICATION_RECIPE_VERSION,
            "creationContextDigest": sha256(canonical_bytes(context)),
        },
        "creation": {
            "requestedMode": requested_mode,
            "selectedMode": selected_mode,
            "manifestFallbackAllowed": fallback_allowed,
            "creatorTreeReason": creator_reason or "not applicable",
            "authority": authority,
            "fallbackReason": fallback_reason or "none",
            "cleanup": cleanup,
            "normalIndexPostcondition": postcondition,
        },
        "supportedScopeCleanliness": cleanliness,
        "creationRecipe": creation_recipe(selected_mode, str(repository.target_root)),
        "readOnlyVerificationRecipe": verification_recipe(selected_mode, str(repository.target_root)),
        "diagnostics": [],
    }


def failure_result(
    status: str,
    code: str,
    message: str,
    *,
    requested_mode: str,
    fallback_allowed: bool,
    creator_reason: str | None,
    authority: dict[str, Any] | None = None,
    cleanup: dict[str, Any] | None = None,
    postcondition: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "schemaVersion": SCHEMA_VERSION,
        "status": status,
        "candidateSourceIdentity": None,
        "creation": {
            "requestedMode": requested_mode,
            "selectedMode": "none",
            "manifestFallbackAllowed": fallback_allowed,
            "creatorTreeReason": creator_reason or "not applicable",
            "authority": authority or {},
            "fallbackReason": code if code in FALLBACK_REASONS else "none",
            "cleanup": cleanup or {"attempted": False, "succeeded": True},
            "normalIndexPostcondition": postcondition or {"verified": False},
        },
        "diagnostics": [{"code": code, "message": message}],
    }


def create_candidate(args: argparse.Namespace) -> dict[str, Any]:
    requested_mode = args.mode or "manifest-digest"
    fallback_allowed = bool(args.allow_manifest_fallback)
    creator_reason = args.creator_tree_reason
    if requested_mode == "creator-tree" and not creator_reason:
        return failure_result(
            "invalid", "creator-tree-reason-required", "creator-tree requires an explicit independence reason",
            requested_mode=requested_mode, fallback_allowed=fallback_allowed, creator_reason=creator_reason,
        )
    try:
        scope = Scope(
            normalize_scope(args.include, "--include", default=(".",)),
            normalize_scope(args.exclude, "--exclude"),
        )
        repository, git = resolve_repository(args.target)
        if args.output and is_within(args.output.resolve(), repository.target_root):
            raise SnapshotError("artifact-inside-target-worktree", "--output must be outside the target worktree", status="invalid")
        base_commit, base_tree = resolve_base(git, repository, args.base_ref)
    except (SnapshotError, OSError, UnicodeError) as exc:
        error = exc if isinstance(exc, SnapshotError) else SnapshotError("candidate-preflight-failed", str(exc), status="invalid")
        return failure_result(error.status, error.code, str(error), requested_mode=requested_mode, fallback_allowed=fallback_allowed, creator_reason=creator_reason)

    if requested_mode == "manifest-digest":
        try:
            manifest, raw_diff = build_manifest_digest(git, repository, base_commit, scope)
            cleanliness = scope_cleanliness(git, base_commit, scope)
            return build_ready_result(
                args.candidate_id, repository, args.base_ref, base_commit, base_tree,
                requested_mode, "manifest-digest", fallback_allowed, creator_reason, None,
                {"gitObjectWriteAuthorized": False, "capabilityExplored": False}, None,
                scope, manifest, raw_diff, cleanliness, {"attempted": False, "succeeded": True},
                {"required": False, "verified": True},
            )
        except (SnapshotError, OSError) as exc:
            error = exc if isinstance(exc, SnapshotError) else SnapshotError("manifest-build-failed", str(exc))
            return failure_result(error.status, error.code, str(error), requested_mode=requested_mode, fallback_allowed=fallback_allowed, creator_reason=creator_reason)

    artifact_dir = args.artifact_dir.resolve()
    fallback_reason, authority = creator_preflight(
        repository, artifact_dir, bool(args.git_object_write_authorized), args.writable_scope
    )
    if fallback_reason:
        if fallback_allowed:
            try:
                manifest, raw_diff = build_manifest_digest(git, repository, base_commit, scope)
                cleanliness = scope_cleanliness(git, base_commit, scope)
                return build_ready_result(
                    args.candidate_id, repository, args.base_ref, base_commit, base_tree,
                    requested_mode, "manifest-digest", fallback_allowed, creator_reason, fallback_reason,
                    authority, None, scope, manifest, raw_diff, cleanliness,
                    {"attempted": False, "succeeded": True}, {"required": False, "verified": True},
                )
            except (SnapshotError, OSError) as exc:
                error = exc if isinstance(exc, SnapshotError) else SnapshotError("manifest-build-failed", str(exc))
                return failure_result(error.status, error.code, str(error), requested_mode=requested_mode, fallback_allowed=fallback_allowed, creator_reason=creator_reason, authority=authority)
        return failure_result(
            "validation-gap", fallback_reason, "creator-tree preflight did not confirm all required authority and capability",
            requested_mode=requested_mode, fallback_allowed=fallback_allowed, creator_reason=creator_reason, authority=authority,
        )

    try:
        before_status = status_snapshot(git)
        authority["normalWorktreeStatusAvailable"] = True
    except (SnapshotError, OSError) as exc:
        authority["normalWorktreeStatusAvailable"] = False
        fallback_reason = "creator-tree-capability-unconfirmed"
        if fallback_allowed:
            try:
                manifest, raw_diff = build_manifest_digest(git, repository, base_commit, scope)
                cleanliness = scope_cleanliness(git, base_commit, scope)
                return build_ready_result(
                    args.candidate_id, repository, args.base_ref, base_commit, base_tree,
                    requested_mode, "manifest-digest", fallback_allowed, creator_reason, fallback_reason,
                    authority, None, scope, manifest, raw_diff, cleanliness,
                    {"attempted": False, "succeeded": True}, {"required": False, "verified": True},
                )
            except (SnapshotError, OSError) as manifest_exc:
                error = manifest_exc if isinstance(manifest_exc, SnapshotError) else SnapshotError("manifest-build-failed", str(manifest_exc))
                return failure_result(error.status, error.code, str(error), requested_mode=requested_mode, fallback_allowed=fallback_allowed, creator_reason=creator_reason, authority=authority)
        return failure_result(
            "validation-gap", fallback_reason, f"normal worktree status preflight failed: {exc}",
            requested_mode=requested_mode, fallback_allowed=fallback_allowed,
            creator_reason=creator_reason, authority=authority,
        )

    before_tree: str | None = None
    temp_index: Path | None = None
    cleanup = {"attempted": False, "succeeded": True}
    write_started = False
    candidate_tree: str | None = None
    try:
        write_started = True
        before_tree = index_tree(git, repository)
        temp_index = artifact_dir / f"candidate-index-{os.getpid()}-{secrets.token_hex(8)}"
        temp_env = {"GIT_INDEX_FILE": str(temp_index)}
        git.run(["read-tree", base_tree], env=temp_env)
        git.run(["add", "-A", "--", *scope.pathspecs()], env=temp_env)
        candidate_tree = index_tree(git, repository, temp_env)
        require_object(git, candidate_tree, "tree")
        manifest, raw_diff = build_tree_manifest(git, base_commit, base_tree, candidate_tree, scope)
        cleanliness = scope_cleanliness(git, base_commit, scope)
    except (SnapshotError, OSError) as exc:
        error = exc if isinstance(exc, SnapshotError) else SnapshotError("creator-tree-build-failed", str(exc))
        cleanup = cleanup_index(temp_index)
        postcondition = creator_postcondition(git, repository, before_tree, before_status)
        if not cleanup["succeeded"]:
            error = SnapshotError("temporary-index-cleanup-failed", "temporary index cleanup failed")
        return failure_result(
            "validation-gap", error.code, str(error), requested_mode=requested_mode,
            fallback_allowed=fallback_allowed, creator_reason=creator_reason, authority={**authority, "writeStarted": write_started},
            cleanup=cleanup, postcondition=postcondition,
        )

    cleanup = cleanup_index(temp_index)
    postcondition = creator_postcondition(git, repository, before_tree, before_status)
    if not cleanup["succeeded"]:
        return failure_result(
            "validation-gap", "temporary-index-cleanup-failed", "temporary index cleanup failed; Candidate was not issued",
            requested_mode=requested_mode, fallback_allowed=fallback_allowed, creator_reason=creator_reason,
            authority={**authority, "writeStarted": True}, cleanup=cleanup, postcondition=postcondition,
        )
    if not postcondition["verified"]:
        return failure_result(
            "validation-gap", "normal-index-postcondition-mismatch", "normal index or worktree status changed during Candidate creation",
            requested_mode=requested_mode, fallback_allowed=fallback_allowed, creator_reason=creator_reason,
            authority={**authority, "writeStarted": True}, cleanup=cleanup, postcondition=postcondition,
        )
    assert candidate_tree is not None
    return build_ready_result(
        args.candidate_id, repository, args.base_ref, base_commit, base_tree,
        requested_mode, "creator-tree", fallback_allowed, creator_reason, None,
        {**authority, "writeStarted": True}, candidate_tree, scope, manifest, raw_diff, cleanliness,
        cleanup, postcondition,
    )


def creator_postcondition(
    git: Git,
    repository: Repository,
    before_tree: str | None,
    before_status: dict[str, Any] | None,
) -> dict[str, Any]:
    if before_tree is None or before_status is None:
        return {
            "verified": False,
            "diagnostic": "normal index/worktree baseline was not fully acquired",
        }
    try:
        after_tree = index_tree(git, repository)
        after_status = status_snapshot(git)
    except (SnapshotError, OSError) as exc:
        return {"verified": False, "diagnostic": str(exc)}
    return {
        "verified": before_tree == after_tree and before_status == after_status,
        "before": {"indexTreeOid": before_tree, "worktreeStatus": before_status},
        "after": {"indexTreeOid": after_tree, "worktreeStatus": after_status},
    }


def verify_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    candidate_id = candidate.get("candidateId", "unknown")
    try:
        if candidate.get("status") != "ready":
            raise SnapshotError("candidate-not-ready", "only a ready Candidate can be verified", status="invalid")
        identity = candidate["candidateSourceIdentity"]
        repository, git = resolve_repository(Path(candidate["targetRoot"]))
        base_commit = identity["baseCommitOid"]
        base_tree = identity["baseTreeOid"]
        require_object(git, base_commit, "commit")
        require_object(git, base_tree, "tree")
        resolved_tree = single_oid(git.run(["rev-parse", f"{base_commit}^{{tree}}"]).rstrip(b"\r\n"), repository, "base tree")
        if resolved_tree != base_tree:
            return verification_result(candidate_id, "mismatch", "base-tree-mismatch", "recorded base commit does not point to the recorded base tree")
        scope = Scope(tuple(identity["includedScope"]), tuple(identity["excludedScope"]))
        if identity["mode"] == "manifest-digest":
            manifest, raw_diff = build_manifest_digest(git, repository, base_commit, scope)
            candidate_tree = None
        elif identity["mode"] == "creator-tree":
            candidate_tree = identity["candidateTreeOid"]
            require_object(git, candidate_tree, "tree")
            manifest, raw_diff = build_tree_manifest(git, base_commit, base_tree, candidate_tree, scope)
        else:
            raise SnapshotError("unsupported-identity-mode", f"unsupported identity mode: {identity['mode']}", status="invalid")
        declared_context = creation_context(
            candidate["targetRoot"],
            candidate["repositoryIdentity"],
            candidate["creation"]["requestedMode"],
            candidate["creation"]["selectedMode"],
            bool(candidate["creation"]["manifestFallbackAllowed"]),
            candidate["creation"]["creatorTreeReason"],
            candidate["creation"]["fallbackReason"],
            candidate["creation"]["authority"],
            candidate["creation"]["cleanup"],
            candidate["creation"]["normalIndexPostcondition"],
            candidate["supportedScopeCleanliness"],
        )
        actual = identity_value(
            identity["mode"],
            base_commit,
            base_tree,
            candidate_tree,
            scope,
            manifest,
            raw_diff,
            declared_context,
        )
        comparisons = {
            "sourceIdentity": actual == identity["value"],
            "declaredManifest": sha256(canonical_bytes(identity["manifest"])) == identity["manifestDigest"],
            "manifestDigest": sha256(canonical_bytes(manifest)) == identity["manifestDigest"],
            "rawDiffCommand": raw_diff_recipe(identity["mode"], base_commit, candidate_tree, scope) == identity["rawDiffCommand"],
            "rawDiffDigest": sha256(raw_diff) == identity["rawDiffDigest"],
            "creationRecipeVersion": identity["creationRecipeVersion"] == CREATION_RECIPE_VERSION,
            "verificationRecipeVersion": identity["verificationRecipeVersion"] == VERIFICATION_RECIPE_VERSION,
            "creationContext": sha256(canonical_bytes(declared_context)) == identity["creationContextDigest"],
            "creationRecipe": candidate["creationRecipe"] == creation_recipe(identity["mode"], str(repository.target_root)),
            "readOnlyVerificationRecipe": candidate["readOnlyVerificationRecipe"] == verification_recipe(identity["mode"], str(repository.target_root)),
            "selectedMode": candidate["creation"]["selectedMode"] == identity["mode"],
            "repositoryIdentity": candidate["repositoryIdentity"] == repository_identity(repository),
            "creatorSafetyState": creator_safety_state(candidate, identity["mode"]),
        }
        if not all(comparisons.values()):
            return verification_result(candidate_id, "mismatch", "candidate-source-mismatch", "one or more source identity fields changed", comparisons)
        return verification_result(candidate_id, "verified", "none", "all declared read-only identity checks matched", comparisons)
    except (KeyError, TypeError, ValueError, SnapshotError, OSError, UnicodeError) as exc:
        code = exc.code if isinstance(exc, SnapshotError) else "candidate-verification-failed"
        return verification_result(candidate_id, "validation-gap", code, str(exc))


def verification_result(candidate_id: str, status: str, code: str, message: str, evidence: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "status": status,
        "candidateId": candidate_id,
        "reviewScope": "Candidate verification only",
        "writesGitMetadata": False,
        "evidence": evidence or {},
        "diagnostics": [] if code == "none" else [{"code": code, "message": message}],
    }


def write_result(result: dict[str, Any], output: Path | None) -> None:
    data = json.dumps(result, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
    if output is None:
        sys.stdout.buffer.write(data)
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(data)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    create = subparsers.add_parser("create")
    create.add_argument("--candidate-id", required=True)
    create.add_argument("--target", type=Path, required=True)
    create.add_argument("--base-ref", required=True)
    create.add_argument("--include", action="append", default=[])
    create.add_argument("--exclude", action="append", default=[])
    create.add_argument("--mode", choices=("manifest-digest", "creator-tree"))
    create.add_argument("--creator-tree-reason")
    create.add_argument("--allow-manifest-fallback", action="store_true")
    create.add_argument("--git-object-write-authorized", action="store_true")
    create.add_argument("--writable-scope", action="append", type=Path, default=[])
    create.add_argument("--artifact-dir", type=Path, required=True)
    create.add_argument("--output", type=Path)
    verify = subparsers.add_parser("verify")
    verify.add_argument("--candidate", type=Path, required=True)
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    try:
        if args.command == "create":
            result = create_candidate(args)
            write_result(result, args.output)
            return 0 if result["status"] == "ready" else 2
        candidate = json.loads(args.candidate.read_text(encoding="utf-8"))
        result = verify_candidate(candidate)
        write_result(result, None)
        return 0 if result["status"] == "verified" else 3
    except (OSError, json.JSONDecodeError, UnicodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
