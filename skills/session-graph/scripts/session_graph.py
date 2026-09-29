#!/usr/bin/env python3
"""Save one shared Mermaid file without overwriting a concurrent session's edit.

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
import os
from pathlib import Path
import re
import sys
import tempfile
import time
from typing import Iterator

GRAPH_NAME = "session-graph.mmd"
LOCK_NAME = ".session-graph.lock"
SNAPSHOT_PREFIX = ".session-graph-snapshot-"


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


def regular_path(path: Path) -> None:
    # Replacing a symlink would silently change which file a session was using.
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise ValueError(f"Expected a regular file, not a link or directory: {path}")


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


def read_graph(folder: Path) -> bytes | None:
    path = folder / GRAPH_NAME
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


def snapshot(folder: Path, timeout: float = 5) -> dict:
    folder = session_folder(folder)
    with graph_lock(folder, timeout):
        data = read_graph(folder)
    # A corrupt existing file is an error, never an empty/new graph.
    text = None if data is None else check_envelope(data)
    fd, name = tempfile.mkstemp(prefix=SNAPSHOT_PREFIX, suffix=".json", dir=folder)
    path = Path(name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump({"graph_path": str(folder / GRAPH_NAME), "content": text},
                      handle, ensure_ascii=False)
            handle.write("\n")
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return {"snapshot_path": str(path), "graph_path": str(folder / GRAPH_NAME),
            "exists": data is not None, "content": text}


def scratch_path(folder: Path, value: str | Path) -> Path:
    path = Path(value)
    if not path.is_absolute():
        raise ValueError("Scratch file paths must be absolute.")
    regular_path(path)
    path = path.resolve(strict=True)
    if path.parent != folder or path.name in (GRAPH_NAME, LOCK_NAME):
        raise ValueError("Use a distinct scratch file directly inside SessionFolder.")
    return path


def save(folder: Path, snapshot_path: Path, input_path: Path, timeout: float = 5) -> dict:
    folder = session_folder(folder)
    base = scratch_path(folder, snapshot_path)
    candidate = scratch_path(folder, input_path)
    if base == candidate or not (base.name.startswith(SNAPSHOT_PREFIX) and base.suffix == ".json"):
        raise ValueError("Supply the untouched snapshot and a separate Mermaid draft.")
    record = json.loads(base.read_text(encoding="utf-8"))
    if (not isinstance(record, dict) or set(record) != {"graph_path", "content"}
            or record["graph_path"] != str(folder / GRAPH_NAME)
            or not (record["content"] is None or isinstance(record["content"], str))):
        raise ValueError("Snapshot does not belong to this SessionFolder.")
    expected = None if record["content"] is None else record["content"].encode("utf-8")
    data = candidate.read_bytes()
    check_envelope(data)
    # Preparation is outside the lock. The critical section is only compare/save.
    with graph_lock(folder, timeout):
        current = read_graph(folder)
        if current != expected:
            raise ConflictError("Graph changed. Take a new snapshot and reapply only your changes.")
        changed = current != data
        if changed:
            fd, name = tempfile.mkstemp(prefix=".session-graph-write-", suffix=".tmp", dir=folder)
            temp = Path(name)
            try:
                with os.fdopen(fd, "wb") as handle:
                    handle.write(data)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temp, folder / GRAPH_NAME)
            finally:
                temp.unlink(missing_ok=True)
    # Keep caller-owned inputs for explicit cleanup; cleanup failure must not
    # turn an already successful save into a reported save failure.
    return {"graph_path": str(folder / GRAPH_NAME), "changed": changed}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("snapshot", "save"))
    parser.add_argument("--session-folder", required=True, type=Path)
    parser.add_argument("--snapshot", type=Path)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--lock-timeout", type=float, default=5)
    args = parser.parse_args(argv)
    if args.command == "save" and (args.snapshot is None or args.input is None):
        parser.error("save requires --snapshot and --input")
    if args.command == "snapshot" and (args.snapshot is not None or args.input is not None):
        parser.error("snapshot does not accept --snapshot or --input")
    try:
        result = (snapshot(args.session_folder, args.lock_timeout) if args.command == "snapshot"
                  else save(args.session_folder, args.snapshot, args.input, args.lock_timeout))
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
