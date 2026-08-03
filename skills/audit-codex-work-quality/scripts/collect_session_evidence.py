#!/usr/bin/env python3
"""Collect one fixed time interval of Codex work evidence without mutating source data."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone, tzinfo
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


SCHEMA_VERSION = 3
UTC = timezone.utc
TAIL_PROBE_PER_FILE_BYTES = 64 * 1024
INDEX_PREVIEW_CHARS = 320
INDEX_GOAL_CUE_LIMIT = 4
INDEX_OUTCOME_CUE_LIMIT = 3
SQLITE_QUERY_TIMEOUT_SECONDS = 120
SQLITE_POST_KILL_WAIT_SECONDS = 5
SQLITE_WORKER_JOIN_TIMEOUT_SECONDS = 5
MAX_PROVIDER_OPERATION_TYPE_CHARS = 128
MAX_TOOL_IDENTIFIER_CHARS = 256
MAX_TOOL_EXIT_CODE_ABS = 2_147_483_648
MAX_TOOL_WALL_TIME_SECONDS = 1_000_000_000
MAX_ROLLOUT_EVENT_DURATION_MS = 9_223_372_036_854_775_807
TOOL_RESULT_STATUSES = {
    "cancelled",
    "completed",
    "error",
    "failed",
    "ok",
    "passed",
    "success",
    "succeeded",
    "timed_out",
    "timeout",
}
ROLLOUT_EVENT_STATUSES = TOOL_RESULT_STATUSES | {
    "in_progress",
    "running",
    "started",
}
REQUIRED_COLUMNS = {
    "sessions_v6": {
        "id",
        "title",
        "state",
        "thread_id",
        "workspace_path",
    },
    "session_messages_v6": {"session_id", "seq", "role", "body", "created_at"},
    "session_turns_v6": {
        "id",
        "session_id",
        "phase",
        "summary",
        "error_summary",
        "started_at",
        "completed_at",
        "updated_at",
    },
    "session_turn_interims_v6": {"turn_id", "seq", "body", "created_at"},
    "session_turn_provider_outputs_v6": {
        "turn_id",
        "seq",
        "kind",
        "summary",
        "payload_json",
        "created_at",
    },
}
OPTIONAL_COLUMNS = {
    "audit_events_v6": {"session_id", "event_type", "summary", "created_at"},
}
ALLOWED_PROVIDER_KINDS = {"operation", "provider_error", "background_task"}
EXCLUDED_JSONL_TYPES = {
    ("event_msg", "token_count"),
    ("event_msg", "rate_limits"),
    ("response_item", "reasoning"),
}


class CollectorError(RuntimeError):
    """A user-actionable collection failure."""


@dataclass(frozen=True)
class FixedWindow:
    timezone_name: str
    local_start: datetime
    local_end: datetime
    utc_start: datetime
    utc_end: datetime
    status: str


@dataclass
class CountBudget:
    name: str
    maximum: int
    used: int = 0

    @property
    def remaining(self) -> int:
        return self.maximum - self.used

    def consume(self, amount: int) -> None:
        if amount < 0 or amount > self.remaining:
            raise CollectorError(
                f"{self.name} exceeded: required {amount}, remaining {self.remaining}"
            )
        self.used += amount


def iso_z(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def resolve_timezone(timezone_name: str) -> tzinfo:
    try:
        return ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        if timezone_name == "Asia/Tokyo":
            return timezone(timedelta(hours=9), name="Asia/Tokyo")
        raise CollectorError(
            f"unknown IANA timezone or timezone data unavailable: {timezone_name}"
        ) from exc


def localize_unambiguous(value: datetime, tz: tzinfo) -> datetime:
    first = value.replace(tzinfo=tz, fold=0)
    round_trip = first.astimezone(UTC).astimezone(tz).replace(tzinfo=None)
    if round_trip != value:
        raise ValueError("nonexistent local datetime in the timezone")
    second = value.replace(tzinfo=tz, fold=1)
    if first.utcoffset() != second.utcoffset():
        raise ValueError("ambiguous local datetime in the timezone")
    return first


def parse_local_boundary(value: str, option: str, tz: tzinfo) -> datetime:
    pattern = (
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}"
        r"(?::\d{2}(?:\.\d{1,6})?)?"
    )
    if re.fullmatch(pattern, value) is None:
        raise CollectorError(
            f"{option} must be a local ISO datetime without an offset, "
            "for example 2026-08-01T20:00"
        )
    try:
        naive = datetime.fromisoformat(value)
    except ValueError as exc:
        raise CollectorError(f"{option} is not a valid local datetime") from exc
    try:
        return localize_unambiguous(naive, tz)
    except ValueError as exc:
        raise CollectorError(f"{option} is {exc}") from exc


def build_window(
    start_text: str,
    end_text: str,
    timezone_name: str,
    *,
    now: datetime | None = None,
) -> FixedWindow:
    tz = resolve_timezone(timezone_name)
    local_start = parse_local_boundary(start_text, "--start", tz)
    local_end = parse_local_boundary(end_text, "--end", tz)
    utc_start = local_start.astimezone(UTC)
    utc_end = local_end.astimezone(UTC)
    if utc_end <= utc_start:
        raise CollectorError("--end must be later than --start")

    current_value = now or datetime.now(tz)
    if current_value.tzinfo is None:
        raise CollectorError("current time must be timezone-aware")
    current = current_value.astimezone(UTC)
    if utc_start > current:
        raise CollectorError("--start must not be in the future")

    return FixedWindow(
        timezone_name=timezone_name,
        local_start=local_start,
        local_end=local_end,
        utc_start=utc_start,
        utc_end=utc_end,
        status="partial" if utc_end > current else "complete",
    )


def require_sqlite() -> tuple[str, str]:
    executable = shutil.which("sqlite3")
    if executable is None:
        raise CollectorError(
            "sqlite3 CLI is required; install SQLite and ensure sqlite3 is on PATH"
        )
    result = subprocess.run(
        [executable, "--version"],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=15,
    )
    if result.returncode != 0:
        raise CollectorError(f"sqlite3 --version failed: {result.stderr.strip()}")
    return executable, result.stdout.strip()


def run_sqlite_json(
    executable: str,
    database: Path,
    query: str,
    byte_budget: CountBudget,
) -> list[dict[str, Any]]:
    command = [
        executable,
        "-readonly",
        "-json",
        str(database),
    ]
    process = subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert process.stdin is not None
    assert process.stdout is not None and process.stderr is not None
    query_bytes = f"PRAGMA query_only=ON; {query}".encode("utf-8")
    stdout_chunks: list[bytes] = []
    stderr_chunks: list[bytes] = []
    stdout_exceeded = threading.Event()
    shutdown_started = threading.Event()
    worker_error_lock = threading.Lock()
    worker_errors: list[tuple[str, BaseException]] = []
    kill_error_lock = threading.Lock()
    kill_errors: list[OSError] = []

    def kill_process() -> None:
        try:
            process.kill()
        except OSError as exc:
            with kill_error_lock:
                kill_errors.append(exc)

    def record_worker_error(channel: str, exc: BaseException) -> None:
        if shutdown_started.is_set():
            return
        with worker_error_lock:
            if not worker_errors:
                worker_errors.append((channel, exc))
        shutdown_started.set()
        kill_process()

    def write_stdin() -> None:
        try:
            process.stdin.write(query_bytes)
            process.stdin.flush()
        except (BrokenPipeError, OSError, ValueError) as exc:
            record_worker_error("stdin", exc)
        finally:
            try:
                process.stdin.close()
            except (OSError, ValueError) as exc:
                record_worker_error("stdin", exc)

    def read_stdout() -> None:
        try:
            remaining = byte_budget.remaining
            while True:
                chunk = process.stdout.read(min(64 * 1024, remaining + 1))
                if not chunk:
                    return
                if len(chunk) > remaining:
                    stdout_chunks.append(chunk[:remaining])
                    stdout_exceeded.set()
                    shutdown_started.set()
                    kill_process()
                    return
                stdout_chunks.append(chunk)
                remaining -= len(chunk)
        except (OSError, ValueError) as exc:
            record_worker_error("stdout", exc)

    def read_stderr() -> None:
        try:
            stored = 0
            while True:
                chunk = process.stderr.read(64 * 1024)
                if not chunk:
                    return
                if stored < 64 * 1024:
                    kept = chunk[: 64 * 1024 - stored]
                    stderr_chunks.append(kept)
                    stored += len(kept)
        except (OSError, ValueError) as exc:
            record_worker_error("stderr", exc)

    stdin_thread = threading.Thread(target=write_stdin, daemon=True)
    stdout_thread = threading.Thread(target=read_stdout, daemon=True)
    stderr_thread = threading.Thread(target=read_stderr, daemon=True)
    stdin_thread.start()
    stdout_thread.start()
    stderr_thread.start()
    timeout_error: subprocess.TimeoutExpired | None = None
    termination_timeout: subprocess.TimeoutExpired | None = None
    return_code: int | None = None
    try:
        return_code = process.wait(timeout=SQLITE_QUERY_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired as exc:
        timeout_error = exc
        shutdown_started.set()
        kill_process()
        try:
            return_code = process.wait(timeout=SQLITE_POST_KILL_WAIT_SECONDS)
        except subprocess.TimeoutExpired as post_kill_exc:
            termination_timeout = post_kill_exc

    workers = (stdin_thread, stdout_thread, stderr_thread)
    for worker in workers:
        worker.join(timeout=SQLITE_WORKER_JOIN_TIMEOUT_SECONDS)
    if any(worker.is_alive() for worker in workers):
        shutdown_started.set()
        for stream in (process.stdin, process.stdout, process.stderr):
            try:
                stream.close()
            except (OSError, ValueError):
                pass
        for worker in workers:
            worker.join(timeout=SQLITE_WORKER_JOIN_TIMEOUT_SECONDS)
    workers_alive = any(worker.is_alive() for worker in workers)
    for stream in (process.stdin, process.stdout, process.stderr):
        try:
            stream.close()
        except (OSError, ValueError):
            pass

    kill_failure = f"; process kill failed: {kill_errors[0]}" if kill_errors else ""
    if termination_timeout is not None:
        raise CollectorError(
            "SQLite process did not terminate after query timeout"
            f"{kill_failure}"
        ) from termination_timeout
    if timeout_error is not None:
        raise CollectorError(
            f"read-only SQLite query timed out{kill_failure}"
        ) from timeout_error
    if workers_alive:
        raise CollectorError(f"SQLite I/O worker did not terminate{kill_failure}")
    if worker_errors:
        channel, exc = worker_errors[0]
        raise CollectorError(
            f"SQLite {channel} I/O failed: {exc}{kill_failure}"
        ) from exc

    if stdout_exceeded.is_set():
        raise CollectorError(f"SQLite output exceeded {byte_budget.name}")
    stdout = b"".join(stdout_chunks)
    stderr = b"".join(stderr_chunks).decode("utf-8", errors="replace")
    byte_budget.consume(len(stdout))
    if return_code != 0:
        detail = stderr.strip() or stdout.decode("utf-8", errors="replace").strip()
        raise CollectorError(f"read-only SQLite query failed: {detail}")
    try:
        payload = stdout.decode("utf-8").strip()
    except UnicodeDecodeError as exc:
        raise CollectorError("sqlite3 returned non-UTF-8 output") from exc
    if not payload:
        return []
    try:
        decoded = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise CollectorError("sqlite3 returned invalid JSON") from exc
    if not isinstance(decoded, list):
        raise CollectorError("sqlite3 JSON result was not an array")
    return decoded


def validate_database(
    executable: str,
    database: Path,
    byte_budget: CountBudget,
) -> frozenset[str]:
    if not database.is_file():
        raise CollectorError(f"WithMate database not found: {database}")

    pragma = run_sqlite_json(
        executable,
        database,
        "SELECT query_only FROM pragma_query_only;",
        byte_budget,
    )
    if pragma != [{"query_only": 1}]:
        raise CollectorError("SQLite query_only preflight did not return 1")

    declared_columns = REQUIRED_COLUMNS | OPTIONAL_COLUMNS
    table_list = ",".join(sql_literal(name) for name in sorted(declared_columns))
    rows = run_sqlite_json(
        executable,
        database,
        "SELECT m.name AS table_name, p.name AS column_name "
        "FROM sqlite_master AS m JOIN pragma_table_info(m.name) AS p "
        f"WHERE m.type='table' AND m.name IN ({table_list});",
        byte_budget,
    )
    found: dict[str, set[str]] = {}
    for row in rows:
        found.setdefault(str(row["table_name"]), set()).add(str(row["column_name"]))
    missing = {
        table: sorted(columns - found.get(table, set()))
        for table, columns in REQUIRED_COLUMNS.items()
        if columns - found.get(table, set())
    }
    missing.update(
        {
            table: sorted(columns - found[table])
            for table, columns in OPTIONAL_COLUMNS.items()
            if table in found and columns - found[table]
        }
    )
    if missing:
        raise CollectorError(f"unsupported WithMate schema; missing columns: {missing}")
    return frozenset(table for table in OPTIONAL_COLUMNS if table in found)


def sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def timestamp_sql_text(column: str) -> str:
    return f"trim(CAST({column} AS TEXT))"


def timestamp_offset_aware(column: str) -> str:
    text = timestamp_sql_text(column)
    return (
        f"(substr({text},-1)='Z' OR instr(substr({text},11),'+')>0 "
        f"OR instr(substr({text},11),'-')>0)"
    )


def timestamp_naive_predicate(column: str) -> str:
    text = timestamp_sql_text(column)
    return f"(instr({text},'/')>0 OR NOT {timestamp_offset_aware(column)})"


def timestamp_predicate(column: str, window: FixedWindow) -> str:
    text = timestamp_sql_text(column)
    local_text = (
        f"(CASE WHEN instr({text},'/')>0 "
        f"THEN replace(substr({text},1,10),'/','-') || 'T' || substr({text},12) "
        f"ELSE replace({text},' ','T') END)"
    )
    local_start = (window.local_start - timedelta(seconds=1)).replace(
        tzinfo=None
    ).isoformat(timespec="microseconds")
    local_end = (window.local_end + timedelta(seconds=1)).replace(
        tzinfo=None
    ).isoformat(timespec="microseconds")
    utc_start = iso_z(window.utc_start - timedelta(seconds=1))
    utc_end = iso_z(window.utc_end + timedelta(seconds=1))
    offset_aware = timestamp_offset_aware(column)
    return (
        f"((instr({text},'/')>0 AND julianday({local_text}) >= julianday({sql_literal(local_start)}) "
        f"AND julianday({local_text}) < julianday({sql_literal(local_end)})) OR "
        f"(instr({text},'/')=0 AND {offset_aware} "
        f"AND julianday({text}) >= julianday({sql_literal(utc_start)}) "
        f"AND julianday({text}) < julianday({sql_literal(utc_end)})) OR "
        f"(instr({text},'/')=0 AND NOT {offset_aware} "
        f"AND julianday({local_text}) >= julianday({sql_literal(local_start)}) "
        f"AND julianday({local_text}) < julianday({sql_literal(local_end)})))"
    )


def timestamp_domain_predicate(column: str) -> str:
    text = timestamp_sql_text(column)
    normalized = (
        f"(CASE WHEN instr({text},'/')>0 "
        f"THEN replace(substr({text},1,10),'/','-') || substr({text},11) "
        f"ELSE {text} END)"
    )
    local_clock = (
        f"(CASE WHEN substr({normalized},17,1)=':' "
        f"THEN substr({normalized},12,8) "
        f"ELSE substr({normalized},12,5) || ':00' END)"
    )
    date_shape = (
        f"(substr({normalized},1,4) GLOB '[0-9][0-9][0-9][0-9]' "
        f"AND CAST(substr({normalized},1,4) AS INTEGER) BETWEEN 1 AND 9999 "
        f"AND substr({normalized},5,1)='-' "
        f"AND substr({normalized},6,2) GLOB '[0-9][0-9]' "
        f"AND substr({normalized},8,1)='-' "
        f"AND substr({normalized},9,2) GLOB '[0-9][0-9]')"
    )
    slash_shape = (
        f"(instr({text},'/')=0 OR "
        f"(substr({text},5,1)='/' AND substr({text},8,1)='/' "
        f"AND substr({text},11,1)=' ' AND "
        f"(length({text}) IN (16,19) OR "
        f"(substr({text},20,1)='.' AND length({text}) BETWEEN 21 AND 26 "
        f"AND NOT substr({text},21) GLOB '*[^0-9]*'))))"
    )
    clock_shape = (
        f"(substr({normalized},12,2) GLOB '[0-9][0-9]' "
        f"AND CAST(substr({normalized},12,2) AS INTEGER) BETWEEN 0 AND 23 "
        f"AND substr({normalized},14,1)=':' "
        f"AND substr({normalized},15,2) GLOB '[0-9][0-9]' "
        f"AND CAST(substr({normalized},15,2) AS INTEGER) BETWEEN 0 AND 59 "
        f"AND (substr({normalized},17,1)!=':' OR "
        f"(substr({normalized},18,2) GLOB '[0-9][0-9]' "
        f"AND CAST(substr({normalized},18,2) AS INTEGER) BETWEEN 0 AND 59)))"
    )
    fraction_tail = f"substr({normalized},21)"
    fraction_length = (
        f"(CASE WHEN instr({fraction_tail},'Z')>0 THEN instr({fraction_tail},'Z')-1 "
        f"WHEN instr({fraction_tail},'+')>0 THEN instr({fraction_tail},'+')-1 "
        f"WHEN instr({fraction_tail},'-')>0 THEN instr({fraction_tail},'-')-1 "
        f"ELSE length({fraction_tail}) END)"
    )
    fraction = f"substr({fraction_tail},1,{fraction_length})"
    fraction_shape = (
        f"(substr({normalized},20,1)!='.' OR "
        f"({fraction_length} BETWEEN 1 AND 6 "
        f"AND NOT {fraction} GLOB '*[^0-9]*'))"
    )
    minute_suffix_shape = (
        f"(substr({normalized},17,1)=':' OR "
        f"substr({normalized},17,1) IN ('','Z','+','-'))"
    )
    iso_suffix = (
        f"(CASE WHEN substr({normalized},17,1)!=':' THEN substr({normalized},17) "
        f"WHEN substr({normalized},20,1)='.' "
        f"THEN substr({fraction_tail},{fraction_length}+1) "
        f"ELSE substr({normalized},20) END)"
    )
    iso_suffix_shape = (
        f"(instr({text},'/')>0 OR {iso_suffix} IN ('','Z') OR "
        f"(length({iso_suffix})=6 AND substr({iso_suffix},1,1) IN ('+','-') "
        f"AND substr({iso_suffix},2,2) GLOB '[0-9][0-9]' "
        f"AND CAST(substr({iso_suffix},2,2) AS INTEGER) BETWEEN 0 AND 14 "
        f"AND substr({iso_suffix},4,1)=':' "
        f"AND substr({iso_suffix},5,2) GLOB '[0-9][0-9]' "
        f"AND CAST(substr({iso_suffix},5,2) AS INTEGER) BETWEEN 0 AND 59 "
        f"AND (CAST(substr({iso_suffix},2,2) AS INTEGER)<14 "
        f"OR CAST(substr({iso_suffix},5,2) AS INTEGER)=0)))"
    )
    return (
        f"(typeof({column})='text' AND length({text})>0 "
        f"AND {date_shape} AND {slash_shape} AND {clock_shape} "
        f"AND {fraction_shape} AND {minute_suffix_shape} AND {iso_suffix_shape} "
        f"AND substr({normalized},11,1) IN ('T',' ') "
        f"AND date(substr({normalized},1,10))=substr({normalized},1,10) "
        f"AND time({local_clock})={local_clock} "
        f"AND julianday({normalized}) IS NOT NULL)"
    )


def collect_timestamp_domain_gaps(
    executable: str,
    database: Path,
    timezone_value: tzinfo,
    row_budget: CountBudget,
    byte_budget: CountBudget,
    gaps: list[str],
    workspace_filter: str | None,
    available_optional_tables: frozenset[str] = frozenset(OPTIONAL_COLUMNS),
) -> int:
    timestamp_columns = [
        (
            "session_messages_v6.created_at",
            "m.created_at",
            False,
            "session_messages_v6 AS m JOIN sessions_v6 AS s ON s.id=m.session_id",
        ),
        (
            "session_turns_v6.started_at",
            "t.started_at",
            False,
            "session_turns_v6 AS t JOIN sessions_v6 AS s ON s.id=t.session_id",
        ),
        (
            "session_turns_v6.completed_at",
            "t.completed_at",
            True,
            "session_turns_v6 AS t JOIN sessions_v6 AS s ON s.id=t.session_id",
        ),
        (
            "session_turns_v6.updated_at",
            "t.updated_at",
            False,
            "session_turns_v6 AS t JOIN sessions_v6 AS s ON s.id=t.session_id",
        ),
        (
            "session_turn_interims_v6.created_at",
            "i.created_at",
            False,
            "session_turn_interims_v6 AS i "
            "JOIN session_turns_v6 AS t ON t.id=i.turn_id "
            "JOIN sessions_v6 AS s ON s.id=t.session_id",
        ),
        (
            "session_turn_provider_outputs_v6.created_at",
            "p.created_at",
            False,
            "session_turn_provider_outputs_v6 AS p "
            "JOIN session_turns_v6 AS t ON t.id=p.turn_id "
            "JOIN sessions_v6 AS s ON s.id=t.session_id",
        ),
    ]
    if "audit_events_v6" in available_optional_tables:
        timestamp_columns.append(
            (
                "audit_events_v6.created_at",
                "a.created_at",
                False,
                "audit_events_v6 AS a JOIN sessions_v6 AS s ON s.id=a.session_id",
            )
        )
    selects: list[str] = []
    for field, column, nullable, from_clause in timestamp_columns:
        null_guard = f"{column} IS NOT NULL AND " if nullable else ""
        selects.append(
            f"SELECT {sql_literal(field)} AS field, s.workspace_path, "
            f"count(*) AS invalid_count FROM {from_clause} "
            f"WHERE {null_guard}NOT {timestamp_domain_predicate(column)} "
            "GROUP BY s.workspace_path"
        )
    rows = run_sqlite_json(
        executable,
        database,
        " UNION ALL ".join(selects) + ";",
        byte_budget,
    )
    invalid_total = 0
    for row in rows:
        if not row_matches_workspace(row, workspace_filter):
            continue
        count = int(row.get("invalid_count") or 0)
        if count <= 0:
            continue
        invalid_total += count
        gaps.append(
            "WithMate timestamp domain invalid before fixed-interval filtering: "
            f"{row.get('field')} count={count}; window membership is unknown"
        )

    naive_selects: list[str] = []
    for field, column, nullable, from_clause in timestamp_columns:
        null_guard = f"{column} IS NOT NULL AND " if nullable else ""
        naive_selects.append(
            f"SELECT {sql_literal(field)} AS field, s.workspace_path, "
            f"{timestamp_sql_text(column)} AS timestamp_value, "
            f"count(*) AS occurrence_count FROM {from_clause} "
            f"WHERE {null_guard}{timestamp_domain_predicate(column)} "
            f"AND {timestamp_naive_predicate(column)} "
            f"GROUP BY s.workspace_path, {timestamp_sql_text(column)}"
        )
    naive_rows = run_budgeted_sqlite_json(
        executable,
        database,
        " UNION ALL ".join(naive_selects) + ";",
        row_budget,
        byte_budget,
        "naive timestamp domain preflight",
    )
    timezone_failures: dict[tuple[str, str], int] = {}
    for row in naive_rows:
        if not row_matches_workspace(row, workspace_filter):
            continue
        value = str(row.get("timestamp_value") or "")
        try:
            parse_timestamp(value, slash_timezone=timezone_value)
        except ValueError as exc:
            detail = str(exc)
            if "ambiguous local datetime" in detail:
                reason = "ambiguous local datetime"
            elif "nonexistent local datetime" in detail:
                reason = "nonexistent local datetime"
            else:
                reason = "timezone semantic validation failed"
            key = (str(row.get("field") or "unknown"), reason)
            timezone_failures[key] = timezone_failures.get(key, 0) + int(
                row.get("occurrence_count") or 0
            )
    for (field, reason), count in sorted(timezone_failures.items()):
        if count <= 0:
            continue
        invalid_total += count
        gaps.append(
            "WithMate naive timestamp timezone invalid before fixed-interval "
            f"filtering: {field} reason={reason} count={count}; "
            "window membership is unknown"
        )
    return invalid_total


def timestamp_comparison(
    column: str,
    operator: str,
    *,
    local_boundary: datetime,
    utc_boundary: datetime,
) -> str:
    if operator not in {"<", ">"}:
        raise ValueError(f"unsupported timestamp comparison operator: {operator}")
    padding = timedelta(seconds=1) if operator == "<" else -timedelta(seconds=1)
    local_boundary = local_boundary + padding
    utc_boundary = utc_boundary + padding
    local_iso = local_boundary.replace(tzinfo=None).isoformat(timespec="microseconds")
    utc_iso = iso_z(utc_boundary)
    text = timestamp_sql_text(column)
    local_text = (
        f"(CASE WHEN instr({text},'/')>0 "
        f"THEN replace(substr({text},1,10),'/','-') || 'T' || substr({text},12) "
        f"ELSE replace({text},' ','T') END)"
    )
    offset_aware = timestamp_offset_aware(column)
    return (
        f"((instr({text},'/')>0 AND julianday({local_text}) {operator} julianday({sql_literal(local_iso)})) OR "
        f"(instr({text},'/')=0 AND {offset_aware} "
        f"AND julianday({text}) {operator} julianday({sql_literal(utc_iso)})) OR "
        f"(instr({text},'/')=0 AND NOT {offset_aware} "
        f"AND julianday({local_text}) {operator} julianday({sql_literal(local_iso)})))"
    )


def parse_timestamp(value: str, *, slash_timezone: tzinfo) -> datetime:
    text = value.strip()
    slash_pattern = (
        r"\d{4}/\d{2}/\d{2} \d{2}:\d{2}"
        r"(?::\d{2}(?:\.\d{1,6})?)?"
    )
    iso_pattern = (
        r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}"
        r"(?::\d{2}(?:\.\d{1,6})?)?"
        r"(?:Z|[+-]\d{2}:\d{2})?"
    )
    expected_pattern = slash_pattern if "/" in text else iso_pattern
    if re.fullmatch(expected_pattern, text) is None:
        raise ValueError(f"unsupported timestamp: {value}")
    offset = re.search(r"[+-](\d{2}):(\d{2})$", text)
    if offset:
        offset_hour = int(offset.group(1))
        offset_minute = int(offset.group(2))
        if offset_minute > 59 or offset_hour > 14 or (
            offset_hour == 14 and offset_minute != 0
        ):
            raise ValueError(f"timestamp offset exceeds supported domain: {value}")
    fraction = re.search(r":\d{2}\.(\d+)(?:Z|[+-]\d{2}:\d{2})?$", text)
    if fraction and len(fraction.group(1)) > 6:
        raise ValueError(f"timestamp precision exceeds microseconds: {value}")
    if "/" in text and "T" not in text:
        for fmt in ("%Y/%m/%d %H:%M:%S.%f", "%Y/%m/%d %H:%M:%S", "%Y/%m/%d %H:%M"):
            try:
                parsed_local = datetime.strptime(text, fmt)
            except ValueError:
                continue
            return localize_unambiguous(parsed_local, slash_timezone).astimezone(UTC)
        raise ValueError(f"unsupported slash timestamp: {value}")
    normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = localize_unambiguous(parsed, slash_timezone)
    return parsed.astimezone(UTC)


def in_window(value: datetime, window: FixedWindow) -> bool:
    return window.utc_start <= value < window.utc_end


def unwrap_withmate_message(text: str, expected_role: str) -> str:
    stripped = text.strip()
    if not stripped.startswith("{"):
        return text
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        return text
    if not isinstance(payload, dict) or payload.get("role") != expected_role:
        return text
    allowed_keys = {"role", "text"} if expected_role == "user" else {
        "role",
        "text",
        "artifact",
    }
    if set(payload) <= allowed_keys and isinstance(payload.get("text"), str):
        return str(payload["text"])
    return text


def normalize_user_text(text: str) -> str:
    envelope = text.lstrip("\ufeff \t\r\n")
    first_line, _, _ = envelope.partition("\n")
    marker_match = re.search(r"(?m)^# User Input[ \t]*$", envelope)
    if first_line.rstrip("\r") == "# Character Definition Snapshot" and marker_match:
        header = envelope[: marker_match.start()]
        if re.search(r"(?m)^Character:[ \t]*\S", header) and re.search(
            r"(?m)^Description:[ \t]*\S", header
        ):
            body = envelope[marker_match.end() :]
            if body.startswith("\r\n"):
                return body[2:]
            if body.startswith(("\n", "\r")):
                return body[1:]
            return body
    return text


def bounded_text(value: Any, limit: int) -> dict[str, Any]:
    if value is None:
        text = ""
    elif isinstance(value, str):
        text = value
    else:
        text = json.dumps(value, ensure_ascii=False, sort_keys=True)
    original_chars = len(text)
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    if original_chars > limit:
        text = text[:limit]
    return {
        "text": text,
        "original_chars": original_chars,
        "truncated": original_chars > limit,
        "sha256": digest,
    }


def bounded_raw_evidence(
    value: Any,
    limit: int,
    *,
    gaps: list[str] | None = None,
    label: str = "raw evidence",
) -> dict[str, Any] | None:
    if isinstance(value, str):
        return bounded_text(value, limit)
    try:
        text = json.dumps(value, ensure_ascii=False, sort_keys=True)
    except (TypeError, ValueError) as exc:
        if gaps is not None:
            gaps.append(f"{label} unavailable: {type(exc).__name__}")
        return None
    evidence = bounded_text(text, limit)
    evidence["source_type"] = type(value).__name__
    evidence["encoding"] = "json"
    return evidence


def content_fingerprint(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        text = value
    else:
        text = json.dumps(value, ensure_ascii=False, sort_keys=True)
    return {
        "original_chars": len(text),
        "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
    }


def safe_tool_identifier(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    if len(value) > MAX_TOOL_IDENTIFIER_CHARS:
        return None
    if re.fullmatch(r"[A-Za-z0-9_.:-]+", value) is None:
        return None
    return value


def canonical_session_id(thread_id: Any, fallback: Any) -> str:
    thread = str(thread_id or "").strip()
    return thread or str(fallback)


def ensure_session(
    sessions: dict[str, dict[str, Any]],
    canonical_id: str,
    *,
    title: str = "",
    workspace: str = "",
    state: str = "",
) -> dict[str, Any]:
    session = sessions.setdefault(
        canonical_id,
        {
            "session_id": canonical_id,
            "title": title,
            "workspace": workspace,
            "workspaces": [workspace] if workspace else [],
            "state": state,
            "withmate_session_ids": [],
            "native_rollouts": [],
            "sources": [],
            "events": [],
        },
    )
    if title and not session["title"]:
        session["title"] = title
    if workspace and not session["workspace"]:
        session["workspace"] = workspace
    if workspace and workspace not in session["workspaces"]:
        session["workspaces"].append(workspace)
    if state and not session["state"]:
        session["state"] = state
    return session


def add_source(session: dict[str, Any], source: str) -> None:
    if source not in session["sources"]:
        session["sources"].append(source)


def add_event(
    session: dict[str, Any],
    *,
    occurred_at: datetime,
    kind: str,
    source: str,
    text: dict[str, Any] | None = None,
    role: str | None = None,
    metadata: dict[str, Any] | None = None,
    budget: CountBudget | None = None,
) -> None:
    if budget is not None:
        budget.consume(1)
    event: dict[str, Any] = {
        "occurred_at_utc": iso_z(occurred_at),
        "kind": kind,
        "source": source,
    }
    if role:
        event["role"] = role
    if text:
        event["content"] = text
    if metadata:
        event["metadata"] = metadata
    session["events"].append(event)


def run_budgeted_sqlite_json(
    executable: str,
    database: Path,
    query: str,
    budget: CountBudget,
    byte_budget: CountBudget,
    label: str,
) -> list[dict[str, Any]]:
    limited_query = query.rstrip().rstrip(";") + f" LIMIT {budget.remaining + 1};"
    rows = run_sqlite_json(executable, database, limited_query, byte_budget)
    if len(rows) > budget.remaining:
        raise CollectorError(f"{label} exceeded {budget.name}")
    budget.consume(len(rows))
    return rows


def session_from_row(
    sessions: dict[str, dict[str, Any]], row: dict[str, Any]
) -> dict[str, Any]:
    canonical_id = canonical_session_id(row.get("thread_id"), row.get("withmate_session_id"))
    session = ensure_session(
        sessions,
        canonical_id,
        title=str(row.get("title") or ""),
        workspace=str(row.get("workspace_path") or ""),
        state=str(row.get("state") or ""),
    )
    withmate_id = str(row.get("withmate_session_id") or "")
    if withmate_id and withmate_id not in session["withmate_session_ids"]:
        session["withmate_session_ids"].append(withmate_id)
    add_source(session, "withmate-v6")
    return session


def row_matches_workspace(
    row: dict[str, Any], workspace_filter: str | None
) -> bool:
    if not workspace_filter:
        return True
    return normalize_path(str(row.get("workspace_path") or "")) == normalize_path(
        workspace_filter
    )


def provider_event_projection(
    row: dict[str, Any],
    *,
    detail: bool,
    text_limit: int,
    gaps: list[str],
) -> tuple[str, dict[str, Any] | None, dict[str, Any]]:
    provider_kind = str(row.get("kind") or "")
    payload_value: Any = None
    payload_value_present = False
    raw_payload = row.get("payload_json")
    if isinstance(raw_payload, str) and raw_payload:
        try:
            decoded_payload = json.loads(raw_payload)
        except json.JSONDecodeError:
            gaps.append("withmate provider payload JSON unavailable: invalid JSON")
        else:
            if isinstance(decoded_payload, dict):
                if "value" in decoded_payload:
                    payload_value = decoded_payload.get("value")
                    payload_value_present = True
            else:
                gaps.append(
                    "withmate provider payload unavailable: expected object envelope"
                )
    elif not detail and row.get("indexed_payload_valid") == 0:
        gaps.append("withmate provider payload JSON unavailable: invalid JSON")
    value_object = payload_value if isinstance(payload_value, dict) else {}
    if not detail:
        value_object = {
            "type": row.get("indexed_operation_type"),
            "call_id": row.get("indexed_call_id"),
            "tool": row.get("indexed_tool"),
            "exit_code": row.get("indexed_exit_code"),
            "status": row.get("indexed_status"),
            "wall_time_seconds": row.get("indexed_wall_time_seconds"),
        }
        if row.get("indexed_is_error_type") in {"true", "false"}:
            value_object["isError"] = bool(row.get("indexed_is_error"))
        payload_value = value_object
        payload_value_present = True
    operation_type = safe_provider_operation_type(value_object.get("type"))
    is_provider_error = provider_kind == "provider_error"

    error_value: Any = None
    error_value_present = False
    if is_provider_error or operation_type == "error":
        if isinstance(payload_value, dict):
            if value_object.get("message") not in (None, ""):
                error_value = value_object.get("message")
                error_value_present = True
            elif value_object.get("error") not in (None, ""):
                error_value = value_object.get("error")
                error_value_present = True
        elif payload_value_present:
            error_value = payload_value
            error_value_present = True
    summary_value: Any = None
    summary_value_present = False
    if (
        isinstance(payload_value, dict)
        and "summary" in value_object
        and value_object.get("summary") not in (None, "")
    ):
        summary_value = value_object.get("summary")
        summary_value_present = True
    elif (
        detail
        and payload_value_present
        and not isinstance(payload_value, (dict, str))
    ):
        summary_value = payload_value
        summary_value_present = True
    elif row.get("summary") not in (None, ""):
        summary_value = row.get("summary")
        summary_value_present = True
    if error_value_present:
        source_value = error_value
        source_value_present = True
    else:
        source_value = summary_value
        source_value_present = summary_value_present

    metadata: dict[str, Any] = {
        "provider_kind": provider_kind,
        "operation_type": operation_type or None,
        "sequence": row.get("seq"),
    }
    call_id = safe_tool_identifier(value_object.get("call_id"))
    tool = safe_tool_identifier(value_object.get("tool") or value_object.get("name"))
    if call_id is not None:
        metadata["call_id"] = call_id
    if tool is not None:
        metadata["tool"] = tool

    if is_provider_error or operation_type == "error":
        metadata["failure_status"] = "known-failure"
        if source_value_present:
            metadata["error_evidence"] = (
                bounded_raw_evidence(
                    source_value,
                    text_limit,
                    gaps=gaps,
                    label="withmate provider error evidence",
                )
                if detail
                else content_fingerprint(source_value)
            )
    elif operation_type == "command_execution":
        signal_metadata = tool_output_metadata(
            {"call_id": call_id, "output": payload_value},
            raw_evidence_limit=text_limit if detail else None,
        )
        for key in (
            "exit_code",
            "isError",
            "status",
            "wall_time_seconds",
            "failure_status",
        ):
            if key in signal_metadata:
                metadata[key] = signal_metadata[key]

    content = None
    if (
        detail
        and source_value_present
        and not (is_provider_error or operation_type == "error")
    ):
        content = bounded_raw_evidence(
            source_value,
            text_limit,
            gaps=gaps,
            label="withmate provider summary evidence",
        )
    if is_provider_error:
        kind = "provider_error"
    elif operation_type in {"command_execution", "error"}:
        kind = operation_type
    elif provider_kind == "operation" and operation_type:
        kind = "provider_operation"
    else:
        kind = provider_kind or "operation"
    return kind, content, metadata


def collect_database(
    executable: str,
    database: Path,
    window: FixedWindow,
    sessions: dict[str, dict[str, Any]],
    *,
    workspace_filter: str | None,
    text_limit: int,
    gaps: list[str],
    row_budget: CountBudget,
    byte_budget: CountBudget,
    event_budget: CountBudget,
    available_optional_tables: frozenset[str],
    detail: bool = False,
) -> dict[str, int]:
    tz = resolve_timezone(window.timezone_name)
    counts: dict[str, int] = {
        "invalid_timestamps": collect_timestamp_domain_gaps(
            executable,
            database,
            tz,
            row_budget,
            byte_budget,
            gaps,
            workspace_filter,
            available_optional_tables,
        )
    }
    counts["audit_events"] = 0
    if "audit_events_v6" not in available_optional_tables:
        gaps.append("optional WithMate source unavailable: audit_events_v6")
    session_projection = (
        "s.id AS withmate_session_id, s.thread_id, s.title, "
        "s.workspace_path, s.state"
    )

    messages = run_budgeted_sqlite_json(
        executable,
        database,
        f"SELECT {session_projection}, m.seq, m.role, m.body, m.created_at "
        "FROM session_messages_v6 AS m JOIN sessions_v6 AS s ON s.id=m.session_id "
        f"WHERE {timestamp_predicate('m.created_at', window)} ORDER BY m.created_at, m.seq;",
        row_budget,
        byte_budget,
        "session messages",
    )
    counts["messages"] = 0
    for row in messages:
        if not row_matches_workspace(row, workspace_filter):
            continue
        counts["messages"] += 1
        try:
            occurred = parse_timestamp(str(row["created_at"]), slash_timezone=tz)
        except (ValueError, TypeError) as exc:
            gaps.append(f"withmate message timestamp skipped: {exc}")
            continue
        if not in_window(occurred, window):
            continue
        session = session_from_row(sessions, row)
        role = str(row.get("role") or "")
        body = unwrap_withmate_message(str(row.get("body") or ""), role)
        if role == "user":
            body = normalize_user_text(body)
        add_event(
            session,
            occurred_at=occurred,
            kind=f"{role}_message" if role else "message",
            source="withmate-v6",
            role=role or None,
            text=bounded_text(body, text_limit),
            metadata={"sequence": row.get("seq")},
            budget=event_budget,
        )

    turns = run_budgeted_sqlite_json(
        executable,
        database,
        f"SELECT {session_projection}, t.id AS turn_id, t.phase, t.summary, "
        "t.error_summary, t.started_at, t.completed_at, t.updated_at "
        "FROM session_turns_v6 AS t JOIN sessions_v6 AS s ON s.id=t.session_id "
        f"WHERE {timestamp_comparison('t.started_at', '<', local_boundary=window.local_end, utc_boundary=window.utc_end)} "
        f"AND {timestamp_comparison('coalesce(t.completed_at,t.updated_at)', '>', local_boundary=window.local_start, utc_boundary=window.utc_start)} "
        "ORDER BY t.started_at;",
        row_budget,
        byte_budget,
        "session turns",
    )
    counts["turns"] = 0
    for row in turns:
        if not row_matches_workspace(row, workspace_filter):
            continue
        counts["turns"] += 1
        try:
            started = parse_timestamp(str(row["started_at"]), slash_timezone=tz)
            ended = parse_timestamp(
                str(row.get("completed_at") or row["updated_at"]), slash_timezone=tz
            )
        except (ValueError, TypeError) as exc:
            gaps.append(f"withmate turn timestamp skipped: {exc}")
            continue
        if not (started < window.utc_end and ended > window.utc_start):
            continue
        session = session_from_row(sessions, row)
        occurred = max(started, window.utc_start)
        error_summary = str(row.get("error_summary") or "")
        summary = str(row.get("summary") or "")
        metadata: dict[str, Any] = {
            "turn_id": row.get("turn_id"),
            "phase": row.get("phase"),
            "started_at_utc": iso_z(started),
            "ended_at_utc": iso_z(ended),
        }
        if error_summary:
            metadata["failure_status"] = "known-failure"
            metadata["error_evidence"] = (
                bounded_raw_evidence(error_summary, text_limit)
                if detail
                else content_fingerprint(error_summary)
            )
        add_event(
            session,
            occurred_at=occurred,
            kind="turn_overlap" if started < window.utc_start else "turn_started",
            source="withmate-v6",
            text=(
                bounded_text(summary, text_limit)
                if summary and not error_summary
                else None
            ),
            metadata=metadata,
            budget=event_budget,
        )

    interims = run_budgeted_sqlite_json(
        executable,
        database,
        f"SELECT {session_projection}, i.seq, i.body, i.created_at "
        "FROM session_turn_interims_v6 AS i "
        "JOIN session_turns_v6 AS t ON t.id=i.turn_id "
        "JOIN sessions_v6 AS s ON s.id=t.session_id "
        f"WHERE {timestamp_predicate('i.created_at', window)} ORDER BY i.created_at, i.seq;",
        row_budget,
        byte_budget,
        "session interims",
    )
    counts["interims"] = 0
    for row in interims:
        if not row_matches_workspace(row, workspace_filter):
            continue
        counts["interims"] += 1
        try:
            occurred = parse_timestamp(str(row["created_at"]), slash_timezone=tz)
        except (ValueError, TypeError) as exc:
            gaps.append(f"withmate interim timestamp skipped: {exc}")
            continue
        if not in_window(occurred, window):
            continue
        session = session_from_row(sessions, row)
        add_event(
            session,
            occurred_at=occurred,
            kind="assistant_progress",
            source="withmate-v6",
            role="assistant",
            text=bounded_text(str(row.get("body") or ""), text_limit),
            metadata={"sequence": row.get("seq")},
            budget=event_budget,
        )

    kind_list = ",".join(sql_literal(kind) for kind in sorted(ALLOWED_PROVIDER_KINDS))
    provider_json = (
        "(CASE WHEN json_valid(p.payload_json) THEN p.payload_json ELSE '{}' END)"
    )
    provider_payload_projection = (
        "p.payload_json, json_valid(p.payload_json) AS indexed_payload_valid, "
        "NULL AS indexed_operation_type, NULL AS indexed_call_id, "
        "NULL AS indexed_tool, NULL AS indexed_exit_code, "
        "NULL AS indexed_is_error_type, NULL AS indexed_is_error, "
        "NULL AS indexed_status, NULL AS indexed_wall_time_seconds"
        if detail
        else (
            f"NULL AS payload_json, json_valid(p.payload_json) AS indexed_payload_valid, "
            f"CASE WHEN json_type({provider_json},'$.value.type')='text' "
            f"THEN json_extract({provider_json},'$.value.type') END AS indexed_operation_type, "
            f"CASE WHEN json_type({provider_json},'$.value.call_id')='text' "
            f"THEN json_extract({provider_json},'$.value.call_id') END AS indexed_call_id, "
            f"coalesce(CASE WHEN json_type({provider_json},'$.value.tool')='text' "
            f"THEN json_extract({provider_json},'$.value.tool') END, "
            f"CASE WHEN json_type({provider_json},'$.value.name')='text' "
            f"THEN json_extract({provider_json},'$.value.name') END) AS indexed_tool, "
            f"CASE WHEN json_type({provider_json},'$.value.exit_code')='integer' "
            f"THEN json_extract({provider_json},'$.value.exit_code') END AS indexed_exit_code, "
            f"json_type({provider_json},'$.value.isError') AS indexed_is_error_type, "
            f"CASE WHEN json_type({provider_json},'$.value.isError') IN ('true','false') "
            f"THEN json_extract({provider_json},'$.value.isError') END AS indexed_is_error, "
            f"CASE WHEN json_type({provider_json},'$.value.status')='text' "
            f"THEN json_extract({provider_json},'$.value.status') END AS indexed_status, "
            f"CASE WHEN json_type({provider_json},'$.value.wall_time_seconds') "
            f"IN ('integer','real') THEN json_extract("
            f"{provider_json},'$.value.wall_time_seconds') END AS indexed_wall_time_seconds"
        )
    )
    outputs = run_budgeted_sqlite_json(
        executable,
        database,
        f"SELECT {session_projection}, p.seq, p.kind, p.summary, "
        f"{provider_payload_projection}, p.created_at "
        "FROM session_turn_provider_outputs_v6 AS p "
        "JOIN session_turns_v6 AS t ON t.id=p.turn_id "
        "JOIN sessions_v6 AS s ON s.id=t.session_id "
        f"WHERE p.kind IN ({kind_list}) AND {timestamp_predicate('p.created_at', window)} "
        "ORDER BY p.created_at, p.seq;",
        row_budget,
        byte_budget,
        "provider outputs",
    )
    counts["provider_outputs"] = 0
    for row in outputs:
        if not row_matches_workspace(row, workspace_filter):
            continue
        counts["provider_outputs"] += 1
        try:
            occurred = parse_timestamp(str(row["created_at"]), slash_timezone=tz)
        except (ValueError, TypeError) as exc:
            gaps.append(f"withmate provider timestamp skipped: {exc}")
            continue
        if not in_window(occurred, window):
            continue
        session = session_from_row(sessions, row)
        kind, content, metadata = provider_event_projection(
            row,
            detail=detail,
            text_limit=text_limit,
            gaps=gaps,
        )
        add_event(
            session,
            occurred_at=occurred,
            kind=kind,
            source="withmate-v6",
            text=content,
            metadata=metadata,
            budget=event_budget,
        )

    if "audit_events_v6" in available_optional_tables:
        audit = run_budgeted_sqlite_json(
            executable,
            database,
            f"SELECT {session_projection}, a.event_type, a.summary, a.created_at "
            "FROM audit_events_v6 AS a JOIN sessions_v6 AS s ON s.id=a.session_id "
            "WHERE a.event_type IN ('session_turn','diagnostic') "
            f"AND {timestamp_predicate('a.created_at', window)} ORDER BY a.created_at;",
            row_budget,
            byte_budget,
            "audit events",
        )
        for row in audit:
            if not row_matches_workspace(row, workspace_filter):
                continue
            try:
                occurred = parse_timestamp(str(row["created_at"]), slash_timezone=tz)
            except (ValueError, TypeError) as exc:
                gaps.append(f"withmate audit timestamp skipped: {exc}")
                continue
            if not in_window(occurred, window):
                continue
            counts["audit_events"] += 1
            session = session_from_row(sessions, row)
            if "summary" not in row:
                gaps.append("withmate audit summary unavailable: missing value")
                summary_evidence = None
            else:
                audit_summary = row.get("summary")
                summary_evidence = (
                    bounded_raw_evidence(
                        audit_summary,
                        text_limit,
                        gaps=gaps,
                        label="withmate audit summary evidence",
                    )
                    if detail
                    else content_fingerprint(audit_summary)
                )
            add_event(
                session,
                occurred_at=occurred,
                kind=f"audit_{row.get('event_type')}",
                source="withmate-v6",
                text=summary_evidence,
                budget=event_budget,
            )

    return counts


def candidate_rollouts(
    sessions_root: Path,
    window: FixedWindow,
    max_bytes: int,
    max_files: int,
    max_tail_probe_bytes: int,
) -> tuple[list[Path], int, int, int]:
    if not sessions_root.is_dir():
        raise CollectorError(f"Codex sessions directory not found: {sessions_root}")
    candidates: list[Path] = []
    total_bytes = 0
    uncertain_tail_files = 0
    probed_bytes = 0
    discovered_files = 0
    for path in sessions_root.rglob("rollout-*.jsonl"):
        discovered_files += 1
        if discovered_files > max_files:
            raise CollectorError("rollout discovery exceeded --max-rollout-files")
        try:
            stat = path.stat()
        except OSError as exc:
            raise CollectorError(f"rollout metadata unreadable: {path.name}: {exc}") from exc
        remaining_probe_bytes = max_tail_probe_bytes - probed_bytes
        if stat.st_size > 0 and remaining_probe_bytes <= 0:
            raise CollectorError("rollout tail probing exceeded --max-tail-probe-bytes")
        tail_status, last_timestamp, bytes_read = last_rollout_timestamp(
            path,
            max_probe_bytes=min(TAIL_PROBE_PER_FILE_BYTES, remaining_probe_bytes),
        )
        if bytes_read > remaining_probe_bytes:
            raise CollectorError("rollout tail probing exceeded --max-tail-probe-bytes")
        probed_bytes += bytes_read
        if tail_status == "known" and last_timestamp is not None and last_timestamp < window.utc_start:
            continue
        if tail_status == "uncertain":
            uncertain_tail_files += 1
        if total_bytes + stat.st_size > max_bytes:
            raise CollectorError(
                "rollout candidate bytes exceed --max-rollout-bytes; raise the explicit "
                "resource limit only after confirming the intended source scope"
            )
        candidates.append(path)
        total_bytes += stat.st_size
    return sorted(candidates), total_bytes, uncertain_tail_files, probed_bytes


def last_rollout_timestamp(
    path: Path, max_probe_bytes: int = TAIL_PROBE_PER_FILE_BYTES
) -> tuple[str, datetime | None, int]:
    with path.open("rb") as handle:
        handle.seek(0, os.SEEK_END)
        end = handle.tell()
        if end == 0:
            return "uncertain", None, 0
        probe = min(end, max_probe_bytes)
        handle.seek(end - probe)
        data = handle.read(probe)

    lines = data.splitlines()
    if probe < end and lines:
        lines = lines[1:]
    last_line = next((line for line in reversed(lines) if line.strip()), None)
    if last_line is None:
        return "uncertain", None, len(data)
    try:
        record = json.loads(last_line.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return "uncertain", None, len(data)
    if not isinstance(record, dict) or not isinstance(record.get("timestamp"), str):
        return "uncertain", None, len(data)
    try:
        timestamp = parse_timestamp(str(record["timestamp"]), slash_timezone=UTC)
    except (ValueError, TypeError):
        return "uncertain", None, len(data)
    return "known", timestamp, len(data)


def tool_call_metadata(
    payload: dict[str, Any], *, raw_evidence_limit: int | None = None
) -> dict[str, Any]:
    if payload.get("type") == "custom_tool_call":
        command_present = "input" in payload
        command = payload.get("input")
    else:
        if "arguments" in payload:
            raw = payload.get("arguments")
        else:
            raw = payload.get("input", "")
        parsed: Any = raw
        if isinstance(raw, str):
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                parsed = raw
        command = (
            parsed.get("cmd")
            if isinstance(parsed, dict)
            else parsed if isinstance(parsed, str) else None
        )
        command_present = bool(command)
    metadata = {
        "call_id": safe_tool_identifier(payload.get("call_id")),
        "tool": safe_tool_identifier(payload.get("name")),
        "namespace": safe_tool_identifier(payload.get("namespace")),
    }
    if command_present:
        metadata["command_evidence"] = (
            bounded_raw_evidence(command, raw_evidence_limit)
            if raw_evidence_limit is not None
            else content_fingerprint(command)
        )
    return metadata


def tool_output_metadata(
    payload: dict[str, Any], *, raw_evidence_limit: int | None = None
) -> dict[str, Any]:
    raw = payload.get("output", "")
    parsed: Any = raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = None
    metadata: dict[str, Any] = {
        "call_id": safe_tool_identifier(payload.get("call_id"))
    }
    if raw not in (None, ""):
        metadata["output_evidence"] = (
            bounded_raw_evidence(raw, raw_evidence_limit)
            if raw_evidence_limit is not None
            else content_fingerprint(raw)
        )
    failure_status = "unknown"
    if isinstance(parsed, dict):
        raw_exit_code = parsed.get("exit_code")
        exit_code = (
            raw_exit_code
            if type(raw_exit_code) is int
            and -MAX_TOOL_EXIT_CODE_ABS <= raw_exit_code < MAX_TOOL_EXIT_CODE_ABS
            else None
        )
        raw_is_error = parsed.get("isError")
        is_error = raw_is_error if type(raw_is_error) is bool else None
        raw_status = parsed.get("status")
        status = (
            raw_status.lower()
            if isinstance(raw_status, str)
            and raw_status.lower() in TOOL_RESULT_STATUSES
            else None
        )
        raw_wall_time = parsed.get("wall_time_seconds")
        wall_time = (
            raw_wall_time
            if type(raw_wall_time) in {int, float}
            and 0 <= raw_wall_time <= MAX_TOOL_WALL_TIME_SECONDS
            else None
        )
        if exit_code is not None:
            metadata["exit_code"] = exit_code
        if is_error is not None:
            metadata["isError"] = is_error
        if status is not None:
            metadata["status"] = status
        if wall_time is not None:
            metadata["wall_time_seconds"] = wall_time
        explicit_error = parsed.get("error")
        stderr = parsed.get("stderr")
        if explicit_error:
            metadata["error_evidence"] = (
                bounded_raw_evidence(explicit_error, raw_evidence_limit)
                if raw_evidence_limit is not None
                else content_fingerprint(explicit_error)
            )
        if stderr:
            metadata["stderr_evidence"] = (
                bounded_raw_evidence(stderr, raw_evidence_limit)
                if raw_evidence_limit is not None
                else content_fingerprint(stderr)
            )
        if is_error is True:
            failure_status = "known-failure"
        elif exit_code is not None and exit_code != 0:
            failure_status = "known-failure"
        elif status in {"cancelled", "error", "failed", "timed_out", "timeout"}:
            failure_status = "known-failure"
        elif explicit_error:
            failure_status = "known-failure"
        elif is_error is False:
            failure_status = "known-success"
        elif exit_code == 0:
            failure_status = "known-success"
        elif status in {"completed", "ok", "passed", "success", "succeeded"}:
            failure_status = "known-success"
    metadata["failure_status"] = failure_status
    return metadata


def rollout_event_metadata(payload: dict[str, Any]) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    turn_id = payload.get("turn_id")
    if isinstance(turn_id, str) and turn_id:
        metadata["turn_id_evidence"] = content_fingerprint(turn_id)
    duration_ms = payload.get("duration_ms")
    if (
        type(duration_ms) is int
        and 0 <= duration_ms <= MAX_ROLLOUT_EVENT_DURATION_MS
    ):
        metadata["duration_ms"] = duration_ms
    status = payload.get("status")
    if isinstance(status, str) and status.lower() in ROLLOUT_EVENT_STATUSES:
        normalized_status = status.lower()
        metadata["status"] = normalized_status
        if normalized_status in {
            "cancelled",
            "error",
            "failed",
            "timed_out",
            "timeout",
        }:
            metadata["failure_status"] = "known-failure"
    return metadata


def native_text(payload: dict[str, Any]) -> str:
    for key in ("message", "last_agent_message"):
        if isinstance(payload.get(key), str):
            return str(payload[key])
    return ""


def collect_rollouts(
    codex_sessions: Path,
    window: FixedWindow,
    sessions: dict[str, dict[str, Any]],
    *,
    text_limit: int,
    max_bytes: int,
    max_line_bytes: int,
    max_files: int,
    max_tail_probe_bytes: int,
    workspace_filter: str | None,
    gaps: list[str],
    event_budget: CountBudget,
    detail: bool = False,
) -> dict[str, Any]:
    candidates, total_bytes, uncertain_tail_files, probed_bytes = candidate_rollouts(
        codex_sessions, window, max_bytes, max_files, max_tail_probe_bytes
    )
    malformed_lines = 0
    timestamp_missing_records = 0
    timestamp_invalid_records = 0
    excluded: dict[str, int] = {}
    parsed_files = 0
    parsed_bytes = 0

    for path in candidates:
        session_id = ""
        session: dict[str, Any] | None = None
        skip_for_workspace = False
        try:
            handle = path.open("rb")
        except OSError as exc:
            gaps.append(f"rollout unreadable ({path.name}): {exc}")
            continue
        with handle:
            line_number = 0
            while True:
                remaining_bytes = max_bytes - parsed_bytes
                if remaining_bytes <= 0:
                    if handle.read(1):
                        raise CollectorError(
                            "rollout bytes grew beyond --max-rollout-bytes during collection"
                        )
                    break
                line_limit = min(remaining_bytes, max_line_bytes)
                line = handle.readline(line_limit + 1)
                if not line:
                    break
                if len(line) > line_limit:
                    raise CollectorError(
                        "rollout JSONL record exceeded --max-rollout-line-bytes"
                    )
                parsed_bytes += len(line)
                line_number += 1
                try:
                    record = json.loads(line)
                except (UnicodeDecodeError, json.JSONDecodeError):
                    malformed_lines += 1
                    continue
                if not isinstance(record, dict):
                    continue
                root_type = str(record.get("type") or "")
                payload = record.get("payload")
                if not isinstance(payload, dict):
                    payload = {}
                payload_type = str(payload.get("type") or "")

                if root_type == "session_meta":
                    session_id = str(payload.get("id") or payload.get("session_id") or path.stem)
                    workspace = str(payload.get("cwd") or "")
                    if workspace_filter and normalize_path(workspace) != normalize_path(workspace_filter):
                        skip_for_workspace = True
                        break
                    session = ensure_session(sessions, session_id, workspace=workspace)
                    if path.name not in session["native_rollouts"]:
                        session["native_rollouts"].append(path.name)
                    add_source(session, "codex-rollout")
                    continue

                if skip_for_workspace:
                    break
                if session is None:
                    session_id = session_id or path.stem
                    session = ensure_session(sessions, session_id)
                    if path.name not in session["native_rollouts"]:
                        session["native_rollouts"].append(path.name)
                    add_source(session, "codex-rollout")

                if (root_type, payload_type) in EXCLUDED_JSONL_TYPES:
                    key = f"{root_type}:{payload_type}"
                    excluded[key] = excluded.get(key, 0) + 1
                    continue

                relevant = (
                    root_type == "event_msg"
                    and payload_type
                    in {
                        "user_message",
                        "agent_message",
                        "task_started",
                        "task_complete",
                        "error",
                        "patch_apply_end",
                        "web_search_end",
                    }
                ) or (
                    root_type == "response_item"
                    and payload_type
                    in {
                        "function_call",
                        "function_call_output",
                        "custom_tool_call",
                        "custom_tool_call_output",
                    }
                )
                if not relevant:
                    continue

                raw_timestamp = record.get("timestamp")
                if not isinstance(raw_timestamp, str):
                    timestamp_missing_records += 1
                    continue
                try:
                    occurred = parse_timestamp(raw_timestamp, slash_timezone=UTC)
                except (ValueError, TypeError):
                    timestamp_invalid_records += 1
                    continue
                if not in_window(occurred, window):
                    continue

                if root_type == "event_msg" and payload_type in {"user_message", "agent_message"}:
                    role = "user" if payload_type == "user_message" else "assistant"
                    text = native_text(payload)
                    if role == "user":
                        text = normalize_user_text(text)
                    add_event(
                        session,
                        occurred_at=occurred,
                        kind=f"{role}_message",
                        source="codex-rollout",
                        role=role,
                        text=bounded_text(text, text_limit),
                        budget=event_budget,
                    )
                elif root_type == "event_msg":
                    if payload_type == "error":
                        metadata: dict[str, Any] = {
                            "failure_status": "known-failure"
                        }
                        error_text = native_text(payload)
                        if error_text:
                            metadata["error_evidence"] = (
                                bounded_raw_evidence(error_text, text_limit)
                                if detail
                                else content_fingerprint(error_text)
                            )
                    else:
                        metadata = rollout_event_metadata(payload)
                    add_event(
                        session,
                        occurred_at=occurred,
                        kind=payload_type,
                        source="codex-rollout",
                        text=None,
                        metadata=metadata or None,
                        budget=event_budget,
                    )
                elif payload_type in {"function_call", "custom_tool_call"}:
                    add_event(
                        session,
                        occurred_at=occurred,
                        kind="tool_call",
                        source="codex-rollout",
                        metadata=tool_call_metadata(
                            payload,
                            raw_evidence_limit=text_limit if detail else None,
                        ),
                        budget=event_budget,
                    )
                else:
                    add_event(
                        session,
                        occurred_at=occurred,
                        kind="tool_result",
                        source="codex-rollout",
                        metadata=tool_output_metadata(
                            payload,
                            raw_evidence_limit=text_limit if detail else None,
                        ),
                        budget=event_budget,
                    )
        parsed_files += 1

    if timestamp_missing_records:
        gaps.append(
            "rollout relevant records missing timestamp "
            f"count={timestamp_missing_records}; window membership is unknown"
        )
    if timestamp_invalid_records:
        gaps.append(
            "rollout relevant records have invalid timestamp "
            f"count={timestamp_invalid_records}; window membership is unknown"
        )

    return {
        "candidate_files": len(candidates),
        "candidate_bytes": total_bytes,
        "parsed_bytes": parsed_bytes,
        "uncertain_tail_files_included": uncertain_tail_files,
        "tail_probe_bytes": probed_bytes,
        "parsed_files": parsed_files,
        "malformed_lines": malformed_lines,
        "timestamp_missing_records": timestamp_missing_records,
        "timestamp_invalid_records": timestamp_invalid_records,
        "excluded_event_counts": excluded,
    }


def normalize_path(value: str) -> str:
    if not value:
        return ""
    return os.path.normpath(os.path.abspath(os.path.expandvars(value))).casefold()


def message_dedupe_key(event: dict[str, Any]) -> tuple[str, str, str] | None:
    if event.get("kind") not in {"user_message", "assistant_message"}:
        return None
    content = event.get("content")
    if not isinstance(content, dict):
        return None
    timestamp = str(event.get("occurred_at_utc") or "")
    return str(event.get("kind")), str(content.get("sha256")), timestamp


def trim_both_ends(values: list[Any], limit: int) -> tuple[list[Any], int]:
    if limit <= 0:
        return [], len(values)
    if len(values) <= limit:
        return values, 0
    head = limit // 2
    tail = limit - head
    return values[:head] + values[-tail:], len(values) - limit


def tool_result_failed(event: dict[str, Any]) -> bool:
    if event.get("kind") != "tool_result":
        return False
    metadata = event.get("metadata")
    if not isinstance(metadata, dict):
        return False
    failure_status = metadata.get("failure_status")
    if failure_status == "known-failure":
        return True
    if failure_status == "known-success":
        return False
    if metadata.get("isError") is True:
        return True
    exit_code = metadata.get("exit_code")
    if exit_code is not None and str(exit_code) != "0":
        return True
    if str(metadata.get("status") or "").lower() in {
        "cancelled",
        "error",
        "failed",
        "timed_out",
        "timeout",
    }:
        return True
    return bool(metadata.get("error"))


def known_failure_event(event: dict[str, Any]) -> bool:
    metadata = event.get("metadata")
    if isinstance(metadata, dict) and metadata.get("failure_status") == "known-failure":
        return True
    if event.get("kind") in {"provider_error", "error"}:
        return True
    return tool_result_failed(event)


def executable_failure_status_unknown(event: dict[str, Any]) -> bool:
    if event.get("kind") not in {"command_execution", "tool_call", "tool_result"}:
        return False
    metadata = event.get("metadata")
    return isinstance(metadata, dict) and metadata.get("failure_status") == "unknown"


def safe_provider_operation_type(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    if len(value) > MAX_PROVIDER_OPERATION_TYPE_CHARS:
        return ""
    if re.fullmatch(r"[A-Za-z][A-Za-z0-9_.:-]*", value) is None:
        return ""
    return value


def correlation_call_id(event: dict[str, Any]) -> str | None:
    metadata = event.get("metadata")
    if not isinstance(metadata, dict):
        return None
    call_id = metadata.get("call_id")
    if not isinstance(call_id, str) or not call_id.strip():
        return None
    return call_id


def mark_unmatched_tool_calls(events: list[dict[str, Any]]) -> None:
    call_counts: dict[tuple[str, str], int] = {}
    result_counts: dict[tuple[str, str], int] = {}
    calls: dict[tuple[str, str], dict[str, Any]] = {}
    results: dict[tuple[str, str], dict[str, Any]] = {}
    for event in events:
        if event.get("kind") not in {"tool_call", "tool_result"}:
            continue
        call_id = correlation_call_id(event)
        if call_id is None:
            continue
        key = (str(event.get("source") or ""), call_id)
        counts = call_counts if event.get("kind") == "tool_call" else result_counts
        counts[key] = counts.get(key, 0) + 1
        targets = calls if event.get("kind") == "tool_call" else results
        targets[key] = event

    for key, call in calls.items():
        if call_counts.get(key) != 1 or result_counts.get(key) != 1:
            continue
        call_metadata = call.get("metadata")
        result_metadata = results[key].get("metadata")
        if not isinstance(call_metadata, dict) or not isinstance(result_metadata, dict):
            continue
        for field in ("tool", "namespace"):
            if call_metadata.get(field) is not None:
                result_metadata[field] = call_metadata[field]

    for event in events:
        if event.get("kind") != "tool_call":
            continue
        metadata = event.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}
            event["metadata"] = metadata
        call_id = correlation_call_id(event)
        key = (str(event.get("source") or ""), call_id or "")
        call_count = call_counts.get(key, 0)
        result_count = result_counts.get(key, 0)
        if call_id is None or call_count != 1 or result_count != 1:
            metadata["failure_status"] = "unknown"
            if call_id is None:
                metadata["result_status"] = "invalid-call-id"
            elif result_count == 0:
                metadata["result_status"] = "missing-in-fixed-interval"
            else:
                metadata["result_status"] = "ambiguous-call-result-cardinality"


def trim_preserving_known_failures(
    events: list[dict[str, Any]], limit: int, limit_name: str
) -> tuple[list[dict[str, Any]], int]:
    if len(events) <= limit:
        return events, 0
    failed_indices = [
        index for index, event in enumerate(events) if known_failure_event(event)
    ]
    if len(failed_indices) > limit:
        raise CollectorError(
            f"known failure events exceed {limit_name}; raise the explicit output limit "
            "rather than dropping failure evidence"
        )
    failed_set = set(failed_indices)
    optional_indices = [
        index for index in range(len(events)) if index not in failed_set
    ]
    kept_optional, _ = trim_both_ends(optional_indices, limit - len(failed_indices))
    kept_indices = failed_set | set(kept_optional)
    kept = [event for index, event in enumerate(events) if index in kept_indices]
    return kept, len(events) - len(kept)


def allocate_balanced_optional_quotas(
    capacities: list[int], total: int
) -> list[int]:
    quotas = [0] * len(capacities)
    while total > 0:
        progressed = False
        for index, capacity in enumerate(capacities):
            if quotas[index] >= capacity:
                continue
            quotas[index] += 1
            total -= 1
            progressed = True
            if total == 0:
                break
        if not progressed:
            break
    return quotas


def index_content_preview(content: dict[str, Any]) -> dict[str, Any]:
    text = str(content.get("text") or "")
    original_chars = int(content.get("original_chars") or len(text))
    return {
        "text": text[:INDEX_PREVIEW_CHARS],
        "original_chars": original_chars,
        "truncated": bool(content.get("truncated"))
        or original_chars > INDEX_PREVIEW_CHARS,
        "sha256": str(content.get("sha256") or ""),
    }


def index_message_cue(event: dict[str, Any]) -> dict[str, Any]:
    sources = [
        str(source)
        for source in (event.get("sources") or [event.get("source")])
        if source
    ]
    cue: dict[str, Any] = {
        "occurred_at_utc": event["occurred_at_utc"],
        "kind": event["kind"],
        "sources": sources,
    }
    if event.get("role"):
        cue["role"] = event["role"]
    content = event.get("content")
    if isinstance(content, dict):
        cue["content"] = index_content_preview(content)
    return cue


def build_session_index(events: list[dict[str, Any]]) -> dict[str, Any]:
    kind_counts: dict[str, int] = {}
    failure_kind_counts: dict[str, int] = {}
    for event in events:
        kind = str(event.get("kind") or "unknown")
        kind_counts[kind] = kind_counts.get(kind, 0) + 1
        if known_failure_event(event):
            failure_kind_counts[kind] = failure_kind_counts.get(kind, 0) + 1

    goal_events = [event for event in events if event.get("kind") == "user_message"]
    outcome_events = [
        event for event in events if event.get("kind") == "assistant_message"
    ]
    kept_goals, omitted_goals = trim_both_ends(
        goal_events, INDEX_GOAL_CUE_LIMIT
    )
    kept_outcomes = outcome_events[-INDEX_OUTCOME_CUE_LIMIT:]
    omitted_outcomes = len(outcome_events) - len(kept_outcomes)
    return {
        "event_count": len(events),
        "event_kind_counts": dict(sorted(kind_counts.items())),
        "known_failure_event_count": sum(failure_kind_counts.values()),
        "known_failure_kind_counts": dict(sorted(failure_kind_counts.items())),
        "unknown_failure_status_events": sum(
            executable_failure_status_unknown(event) for event in events
        ),
        "goal_cues": [index_message_cue(event) for event in kept_goals],
        "goal_cues_omitted": omitted_goals,
        "outcome_cues": [index_message_cue(event) for event in kept_outcomes],
        "outcome_cues_omitted": omitted_outcomes,
    }


def project_session_index(
    session: dict[str, Any], session_index: dict[str, Any]
) -> dict[str, Any]:
    return {
        "session_id": session["session_id"],
        "withmate_session_ids": sorted(session["withmate_session_ids"]),
        "first_event_at_utc": session["first_event_at_utc"],
        "last_event_at_utc": session["last_event_at_utc"],
        "workspaces": list(session["workspaces"]),
        "sources": list(session["sources"]),
        "session_index": session_index,
    }


def finalize_sessions(
    sessions: dict[str, dict[str, Any]],
    *,
    workspace_filter: str | None,
    selected_ids: set[str],
    max_events_per_session: int,
    max_events: int,
    detail: bool,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    output: list[dict[str, Any]] = []
    total_omitted = 0
    duplicate_messages = 0
    detail_events_not_projected = 0
    goal_cues_omitted = 0
    outcome_cues_omitted = 0
    unknown_failure_status_total = 0
    for session in sessions.values():
        normalized_workspaces = {
            normalize_path(workspace)
            for workspace in session.get("workspaces", [])
            if workspace
        }
        if workspace_filter:
            normalized_filter = normalize_path(workspace_filter)
            if normalized_filter not in normalized_workspaces:
                continue
            if normalized_workspaces != {normalized_filter}:
                raise CollectorError(
                    "workspace filter boundary mixed evidence from another workspace"
                )
        identity_set = {
            session["session_id"],
            *session["withmate_session_ids"],
        }
        if selected_ids and not (identity_set & selected_ids):
            continue
        events = sorted(session["events"], key=lambda event: event["occurred_at_utc"])
        message_groups: dict[
            tuple[str, str, str], list[tuple[int, dict[str, Any]]]
        ] = {}
        for index, event in enumerate(events):
            key = message_dedupe_key(event)
            if key is not None:
                message_groups.setdefault(key, []).append((index, event))

        merged_sources: dict[int, list[str]] = {}
        duplicate_indices: set[int] = set()
        for group in message_groups.values():
            sources = [str(event.get("source") or "") for _, event in group]
            if len(group) < 2 or len(set(sources)) != len(group):
                continue
            retained_index, _ = group[0]
            merged_sources[retained_index] = sorted(sources)
            duplicate_indices.update(index for index, _ in group[1:])

        deduped: list[dict[str, Any]] = []
        for index, event in enumerate(events):
            if index in duplicate_indices:
                duplicate_messages += 1
                continue
            source = str(event.get("source") or "")
            event["sources"] = merged_sources.get(index, [source])
            deduped.append(event)
        if not deduped:
            continue
        mark_unmatched_tool_calls(deduped)
        unknown_failure_status_events = sum(
            executable_failure_status_unknown(event) for event in deduped
        )
        unknown_failure_status_total += unknown_failure_status_events
        kind_counts: dict[str, int] = {}
        for event in deduped:
            kind = str(event.get("kind") or "unknown")
            kind_counts[kind] = kind_counts.get(kind, 0) + 1
        if detail:
            kept, omitted = trim_preserving_known_failures(
                deduped, max_events_per_session, "--max-events-per-session"
            )
            total_omitted += omitted
            session["events"] = kept
            session["event_count_before_limits"] = len(deduped)
            session["event_kind_counts_before_limits"] = dict(
                sorted(kind_counts.items())
            )
            session["omitted_events"] = omitted
            session["unknown_failure_status_events"] = (
                unknown_failure_status_events
            )
        else:
            session_index = build_session_index(deduped)
            detail_events_not_projected += len(deduped)
            goal_cues_omitted += session_index["goal_cues_omitted"]
            outcome_cues_omitted += session_index["outcome_cues_omitted"]
        session["first_event_at_utc"] = deduped[0]["occurred_at_utc"]
        session["last_event_at_utc"] = deduped[-1]["occurred_at_utc"]
        session["sources"].sort()
        session["workspaces"].sort(key=normalize_path)
        output.append(
            session if detail else project_session_index(session, session_index)
        )

    output.sort(
        key=lambda session: (session["first_event_at_utc"], session["session_id"])
    )
    if detail and sum(len(session["events"]) for session in output) > max_events:
        failed_counts = [
            sum(known_failure_event(event) for event in session["events"])
            for session in output
        ]
        total_failed = sum(failed_counts)
        if total_failed > max_events:
            raise CollectorError(
                "known failure events exceed --max-events; raise the explicit output "
                "limit rather than dropping failure evidence"
            )
        optional_capacities = [
            len(session["events"]) - failed_count
            for session, failed_count in zip(output, failed_counts)
        ]
        optional_quotas = allocate_balanced_optional_quotas(
            optional_capacities, max_events - total_failed
        )
        for session, failed_count, optional_quota in zip(
            output, failed_counts, optional_quotas
        ):
            quota = failed_count + optional_quota
            kept, omitted = trim_preserving_known_failures(
                session["events"], quota, "--max-events"
            )
            session["events"] = kept
            session["omitted_events"] += omitted
            total_omitted += omitted
    unknown_failure_status_omitted = 0
    for session in output:
        if detail:
            retained = sum(
                executable_failure_status_unknown(event)
                for event in session["events"]
            )
            omitted = session["unknown_failure_status_events"] - retained
            session["unknown_failure_status_omitted"] = omitted
        else:
            omitted = session["session_index"]["unknown_failure_status_events"]
        unknown_failure_status_omitted += omitted
    return output, {
        "omitted_events": total_omitted,
        "deduplicated_messages": duplicate_messages,
        "unknown_failure_status_events": unknown_failure_status_total,
        "unknown_failure_status_omitted": unknown_failure_status_omitted,
        "detail_events_not_projected": detail_events_not_projected,
        "goal_cues_omitted": goal_cues_omitted,
        "outcome_cues_omitted": outcome_cues_omitted,
    }


def default_withmate_db() -> Path:
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / "WithMate" / "withmate-v6.db"
    return Path.home() / ".local" / "share" / "WithMate" / "withmate-v6.db"


def default_codex_home() -> Path:
    configured = os.environ.get("CODEX_HOME")
    return Path(configured) if configured else Path.home() / ".codex"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Collect one fixed time interval of Codex work evidence as JSON."
    )
    parser.add_argument(
        "--start", required=True, help="inclusive local ISO datetime without offset"
    )
    parser.add_argument(
        "--end", required=True, help="exclusive local ISO datetime without offset"
    )
    parser.add_argument("--timezone", default="Asia/Tokyo", help="IANA timezone")
    parser.add_argument("--withmate-db", type=Path, default=default_withmate_db())
    parser.add_argument("--codex-home", type=Path, default=default_codex_home())
    parser.add_argument("--workspace", help="case-insensitive exact workspace path filter")
    parser.add_argument("--session-id", action="append", default=[])
    parser.add_argument(
        "--detail",
        action="store_true",
        help="emit bounded event-level evidence instead of the session index",
    )
    parser.add_argument("--max-rollout-bytes", type=int, default=512 * 1024 * 1024)
    parser.add_argument("--max-rollout-line-bytes", type=int, default=8 * 1024 * 1024)
    parser.add_argument("--max-rollout-files", type=int, default=10_000)
    parser.add_argument("--max-tail-probe-bytes", type=int, default=512 * 1024 * 1024)
    parser.add_argument("--max-database-bytes", type=int, default=128 * 1024 * 1024)
    parser.add_argument("--max-database-rows", type=int, default=250_000)
    parser.add_argument("--max-collected-events", type=int, default=100_000)
    parser.add_argument("--max-events-per-session", type=int)
    parser.add_argument("--max-events", type=int)
    return parser


def validate_positive(name: str, value: int) -> None:
    if value <= 0:
        raise CollectorError(f"{name} must be greater than zero")


def collect(args: argparse.Namespace) -> dict[str, Any]:
    if not args.detail and (
        args.max_events_per_session is not None or args.max_events is not None
    ):
        raise CollectorError(
            "--max-events-per-session and --max-events require --detail"
        )
    max_events_per_session = (
        1200 if args.max_events_per_session is None else args.max_events_per_session
    ) if args.detail else 0
    max_events = (
        12000 if args.max_events is None else args.max_events
    ) if args.detail else 0
    validate_positive("--max-rollout-bytes", int(args.max_rollout_bytes))
    validate_positive("--max-rollout-line-bytes", int(args.max_rollout_line_bytes))
    validate_positive("--max-rollout-files", int(args.max_rollout_files))
    validate_positive("--max-tail-probe-bytes", int(args.max_tail_probe_bytes))
    validate_positive("--max-database-bytes", int(args.max_database_bytes))
    validate_positive("--max-database-rows", int(args.max_database_rows))
    validate_positive("--max-collected-events", int(args.max_collected_events))
    if args.detail:
        validate_positive("--max-events-per-session", int(max_events_per_session))
        validate_positive("--max-events", int(max_events))
    window = build_window(args.start, args.end, args.timezone)
    sqlite_executable, sqlite_version = require_sqlite()
    database = args.withmate_db.expanduser().resolve()
    codex_home = args.codex_home.expanduser().resolve()
    codex_sessions = codex_home / "sessions"
    database_byte_budget = CountBudget(
        "--max-database-bytes", int(args.max_database_bytes)
    )
    available_optional_tables = validate_database(
        sqlite_executable, database, database_byte_budget
    )

    sessions: dict[str, dict[str, Any]] = {}
    gaps: list[str] = []
    text_limit = 6000 if args.detail else 1200
    row_budget = CountBudget("--max-database-rows", int(args.max_database_rows))
    event_budget = CountBudget("--max-collected-events", int(args.max_collected_events))
    database_counts = collect_database(
        sqlite_executable,
        database,
        window,
        sessions,
        workspace_filter=args.workspace,
        text_limit=text_limit,
        gaps=gaps,
        row_budget=row_budget,
        byte_budget=database_byte_budget,
        event_budget=event_budget,
        available_optional_tables=available_optional_tables,
        detail=args.detail,
    )
    rollout_counts = collect_rollouts(
        codex_sessions,
        window,
        sessions,
        text_limit=text_limit,
        max_bytes=args.max_rollout_bytes,
        max_line_bytes=args.max_rollout_line_bytes,
        max_files=args.max_rollout_files,
        max_tail_probe_bytes=args.max_tail_probe_bytes,
        workspace_filter=args.workspace,
        gaps=gaps,
        event_budget=event_budget,
        detail=args.detail,
    )
    finalized, truncation = finalize_sessions(
        sessions,
        workspace_filter=args.workspace,
        selected_ids=set(args.session_id),
        max_events_per_session=max_events_per_session,
        max_events=max_events,
        detail=args.detail,
    )
    if args.session_id:
        found = {
            identity
            for session in finalized
            for identity in [session["session_id"], *session["withmate_session_ids"]]
        }
        missing = sorted(set(args.session_id) - found)
        if missing:
            gaps.append(f"requested session IDs not found in fixed interval: {missing}")

    return {
        "schema_version": SCHEMA_VERSION,
        "fixed_window": {
            "timezone": window.timezone_name,
            "local_start": window.local_start.isoformat(),
            "local_end": window.local_end.isoformat(),
            "utc_start": iso_z(window.utc_start),
            "utc_end": iso_z(window.utc_end),
            "status": window.status,
        },
        "collection_contract": {
            "sqlite_required": True,
            "sqlite_version": sqlite_version,
            "database_mode": "sqlite3 -readonly + PRAGMA query_only=ON",
            "event_interval": "half-open [start, end)",
            "rollout_candidate_rule": (
                "last event >= UTC start; path date never excludes a file; "
                "unparseable tails are included"
            ),
            "usage_and_token_events": "excluded",
            "raw_log_persistence": "none",
            "content_mode": "detail" if args.detail else "session-index",
            "resource_limits": {
                "max_rollout_bytes": args.max_rollout_bytes,
                "max_rollout_line_bytes": args.max_rollout_line_bytes,
                "max_rollout_files": args.max_rollout_files,
                "max_tail_probe_bytes": args.max_tail_probe_bytes,
                "tail_probe_per_file_bytes": TAIL_PROBE_PER_FILE_BYTES,
                "max_database_bytes": args.max_database_bytes,
                "database_bytes_used": database_byte_budget.used,
                "max_database_rows": args.max_database_rows,
                "database_rows_used": row_budget.used,
                "max_collected_events": args.max_collected_events,
                "collected_events_used": event_budget.used,
                "detail_max_events_per_session": (
                    max_events_per_session if args.detail else None
                ),
                "detail_max_events": max_events if args.detail else None,
                "index_preview_chars": INDEX_PREVIEW_CHARS,
                "index_goal_cues": INDEX_GOAL_CUE_LIMIT,
                "index_outcome_cues": INDEX_OUTCOME_CUE_LIMIT,
            },
        },
        "source_counts": {
            "withmate": database_counts,
            "codex_rollouts": rollout_counts,
        },
        "session_count": len(finalized),
        "sessions": finalized,
        "truncation": truncation,
        "data_gaps": gaps,
    }


def main(argv: Iterable[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
    parser = build_parser()
    try:
        result = collect(parser.parse_args(list(argv) if argv is not None else None))
    except (CollectorError, OSError, subprocess.SubprocessError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
