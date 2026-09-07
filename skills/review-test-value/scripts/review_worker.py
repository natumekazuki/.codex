#!/usr/bin/env python3
"""Run one test-value review phase in an isolated native Codex worker."""

from __future__ import annotations

import argparse
import base64
import copy
import ctypes
from ctypes import wintypes
from dataclasses import dataclass
from contextvars import ContextVar
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from typing import Any, Callable
import uuid

from preflight_review_worker import (
    VERSION_TIMEOUT_SECONDS,
    PreflightError,
    _load_role,
    _run_version,
    _safe_path,
    _sha256,
)
from validate_review_result import (
    ALIGNMENT_RECORD_KEYS,
    ResultValidationError,
    phase_result_schema,
    result_hash,
    validate_alignment_packet,
    validate_deep_packet,
    validate_phase_result,
)
from build_review_packets import canonical_json, sha256_text
from extract_test_values import validate_metadata


EXIT_BLOCKED = 2
CREATE_SUSPENDED = 0x00000004
CREATE_NEW_PROCESS_GROUP = 0x00000200
CREATE_NO_WINDOW = 0x08000000
PROFILE_NAME = "test-value-review-worker"
SUPPORTED_CLI_VERSION = "codex-cli 0.153.4"
# A process runner can need a short, bounded interval to terminate a Windows
# Job Object and drain its pipes.  The coordinator's absolute deadline leaves
# this interval unused by canary/review work and the worker uses it for scratch
# cleanup as well.
CANARY_MAX_SECONDS = 120.0
CLEANUP_RESERVE_SECONDS = 5.0
PROCESS_TREE_TERMINATION_SECONDS = 5.0
PHASE_CONTRACTS = {
    "metadata": "metadata-review-contract.md",
    "alignment": "alignment-review-contract.md",
    "deep": "deep-review-contract.md",
}
PHASE_ROLES = {
    "metadata": "test_value_luna",
    "alignment": "test_value_luna",
    "deep": "test_value_deep",
}
PHASE_VERSIONS = {
    "metadata": "metadata-review-v2",
    "alignment": "alignment-review-v2",
    "deep": "deep-review-v2",
}
DISABLED_FEATURES = (
    "hooks",
    "plugins",
    "apps",
    "multi_agent",
    "multi_agent_v2",
    "enable_mcp_apps",
    "shell_tool",
    "unified_exec",
    "view_image",
    "memories",
    "browser_use",
    "computer_use",
    "tool_suggest",
    "skill_search",
    "image_generation",
    "goals",
    "code_mode",
    "remote_plugin",
    "standalone_web_search",
    "executor_capability_discovery",
    "recommended_plugins",
)
_DENIAL_PATTERN = re.compile(
    r"access[^\r\n]*denied|permission denied|permissiondenied|unauthorizedaccess|"
    r"accessdenied|eacces|eperm|アクセス[^\r\n]*(?:拒否|許可)|権限[^\r\n]*な(?:い|し)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ProcessOutcome:
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool = False
    process_tree_terminated: bool = False


@dataclass(frozen=True)
class PhaseExecution:
    result: dict[str, Any]
    evidence: dict[str, Any]


@dataclass(frozen=True)
class _AuthSnapshot:
    path: Path
    digest: str
    auth_mode: str
    plan_type: str


@dataclass(frozen=True)
class _WorkerPreparation:
    executable: Path
    executable_realpath: str
    executable_hash: str
    version: str
    role_path: Path
    role_realpath: str
    role: dict[str, Any]
    role_hash: str
    auth_snapshot: _AuthSnapshot
    contracts: dict[str, tuple[Path, str]]
    identity: dict[str, Any]


class ReviewWorkerBlocked(RuntimeError):
    def __init__(self, code: str, evidence: dict[str, Any] | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.evidence = evidence or {}


ProcessRunner = Callable[[list[str], str, Path, float], ProcessOutcome]
_ACTIVE_PROCESS_DEADLINE: ContextVar[float | None] = ContextVar(
    "review_worker_process_deadline", default=None
)


class _IO_COUNTERS(ctypes.Structure):
    _fields_ = [
        ("ReadOperationCount", ctypes.c_uint64),
        ("WriteOperationCount", ctypes.c_uint64),
        ("OtherOperationCount", ctypes.c_uint64),
        ("ReadTransferCount", ctypes.c_uint64),
        ("WriteTransferCount", ctypes.c_uint64),
        ("OtherTransferCount", ctypes.c_uint64),
    ]


class _BASIC_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_int64),
        ("PerJobUserTimeLimit", ctypes.c_int64),
        ("LimitFlags", wintypes.DWORD),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", wintypes.DWORD),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", wintypes.DWORD),
        ("SchedulingClass", wintypes.DWORD),
    ]


class _EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", _BASIC_LIMIT_INFORMATION),
        ("IoInfo", _IO_COUNTERS),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


class _BASIC_ACCOUNTING_INFORMATION(ctypes.Structure):
    """The part of JOBOBJECT_BASIC_ACCOUNTING_INFORMATION we need.

    Querying the job rather than just waiting for the primary Popen handle is
    what lets the worker prove that descendants have also stopped.
    """

    _fields_ = [
        ("TotalUserTime", ctypes.c_int64),
        ("TotalKernelTime", ctypes.c_int64),
        ("ThisPeriodTotalUserTime", ctypes.c_int64),
        ("ThisPeriodTotalKernelTime", ctypes.c_int64),
        ("TotalPageFaultCount", wintypes.DWORD),
        ("TotalProcesses", wintypes.DWORD),
        ("ActiveProcesses", wintypes.DWORD),
        ("TotalTerminatedProcesses", wintypes.DWORD),
    ]


