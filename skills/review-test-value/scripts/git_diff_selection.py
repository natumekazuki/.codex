from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Protocol, Sequence


class AdapterProfileLike(Protocol):
    language: str
    extensions: tuple[str, ...]
    adapter: str
    coverage: str


ExtractSourceText = Callable[
    [str, str, AdapterProfileLike, str | None],
    tuple[list[dict[str, Any]], list[dict[str, Any]]],
]
DiagnosticFactory = Callable[[str, str, int, str], dict[str, Any]]


@dataclass(frozen=True)
class ChangedFile:
    path: str
    ranges: tuple[tuple[int, int], ...]
    deletion_anchors: tuple[int, ...] = ()
    status: str = "M"
    old_path: str | None = None
    whole_file: bool = False


@dataclass
class _ChangedFileBuilder:
    status: str
    ranges: list[tuple[int, int]]
    deletion_anchors: list[int]
    old_path: str | None = None
    whole_file: bool = False


class SourceOutsideRootError(ValueError):
    def __init__(self, path: str) -> None:
        super().__init__(path)
        self.path = path


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
    common = [
        "diff",
        "--no-ext-diff",
        "--no-textconv",
        "--text",
        "--no-color",
        "--find-renames",
        "--unified=0",
    ]
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
    files: dict[str, _ChangedFileBuilder] = {}
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
        files.setdefault(path, _ChangedFileBuilder(code, [], [], old_path))
    for path, item in files.items():
        paths = [item.old_path, path] if item.old_path is not None else [path]
        args = _diff_args(base, mode, head) + ["--", *paths]
        for line in str(_git(root, args)).splitlines():
            m = _HUNK.match(line)
            if m:
                start = int(m.group(1))
                count = int(m.group(2) or 1)
                if count:
                    item.ranges.append((start, start + count - 1))
                else:
                    item.deletion_anchors.append(start)
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
            files.setdefault(
                path.replace("\\", "/"),
                _ChangedFileBuilder("A", [], [], whole_file=True),
            )
    return tuple(
        ChangedFile(
            path=path,
            ranges=tuple(item.ranges),
            deletion_anchors=tuple(item.deletion_anchors),
            status=item.status,
            old_path=item.old_path,
            whole_file=item.whole_file,
        )
        for path, item in sorted(files.items())
    )


def _snapshot(root: Path, path: str, mode: str, head: str | None) -> bytes:
    if mode == "working":
        resolved_root = root.resolve(strict=True)
        resolved = (resolved_root / path).resolve(strict=True)
        if not resolved.is_relative_to(resolved_root):
            raise SourceOutsideRootError(path)
        return resolved.read_bytes()
    spec = f"{head}:{path}" if mode == "head" else f":{path}"
    return bytes(_git(root, ["show", spec], text=False))


def _base_snapshot(root: Path, base: str, item: ChangedFile) -> bytes | None:
    if item.status == "A":
        return None
    path = item.old_path or item.path
    return bytes(_git(root, ["show", f"{base}:{path}"], text=False))


def _affects_span(item: ChangedFile, start: int, end: int) -> bool:
    if item.whole_file:
        return True
    if any(start <= high and end >= low for low, high in item.ranges):
        return True
    return any(start - 1 <= anchor <= end for anchor in item.deletion_anchors)


def select_git(
    root: Path,
    base: str,
    profile: AdapterProfileLike,
    extract_source_text: ExtractSourceText,
    diagnostic: DiagnosticFactory,
    mode: str = "working",
    head: str | None = None,
) -> dict:
    files = [
        item
        for item in changed_files(root, base, mode, head)
        if Path(item.path).suffix.lower() in profile.extensions
    ]
    tests: list[dict] = []
    diagnostics: list[dict] = []
    for item in files:
        try:
            snapshot = _snapshot(root, item.path, mode, head)
        except SourceOutsideRootError:
            diagnostics.append(
                diagnostic(
                    "SOURCE_OUTSIDE_ROOT",
                    item.path,
                    0,
                    "source path resolves outside repository root",
                )
            )
            continue
        if not item.whole_file and not item.ranges and not item.deletion_anchors:
            base_snapshot = _base_snapshot(root, base, item)
            if base_snapshot == snapshot:
                continue
            if base_snapshot is not None:
                raise ValueError(
                    f"Git reported a content change without text hunks: {item.path}"
                )
        try:
            raw = snapshot.decode("utf-8-sig")
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
        recs, diags = extract_source_text(
            raw,
            item.path,
            profile,
            Path(item.path).suffix.lower(),
        )
        selected_spans: list[tuple[int, int]] = []
        for rec in recs:
            s = rec["source"]
            start = s["metadata_start_line"] or s["declaration_start_line"]
            end = s["declaration_end_line"]
            if _affects_span(item, start, end):
                tests.append(rec)
                selected_spans.append((start, end))
        for d in diags:
            if d["code"] in {"SOURCE_SYNTAX_ERROR", "SOURCE_DECODE_ERROR"} or (
                item.whole_file
                or _affects_span(item, d["line"], d["line"])
                or any(low <= d["line"] <= high for low, high in selected_spans)
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
