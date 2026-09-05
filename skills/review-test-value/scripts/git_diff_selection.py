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
DiagnosticProjector = Callable[[dict[str, Any]], dict[str, Any]]


@dataclass(frozen=True)
class ChangedFile:
    path: str
    ranges: tuple[tuple[int, int], ...]
    hunks: tuple["DiffHunk", ...] = ()
    status: str = "M"
    old_path: str | None = None
    whole_file: bool = False


@dataclass
class _ChangedFileBuilder:
    status: str
    ranges: list[tuple[int, int]]
    hunks: list["DiffHunk"]
    old_path: str | None = None
    whole_file: bool = False


class SourceOutsideRootError(ValueError):
    def __init__(self, path: str) -> None:
        super().__init__(path)
        self.path = path


@dataclass(frozen=True)
class DiffHunk:
    old_start: int
    old_count: int
    new_start: int
    new_count: int

    @property
    def old_end(self) -> int:
        return self.old_start + self.old_count - 1


_HUNK = re.compile(
    r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@"
)


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
        "--ignore-cr-at-eol",
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
        files.setdefault(path, _ChangedFileBuilder(code, [], [], old_path))
    for path, item in files.items():
        paths = [item.old_path, path] if item.old_path is not None else [path]
        args = _diff_args(base, mode, head) + ["--", *paths]
        for line in str(_git(root, args)).splitlines():
            m = _HUNK.match(line)
            if m:
                old_start = int(m.group(1))
                old_count = int(m.group(2) or 1)
                new_start = int(m.group(3))
                new_count = int(m.group(4) or 1)
                item.hunks.append(
                    DiffHunk(
                        old_start=old_start,
                        old_count=old_count,
                        new_start=new_start,
                        new_count=new_count,
                    )
                )
                if new_count:
                    item.ranges.append((new_start, new_start + new_count - 1))
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
            hunks=tuple(item.hunks),
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


def _same_normalized_source(left: bytes, right: bytes) -> bool:
    try:
        left_text = left.decode("utf-8-sig")
        right_text = right.decode("utf-8-sig")
    except UnicodeDecodeError:
        return False
    return left_text.replace("\r\n", "\n").replace("\r", "\n") == (
        right_text.replace("\r\n", "\n").replace("\r", "\n")
    )


def _affects_span(
    item: ChangedFile,
    start: int,
    end: int,
    deletion_anchors: tuple[int, ...],
) -> bool:
    if item.whole_file:
        return True
    if any(start <= high and end >= low for low, high in item.ranges):
        return True
    return any(start - 1 <= anchor <= end for anchor in deletion_anchors)


def _map_old_line_to_new(line: int, hunks: tuple[DiffHunk, ...]) -> int:
    delta = 0
    for hunk in hunks:
        if hunk.old_count == 0:
            if line >= hunk.old_start:
                delta += hunk.new_count
            continue
        if line < hunk.old_start:
            break
        if line > hunk.old_end:
            delta += hunk.new_count - hunk.old_count
            continue
        if hunk.new_count == 0:
            return hunk.new_start
        return hunk.new_start + min(line - hunk.old_start, hunk.new_count - 1)
    return line + delta


def _map_old_declaration_start_to_new(
    line: int, hunks: tuple[DiffHunk, ...]
) -> int:
    for hunk in hunks:
        if (
            hunk.old_count
            and hunk.new_count == 0
            and hunk.old_start <= line <= hunk.old_end
        ):
            return hunk.new_start + 1
    return _map_old_line_to_new(line, hunks)


def _hunk_intersects_old_span(hunk: DiffHunk, start: int, end: int) -> bool:
    if hunk.old_count == 0:
        # Git anchors an insertion after the preceding old line.  The
        # declaration end therefore remains inside the changed span.
        return start <= hunk.old_start <= end
    return start <= hunk.old_end and end >= hunk.old_start


def _base_diagnostic_was_fully_replaced(
    item: ChangedFile,
    diagnostic: dict[str, Any],
) -> bool:
    start = diagnostic.get("_selection_start_line", diagnostic["line"])
    end = diagnostic.get("_selection_end_line", diagnostic["line"])
    return any(
        hunk.old_count
        and hunk.old_start <= start
        and hunk.old_end >= end
        for hunk in item.hunks
    )