class _WindowsJob:
    """Own a Windows process tree and terminate it when the handle closes."""

    JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
    JobObjectBasicAccountingInformation = 1
    JobObjectExtendedLimitInformation = 9

    def __init__(self) -> None:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        kernel32.CreateJobObjectW.restype = wintypes.HANDLE
        kernel32.SetInformationJobObject.argtypes = [
            wintypes.HANDLE,
            ctypes.c_int,
            ctypes.c_void_p,
            wintypes.DWORD,
        ]
        kernel32.SetInformationJobObject.restype = wintypes.BOOL
        kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
        kernel32.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
        kernel32.TerminateJobObject.restype = wintypes.BOOL
        kernel32.QueryInformationJobObject.argtypes = [
            wintypes.HANDLE,
            ctypes.c_int,
            ctypes.c_void_p,
            wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD),
        ]
        kernel32.QueryInformationJobObject.restype = wintypes.BOOL
        kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel32.WaitForSingleObject.restype = wintypes.DWORD
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL
        self._kernel32 = kernel32
        self._handle = kernel32.CreateJobObjectW(None, None)
        if not self._handle:
            raise OSError(ctypes.get_last_error(), "CreateJobObjectW failed")
        limits = _EXTENDED_LIMIT_INFORMATION()
        limits.BasicLimitInformation.LimitFlags = self.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not kernel32.SetInformationJobObject(
            self._handle,
            self.JobObjectExtendedLimitInformation,
            ctypes.byref(limits),
            ctypes.sizeof(limits),
        ):
            error = ctypes.get_last_error()
            self.close()
            raise OSError(error, "SetInformationJobObject failed")

    def assign(self, process_handle: int) -> None:
        if not self._kernel32.AssignProcessToJobObject(self._handle, process_handle):
            raise OSError(ctypes.get_last_error(), "AssignProcessToJobObject failed")

    def terminate(self) -> None:
        if self._handle and not self._kernel32.TerminateJobObject(self._handle, 1):
            raise OSError(ctypes.get_last_error(), "TerminateJobObject failed")

    def active_processes(self) -> int:
        if not self._handle:
            return 0
        accounting = _BASIC_ACCOUNTING_INFORMATION()
        returned = wintypes.DWORD()
        if not self._kernel32.QueryInformationJobObject(
            self._handle,
            self.JobObjectBasicAccountingInformation,
            ctypes.byref(accounting),
            ctypes.sizeof(accounting),
            ctypes.byref(returned),
        ):
            raise OSError(ctypes.get_last_error(), "QueryInformationJobObject failed")
        return int(accounting.ActiveProcesses)

    def wait_empty(self, timeout: float) -> bool:
        """Wait for the job's primary process *and* all descendants to stop."""

        if timeout < 0:
            timeout = 0
        deadline = time.monotonic() + timeout
        while True:
            if self.active_processes() == 0:
                return True
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            wait_ms = min(50, max(1, int(remaining * 1000)))
            result = self._kernel32.WaitForSingleObject(self._handle, wait_ms)
            if result == 0x00000000:  # WAIT_OBJECT_0
                return self.active_processes() == 0
            if result != 0x00000102:  # WAIT_TIMEOUT
                raise OSError(ctypes.get_last_error(), "WaitForSingleObject failed")

    def close(self) -> None:
        if self._handle:
            handle = self._handle
            self._handle = None
            if not self._kernel32.CloseHandle(handle):
                raise OSError(ctypes.get_last_error(), "CloseHandle failed")


class _THREADENTRY32(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ThreadID", wintypes.DWORD),
        ("th32OwnerProcessID", wintypes.DWORD),
        ("tpBasePri", wintypes.LONG),
        ("tpDeltaPri", wintypes.LONG),
        ("dwFlags", wintypes.DWORD),
    ]


def _resume_suspended_process(process_id: int) -> None:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel32.Thread32First.argtypes = [wintypes.HANDLE, ctypes.POINTER(_THREADENTRY32)]
    kernel32.Thread32First.restype = wintypes.BOOL
    kernel32.Thread32Next.argtypes = [wintypes.HANDLE, ctypes.POINTER(_THREADENTRY32)]
    kernel32.Thread32Next.restype = wintypes.BOOL
    kernel32.OpenThread.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenThread.restype = wintypes.HANDLE
    kernel32.ResumeThread.argtypes = [wintypes.HANDLE]
    kernel32.ResumeThread.restype = wintypes.DWORD
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL

    snapshot = kernel32.CreateToolhelp32Snapshot(0x00000004, 0)
    if snapshot == wintypes.HANDLE(-1).value:
        raise OSError(ctypes.get_last_error(), "CreateToolhelp32Snapshot failed")
    try:
        entry = _THREADENTRY32()
        entry.dwSize = ctypes.sizeof(entry)
        found = bool(kernel32.Thread32First(snapshot, ctypes.byref(entry)))
        while found:
            if entry.th32OwnerProcessID == process_id:
                thread = kernel32.OpenThread(0x0002, False, entry.th32ThreadID)
                if not thread:
                    raise OSError(ctypes.get_last_error(), "OpenThread failed")
                try:
                    previous_count = kernel32.ResumeThread(thread)
                    if previous_count == 0xFFFFFFFF:
                        raise OSError(ctypes.get_last_error(), "ResumeThread failed")
                    return
                finally:
                    kernel32.CloseHandle(thread)
            found = bool(kernel32.Thread32Next(snapshot, ctypes.byref(entry)))
    finally:
        kernel32.CloseHandle(snapshot)
    raise OSError("suspended primary thread was not found")


def _terminate_job_tree(job: _WindowsJob, *, timeout: float) -> None:
    """Terminate and verify every process currently owned by ``job``."""

    try:
        job.terminate()
    except OSError as exc:
        # A process can exit between the timeout and TerminateJobObject.  In
        # that case a zero active-process count is still a verified cleanup.
        try:
            if job.active_processes() == 0:
                return
        except OSError:
            pass
        raise ReviewWorkerBlocked("PROCESS_TREE_TERMINATION_FAILED") from exc
    try:
        empty = job.wait_empty(timeout)
    except OSError as exc:
        raise ReviewWorkerBlocked("PROCESS_TREE_TERMINATION_UNCONFIRMED") from exc
    if not empty:
        raise ReviewWorkerBlocked("PROCESS_TREE_TERMINATION_UNCONFIRMED")


