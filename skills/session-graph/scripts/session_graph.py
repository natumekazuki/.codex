#!/usr/bin/env python3
"""Save a selected shared Mermaid file without overwriting a concurrent edit.

Snapshots are temporary compare inputs, not a second source of truth. All writers
must use this helper; advisory locks cannot protect against editors bypassing it.
Only the Mermaid envelope is checked here, not its syntax or its meaning.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import errno
import json
import math
import ntpath
import os
from pathlib import Path
import re
import stat as stat_module
import sys
import tempfile
import time
from typing import Iterator

GRAPH_DIR = "session-graph"
LOCK_NAME = ".session-graph.lock"
SNAPSHOT_PREFIX = ".session-graph-snapshot-"
RESERVED_NAMES = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
                  *(f"LPT{i}" for i in range(1, 10)),
                  *(f"COM{i}" for i in "¹²³"), *(f"LPT{i}" for i in "¹²³")}


class ConflictError(Exception):
    """The shared graph changed since the supplied snapshot was read."""


def session_folder(value: str | Path) -> Path:
    path = Path(value)
    if not path.is_absolute():
        raise ValueError("SessionFolder must be an explicitly supplied absolute path.")
    path = path.resolve(strict=True)
    if not path.is_dir():
        raise ValueError("SessionFolder must be an existing directory.")
    return path


def redirected_path(path: Path) -> bool:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return False
    return path.is_symlink() or bool(getattr(info, "st_file_attributes", 0)
                                     & getattr(stat_module, "FILE_ATTRIBUTE_REPARSE_POINT", 0))


def regular_path(path: Path) -> None:
    # Do not follow symlinks or Windows junctions/reparse points, including dangling ones.
    if redirected_path(path) or (path.exists() and not path.is_file()):
        raise ValueError(f"Expected a regular file, not a link or directory: {path}")


def graph_path(folder: Path, name: str) -> Path:
    if (not isinstance(name, str) or not name.endswith(".mmd")
            or name in (".mmd", "..mmd") or name.endswith(" .mmd")
            or any(char in name for char in '<>:"/\\|?*')
            or any(ord(char) < 32 for char in name)
            or ntpath.basename(name) != name
            or name.split(".", 1)[0].rstrip(" .").upper() in RESERVED_NAMES):
        raise ValueError("--graph must be a safe direct-child .mmd filename.")
    directory = folder / GRAPH_DIR
    if redirected_path(directory) or (directory.exists() and not directory.is_dir()):
        raise ValueError("Session graph directory must not be a link or file.")
    directory.mkdir(exist_ok=True)
    if redirected_path(directory):
        raise ValueError("Session graph directory must not be a link.")
    path = directory / name
    regular_path(path)
    return path


@contextmanager
def graph_lock(folder: Path, timeout: float) -> Iterator[None]:
    if not math.isfinite(timeout) or not 0 <= timeout <= 30:
        raise ValueError("Lock timeout must be between 0 and 30 seconds.")
    lock_path = folder / LOCK_NAME
    regular_path(lock_path)
    # Keep this inode after releasing: unlinking a lock file can split the lock.
    with lock_path.open("a+b") as handle:
        deadline = time.monotonic() + timeout
        while True:
            try:
                if os.name == "nt":
                    import msvcrt
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError as exc:
                if exc.errno not in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
                    raise
                if time.monotonic() >= deadline:
                    raise TimeoutError("Session graph is busy; retry after rereading.") from exc
                time.sleep(min(0.05, max(0, deadline - time.monotonic())))
        try:
            yield
        finally:
            if os.name == "nt":
                import msvcrt
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def read_graph(path: Path) -> bytes | None:
    if redirected_path(path.parent):
        raise ValueError("Session graph directory must not be a link.")
    regular_path(path)
    try:
        return path.read_bytes()
    except FileNotFoundError:
        return None


def check_envelope(data: bytes) -> str:
    text = data.decode("utf-8")
    lines = [line.strip() for line in text.splitlines()
             if line.strip() and not line.lstrip().startswith("%%")]
    if not lines or not re.fullmatch(r"flowchart\s+(TB|TD|BT|RL|LR)\s*;?", lines[0]):
        raise ValueError("Expected an unwrapped UTF-8 Mermaid flowchart (no Markdown fence).")
    if len(lines) < 2 or "```" in text or "\x00" in text:
        raise ValueError("The graph must contain a definition, not an empty/fenced document.")
    return text


def snapshot(folder: Path, graph: str, timeout: float = 5) -> dict:
    folder = session_folder(folder)
    target = graph_path(folder, graph)
    with graph_lock(folder, timeout):
        data = read_graph(target)
    # A corrupt existing file is an error, never an empty/new graph.
    text = None if data is None else check_envelope(data)
    fd, name = tempfile.mkstemp(prefix=SNAPSHOT_PREFIX, suffix=".json", dir=folder)
    snapshot_file = Path(name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump({"graph_path": str(target), "content": text},
                      handle, ensure_ascii=False)
            handle.write("\n")
    except BaseException:
        snapshot_file.unlink(missing_ok=True)
        raise
    return {"snapshot_path": str(snapshot_file), "graph_path": str(target),
            "exists": data is not None, "content": text}


def scratch_path(folder: Path, value: str | Path) -> Path:
    path = Path(value)
    if not path.is_absolute():
        raise ValueError("Scratch file paths must be absolute.")
    regular_path(path)
    path = path.resolve(strict=True)
    if path.parent != folder or path.name == LOCK_NAME:
        raise ValueError("Use a distinct scratch file directly inside SessionFolder.")
    return path


def save(folder: Path, graph: str, snapshot_path: Path, input_path: Path,
         timeout: float = 5) -> dict:
    folder = session_folder(folder)
    path = graph_path(folder, graph)
    base = scratch_path(folder, snapshot_path)
    candidate = scratch_path(folder, input_path)
    if base == candidate or not (base.name.startswith(SNAPSHOT_PREFIX) and base.suffix == ".json"):
        raise ValueError("Supply the untouched snapshot and a separate Mermaid draft.")
    record = json.loads(base.read_text(encoding="utf-8"))
    if (not isinstance(record, dict) or set(record) != {"graph_path", "content"}
            or record["graph_path"] != str(path)
            or not (record["content"] is None or isinstance(record["content"], str))):
        raise ValueError("Snapshot does not belong to the selected session graph.")
    expected = None if record["content"] is None else record["content"].encode("utf-8")
    data = candidate.read_bytes()
    check_envelope(data)
    # Preparation is outside the lock. The critical section is only compare/save.
    with graph_lock(folder, timeout):
        current = read_graph(path)
        if current != expected:
            raise ConflictError("Graph changed. Take a new snapshot and reapply only your changes.")
        changed = current != data
        if changed:
            fd, name = tempfile.mkstemp(prefix=".session-graph-write-", suffix=".tmp",
                                        dir=path.parent)
            temp = Path(name)
            try:
                with os.fdopen(fd, "wb") as handle:
                    handle.write(data)
                    handle.flush()
                    os.fsync(handle.fileno())
                regular_path(path)
                if redirected_path(path.parent):
                    raise ValueError("Session graph directory must not be a link.")
                os.replace(temp, path)
            finally:
                temp.unlink(missing_ok=True)
    # Keep caller-owned inputs for explicit cleanup; cleanup failure must not
    # turn an already successful save into a reported save failure.
    return {"graph_path": str(path), "changed": changed}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("snapshot", "save"))
    parser.add_argument("--session-folder", required=True, type=Path)
    parser.add_argument("--graph", required=True)
    parser.add_argument("--snapshot", type=Path)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--lock-timeout", type=float, default=5)
    args = parser.parse_args(argv)
    if args.command == "save" and (args.snapshot is None or args.input is None):
        parser.error("save requires --snapshot and --input")
    if args.command == "snapshot" and (args.snapshot is not None or args.input is not None):
        parser.error("snapshot does not accept --snapshot or --input")
    try:
        result = (snapshot(args.session_folder, args.graph, args.lock_timeout)
                  if args.command == "snapshot" else
                  save(args.session_folder, args.graph, args.snapshot, args.input,
                       args.lock_timeout))
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except ConflictError as exc:
        print(str(exc), file=sys.stderr)
        return 3
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
