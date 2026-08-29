from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from extract_test_values import (
    ADAPTER_PROFILES,
    diagnostic,
    extract_source_text,
)


@dataclass(frozen=True)
class ChangedFile:
    path: str
    ranges: tuple[tuple[int, int], ...]
    status: str = "M"
    old_path: str | None = None


_HUNK = re.compile(r"^@@ -(?:\d+)(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


def _git(root: Path, args: Sequence[str], *, text: bool = True) -> str | bytes:
    try:
        p = subprocess.run(
            ["git", "--no-pager", *args],
            cwd=root,
            check=False,
            capture_output=True,
            text=text,
            encoding="utf-8" if text else None,
        )
    except OSError as e:
        raise ValueError(f"git is unavailable: {e}") from e
    if p.returncode:
        detail = (p.stderr or p.stdout or b"").strip()
        if isinstance(detail, bytes):
            detail = detail.decode("utf-8", "replace")
        raise ValueError(f"git command failed: {detail}")
    return p.stdout


def _diff_args(base: str, mode: str, head: str | None) -> list[str]:
    common = ["diff", "--no-ext-diff", "--no-color", "--find-renames", "--unified=0"]
    if mode == "working":
        return [*common, base]
    if mode == "staged":
        return [*common, "--cached", base]
    return [*common, base, head or ""]


def changed_files(
    root: Path,
    base: str,
    mode: str = "working",
    head: str | None = None,
) -> tuple[ChangedFile, ...]:
    if mode not in {"working", "staged", "head"} or (mode == "head" and not head):
        raise ValueError("invalid git diff mode")
    actual = str(_git(root, ["rev-parse", "--show-toplevel"])).strip()
    if Path(actual).resolve() != root.resolve():
        raise ValueError("--root must be the Git repository root")
    _git(root, ["rev-parse", "--verify", f"{base}^{{commit}}"])
    if mode == "head":
        _git(root, ["rev-parse", "--verify", f"{head}^{{commit}}"])
    diff_base = [
        "diff",
        "--no-ext-diff",
        "--no-color",
        "--find-renames",
        "--name-status",
        "-z",
        base,
    ]
    if mode == "head":
        diff_base.append(head or "")
    elif mode == "staged":
        diff_base.append("--cached")
    payload = bytes(_git(root, diff_base, text=False))
    tokens = payload.split(b"\0")
    files: dict[str, tuple[str, list[tuple[int, int]], str | None]] = {}
    i = 0
    while i < len(tokens) - 1:
        status = tokens[i].decode("ascii", "replace")
        i += 1
        if not status:
            continue
        code = status[0]
        old_path = None
        if code in {"R", "C"}:
            old_path = tokens[i].decode("utf-8", "surrogateescape")
            i += 1
        if i >= len(tokens):
            break
        path = tokens[i].decode("utf-8", "surrogateescape")
        i += 1
        if code == "D":
            continue
        files.setdefault(path, (code, [], old_path))
    for path, (_status, ranges, old_path) in files.items():
        paths = [old_path, path] if old_path is not None else [path]
        args = _diff_args(base, mode, head) + ["--", *paths]
        for line in str(_git(root, args)).splitlines():
            m = _HUNK.match(line)
            if m:
                start = int(m.group(1))
                count = int(m.group(2) or 1)
                if count:
                    ranges.append((start, start + count - 1))
    if mode == "working":
        untracked = bytes(
            _git(
                root,
                ["ls-files", "--others", "--exclude-standard", "-z"],
                text=False,
            )
        )
        for raw_path in filter(None, untracked.split(b"\0")):
            path = raw_path.decode("utf-8", "surrogateescape")
            p = root / path
            try:
                count = len(p.read_text(encoding="utf-8-sig").splitlines())
            except (OSError, UnicodeError):
                count = 1
            files.setdefault(path.replace("\\", "/"), ("A", [(1, max(1, count))], None))
    return tuple(
        ChangedFile(path, tuple(ranges), status, old_path)
        for path, (status, ranges, old_path) in sorted(files.items())
    )


def _snapshot(root: Path, path: str, mode: str, head: str | None) -> bytes:
    if mode == "working":
        return (root / path).read_bytes()
    spec = f"{head}:{path}" if mode == "head" else f":{path}"
    return bytes(_git(root, ["show", spec], text=False))


def select_git(
    root: Path,
    base: str,
    language: str,
    mode: str = "working",
    head: str | None = None,
) -> dict:
    profile = next((p for p in ADAPTER_PROFILES if p.language == language), None)
    if profile is None:
        raise ValueError(f"unsupported language: {language}")
    files = [
        item
        for item in changed_files(root, base, mode, head)
        if Path(item.path).suffix.lower() in profile.extensions and item.ranges
    ]
    tests: list[dict] = []
    diagnostics: list[dict] = []
    for item in files:
        try:
            raw = _snapshot(root, item.path, mode, head).decode("utf-8-sig")
        except UnicodeDecodeError as e:
            diagnostics.append(
                diagnostic(
                    "SOURCE_DECODE_ERROR",
                    item.path,
                    0,
                    f"source is not valid UTF-8: {e}",
                )
            )
            continue
        recs, diags = extract_source_text(raw, item.path, profile)
        selected_spans: list[tuple[int, int]] = []
        for rec in recs:
            s = rec["source"]
            start = s["metadata_start_line"] or s["declaration_start_line"]
            end = s["declaration_end_line"]
            if any(start <= hi and end >= lo for lo, hi in item.ranges):
                tests.append(rec)
                selected_spans.append((start, end))
        for d in diags:
            if d["code"] in {"SOURCE_SYNTAX_ERROR", "SOURCE_DECODE_ERROR"} or (
                any(lo <= d["line"] <= hi for lo, hi in item.ranges)
                or any(lo <= d["line"] <= hi for lo, hi in selected_spans)
            ):
                diagnostics.append(d)
    tests.sort(
        key=lambda r: (
            r["source"]["path"],
            r["source"]["declaration_start_line"],
            r["source"]["symbol"],
        )
    )
    diagnostics.sort(key=lambda d: (d["path"], d["line"], d["code"]))
    return {
        "schema_version": 1,
        "adapter": profile.adapter,
        "coverage": profile.coverage,
        "repository_root": ".",
        "tests": tests,
        "diagnostics": diagnostics,
    }