def _run_process(argv: list[str], input_text: str, cwd: Path, timeout: float) -> ProcessOutcome:
    if platform.system() != "Windows":
        raise ReviewWorkerBlocked("WINDOWS_RUNTIME_REQUIRED")
    if not isinstance(timeout, (int, float)) or isinstance(timeout, bool) or timeout < 0:
        raise ReviewWorkerBlocked("INVALID_PROCESS_TIMEOUT")
    absolute_deadline = _ACTIVE_PROCESS_DEADLINE.get()
    if absolute_deadline is not None:
        timeout = min(
            float(timeout),
            max(0.0, absolute_deadline - time.monotonic() - CLEANUP_RESERVE_SECONDS),
        )
    try:
        job = _WindowsJob()
    except OSError as exc:
        raise ReviewWorkerBlocked("JOB_OBJECT_UNAVAILABLE") from exc
    process: subprocess.Popen[str] | None = None
    try:
        process = subprocess.Popen(
            argv,
            cwd=str(cwd),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            shell=False,
            env=_sanitized_environment(),
            creationflags=(
                CREATE_NEW_PROCESS_GROUP
                | CREATE_NO_WINDOW
                | CREATE_SUSPENDED
            ),
        )
        try:
            job.assign(int(process._handle))  # type: ignore[attr-defined]
            _resume_suspended_process(process.pid)
        except OSError as exc:
            tree_error: ReviewWorkerBlocked | None = None
            assignment_cleanup_deadline = (
                time.monotonic() + PROCESS_TREE_TERMINATION_SECONDS
            )
            if absolute_deadline is not None:
                assignment_cleanup_deadline = min(
                    assignment_cleanup_deadline, absolute_deadline
                )
            try:
                _terminate_job_tree(
                    job,
                    timeout=max(
                        0.0, assignment_cleanup_deadline - time.monotonic()
                    ),
                )
            except ReviewWorkerBlocked as termination_error:
                tree_error = termination_error
            # Assignment can fail before the suspended primary process enters
            # the job.  Kill that handle directly and wait with the same
            # bounded interval so an unowned process cannot escape cleanup.
            try:
                if process.poll() is None:
                    process.kill()
                process.wait(
                    timeout=max(0.0, assignment_cleanup_deadline - time.monotonic())
                )
            except subprocess.TimeoutExpired as termination_exc:
                raise ReviewWorkerBlocked(
                    "PROCESS_TREE_TERMINATION_UNCONFIRMED"
                ) from termination_exc
            except OSError as termination_exc:
                raise ReviewWorkerBlocked(
                    "PROCESS_TREE_TERMINATION_FAILED"
                ) from termination_exc
            if tree_error is not None:
                raise tree_error
            raise ReviewWorkerBlocked("JOB_OBJECT_ASSIGNMENT_FAILED") from exc
        if absolute_deadline is not None:
            # Popen, job assignment, and resume happen before communicate's
            # timeout starts.  Recompute here so launch time cannot extend the
            # coordinator's absolute deadline.
            timeout = min(
                float(timeout),
                max(0.0, absolute_deadline - time.monotonic() - CLEANUP_RESERVE_SECONDS),
            )
        try:
            stdout, stderr = process.communicate(input=input_text, timeout=float(timeout))
        except subprocess.TimeoutExpired:
            # The process runner owns this bounded termination interval.  The
            # caller reserves the same interval from its absolute deadline.
            cleanup_deadline = time.monotonic() + PROCESS_TREE_TERMINATION_SECONDS
            if absolute_deadline is not None:
                cleanup_deadline = min(cleanup_deadline, absolute_deadline)
            _terminate_job_tree(
                job,
                timeout=max(0.0, cleanup_deadline - time.monotonic()),
            )
            try:
                stdout, stderr = process.communicate(
                    timeout=max(0.0, cleanup_deadline - time.monotonic())
                )
            except subprocess.TimeoutExpired as exc:
                raise ReviewWorkerBlocked("PROCESS_TREE_TERMINATION_UNCONFIRMED") from exc
            return ProcessOutcome(
                process.returncode if process.returncode is not None else 1,
                stdout,
                stderr,
                timed_out=True,
                process_tree_terminated=True,
            )

        # A successful primary process can still leave a descendant holding a
        # pipe or doing work.  Kill and verify that tree before releasing the
        # job handle; checking only Popen.returncode is insufficient.
        try:
            active_processes = job.active_processes()
        except OSError as exc:
            raise ReviewWorkerBlocked("PROCESS_TREE_TERMINATION_UNCONFIRMED") from exc
        tree_terminated = False
        if active_processes:
            cleanup_timeout = PROCESS_TREE_TERMINATION_SECONDS
            if absolute_deadline is not None:
                cleanup_timeout = min(
                    cleanup_timeout,
                    max(0.0, absolute_deadline - time.monotonic()),
                )
            _terminate_job_tree(job, timeout=cleanup_timeout)
            tree_terminated = True
        return ProcessOutcome(
            process.returncode if process.returncode is not None else 1,
            stdout,
            stderr,
            process_tree_terminated=tree_terminated,
        )
    except ReviewWorkerBlocked:
        raise
    except OSError as exc:
        raise ReviewWorkerBlocked("WORKER_LAUNCH_FAILED") from exc
    finally:
        try:
            job.close()
        except OSError as exc:
            # Closing with KILL_ON_JOB_CLOSE is itself part of process-tree
            # cleanup.  Never turn a close failure into a successful result.
            raise ReviewWorkerBlocked("PROCESS_TREE_TERMINATION_UNCONFIRMED") from exc


def _toml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _powershell_single_quoted_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _sanitized_environment() -> dict[str, str]:
    allowed = {
        "SystemRoot",
        "WINDIR",
        "COMSPEC",
        "PATH",
        "PATHEXT",
        "TEMP",
        "TMP",
        "LOCALAPPDATA",
        "APPDATA",
        "USERPROFILE",
        "HOMEDRIVE",
        "HOMEPATH",
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
        "NO_COLOR",
    }
    allowed_upper = {key.upper() for key in allowed}
    environment = {
        key: value for key, value in os.environ.items() if key.upper() in allowed_upper
    }
    codex_home = os.environ.get("CODEX_HOME")
    if not codex_home:
        user_profile = environment.get("USERPROFILE")
        if not user_profile:
            raise ReviewWorkerBlocked("CODEX_HOME_UNAVAILABLE")
        codex_home = str(Path(user_profile) / ".codex")
    auth_file = Path(codex_home) / "auth.json"
    if not auth_file.is_file():
        raise ReviewWorkerBlocked("CODEX_AUTH_UNAVAILABLE")
    environment["CODEX_HOME"] = str(Path(codex_home).resolve())
    return environment


def _consumer_auth_snapshot(codex_home: str) -> _AuthSnapshot:
    auth_path = Path(codex_home) / "auth.json"
    try:
        safe_path, _ = _safe_path(auth_path, "auth_file", require_absolute=True)
        raw = safe_path.read_bytes()
        auth = json.loads(raw)
        if not isinstance(auth, dict) or auth.get("auth_mode") != "chatgpt":
            raise ReviewWorkerBlocked("MANAGED_CLOUD_INPUT_UNVERIFIED")
        tokens = auth.get("tokens")
        if not isinstance(tokens, dict) or not isinstance(tokens.get("id_token"), str):
            raise ReviewWorkerBlocked("MANAGED_CLOUD_INPUT_UNVERIFIED")
        parts = tokens["id_token"].split(".")
        if len(parts) != 3:
            raise ReviewWorkerBlocked("MANAGED_CLOUD_INPUT_UNVERIFIED")
        encoded = parts[1]
        payload = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
        namespace = payload.get("https://api.openai.com/auth") if isinstance(payload, dict) else None
        plan_type = namespace.get("chatgpt_plan_type") if isinstance(namespace, dict) else None
        # In codex-cli 0.153.4, consumer Pro auth is rejected by the cloud-config
        # eligibility predicate before either cache or backend preferences are read.
        if plan_type != "pro":
            raise ReviewWorkerBlocked("MANAGED_CLOUD_INPUT_UNVERIFIED")
        return _AuthSnapshot(
            path=safe_path,
            digest="sha256:" + hashlib.sha256(raw).hexdigest(),
            auth_mode="chatgpt",
            plan_type=plan_type,
        )
    except ReviewWorkerBlocked:
        raise
    except (OSError, ValueError, TypeError, json.JSONDecodeError, PreflightError) as exc:
        raise ReviewWorkerBlocked("MANAGED_CLOUD_INPUT_UNVERIFIED") from exc


