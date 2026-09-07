"""Host-owned evidence, current artifact checks, and one task-local result state."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import date
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import tempfile
from typing import Any, Iterator

from build_review_packets import digest
from extract_test_values import sha256_text
from validate_review_result import CONTRACT_VERSION, VERDICTS, ReviewError, parse_json, validate_response

EVIDENCE_KINDS = {"accepted-contract", "security-safety", "approved-compatibility",
                  "incident-regression", "reference-model"}


def git(root: Path, *args: str) -> bytes:
    try:
        completed = subprocess.run(["git", "--no-pager", *args], cwd=root,
                                   capture_output=True, timeout=60, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ReviewError("input", "GIT_UNAVAILABLE") from exc
    if completed.returncode:
        raise ReviewError("input", "GIT_FAILED")
    return completed.stdout


class Target:
    def __init__(self, root: Path, base: str, mode: str = "working", head: str | None = None):
        self.root = root.resolve(strict=True)
        if Path(git(self.root, "rev-parse", "--show-toplevel").decode().strip()).resolve() != self.root:
            raise ReviewError("input", "ROOT_NOT_REPOSITORY")
        self.base = git(self.root, "rev-parse", "--verify", f"{base}^{{commit}}").decode().strip()
        self.mode = mode
        self.head = (git(self.root, "rev-parse", "--verify", f"{head}^{{commit}}").decode().strip()
                     if head else None)
        if mode not in {"working", "staged", "head"} or (mode == "head" and not self.head):
            raise ReviewError("input", "TARGET_MODE")

    def read(self, relative: str) -> str | None:
        if not isinstance(relative, str) or not relative:
            raise ReviewError("input", "CONTEXT_PATH_INVALID")
        path = PurePosixPath(relative.replace("\\", "/"))
        if path.is_absolute() or ".." in path.parts or not path.parts or ":" in str(path):
            raise ReviewError("input", "CONTEXT_OUTSIDE_ROOT")
        normalized = str(path)
        try:
            if self.mode == "working":
                local = (self.root / normalized).resolve(strict=False)
                if not local.is_relative_to(self.root):
                    raise ReviewError("input", "CONTEXT_OUTSIDE_ROOT")
                if not local.exists():
                    return None
                raw = local.read_bytes()
            else:
                listing = git(self.root, *( ["ls-files", "--stage", "--", normalized]
                                          if self.mode == "staged" else
                                          ["ls-tree", self.head, "--", normalized]))
                if not listing:
                    return None
                if listing.startswith((b"120000", b"160000")):
                    raise ReviewError("input", "CONTEXT_NOT_REGULAR_FILE")
                spec = f":{normalized}" if self.mode == "staged" else f"{self.head}:{normalized}"
                raw = git(self.root, "show", spec)
            return raw.decode("utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
        except (OSError, UnicodeError) as exc:
            raise ReviewError("input", "CONTEXT_UNREADABLE") from exc

    def snapshot(self) -> str:
        args = ["diff", "--binary", "--full-index", "--no-ext-diff", "--no-textconv", self.base]
        if self.mode == "staged":
            args.append("--cached")
        elif self.mode == "head":
            args.append(self.head)
        untracked = []
        if self.mode == "working":
            for name in sorted(filter(None, git(self.root, "ls-files", "--others", "--exclude-standard", "-z").split(b"\0"))):
                relative = name.decode("utf-8")
                local = (self.root / relative).resolve(strict=True)
                if not local.is_relative_to(self.root) or not local.is_file():
                    raise ReviewError("input", "SNAPSHOT_OUTSIDE_ROOT")
                untracked.append((relative, digest(local.read_bytes().hex())))
        return digest({"base": self.base, "mode": self.mode, "head": self.head,
                       "diff": sha256_text(git(self.root, *args).hex()), "untracked": untracked})


def bounded_context(target: Target, entries: Any) -> list[dict[str, Any]]:
    if not isinstance(entries, list):
        raise ReviewError("input", "CONTEXT_SHAPE")
    result = []
    seen = set()
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("ref"), str) or not entry["ref"]:
            raise ReviewError("input", "CONTEXT_SHAPE")
        source = entry.get("source")
        ref = entry["ref"]
        kind = entry.get("kind")
        if not isinstance(kind, str) or not kind:
            raise ReviewError("input", "CONTEXT_KIND")
        if source == "repository":
            if set(entry) != {"source", "ref", "kind", "start_line", "end_line"}:
                raise ReviewError("input", "CONTEXT_SHAPE")
            content = target.read(ref)
            if content is None:
                raise ReviewError("input", "CONTEXT_MISSING")
            start, end = entry["start_line"], entry["end_line"]
            if start is not None or end is not None:
                lines = content.splitlines(keepends=True)
                if type(start) is not int or type(end) is not int or not 1 <= start <= end <= len(lines):
                    raise ReviewError("input", "CONTEXT_RANGE")
                content = "".join(lines[start - 1:end])
                ref += f"#L{start}-L{end}"
        elif source == "host-observed":
            if (set(entry) != {"source", "ref", "kind", "content", "authority"}
                    or entry["authority"] not in {"issue", "external-contract", "explicit-user-requirement"}
                    or not isinstance(entry["content"], str)):
                raise ReviewError("input", "CONTEXT_SHAPE")
            content = entry["content"]
        else:
            raise ReviewError("input", "CONTEXT_SOURCE")
        if ref in seen:
            raise ReviewError("input", "CONTEXT_DUPLICATE")
        seen.add(ref)
        result.append({"ref": ref, "kind": kind, "content": content,
                       "content_hash": sha256_text(content)})
    return result


def supported_refs(refs: Any, context: list[dict[str, Any]], *, contract_only: bool = False) -> bool:
    available = {x["ref"] for x in context if x["kind"] in
                 ({"accepted-contract"} if contract_only else EVIDENCE_KINDS)}
    return (isinstance(refs, list) and bool(refs)
            and all(isinstance(x, str) for x in refs)
            and len(refs) == len(set(refs)) and set(refs) <= available)


def retention_basis(retention: Any, context: list[dict[str, Any]]) -> str:
    if (not isinstance(retention, dict)
            or set(retention) != {"basis", "reason", "evidence_refs", "temporal"}
            or not isinstance(retention["basis"], str)
            or retention["basis"] not in {"SUPPORTED", "UNSUPPORTED", "UNRESOLVED"}
            or not isinstance(retention["reason"], str)):
        raise ReviewError("retention_resolution", "RETENTION_SHAPE")
    if retention["basis"] == "UNRESOLVED" or not retention["reason"].strip():
        return "UNRESOLVED"
    if not supported_refs(retention["evidence_refs"], context):
        return "UNRESOLVED"
    return retention["basis"]


def resolution_verified(target: Target, resolution: Any, context: list[dict[str, Any]],
                        verdict: str, snapshot: str, basis: str) -> bool:
    if resolution is None:
        return False
    required = {"action", "snapshot_hash", "reason_kind", "reason", "evidence_refs", "target", "check"}
    if not isinstance(resolution, dict) or set(resolution) != required:
        raise ReviewError("retention_resolution", "RESOLUTION_SHAPE")
    if (resolution["action"] != verdict or resolution["snapshot_hash"] != snapshot
            or not isinstance(resolution["reason"], str) or not resolution["reason"].strip()
            or not supported_refs(resolution["evidence_refs"], context)):
        return False
    if verdict == "DROP" and resolution["reason_kind"] == "NO_ALTERNATIVE_REQUIRED":
        return (basis == "UNSUPPORTED" and resolution["target"] is None
                and resolution["check"] is None
                and supported_refs(resolution["evidence_refs"], context, contract_only=True))
    if (verdict == "DROP" and (basis != "SUPPORTED" or resolution["reason_kind"] != "COVERED_BY_EXISTING_CHECK")):
        return False
    if verdict == "MOVE_TO_POLICY_CHECK" and resolution["reason_kind"] != "POLICY_CHECK":
        return False
    destination, check = resolution["target"], resolution["check"]
    if (not isinstance(destination, dict) or set(destination) != {"ref", "content_hash"}
            or not isinstance(check, dict)
            or set(check) != {"snapshot_hash", "target_hash", "exit_code", "output_hash"}):
        raise ReviewError("retention_resolution", "RESOLUTION_RECEIPT_SHAPE")
    actual = target.read(destination["ref"])
    return (actual is not None and sha256_text(actual) == destination["content_hash"]
            and check["snapshot_hash"] == snapshot and check["target_hash"] == destination["content_hash"]
            and type(check["exit_code"]) is int and check["exit_code"] == 0
            and isinstance(check["output_hash"], str) and check["output_hash"].startswith("sha256:")
            and len(check["output_hash"]) == 71
            and all(c in "0123456789abcdef" for c in check["output_hash"][7:]))


def record_gate(record: dict[str, Any], verdict: str, host: dict[str, Any],
                target: Target, snapshot: str, today: date) -> tuple[str, str | None]:
    if verdict == "NEEDS_CONTEXT":
        return "BLOCKED", "NEEDS_CONTEXT"
    if verdict == "REDESIGN":
        return "CHANGES_REQUIRED", "REDESIGN"
    basis = retention_basis(host["retention"], host["context"])
    present = record["change_kind"] != "DELETED"
    if verdict in {"DROP", "MOVE_TO_POLICY_CHECK"}:
        if present:
            return "CHANGES_REQUIRED", "TEST_STILL_PRESENT"
        if resolution_verified(target, host["resolution"], host["context"], verdict, snapshot, basis):
            return "PASS", None
        return "CHANGES_REQUIRED", "RESOLUTION_REQUIRED"
    if not present or basis != "SUPPORTED":
        return "BLOCKED", "RETENTION_UNVERIFIED"
    metadata = record["metadata"]
    lifecycle = metadata["lifecycle"]
    if verdict == "KEEP_PERMANENT":
        return ("PASS", None) if lifecycle == "permanent" else ("CHANGES_REQUIRED", "LIFECYCLE_MISMATCH")
    if verdict != "KEEP_TEMPORARY" or lifecycle not in {"characterization", "ephemeral"}:
        return "CHANGES_REQUIRED", "LIFECYCLE_MISMATCH"
    expiry = metadata.get("expires_on")
    if expiry is not None and date.fromisoformat(expiry) <= today:
        return "CHANGES_REQUIRED", "TEMPORARY_EXPIRED"
    conditional = metadata.get("review_when") or metadata.get("remove_when")
    if not expiry and not conditional:
        return "BLOCKED", "TEMPORARY_CONDITION_MISSING"
    if conditional:
        temporal = host["retention"]["temporal"]
        if (not isinstance(temporal, dict)
                or set(temporal) != {"observed_on", "state", "reason", "evidence_refs"}
                or temporal["observed_on"] != today.isoformat()
                or temporal["state"] not in {"ACTIVE", "EXPIRED", "UNRESOLVED"}
                or not isinstance(temporal["reason"], str) or not temporal["reason"].strip()
                or not supported_refs(temporal["evidence_refs"], host["context"])):
            return "BLOCKED", "TEMPORARY_UNVERIFIED"
        if temporal["state"] != "ACTIVE":
            return ("CHANGES_REQUIRED", "TEMPORARY_EXPIRED") if temporal["state"] == "EXPIRED" else ("BLOCKED", "TEMPORARY_UNVERIFIED")
    return "PASS", None


def aggregate_gate(gates: list[str]) -> str:
    if not gates or "BLOCKED" in gates:
        return "BLOCKED"
    return "CHANGES_REQUIRED" if "CHANGES_REQUIRED" in gates else "PASS"


@contextmanager
def state_lock(directory: Path) -> Iterator[Any]:
    """OS-owned lock, also retaining a task marker if the result file is lost."""
    if not directory.is_dir():
        raise ReviewError("retention_resolution", "STATE_DIRECTORY_MISSING")
    stream = (directory / ".review.lock").open("a+b")
    acquired = False
    try:
        if stream.seek(0, 2) == 0:
            stream.write(b"\0")
            stream.flush()
        stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            acquired = True
        except OSError as exc:
            raise ReviewError("retention_resolution", "STATE_IN_USE") from exc
        yield stream
    finally:
        if acquired:
            stream.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
        stream.close()


def save_state(directory: Path, state: dict[str, Any]) -> None:
    temporary = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=directory, delete=False) as out:
            temporary = Path(out.name)
            json.dump(state, out, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
            out.flush()
            os.fsync(out.fileno())
        os.replace(temporary, directory / "review-state.json")
        temporary = None
    except OSError as exc:
        raise ReviewError("retention_resolution", "STATE_WRITE_FAILED") from exc
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def load_state(directory: Path, owner: dict[str, str], lock: Any) -> dict[str, Any]:
    if any((directory / name).exists() for name in
           ("task-manifest.json", "generations", "initial-manifest.json", "resolution-ledger.json")):
        raise ReviewError("retention_resolution", "OLD_CANDIDATE_STATE")
    path = directory / "review-state.json"
    lock.seek(1)
    marker = lock.read()
    owner_bytes = digest(owner).encode()
    if not path.exists():
        if marker:
            raise ReviewError("retention_resolution", "STATE_MISSING")
        lock.seek(1)
        lock.write(owner_bytes)
        lock.flush()
        os.fsync(lock.fileno())
        state = {"contract_version": CONTRACT_VERSION, "owner": owner, "records": {}}
        save_state(directory, state)
        return state
    if marker != owner_bytes:
        raise ReviewError("retention_resolution", "STATE_OWNER_MISMATCH")
    try:
        state = parse_json(path.read_text(encoding="utf-8"), category="retention_resolution")
        if (not isinstance(state, dict) or set(state) != {"contract_version", "owner", "records"}
                or state["contract_version"] != CONTRACT_VERSION or state["owner"] != owner
                or not isinstance(state["records"], dict)):
            raise ValueError()
        for entry in state["records"].values():
            if (not isinstance(entry, dict) or set(entry) != {"identity", "input_hash", "review", "failure", "gate"}
                    or entry["gate"] not in {"PASS", "CHANGES_REQUIRED", "BLOCKED"}
                    or (entry["review"] is not None and entry["review"].get("verdict") not in VERDICTS)):
                raise ValueError()
            identity = entry["identity"]
            identity_keys = {"record_id", "source_hash", "metadata_hash", "locator", "adapter", "change_kind"}
            if not isinstance(identity, dict) or set(identity) != identity_keys:
                raise ValueError()
            if identity["record_id"] != digest({k: v for k, v in identity.items() if k != "record_id"}):
                raise ValueError()
            if not isinstance(entry["input_hash"], str) or not entry["input_hash"].startswith("sha256:"):
                raise ValueError()
            if entry["review"] is not None:
                validate_response({"reviews": [{"ordinal": 0, **entry["review"]}]}, 1)
                if entry["failure"] is not None:
                    raise ValueError()
            elif not isinstance(entry["failure"], dict) or entry["gate"] != "BLOCKED":
                raise ValueError()
    except (ValueError, OSError, AttributeError, TypeError, KeyError) as exc:
        raise ReviewError("retention_resolution", "STATE_INVALID") from exc
    return state