def _base_change_projection(
    item: ChangedFile,
    base_records: Sequence[dict[str, Any]],
    base_diagnostics: Sequence[dict[str, Any]],
) -> tuple[tuple[int, ...], tuple[int, ...]]:
    if not item.hunks:
        return (), ()
    source_incomplete = any(
        diagnostic["code"] == "SOURCE_SYNTAX_ERROR"
        for diagnostic in base_diagnostics
    )
    unsupported_spans = {
        (
            diagnostic.get("_selection_start_line", diagnostic["line"]),
            diagnostic.get("_selection_end_line", diagnostic["line"]),
        )
        for diagnostic in base_diagnostics
        if diagnostic["code"] == "TEST_DECLARATION_UNSUPPORTED"
    }
    spans: list[tuple[int, int, int]] = []
    for record in base_records:
        source = record["source"]
        spans.append(
            (
                source["metadata_start_line"]
                or source["declaration_start_line"],
                source["declaration_end_line"],
                source["declaration_start_line"],
            )
        )
    projected_starts: set[int] = set()
    fallback_anchors: set[int] = set()
    for hunk in item.hunks:
        overlapping = [
            (start, end, declaration_start)
            for start, end, declaration_start in spans
            if _hunk_intersects_old_span(hunk, start, end)
        ]
        for start, end, declaration_start in overlapping:
            if (
                hunk.old_count
                and hunk.old_start <= start
                and hunk.old_end >= end
            ):
                continue
            projected_starts.add(
                _map_old_declaration_start_to_new(declaration_start, item.hunks)
            )
        hunk_is_uncertain = source_incomplete or any(
            _hunk_intersects_old_span(hunk, start, end)
            and not (
                hunk.old_count
                and hunk.old_start <= start
                and hunk.old_end >= end
            )
            for start, end in unsupported_spans
        )
        if hunk_is_uncertain:
            fallback_anchors.add(hunk.new_start)
            if hunk.new_count:
                fallback_anchors.add(hunk.new_start - 1)
    return tuple(sorted(projected_starts)), tuple(sorted(fallback_anchors))


def _record_sort_key(record: dict[str, Any]) -> tuple[str, int, str]:
    source = record["source"]
    return (
        source["path"],
        source["declaration_start_line"],
        source["symbol"],
    )


def _record_span(record: dict[str, Any]) -> tuple[int, int]:
    source = record["source"]
    return (
        source["metadata_start_line"] or source["declaration_start_line"],
        source["declaration_end_line"],
    )


def _record_was_fully_replaced(
    item: ChangedFile,
    record: dict[str, Any],
) -> bool:
    start, end = _record_span(record)
    return any(
        hunk.old_count
        and hunk.old_start <= start
        and hunk.old_end >= end
        for hunk in item.hunks
    )


def _transition_diagnostic(
    diagnostic: DiagnosticFactory,
    record: dict[str, Any],
    message: str,
) -> dict[str, Any]:
    source = record["source"]
    return diagnostic(
        "RECORD_TRANSITION_UNRESOLVED",
        source["path"],
        source["declaration_start_line"],
        message,
    )