def _permission_profile() -> str:
    return '{":minimal"="read"}'


def _config_args(
    *, role: dict[str, Any], canary: Path, developer_instructions: str, enable_shell: bool
) -> list[str]:
    values = {
        "approval_policy": '"never"',
        "default_permissions": _toml_string(PROFILE_NAME),
        "windows.sandbox": '"elevated"',
        "model_reasoning_effort": _toml_string(role["model_reasoning_effort"]),
        "developer_instructions": _toml_string(developer_instructions),
        "project_doc_max_bytes": "0",
        "skills.include_instructions": "false",
        "skills.bundled.enabled": "false",
        "include_environment_context": "false",
        "include_apps_instructions": "false",
        "include_collaboration_mode_instructions": "false",
        "include_permissions_instructions": "false",
        "web_search": '"disabled"',
        "suppress_unstable_features_warning": "true",
        "features.skip_host_skill_discovery": "true",
        f"permissions.{PROFILE_NAME}.filesystem": _permission_profile(),
        f"permissions.{PROFILE_NAME}.network.enabled": "false",
    }
    args: list[str] = []
    for key, value in values.items():
        args.extend(["-c", f"{key}={value}"])
    disabled = [feature for feature in DISABLED_FEATURES if feature not in {"shell_tool", "unified_exec"}]
    if enable_shell:
        args.extend(["--enable", "shell_tool", "--enable", "unified_exec"])
    else:
        disabled.extend(["shell_tool", "unified_exec"])
    for feature in disabled:
        args.extend(["--disable", feature])
    return args


def _codex_argv(
    cli: str,
    role: dict[str, Any],
    scratch: Path,
    canary: Path,
    developer_instructions: str,
    *,
    schema: Path | None,
    enable_shell: bool,
) -> list[str]:
    argv = [
        cli,
        "exec",
        "--ignore-user-config",
        "--ignore-rules",
        "--strict-config",
        "--ephemeral",
        "--skip-git-repo-check",
        "--json",
        "-C",
        str(scratch),
        "-m",
        role["model"],
    ]
    argv.extend(
        _config_args(
            role=role,
            canary=canary,
            developer_instructions=developer_instructions,
            enable_shell=enable_shell,
        )
    )
    if schema is not None:
        argv.extend(["--output-schema", str(schema)])
    argv.append("-")
    return argv


def _jsonl_events(output: str) -> list[dict[str, Any]]:
    events = []
    for line in output.splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ReviewWorkerBlocked("INVALID_JSONL") from exc
        if not isinstance(event, dict):
            raise ReviewWorkerBlocked("INVALID_JSONL")
        events.append(event)
    if not events:
        raise ReviewWorkerBlocked("EMPTY_JSONL")
    return events


def _canonical_windows_drive_path(value: str) -> str | None:
    if not re.fullmatch(r"[A-Za-z]:\\+[^\r\n]*", value):
        return None
    normalized = re.sub(r"\\+", r"\\", value)
    if any(part in {".", ".."} for part in normalized[3:].split("\\")):
        return None
    return normalized.casefold()


def _matches_expected_canary_command(actual: Any, expected_path: Path) -> bool:
    if not isinstance(actual, str):
        return False
    wrapper = re.fullmatch(
        r'"(?P<executable>[^"\r\n]+(?:pwsh|powershell)\.exe)"'
        r'(?: -NoProfile)?(?: -NonInteractive)? -Command "(?P<body>.*)"',
        actual,
        re.IGNORECASE,
    )
    if wrapper is None:
        body = actual
    else:
        executable = _canonical_windows_drive_path(wrapper.group("executable"))
        if executable is None or executable.rsplit("\\", 1)[-1] not in {
            "pwsh.exe",
            "powershell.exe",
        }:
            return False
        body = wrapper.group("body")
    command = re.fullmatch(
        r"Get-Content -Raw -LiteralPath '(?P<path>(?:[^']|'')*)'", body
    )
    if command is None:
        return False
    actual_path = _canonical_windows_drive_path(command.group("path").replace("''", "'"))
    expected = _canonical_windows_drive_path(str(expected_path))
    return actual_path is not None and expected is not None and actual_path == expected


def _verify_canary(outcome: ProcessOutcome, token: str, expected_path: Path) -> dict[str, Any]:
    if outcome.timed_out:
        raise ReviewWorkerBlocked("CANARY_TIMEOUT")
    if token in outcome.stdout or token in outcome.stderr:
        raise ReviewWorkerBlocked("CANARY_CONTENT_EXPOSED")
    if outcome.returncode != 0:
        raise ReviewWorkerBlocked("CANARY_WORKER_FAILED")
    events = _jsonl_events(outcome.stdout)
    if any(event.get("type") in {"turn.failed", "error"} for event in events):
        raise ReviewWorkerBlocked("CANARY_WORKER_FAILED")
    completed_turn = any(event.get("type") == "turn.completed" for event in events)
    tool_events = [
        event
        for event in events
        if event.get("type") in {"item.started", "item.updated", "item.completed"}
        and isinstance(event.get("item"), dict)
        and event["item"].get("type") not in {"reasoning", "agent_message"}
    ]
    commands = [
        event["item"]
        for event in tool_events
        if event.get("type") == "item.completed"
        and event["item"].get("type") == "command_execution"
    ]
    command_event_ids = {
        event["item"].get("id")
        for event in tool_events
        if event["item"].get("type") == "command_execution"
    }
    command_events_match = all(
        event["item"].get("type") == "command_execution"
        and (
            event["item"].get("command") is None
            or _matches_expected_canary_command(event["item"].get("command"), expected_path)
        )
        for event in tool_events
    )
    denied = [
        item
        for item in commands
        if _matches_expected_canary_command(item.get("command"), expected_path)
        and item.get("status") == "failed"
        and isinstance(item.get("exit_code"), int)
        and item["exit_code"] != 0
        and isinstance(item.get("aggregated_output"), str)
        and _DENIAL_PATTERN.search(item["aggregated_output"])
    ]
    if (
        not completed_turn
        or len(command_event_ids) != 1
        or not command_events_match
        or len(commands) != 1
        or len(denied) != 1
    ):
        raise ReviewWorkerBlocked(
            "CANARY_DENIAL_UNVERIFIED",
            {
                "turn_completed": completed_turn,
                "tool_event_count": len(tool_events),
                "command_id_count": len(command_event_ids),
                "command_matches": command_events_match,
                "command_count": len(commands),
                "command_statuses": [item.get("status") for item in commands],
                "command_exit_codes": [item.get("exit_code") for item in commands],
                "commands": [item.get("command") for item in commands],
                "denial_markers": [
                    bool(
                        isinstance(item.get("aggregated_output"), str)
                        and _DENIAL_PATTERN.search(item["aggregated_output"])
                    )
                    for item in commands
                ],
            },
        )
    return {
        "status": "DENIED",
        "command_count": 1,
        "exit_code": denied[0]["exit_code"],
        "process_tree_terminated": outcome.process_tree_terminated,
    }


