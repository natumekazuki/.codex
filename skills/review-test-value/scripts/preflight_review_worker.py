"""Fail-closed preflight for the isolated review worker.

This module only verifies the native executable and role declaration before a
worker payload could be constructed.  It deliberately does not start a
review worker or inspect the effective tool surface.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
from typing import Any, Callable


EXIT_BLOCKED = 2
VERSION_TIMEOUT_SECONDS = 10.0
_REPARSE_POINT = 0x400
VersionRunner = Callable[[str, float], tuple[int, str, str]]


class PreflightError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _safe_path(path: Path, label: str, *, require_absolute: bool = False) -> tuple[Path, str]:
    if require_absolute and not path.is_absolute():
        raise PreflightError("RUNTIME_UNSUPPORTED", f"{label} must be absolute")
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise PreflightError("RUNTIME_UNSUPPORTED", f"{label} is not accessible") from exc
    for candidate in (path, *path.parents):
        try:
            stat = candidate.stat(follow_symlinks=False)
        except OSError as exc:
            raise PreflightError("RUNTIME_UNSUPPORTED", f"{label} is not accessible") from exc
        if candidate.is_symlink() or getattr(stat, "st_file_attributes", 0) & _REPARSE_POINT:
            raise PreflightError("RUNTIME_UNSUPPORTED", f"{label} must not use a link or reparse point")
    if not resolved.is_file():
        raise PreflightError("RUNTIME_UNSUPPORTED", f"{label} must be a regular file")
    return path, str(resolved)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _run_version(executable: str, timeout: float) -> tuple[int, str, str]:
    try:
        completed = subprocess.run(
            [executable, "--version"],
            capture_output=True,
            stdin=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise PreflightError("CLI_VERSION_TIMEOUT", "native --version timed out") from exc
    except OSError as exc:
        raise PreflightError("CLI_VERSION_QUERY_FAILED", "native --version could not run") from exc
    if completed.returncode != 0:
        raise PreflightError("CLI_VERSION_QUERY_FAILED", "native --version failed")
    # stderr is intentionally discarded; receipts must not contain raw CLI output.
    version = completed.stdout.strip()
    if not re.fullmatch(r"codex-cli \d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?", version):
        raise PreflightError("CLI_VERSION_QUERY_FAILED", "native --version returned invalid output")
    return completed.returncode, version, ""


def _load_role(role_path: Path) -> tuple[dict[str, Any], str]:
    import tomllib

    try:
        role_bytes = role_path.read_bytes()
        role = tomllib.loads(role_bytes.decode("utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise PreflightError("RUNTIME_UNSUPPORTED", "role TOML could not be read") from exc
    required = {"name", "model", "model_reasoning_effort", "developer_instructions"}
    optional = {"description", "sandbox_mode"}
    if set(role) - required - optional or not required <= set(role):
        raise PreflightError("RUNTIME_UNSUPPORTED", "role TOML does not match the supported role contract")
    if any(not isinstance(role[key], str) or not role[key].strip() for key in required | (set(role) & optional)):
        raise PreflightError("RUNTIME_UNSUPPORTED", "role TOML does not match the supported role contract")
    if role["name"] not in {"test_value_luna", "test_value_sol"}:
        raise PreflightError("RUNTIME_UNSUPPORTED", "role TOML is not one of the supported review roles")
    return role, "sha256:" + hashlib.sha256(role_bytes).hexdigest()


def _receipt(
    *,
    executable: Path | None,
    executable_realpath: str | None,
    executable_hash: str | None,
    version: str | None,
    role: Path | None,
    role_realpath: str | None,
    role_hash: str | None,
    requested_model: str | None,
    requested_effort: str | None,
    reason_codes: list[str],
) -> dict[str, Any]:
    return {
        "schema_version": "runtime-readiness-v1",
        "status": "BLOCKED",
        "reason_codes": reason_codes,
        "cli": {
            "path": str(executable) if executable else None,
            "realpath": executable_realpath,
            "sha256": executable_hash,
            "version": version,
        },
        "role": {
            "path": str(role) if role else None,
            "realpath": role_realpath,
            "sha256": role_hash,
        },
        "requested": {"model": requested_model, "effort": requested_effort},
        "effective": {"model": None, "effort": None, "tools": None, "managed_inputs": None},
        "model_available": None,
        "isolation_verified": False,
        "payload_delivered": False,
    }


def run_preflight(cli: str, role_file: str, *, runner: VersionRunner = _run_version) -> dict[str, Any]:
    reasons = ["EFFECTIVE_TOOL_SURFACE_UNVERIFIED", "MANAGED_INPUTS_UNVERIFIED"]
    executable: Path | None = None
    role_path: Path | None = None
    executable_realpath = role_realpath = None
    executable_hash = role_hash = None
    version = requested_model = requested_effort = None
    try:
        executable, executable_realpath = _safe_path(Path(cli), "--cli")
        if executable.suffix.lower() != ".exe":
            raise PreflightError("RUNTIME_UNSUPPORTED", "--cli must point to a native .exe")
        before_hash = _sha256(executable)
        role_path, role_realpath = _safe_path(Path(role_file), "--role-file")
        role, role_hash = _load_role(role_path)
        requested_model = role["model"]
        requested_effort = role["model_reasoning_effort"]
        _, version, _ = runner(executable_realpath, VERSION_TIMEOUT_SECONDS)
        after_hash = _sha256(executable)
        if before_hash != after_hash:
            raise PreflightError("CLI_SNAPSHOT_CHANGED", "CLI changed during version query")
        executable_hash = after_hash
    except subprocess.TimeoutExpired:
        reasons.append("CLI_VERSION_TIMEOUT")
    except PreflightError as exc:
        reasons.append(exc.code)
    except OSError:
        reasons.append("RUNTIME_UNSUPPORTED")
    return _receipt(
        executable=executable,
        executable_realpath=executable_realpath,
        executable_hash=executable_hash,
        version=version,
        role=role_path,
        role_realpath=role_realpath,
        role_hash=role_hash,
        requested_model=requested_model,
        requested_effort=requested_effort,
        reason_codes=list(dict.fromkeys(reasons)),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cli", required=True)
    parser.add_argument("--role-file", required=True)
    args = parser.parse_args(argv)
    result = run_preflight(args.cli, args.role_file)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return EXIT_BLOCKED


if __name__ == "__main__":
    raise SystemExit(main())