def _build_transitions(
    item: ChangedFile,
    before_records: Sequence[dict[str, Any]],
    after_records: Sequence[dict[str, Any]],
    diagnostic: DiagnosticFactory,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    affected_before = [
        record
        for record in before_records
        if any(
            _hunk_intersects_old_span(hunk, *_record_span(record))
            for hunk in item.hunks
        )
    ]
    unmatched_after = list(after_records)
    transitions: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []

    for before in sorted(affected_before, key=_record_sort_key):
        source = before["source"]
        fully_replaced = _record_was_fully_replaced(item, before)
        projected_start = _map_old_declaration_start_to_new(
            source["declaration_start_line"], item.hunks
        )
        hash_candidates = [
            after
            for after in unmatched_after
            if after["source_hash"] == before["source_hash"]
            and after["metadata_hash"] == before["metadata_hash"]
        ]
        position_candidates = [
            after
            for after in unmatched_after
            if not fully_replaced
            and after["source"]["declaration_start_line"] == projected_start
        ]
        candidate_sets = [
            candidates
            for candidates in (hash_candidates, position_candidates)
            if candidates
        ]
        ambiguous = any(len(candidates) != 1 for candidates in candidate_sets)
        if len(candidate_sets) == 2 and candidate_sets[0][0] is not candidate_sets[1][0]:
            ambiguous = True
        if ambiguous:
            diagnostics.append(
                _transition_diagnostic(
                    diagnostic,
                    before,
                    "record hashes and Git hunk projection do not identify one current record",
                )
            )
            continue

        matched = candidate_sets[0][0] if candidate_sets else None
        if matched is None and not fully_replaced:
            diagnostics.append(
                _transition_diagnostic(
                    diagnostic,
                    before,
                    "a partially changed base record has no reliable current record mapping",
                )
            )
            continue
        if matched is None:
            transitions.append({"kind": "DELETED", "before": before, "after": None})
            continue
        unmatched_after.remove(matched)
        transitions.append({"kind": "SURVIVED", "before": before, "after": matched})

    transitions.extend(
        {"kind": "ADDED", "before": None, "after": after}
        for after in unmatched_after
    )
    transitions.sort(
        key=lambda transition: (
            _record_sort_key(transition["after"] or transition["before"]),
            transition["kind"],
        )
    )
    return transitions, diagnostics


def _deleted_base_diagnostics(
    item: ChangedFile,
    transitions: Sequence[dict[str, Any]],
    base_diagnostics: Sequence[dict[str, Any]],
    project_diagnostic: DiagnosticProjector,
) -> list[dict[str, Any]]:
    deleted_spans = [
        _record_span(transition["before"])
        for transition in transitions
        if transition["kind"] == "DELETED"
    ]
    if not deleted_spans and item.status != "D":
        return []
    return [
        project_diagnostic(value)
        for value in base_diagnostics
        if item.status == "D"
        or value["code"] == "SOURCE_SYNTAX_ERROR"
        or any(
            low <= value.get("_selection_end_line", value["line"])
            and high >= value.get("_selection_start_line", value["line"])
            for low, high in deleted_spans
        )
    ]


def select_git(
    root: Path,
    base: str,
    profile: AdapterProfileLike,
    extract_source_text: ExtractSourceText,
    diagnostic: DiagnosticFactory,
    project_diagnostic: DiagnosticProjector,
    mode: str = "working",
    head: str | None = None,
) -> dict:
    files = [
        item
        for item in changed_files(root, base, mode, head)
        if Path(item.path).suffix.lower() in profile.extensions
    ]
    tests: list[dict] = []
    transitions: list[dict] = []
    diagnostics: list[dict] = []
    for item in files:
        base_snapshot = _base_snapshot(root, base, item)
        base_records: list[dict[str, Any]] = []
        base_diagnostics: list[dict[str, Any]] = []
        if base_snapshot is not None:
            try:
                base_raw = base_snapshot.decode("utf-8-sig")
            except UnicodeDecodeError as error:
                diagnostics.append(
                    diagnostic(
                        "SOURCE_DECODE_ERROR",
                        item.old_path or item.path,
                        0,
                        f"base source is not valid UTF-8: {error}",
                    )
                )
                continue
            base_records, base_diagnostics = extract_source_text(
                base_raw,
                item.old_path or item.path,
                profile,
                Path(item.old_path or item.path).suffix.lower(),
            )
        if item.status == "D":
            file_transitions, transition_diagnostics = _build_transitions(
                item,
                base_records,
                (),
                diagnostic,
            )
            transitions.extend(file_transitions)
            diagnostics.extend(transition_diagnostics)
            diagnostics.extend(
                _deleted_base_diagnostics(
                    item,
                    file_transitions,
                    base_diagnostics,
                    project_diagnostic,
                )
            )
            continue
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
        if not item.whole_file and not item.hunks:
            if base_snapshot == snapshot or (
                base_snapshot is not None
                and _same_normalized_source(base_snapshot, snapshot)
            ):
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
        projected_starts, fallback_anchors = _base_change_projection(
            item,
            base_records,
            base_diagnostics,
        )
        selected_spans: list[tuple[int, int]] = []
        selected_records: list[dict[str, Any]] = []
        for rec in recs:
            s = rec["source"]
            start = s["metadata_start_line"] or s["declaration_start_line"]
            end = s["declaration_end_line"]
            if s["declaration_start_line"] in projected_starts or _affects_span(
                item,
                start,
                end,
                fallback_anchors,
            ):
                tests.append(rec)
                selected_records.append(rec)
                selected_spans.append((start, end))
        for d in diags:
            if d["code"] in {"SOURCE_SYNTAX_ERROR", "SOURCE_DECODE_ERROR"} or (
                item.whole_file
                or _affects_span(
                    item,
                    d.get("_selection_start_line", d["line"]),
                    d.get("_selection_end_line", d["line"]),
                    fallback_anchors,
                )
                or any(low <= d["line"] <= high for low, high in selected_spans)
            ):
                diagnostics.append(project_diagnostic(d))
        file_transitions, transition_diagnostics = _build_transitions(
            item,
            base_records,
            selected_records,
            diagnostic,
        )
        transitions.extend(file_transitions)
        diagnostics.extend(transition_diagnostics)
        diagnostics.extend(
            _deleted_base_diagnostics(
                item,
                file_transitions,
                base_diagnostics,
                project_diagnostic,
            )
        )
        diagnostics.extend(
            project_diagnostic(value)
            for value in base_diagnostics
            if value["code"] == "TEST_DECLARATION_UNSUPPORTED"
            and _base_diagnostic_was_fully_replaced(item, value)
        )
    tests.sort(key=_record_sort_key)
    transitions.sort(
        key=lambda transition: (
            _record_sort_key(transition["after"] or transition["before"]),
            transition["kind"],
        )
    )
    diagnostics.sort(key=lambda d: (d["path"], d["line"], d["code"]))
    return {
        "schema_version": 2,
        "adapter": profile.adapter,
        "coverage": profile.coverage,
        "repository_root": ".",
        "tests": tests,
        "transitions": transitions,
        "diagnostics": diagnostics,
        "warnings": [],
    }