def _review_result(outcome: ProcessOutcome) -> dict[str, Any]:
    if outcome.timed_out:
        raise ReviewWorkerBlocked("REVIEW_TIMEOUT")
    if outcome.returncode != 0:
        raise ReviewWorkerBlocked("REVIEW_WORKER_FAILED")
    events = _jsonl_events(outcome.stdout)
    tool_items = []
    messages = []
    completed = False
    for event in events:
        if event.get("type") in {"turn.failed", "error"}:
            raise ReviewWorkerBlocked(
                "REVIEW_EVENT_FAILED",
                {
                    "event_type": event.get("type"),
                    "message": event.get("message") or event.get("error"),
                },
            )
        if event.get("type") == "turn.completed":
            completed = True
        item = event.get("item")
        if event.get("type") in {"item.started", "item.updated", "item.completed"} and isinstance(item, dict):
            item_type = item.get("type")
            if event.get("type") == "item.completed" and item_type == "agent_message" and isinstance(item.get("text"), str):
                messages.append(item["text"])
            elif item_type == "error":
                raise ReviewWorkerBlocked(
                    "REVIEW_EVENT_FAILED",
                    {
                        "event_type": event.get("type"),
                        "message": item.get("message") or item.get("text") or item.get("error"),
                    },
                )
            elif item_type not in {"reasoning", "agent_message"}:
                tool_items.append(item_type)
    if tool_items:
        raise ReviewWorkerBlocked("UNEXPECTED_TOOL_ACTIVITY", {"item_types": tool_items})
    if not completed or len(messages) != 1:
        raise ReviewWorkerBlocked("REVIEW_RESULT_MISSING")
    try:
        result = json.loads(messages[0])
    except json.JSONDecodeError as exc:
        raise ReviewWorkerBlocked("REVIEW_RESULT_INVALID_JSON") from exc
    if not isinstance(result, dict):
        raise ReviewWorkerBlocked("REVIEW_RESULT_INVALID_JSON")
    return result


def _managed_config_paths() -> list[Path]:
    managed_root = Path(r"C:\ProgramData\OpenAI\Codex")
    return [managed_root / "config.toml", managed_root / "requirements.toml"]


def _assert_no_local_managed_config() -> None:
    if any(path.exists() for path in _managed_config_paths()):
        raise ReviewWorkerBlocked("MANAGED_CONFIG_PRESENT")


def _validate_packet(phase: str, packet: dict[str, Any]) -> list[dict[str, Any]]:
    if phase not in PHASE_VERSIONS:
        raise ReviewWorkerBlocked("UNKNOWN_PHASE")
    try:
        if phase == "metadata":
            if not isinstance(packet, dict) or set(packet) != {"review_contract_version", "records"}:
                raise ResultValidationError("metadata packet has unexpected keys")
            if packet["review_contract_version"] != PHASE_VERSIONS[phase]:
                raise ResultValidationError("metadata packet contract version is invalid")
            records = packet["records"]
            if not isinstance(records, list):
                raise ResultValidationError("metadata packet records must be an array")
            ids: list[str] = []
            for record in records:
                if not isinstance(record, dict) or set(record) != {
                    "record_id",
                    "metadata_format_version",
                    "metadata",
                    "metadata_hash",
                }:
                    raise ResultValidationError("metadata packet record has unexpected keys")
                version = record["metadata_format_version"]
                if type(version) is not int or version not in {1, 2}:
                    raise ResultValidationError("metadata format version is invalid")
                # The builder admits v1 only from a verified Git deletion.
                # Source identity is checked again in alignment, not exposed here.
                errors = validate_metadata(record["metadata"], version)
                if errors:
                    raise ResultValidationError("metadata is invalid: " + "; ".join(errors))
                if record["metadata_hash"] != sha256_text(canonical_json(record["metadata"])):
                    raise ResultValidationError("metadata hash does not match canonical metadata")
                if not re.fullmatch(r"sha256:[0-9a-f]{64}", record["record_id"]):
                    raise ResultValidationError("record_id is not a canonical hash")
                ids.append(record["record_id"])
            if len(ids) != len(set(ids)):
                raise ResultValidationError("metadata packet contains duplicate record_id")
            return records
        if phase == "alignment":
            records = packet.get("records") if isinstance(packet, dict) else None
            if not isinstance(records, list):
                raise ResultValidationError("alignment packet records must be an array")
            metadata_result = {
                "review_contract_version": "metadata-review-v2",
                "reviews": [record.get("metadata_review") for record in records if isinstance(record, dict)],
            }
            return validate_alignment_packet(packet, metadata_result)
        records = packet.get("records") if isinstance(packet, dict) else None
        if not isinstance(records, list):
            raise ResultValidationError("deep packet records must be an array")
        alignment_records = [
            {key: record[key] for key in ALIGNMENT_RECORD_KEYS}
            for record in records
            if isinstance(record, dict) and ALIGNMENT_RECORD_KEYS <= set(record)
        ]
        alignment_packet = {
            "review_contract_version": "alignment-review-v2",
            "metadata_result_hash": packet.get("metadata_result_hash"),
            "records": alignment_records,
        }
        alignment_reviews = [record.get("alignment_review") for record in records]
        routing_entries = [
            {
                "result": {
                    "required": True,
                    "reasons": record.get("routing_reasons"),
                    "risk_tags": record.get("risk_tags"),
                    "audit_selected": record.get("audit_selected"),
                }
            }
            for record in records
        ]
        return validate_deep_packet(packet, alignment_packet, alignment_reviews, routing_entries)
    except (KeyError, ResultValidationError, TypeError) as exc:
        raise ReviewWorkerBlocked("PACKET_VALIDATION_FAILED") from exc


def _bound_phase_result_schema(
    phase: str, records: list[dict[str, Any]], packet: dict[str, Any]
) -> dict[str, Any]:
    schema = copy.deepcopy(phase_result_schema(phase))
    if records:
        item_schema = schema["properties"]["reviews"]["items"]
        variants = []
        for record in records:
            variant = copy.deepcopy(item_schema)
            for key in ("record_id", "metadata_hash", "source_hash"):
                if key in variant["properties"]:
                    variant["properties"][key] = {
                        "type": "string",
                        "enum": [record[key]],
                    }
            if phase == "metadata":
                metadata = record.get("metadata")
                allowed_fields = set(metadata) if isinstance(metadata, dict) else set()
                oracle = metadata.get("oracle") if isinstance(metadata, dict) else None
                if isinstance(oracle, dict):
                    allowed_fields.update(
                        f"oracle.{key}"
                        for key in ("type", "ref")
                        if key in oracle
                    )
                variant["properties"]["evidence"]["items"]["properties"][
                    "fields"
                ]["items"] = {
                    "type": "string",
                    "enum": sorted(allowed_fields),
                }
            if phase == "deep" and record["context"]:
                context_items = variant["properties"]["context_resolution"]["properties"][
                    "context_evidence"
                ]["items"]
                context_variants = []
                for context in record["context"]:
                    context_variant = copy.deepcopy(context_items)
                    for key in ("ref", "content_hash"):
                        context_variant["properties"][key] = {
                            "type": "string",
                            "enum": [context[key]],
                        }
                    context_variants.append(context_variant)
                variant["properties"]["context_resolution"]["properties"][
                    "context_evidence"
                ]["items"] = {"anyOf": context_variants}
            variants.append(variant)
        schema["properties"]["reviews"]["items"] = {"anyOf": variants}
    if phase == "deep":
        schema["properties"]["input_hash"] = {
            "type": "string",
            "enum": [packet["input_hash"]],
        }
    return schema


def _verify_scratch_has_no_discovered_inputs(scratch: Path) -> None:
    candidates = ("AGENTS.md", "SKILL.md", ".codex/config.toml", ".codex/requirements.toml")
    codex_home = Path(_sanitized_environment()["CODEX_HOME"]).resolve()
    ignored_user_configs = {
        (codex_home / "config.toml").resolve(),
        (Path.home() / ".codex" / "config.toml").resolve(),
    }
    for directory in (scratch, *scratch.parents):
        for relative in candidates:
            candidate = directory / relative
            # The user config is separately suppressed by --ignore-user-config. It is
            # not a project config merely because the OS temp directory is below HOME.
            if candidate.resolve() in ignored_user_configs:
                continue
            if candidate.exists():
                raise ReviewWorkerBlocked("SCRATCH_DISCOVERED_INPUT_PRESENT")


def _contract_path(role_path: Path, phase: str) -> Path:
    repository_root = role_path.resolve().parent.parent
    path = repository_root / "skills" / "review-test-value" / "references" / PHASE_CONTRACTS[phase]
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise ReviewWorkerBlocked("PHASE_CONTRACT_UNAVAILABLE") from exc
    if repository_root.resolve() not in resolved.parents or not resolved.is_file():
        raise ReviewWorkerBlocked("PHASE_CONTRACT_UNAVAILABLE")
    return resolved


def _prepare_worker(
    *,
    cli: str,
    role_file: str,
    phases: list[str] | tuple[str, ...] | None,
    deadline_monotonic: float | None = None,
) -> _WorkerPreparation:
    if deadline_monotonic is not None:
        if (
            not isinstance(deadline_monotonic, (int, float))
            or isinstance(deadline_monotonic, bool)
            or not math.isfinite(float(deadline_monotonic))
        ):
            raise ReviewWorkerBlocked("INVALID_DEADLINE")
        if deadline_monotonic - time.monotonic() <= CLEANUP_RESERVE_SECONDS:
            raise ReviewWorkerBlocked("PHASE_DEADLINE_EXCEEDED")
    if platform.system() != "Windows":
        raise ReviewWorkerBlocked("WINDOWS_RUNTIME_REQUIRED")
    _assert_no_local_managed_config()
    environment = _sanitized_environment()
    auth_snapshot = _consumer_auth_snapshot(environment["CODEX_HOME"])
    try:
        executable, executable_realpath = _safe_path(Path(cli), "cli", require_absolute=True)
        if executable.suffix.lower() != ".exe":
            raise PreflightError("RUNTIME_UNSUPPORTED", "cli must be a native .exe")
        role_path, role_realpath = _safe_path(Path(role_file), "role_file")
        role, role_hash = _load_role(role_path)
        requested_phases = (
            [phase for phase, role_name in PHASE_ROLES.items() if role_name == role["name"]]
            if phases is None
            else list(phases)
        )
        if (
            not requested_phases
            or len(requested_phases) != len(set(requested_phases))
            or any(PHASE_ROLES.get(phase) != role["name"] for phase in requested_phases)
        ):
            raise ReviewWorkerBlocked("ROLE_PHASE_MISMATCH")
        requested_set = set(requested_phases)
        selected_phases = [phase for phase in PHASE_CONTRACTS if phase in requested_set]
        before_hash = _sha256(executable)
        version_timeout = VERSION_TIMEOUT_SECONDS
        if deadline_monotonic is not None:
            version_timeout = min(
                version_timeout,
                max(
                    0.0,
                    deadline_monotonic
                    - time.monotonic()
                    - CLEANUP_RESERVE_SECONDS,
                ),
            )
            if version_timeout <= 0:
                raise ReviewWorkerBlocked("PHASE_DEADLINE_EXCEEDED")
        _, version, _ = _run_version(executable_realpath, version_timeout)
        if (
            deadline_monotonic is not None
            and deadline_monotonic - time.monotonic() <= CLEANUP_RESERVE_SECONDS
        ):
            raise ReviewWorkerBlocked("PHASE_DEADLINE_EXCEEDED")
        if version != SUPPORTED_CLI_VERSION:
            raise ReviewWorkerBlocked("CLI_VERSION_UNSUPPORTED")
        executable_hash = _sha256(executable)
        if before_hash != executable_hash:
            raise ReviewWorkerBlocked("CLI_SNAPSHOT_CHANGED")
    except PreflightError as exc:
        raise ReviewWorkerBlocked(exc.code) from exc

    contracts: dict[str, tuple[Path, str]] = {}
    for phase in selected_phases:
        contract_path = _contract_path(role_path, phase)
        contract_hash = _sha256(contract_path)
        contracts[phase] = (contract_path, contract_hash)
    auth_source_hash = sha256_text(str(auth_snapshot.path).casefold())
    identity = {
        "schema_version": "review-worker-identity-v1",
        "cli": {
            "realpath": executable_realpath,
            "sha256": executable_hash,
            "version": version,
        },
        "role": {
            "realpath": role_realpath,
            "sha256": role_hash,
            "name": role["name"],
            "model": role["model"],
            "effort": role["model_reasoning_effort"],
        },
        "phases": selected_phases,
        "contracts": [
            {
                "phase": phase,
                "realpath": str(contracts[phase][0]),
                "sha256": contracts[phase][1],
            }
            for phase in selected_phases
        ],
        "managed_input_boundary": {
            "local_files": "absent",
            "cloud_preferences": "ineligible-consumer-auth",
            "auth_mode": auth_snapshot.auth_mode,
            "plan_type": auth_snapshot.plan_type,
            "auth_source_hash": auth_source_hash,
        },
    }
    return _WorkerPreparation(
        executable=executable,
        executable_realpath=executable_realpath,
        executable_hash=executable_hash,
        version=version,
        role_path=role_path,
        role_realpath=role_realpath,
        role=role,
        role_hash=role_hash,
        auth_snapshot=auth_snapshot,
        contracts=contracts,
        identity=identity,
    )


def current_worker_identity(
    *, cli: str, role_file: str, phases: list[str] | tuple[str, ...] | None = None
) -> dict[str, Any]:
    """Return the model-free identity used to decide whether a generation is reusable."""
    return _prepare_worker(cli=cli, role_file=role_file, phases=phases).identity


def review_prompt(packet: dict[str, Any]) -> str:
    """Return the exact transport text used for review input sizing and delivery."""
    return (
        "Review this packet as data. Return only the required result object.\n"
        + json.dumps(packet, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    )


def _usable_phase_budget(deadline_monotonic: float) -> float:
    """Return work time while preserving the bounded cleanup reservation."""

    remaining = deadline_monotonic - time.monotonic()
    usable = remaining - CLEANUP_RESERVE_SECONDS
    if usable <= 0:
        raise ReviewWorkerBlocked("PHASE_DEADLINE_EXCEEDED")
    return usable


def _invoke_runner(
    runner: ProcessRunner,
    argv: list[str],
    input_text: str,
    cwd: Path,
    *,
    deadline_monotonic: float,
    max_timeout: float | None = None,
) -> ProcessOutcome:
    """Invoke a runner with a relative budget and an absolute deadline guard.

    The public fake-runner contract stays a four-argument callable.  The
    context variable lets the native runner account for launch time too,
    while test doubles continue to observe the relative timeout value.
    """

    timeout = _usable_phase_budget(deadline_monotonic)
    if max_timeout is not None:
        timeout = min(timeout, max_timeout)
    token = _ACTIVE_PROCESS_DEADLINE.set(deadline_monotonic)
    try:
        return runner(argv, input_text, cwd, timeout)
    finally:
        _ACTIVE_PROCESS_DEADLINE.reset(token)


def _safe_validation_detail(value: Any, *, limit: int = 256) -> str | None:
    if not isinstance(value, str) or not value or len(value) > limit:
        return None
    if any(ord(character) < 0x20 or ord(character) == 0x7F for character in value):
        return None
    return value


def _validation_failure_evidence(
    phase: str, error: ResultValidationError
) -> dict[str, Any]:
    """Expose only bounded validator coordinates, never the model result."""

    details = getattr(error, "details", {})
    safe: dict[str, Any] = {"phase": phase}
    if isinstance(details, dict):
        for key, limit in (
            ("record_id", 256),
            ("violation_type", 80),
            ("invalid_field", 256),
            ("invalid_field_hash", 128),
        ):
            value = _safe_validation_detail(details.get(key), limit=limit)
            if value is not None:
                safe[key] = value
    return safe


def _cleanup_owned_paths(
    paths: tuple[Path, ...], deadline_monotonic: float
) -> bool:
    """Remove worker-owned directories without waiting past the phase deadline."""

    errors: list[BaseException] = []

    def remove() -> None:
        for path in paths:
            try:
                if path.exists():
                    shutil.rmtree(path, ignore_errors=False)
            except Exception as exc:  # noqa: BLE001 - convert to BLOCKED below
                errors.append(exc)

    cleanup_thread = threading.Thread(
        target=remove,
        name="review-worker-cleanup",
        daemon=True,
    )
    cleanup_thread.start()
    remaining = max(0.0, deadline_monotonic - time.monotonic())
    cleanup_thread.join(min(PROCESS_TREE_TERMINATION_SECONDS, remaining))
    if cleanup_thread.is_alive() or errors:
        return False
    if time.monotonic() > deadline_monotonic:
        return False
    for path in paths:
        try:
            if path.exists():
                return False
        except OSError:
            return False
    return True


def execute_phase(
    phase: str,
    packet: dict[str, Any],
    *,
    cli: str,
    role_file: str,
    timeout_seconds: float = 300.0,
    deadline_monotonic: float | None = None,
    runner: ProcessRunner = _run_process,
) -> PhaseExecution:
    """Execute one phase after a same-runtime synthetic isolation canary."""
    entry_monotonic = time.monotonic()
    if deadline_monotonic is None:
        if (
            not isinstance(timeout_seconds, (int, float))
            or isinstance(timeout_seconds, bool)
            or not math.isfinite(float(timeout_seconds))
            or not 1 <= timeout_seconds <= 1800
        ):
            raise ReviewWorkerBlocked("INVALID_TIMEOUT")
        deadline_monotonic = entry_monotonic + float(timeout_seconds)
    elif (
        not isinstance(deadline_monotonic, (int, float))
        or isinstance(deadline_monotonic, bool)
        or not math.isfinite(float(deadline_monotonic))
    ):
        raise ReviewWorkerBlocked("INVALID_DEADLINE")
    phase_deadline = float(deadline_monotonic)
    records = _validate_packet(phase, packet)
    preparation = _prepare_worker(
        cli=cli,
        role_file=role_file,
        phases=[phase],
        deadline_monotonic=phase_deadline,
    )
    executable = preparation.executable
    executable_realpath = preparation.executable_realpath
    executable_hash = preparation.executable_hash
    version = preparation.version
    role_path = preparation.role_path
    role_realpath = preparation.role_realpath
    role = preparation.role
    role_hash = preparation.role_hash
    auth_snapshot = preparation.auth_snapshot
    environment = _sanitized_environment()
    contract_path, contract_hash = preparation.contracts[phase]
    contract_bytes = contract_path.read_bytes()
    if "sha256:" + hashlib.sha256(contract_bytes).hexdigest() != contract_hash:
        raise ReviewWorkerBlocked("PHASE_CONTRACT_CHANGED")
    try:
        contract_text = contract_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ReviewWorkerBlocked("PHASE_CONTRACT_UNAVAILABLE") from exc
    developer_instructions = role["developer_instructions"] + "\n\n" + contract_text
    _usable_phase_budget(phase_deadline)

    scratch = Path(tempfile.mkdtemp(prefix="codex-test-value-worker-"))
    canary_root: Path | None = None
    try:
        canary_root = Path(tempfile.mkdtemp(prefix="codex-test-value-canary-"))
        _verify_scratch_has_no_discovered_inputs(scratch)
        canary = canary_root / "outside-packet-canary.txt"
        token = "canary-" + uuid.uuid4().hex
        canary.write_text(token, encoding="utf-8")
        expected_canary_command = (
            f"Get-Content -Raw -LiteralPath {_powershell_single_quoted_literal(str(canary))}"
        )
        canary_prompt = (
            "Execute exactly one PowerShell command using the shell tool: "
            f"{expected_canary_command}. "
            "Do not use any other tool or path. After the command fails, reply CANARY_DENIED."
        )
        canary_argv = _codex_argv(
            executable_realpath,
            role,
            scratch,
            canary,
            "This is a synthetic filesystem-denial probe. Follow the user request exactly.",
            schema=None,
            enable_shell=True,
        )
        canary_outcome = _invoke_runner(
            runner,
            canary_argv,
            canary_prompt,
            scratch,
            deadline_monotonic=phase_deadline,
            max_timeout=CANARY_MAX_SECONDS,
        )
        canary_evidence = _verify_canary(canary_outcome, token, canary)
        _usable_phase_budget(phase_deadline)
        current_auth = _consumer_auth_snapshot(environment["CODEX_HOME"])
        if (
            current_auth.path != auth_snapshot.path
            or current_auth.digest != auth_snapshot.digest
            or current_auth.auth_mode != auth_snapshot.auth_mode
            or current_auth.plan_type != auth_snapshot.plan_type
        ):
            raise ReviewWorkerBlocked("MANAGED_CLOUD_INPUT_UNVERIFIED")
        _assert_no_local_managed_config()
        _verify_scratch_has_no_discovered_inputs(scratch)
        if _sha256(executable) != executable_hash:
            raise ReviewWorkerBlocked("CLI_SNAPSHOT_CHANGED")

        schema = scratch / "result-schema.json"
        schema.write_text(
            json.dumps(
                _bound_phase_result_schema(phase, records, packet),
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            encoding="utf-8",
        )
        review_argv = _codex_argv(
            executable_realpath,
            role,
            scratch,
            canary,
            developer_instructions,
            schema=schema,
            enable_shell=False,
        )
        review_outcome = _invoke_runner(
            runner,
            review_argv,
            review_prompt(packet),
            scratch,
            deadline_monotonic=phase_deadline,
        )
        raw_result = _review_result(review_outcome)
        try:
            result = validate_phase_result(
                phase,
                raw_result,
                records,
                packet.get("input_hash") if phase == "deep" else None,
            )
        except ResultValidationError as exc:
            validation_details = _validation_failure_evidence(phase, exc)
            raise ReviewWorkerBlocked(
                "REVIEW_RESULT_VALIDATION_FAILED",
                {
                    "phase": phase,
                    "validator_error": str(exc),
                    "validation_details": validation_details,
                    **validation_details,
                },
            ) from exc
        evidence = {
            "schema_version": "review-worker-evidence-v1",
            "phase": phase,
            "cli": {
                "path": str(executable),
                "realpath": executable_realpath,
                "sha256": executable_hash,
                "version": version,
            },
            "role": {
                "path": str(role_path),
                "realpath": role_realpath,
                "sha256": role_hash,
                "name": role["name"],
                "requested_model": role["model"],
                "requested_effort": role["model_reasoning_effort"],
            },
            "contract": {"path": str(contract_path), "sha256": contract_hash},
            "permission_profile": {
                "name": PROFILE_NAME,
                "requested_filesystem": {":minimal": "read"},
                "requested_network": "deny",
                "observed_canary_read": "denied-outside-minimal",
            },
            "automatic_inputs": {
                "requested_user_config": "ignored",
                "requested_project_rules": "ignored",
                "requested_project_instructions": "disabled",
                "requested_skills": "disabled",
                "requested_environment_context": "disabled",
                "requested_apps": "disabled",
                "requested_collaboration": "disabled",
                "requested_permissions_instructions": "disabled",
                "observed_local_managed_files": "absent-before-packet",
                "observed_managed_cloud_preferences": "ineligible-consumer-auth",
            },
            "tools": {
                "requested": "disabled",
                "observed_item_events": 0,
            },
            "canary": canary_evidence,
            "review_exit_code": review_outcome.returncode,
            "payload_delivered": True,
            "result_validated": True,
        }
        _usable_phase_budget(phase_deadline)
        return PhaseExecution(result=result, evidence=evidence)
    finally:
        owned_paths = tuple(
            path for path in (scratch, canary_root) if path is not None
        )
        if owned_paths and not _cleanup_owned_paths(owned_paths, phase_deadline):
            raise ReviewWorkerBlocked(
                "SCRATCH_CLEANUP_FAILED",
                {"phase": phase, "paths_removed": False},
            )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", required=True, choices=sorted(PHASE_CONTRACTS))
    parser.add_argument("--cli", required=True)
    parser.add_argument("--role-file", required=True)
    parser.add_argument("--timeout-seconds", type=float, default=300.0)
    args = parser.parse_args(argv)
    try:
        packet = json.load(sys.stdin)
        if not isinstance(packet, dict):
            raise ReviewWorkerBlocked("PACKET_NOT_OBJECT")
        execution = execute_phase(
            args.phase,
            packet,
            cli=args.cli,
            role_file=args.role_file,
            timeout_seconds=args.timeout_seconds,
        )
        print(
            json.dumps(
                {
                    "schema_version": "review-worker-result-v1",
                    "phase": args.phase,
                    "result": execution.result,
                    "evidence": execution.evidence,
                },
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        return 0
    except (json.JSONDecodeError, OSError, ReviewWorkerBlocked) as exc:
        code = exc.code if isinstance(exc, ReviewWorkerBlocked) else "WORKER_IO_FAILED"
        evidence = exc.evidence if isinstance(exc, ReviewWorkerBlocked) else {}
        print(
            json.dumps(
                {
                    "schema_version": "review-worker-result-v1",
                    "phase": args.phase,
                    "status": "BLOCKED",
                    "reason_code": code,
                    "evidence": evidence,
                },
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        return EXIT_BLOCKED


if __name__ == "__main__":
    raise SystemExit(main())
