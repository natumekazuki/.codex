#!/usr/bin/env python3
"""Claim and store bounded, focus-level Codex work audit results."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
import sys
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable


SCRIPT_DIRECTORY = Path(__file__).resolve().parent
if str(SCRIPT_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIRECTORY))

from collect_session_evidence import (  # noqa: E402
    CollectorError,
    FixedWindow,
    build_window,
    default_codex_home,
    iso_z,
    normalize_path,
)


SCHEMA_VERSION = 1
RESULT_VERSION = 1
SCOPE_VERSION = 1
FOCUS_VERSION = 1
ANALYSIS_CONTRACT_VERSION = 1
ANALYSIS_PROFILE = "quality-rubric-v1"
LEASE_SECONDS = 6 * 60 * 60
SQLITE_BUSY_TIMEOUT_MS = 5000
MAX_DATABASE_BYTES = 64 * 1024 * 1024
MAX_RESULT_BYTES = 64 * 1024
MAX_FOCUS_KEY_CHARS = 64
MAX_FOCUS_QUESTION_CHARS = 1000
MAX_SUMMARY_CHARS = 6000
MAX_REASON_CHARS = 1000
MAX_LIST_ITEMS = 32
MAX_LIST_ITEM_CHARS = 1000
FOCUS_KEY_PATTERN = re.compile(r"[a-z0-9][a-z0-9-]{0,63}")
CLAIM_KEY_PATTERN = re.compile(r"[A-Za-z0-9._:-]{1,128}")
FAILURE_CODE_PATTERN = re.compile(r"[a-z0-9][a-z0-9-]{0,63}")
CONFIDENCE_VALUES = {"high", "medium", "low", "unknown"}


class HistoryError(RuntimeError):
    """A user-actionable audit history failure."""


SCHEMA_STATEMENTS = (
    """
    CREATE TABLE audit_targets (
      id INTEGER PRIMARY KEY,
      identity_sha256 TEXT NOT NULL UNIQUE,
      identity_json TEXT NOT NULL,
      utc_start TEXT NOT NULL,
      utc_end TEXT NOT NULL,
      scope_sha256 TEXT NOT NULL,
      focus_key TEXT NOT NULL,
      focus_question TEXT NOT NULL,
      focus_question_sha256 TEXT NOT NULL,
      analysis_profile TEXT NOT NULL,
      analysis_contract_version INTEGER NOT NULL,
      created_at_utc TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE audit_runs (
      run_id TEXT PRIMARY KEY,
      target_id INTEGER NOT NULL REFERENCES audit_targets(id) ON DELETE RESTRICT,
      claim_key TEXT NOT NULL UNIQUE,
      attempt_no INTEGER NOT NULL,
      status TEXT NOT NULL CHECK (
        status IN ('in_progress', 'completed', 'failed', 'abandoned')
      ),
      window_status TEXT NOT NULL CHECK (window_status IN ('complete', 'partial')),
      started_at_utc TEXT NOT NULL,
      heartbeat_at_utc TEXT NOT NULL,
      lease_expires_at_utc TEXT NOT NULL,
      finished_at_utc TEXT,
      force_reason TEXT,
      result_version INTEGER,
      result_json TEXT,
      result_sha256 TEXT,
      result_bytes INTEGER,
      failure_code TEXT,
      failure_summary TEXT,
      UNIQUE (target_id, attempt_no)
    )
    """,
    """
    CREATE UNIQUE INDEX audit_one_active_run_per_target
    ON audit_runs (target_id) WHERE status = 'in_progress'
    """,
    """
    CREATE INDEX audit_targets_focus_scope_idx
    ON audit_targets (focus_key, scope_sha256, created_at_utc DESC)
    """,
    """
    CREATE INDEX audit_runs_target_finished_idx
    ON audit_runs (target_id, finished_at_utc DESC)
    """,
)

REQUIRED_SCHEMA_OBJECTS = {
    ("table", "audit_targets"): SCHEMA_STATEMENTS[0],
    ("table", "audit_runs"): SCHEMA_STATEMENTS[1],
    ("index", "audit_one_active_run_per_target"): SCHEMA_STATEMENTS[2],
    ("index", "audit_targets_focus_scope_idx"): SCHEMA_STATEMENTS[3],
    ("index", "audit_runs_target_finished_idx"): SCHEMA_STATEMENTS[4],
}

REQUIRED_COLUMNS = {
    "audit_targets": {
        "id",
        "identity_sha256",
        "identity_json",
        "utc_start",
        "utc_end",
        "scope_sha256",
        "focus_key",
        "focus_question",
        "focus_question_sha256",
        "analysis_profile",
        "analysis_contract_version",
        "created_at_utc",
    },
    "audit_runs": {
        "run_id",
        "target_id",
        "claim_key",
        "attempt_no",
        "status",
        "window_status",
        "started_at_utc",
        "heartbeat_at_utc",
        "lease_expires_at_utc",
        "finished_at_utc",
        "force_reason",
        "result_version",
        "result_json",
        "result_sha256",
        "result_bytes",
        "failure_code",
        "failure_summary",
    },
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def default_history_database() -> Path:
    return default_codex_home() / "audit-codex-work-quality" / "history.sqlite3"


def reject_unknown_fields(value: dict[str, Any], allowed: set[str], label: str) -> None:
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise HistoryError(f"{label} contains unknown fields: {unknown}")


def bounded_text(
    value: Any, label: str, maximum: int, *, optional: bool = False
) -> str | None:
    if value is None and optional:
        return None
    if not isinstance(value, str):
        raise HistoryError(f"{label} must be a string")
    text = value.strip()
    if not text:
        if optional:
            return None
        raise HistoryError(f"{label} must not be blank")
    if "\x00" in text:
        raise HistoryError(f"{label} must not contain NUL")
    if len(text) > maximum:
        raise HistoryError(f"{label} exceeds {maximum} characters")
    return text


def canonical_json(value: Any) -> str:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def normalize_focus_question(value: str) -> str:
    normalized = unicodedata.normalize("NFC", value)
    return " ".join(normalized.split()).casefold()


def validate_focus_key(value: Any) -> str:
    text = bounded_text(value, "focus_key", MAX_FOCUS_KEY_CHARS)
    assert text is not None
    key = text.casefold()
    if FOCUS_KEY_PATTERN.fullmatch(key) is None:
        raise HistoryError(
            "focus_key must use lowercase letters, digits, and internal hyphens"
        )
    return key


def validate_claim_key(value: Any) -> str:
    text = bounded_text(value, "claim_key", 128)
    assert text is not None
    if CLAIM_KEY_PATTERN.fullmatch(text) is None:
        raise HistoryError(
            "claim_key must use letters, digits, dot, underscore, colon, or hyphen"
        )
    return text


def validate_string_list(value: Any, label: str) -> list[str]:
    if not isinstance(value, list):
        raise HistoryError(f"{label} must be an array")
    if len(value) > MAX_LIST_ITEMS:
        raise HistoryError(f"{label} exceeds {MAX_LIST_ITEMS} items")
    result: list[str] = []
    for index, item in enumerate(value):
        text = bounded_text(item, f"{label}[{index}]", MAX_LIST_ITEM_CHARS)
        assert text is not None
        result.append(text)
    return result


def validate_target_request(value: Any, *, claim: bool) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise HistoryError("request must be an object")
    allowed = {
        "start",
        "end",
        "timezone",
        "workspace",
        "focus_key",
        "focus_question",
    }
    if claim:
        allowed.update({"claim_key", "force_reason"})
    reject_unknown_fields(value, allowed, "request")
    start = bounded_text(value.get("start"), "start", 64)
    end = bounded_text(value.get("end"), "end", 64)
    timezone_name = bounded_text(
        value.get("timezone", "Asia/Tokyo"), "timezone", 128
    )
    assert start is not None and end is not None and timezone_name is not None
    try:
        window = build_window(start, end, timezone_name)
    except CollectorError as exc:
        raise HistoryError(str(exc)) from exc
    workspace = bounded_text(value.get("workspace"), "workspace", 4096, optional=True)
    workspace_key = normalize_path(workspace or "")
    scope_json = canonical_json(
        {
            "scope_version": SCOPE_VERSION,
            "workspace_specified": workspace is not None,
            "workspace_sha256": sha256_text(workspace_key),
        }
    )
    focus_key = validate_focus_key(value.get("focus_key"))
    focus_question = bounded_text(
        value.get("focus_question"),
        "focus_question",
        MAX_FOCUS_QUESTION_CHARS,
    )
    assert focus_question is not None
    question_sha256 = sha256_text(normalize_focus_question(focus_question))
    identity_json = canonical_json(
        {
            "analysis_contract_version": ANALYSIS_CONTRACT_VERSION,
            "analysis_profile": ANALYSIS_PROFILE,
            "focus": {
                "focus_key": focus_key,
                "focus_question_sha256": question_sha256,
                "focus_version": FOCUS_VERSION,
            },
            "scope": json.loads(scope_json),
            "utc_end": iso_z(window.utc_end),
            "utc_start": iso_z(window.utc_start),
        }
    )
    request = {
        "window": window,
        "workspace": workspace,
        "scope_sha256": sha256_text(scope_json),
        "focus_key": focus_key,
        "focus_question": focus_question,
        "focus_question_sha256": question_sha256,
        "identity_json": identity_json,
        "identity_sha256": sha256_text(identity_json),
    }
    if claim:
        request["claim_key"] = validate_claim_key(value.get("claim_key"))
        request["force_reason"] = bounded_text(
            value.get("force_reason"),
            "force_reason",
            MAX_REASON_CHARS,
            optional=True,
        )
    return request


def validate_run_request(value: Any, operation: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise HistoryError("request must be an object")
    allowed = {"run_id", "claim_key"}
    if operation == "complete":
        allowed.add("result")
    if operation == "fail":
        allowed.update({"failure_code", "failure_summary"})
    reject_unknown_fields(value, allowed, "request")
    run_id = bounded_text(value.get("run_id"), "run_id", 64)
    claim_key = validate_claim_key(value.get("claim_key"))
    assert run_id is not None
    request: dict[str, Any] = {"run_id": run_id, "claim_key": claim_key}
    if operation == "complete":
        request["result"] = validate_result(value.get("result"))
    if operation == "fail":
        failure_code = bounded_text(value.get("failure_code"), "failure_code", 64)
        assert failure_code is not None
        failure_code = failure_code.casefold()
        if FAILURE_CODE_PATTERN.fullmatch(failure_code) is None:
            raise HistoryError(
                "failure_code must use lowercase letters, digits, and internal hyphens"
            )
        failure_summary = bounded_text(
            value.get("failure_summary"), "failure_summary", MAX_REASON_CHARS
        )
        assert failure_summary is not None
        request.update(
            {"failure_code": failure_code, "failure_summary": failure_summary}
        )
    return request


def validate_result(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise HistoryError("result must be an object")
    reject_unknown_fields(
        value,
        {
            "summary",
            "confidence",
            "finding_families",
            "good_decisions",
            "data_gaps",
            "interventions",
            "outcome_context_checked_at_utc",
        },
        "result",
    )
    summary = bounded_text(value.get("summary"), "result.summary", MAX_SUMMARY_CHARS)
    confidence = bounded_text(value.get("confidence"), "result.confidence", 16)
    assert summary is not None and confidence is not None
    if confidence not in CONFIDENCE_VALUES:
        raise HistoryError(
            f"result.confidence must be one of {sorted(CONFIDENCE_VALUES)}"
        )
    checked_at = bounded_text(
        value.get("outcome_context_checked_at_utc"),
        "result.outcome_context_checked_at_utc",
        64,
        optional=True,
    )
    if checked_at is not None:
        try:
            parsed = datetime.fromisoformat(checked_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise HistoryError(
                "result.outcome_context_checked_at_utc must be an offset-aware ISO datetime"
            ) from exc
        if parsed.tzinfo is None:
            raise HistoryError(
                "result.outcome_context_checked_at_utc must include an offset"
            )
        checked_at = iso_z(parsed)
    result = {
        "result_version": RESULT_VERSION,
        "summary": summary,
        "confidence": confidence,
        "finding_families": validate_string_list(
            value.get("finding_families"), "result.finding_families"
        ),
        "good_decisions": validate_string_list(
            value.get("good_decisions"), "result.good_decisions"
        ),
        "data_gaps": validate_string_list(value.get("data_gaps"), "result.data_gaps"),
        "interventions": validate_string_list(
            value.get("interventions"), "result.interventions"
        ),
        "outcome_context_checked_at_utc": checked_at,
    }
    encoded = canonical_json(result).encode("utf-8")
    if len(encoded) > MAX_RESULT_BYTES:
        raise HistoryError(f"result exceeds {MAX_RESULT_BYTES} UTF-8 bytes")
    return result


def configure_connection(connection: sqlite3.Connection) -> None:
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute(f"PRAGMA busy_timeout={SQLITE_BUSY_TIMEOUT_MS}")
    connection.execute("PRAGMA synchronous=FULL")


def user_tables(connection: sqlite3.Connection) -> set[str]:
    return {
        str(row[0])
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
    }


def normalize_schema_sql(value: str) -> str:
    return " ".join(value.split()).casefold()


def validate_schema(connection: sqlite3.Connection) -> None:
    version = int(connection.execute("PRAGMA user_version").fetchone()[0])
    if version != SCHEMA_VERSION:
        raise HistoryError(
            f"unsupported audit history schema version: {version}; expected {SCHEMA_VERSION}"
        )
    missing_tables = sorted(set(REQUIRED_COLUMNS) - user_tables(connection))
    if missing_tables:
        raise HistoryError(f"audit history schema is missing tables: {missing_tables}")
    for table, required in REQUIRED_COLUMNS.items():
        columns = {
            str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})")
        }
        missing = sorted(required - columns)
        if missing:
            raise HistoryError(f"audit history table {table} is missing columns: {missing}")
    stored_objects = {
        (str(row[0]), str(row[1])): normalize_schema_sql(str(row[2]))
        for row in connection.execute(
            """
            SELECT type, name, sql FROM sqlite_master
            WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite_autoindex_%'
            """
        )
    }
    expected_objects = {
        key: normalize_schema_sql(statement)
        for key, statement in REQUIRED_SCHEMA_OBJECTS.items()
    }
    if stored_objects != expected_objects:
        raise HistoryError("audit history schema objects do not match version 1")
    if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
        raise HistoryError("audit history foreign key check failed")
    quick_check = connection.execute("PRAGMA quick_check(1)").fetchone()
    if quick_check is None or str(quick_check[0]) != "ok":
        raise HistoryError("audit history integrity check failed")


def initialize_schema(connection: sqlite3.Connection) -> None:
    version = int(connection.execute("PRAGMA user_version").fetchone()[0])
    if version == SCHEMA_VERSION:
        validate_schema(connection)
        return
    if version != 0 or user_tables(connection):
        raise HistoryError(
            f"unsupported or partial audit history schema version: {version}"
        )
    for statement in SCHEMA_STATEMENTS:
        connection.execute(statement)
    connection.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
    validate_schema(connection)


def database_size(connection: sqlite3.Connection) -> int:
    page_count = int(connection.execute("PRAGMA page_count").fetchone()[0])
    page_size = int(connection.execute("PRAGMA page_size").fetchone()[0])
    return page_count * page_size


def enforce_database_size(connection: sqlite3.Connection) -> None:
    if database_size(connection) > MAX_DATABASE_BYTES:
        raise HistoryError(
            f"audit history database exceeds {MAX_DATABASE_BYTES} bytes"
        )


def open_writable_database(database: Path) -> sqlite3.Connection:
    database.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    connection = sqlite3.connect(
        database, timeout=SQLITE_BUSY_TIMEOUT_MS / 1000, isolation_level=None
    )
    try:
        if os.name != "nt":
            database.chmod(0o600)
        configure_connection(connection)
        return connection
    except BaseException:
        connection.close()
        raise


def create_or_get_target(
    connection: sqlite3.Connection, request: dict[str, Any], now_text: str
) -> int:
    row = connection.execute(
        "SELECT id, identity_json FROM audit_targets WHERE identity_sha256 = ?",
        (request["identity_sha256"],),
    ).fetchone()
    if row is not None:
        if row["identity_json"] != request["identity_json"]:
            raise HistoryError("audit target identity hash collision")
        return int(row["id"])
    window: FixedWindow = request["window"]
    cursor = connection.execute(
        """
        INSERT INTO audit_targets (
          identity_sha256, identity_json, utc_start, utc_end, scope_sha256,
          focus_key, focus_question, focus_question_sha256, analysis_profile,
          analysis_contract_version, created_at_utc
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            request["identity_sha256"],
            request["identity_json"],
            iso_z(window.utc_start),
            iso_z(window.utc_end),
            request["scope_sha256"],
            request["focus_key"],
            request["focus_question"],
            request["focus_question_sha256"],
            ANALYSIS_PROFILE,
            ANALYSIS_CONTRACT_VERSION,
            now_text,
        ),
    )
    return int(cursor.lastrowid)


def decode_result(row: sqlite3.Row) -> dict[str, Any] | None:
    raw = row["result_json"]
    if raw is None:
        raise HistoryError("completed audit run has no stored result")
    raw_text = str(raw)
    raw_bytes = raw_text.encode("utf-8")
    if row["result_version"] != RESULT_VERSION:
        raise HistoryError("stored audit result has an unsupported version")
    if row["result_bytes"] != len(raw_bytes) or len(raw_bytes) > MAX_RESULT_BYTES:
        raise HistoryError("stored audit result size metadata is invalid")
    if row["result_sha256"] != sha256_text(raw_text):
        raise HistoryError("stored audit result digest is invalid")
    try:
        value = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise HistoryError("stored audit result is invalid JSON") from exc
    if not isinstance(value, dict):
        raise HistoryError("stored audit result is not an object")
    if value.get("result_version") != RESULT_VERSION:
        raise HistoryError("stored audit result payload has an unsupported version")
    submitted = dict(value)
    submitted.pop("result_version", None)
    validated = validate_result(submitted)
    if validated != value or canonical_json(validated) != raw_text:
        raise HistoryError("stored audit result is not canonical or valid")
    return validated


def project_run(row: sqlite3.Row, *, include_result: bool) -> dict[str, Any]:
    result = {
        "run_id": row["run_id"],
        "status": row["status"],
        "window_status": row["window_status"],
        "started_at_utc": row["started_at_utc"],
        "heartbeat_at_utc": row["heartbeat_at_utc"],
        "lease_expires_at_utc": row["lease_expires_at_utc"],
        "finished_at_utc": row["finished_at_utc"],
        "force_reason": row["force_reason"],
        "failure_code": row["failure_code"],
        "failure_summary": row["failure_summary"],
    }
    if include_result:
        result["result"] = decode_result(row)
    return result


RUN_COLUMNS = """
    r.run_id, r.status, r.window_status, r.started_at_utc,
    r.heartbeat_at_utc, r.lease_expires_at_utc, r.finished_at_utc,
    r.force_reason, r.result_version, r.result_json, r.result_sha256,
    r.result_bytes, r.failure_code, r.failure_summary
"""


def latest_completed(
    connection: sqlite3.Connection, target_id: int, *, reusable_only: bool
) -> sqlite3.Row | None:
    status_clause = "AND r.window_status = 'complete'" if reusable_only else ""
    return connection.execute(
        f"""
        SELECT {RUN_COLUMNS}
        FROM audit_runs r
        WHERE r.target_id = ? AND r.status = 'completed' {status_clause}
        ORDER BY r.finished_at_utc DESC, r.attempt_no DESC LIMIT 1
        """,
        (target_id,),
    ).fetchone()


def lookup_history(database: Path, raw_request: Any) -> dict[str, Any]:
    request = validate_target_request(raw_request, claim=False)
    window: FixedWindow = request["window"]
    result: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "analysis_profile": ANALYSIS_PROFILE,
        "analysis_contract_version": ANALYSIS_CONTRACT_VERSION,
        "fixed_window": {
            "timezone": window.timezone_name,
            "local_start": window.local_start.isoformat(),
            "local_end": window.local_end.isoformat(),
            "utc_start": iso_z(window.utc_start),
            "utc_end": iso_z(window.utc_end),
            "status": window.status,
        },
        "workspace": request["workspace"],
        "focus_key": request["focus_key"],
        "focus_question": request["focus_question"],
        "history_available": database.is_file(),
        "reusable_exact_match": None,
        "active_run": None,
        "same_window_related_questions": [],
        "latest_same_focus": [],
    }
    if not database.is_file():
        return result
    uri = database.resolve().as_uri() + "?mode=ro"
    connection = sqlite3.connect(
        uri, uri=True, timeout=SQLITE_BUSY_TIMEOUT_MS / 1000
    )
    try:
        configure_connection(connection)
        connection.execute("PRAGMA query_only=ON")
        validate_schema(connection)
        enforce_database_size(connection)
        target = connection.execute(
            "SELECT id FROM audit_targets WHERE identity_sha256 = ? AND identity_json = ?",
            (request["identity_sha256"], request["identity_json"]),
        ).fetchone()
        if target is not None:
            target_id = int(target["id"])
            completed = latest_completed(connection, target_id, reusable_only=True)
            if completed is not None and window.status == "complete":
                result["reusable_exact_match"] = project_run(
                    completed, include_result=True
                )
            active = connection.execute(
                (
                    f"SELECT {RUN_COLUMNS} FROM audit_runs r "
                    "WHERE r.target_id = ? AND r.status = 'in_progress'"
                ),
                (target_id,),
            ).fetchone()
            if active is not None:
                result["active_run"] = project_run(active, include_result=False)
        related = connection.execute(
            f"""
            SELECT t.focus_question, {RUN_COLUMNS}
            FROM audit_targets t
            JOIN audit_runs r ON r.target_id = t.id
            WHERE t.utc_start = ? AND t.utc_end = ? AND t.scope_sha256 = ?
              AND t.focus_key = ? AND t.focus_question_sha256 <> ?
              AND t.analysis_profile = ? AND t.analysis_contract_version = ?
              AND r.status = 'completed'
            ORDER BY r.finished_at_utc DESC LIMIT 10
            """,
            (
                iso_z(window.utc_start),
                iso_z(window.utc_end),
                request["scope_sha256"],
                request["focus_key"],
                request["focus_question_sha256"],
                ANALYSIS_PROFILE,
                ANALYSIS_CONTRACT_VERSION,
            ),
        ).fetchall()
        result["same_window_related_questions"] = [
            {
                "focus_question": row["focus_question"],
                "run": project_run(row, include_result=True),
            }
            for row in related
        ]
        latest = connection.execute(
            f"""
            SELECT t.utc_start, t.utc_end, t.focus_question, {RUN_COLUMNS}
            FROM audit_targets t
            JOIN audit_runs r ON r.target_id = t.id
            WHERE t.scope_sha256 = ? AND t.focus_key = ?
              AND t.analysis_profile = ? AND t.analysis_contract_version = ?
              AND r.status = 'completed'
            ORDER BY r.finished_at_utc DESC LIMIT 5
            """,
            (
                request["scope_sha256"],
                request["focus_key"],
                ANALYSIS_PROFILE,
                ANALYSIS_CONTRACT_VERSION,
            ),
        ).fetchall()
        result["latest_same_focus"] = [
            {
                "utc_start": row["utc_start"],
                "utc_end": row["utc_end"],
                "focus_question": row["focus_question"],
                "run": project_run(row, include_result=True),
            }
            for row in latest
        ]
    finally:
        connection.close()
    return result


def claim_history(database: Path, raw_request: Any) -> dict[str, Any]:
    request = validate_target_request(raw_request, claim=True)
    connection = open_writable_database(database)
    try:
        connection.execute("BEGIN IMMEDIATE")
        initialize_schema(connection)
        enforce_database_size(connection)
        now = utc_now()
        now_text = iso_z(now)
        lease_text = iso_z(now + timedelta(seconds=LEASE_SECONDS))
        target_id = create_or_get_target(connection, request, now_text)
        connection.execute(
            """
            UPDATE audit_runs SET status = 'abandoned', finished_at_utc = ?,
              failure_code = 'lease-expired', failure_summary = 'claim lease expired'
            WHERE target_id = ? AND status = 'in_progress'
              AND lease_expires_at_utc <= ?
            """,
            (now_text, target_id, now_text),
        )
        enforce_database_size(connection)
        existing_claim = connection.execute(
            """
            SELECT r.target_id, r.claim_key, r.status, r.run_id
            FROM audit_runs r WHERE r.claim_key = ?
            """,
            (request["claim_key"],),
        ).fetchone()
        if existing_claim is not None:
            if int(existing_claim["target_id"]) != target_id:
                raise HistoryError("claim_key already belongs to a different audit target")
            row = connection.execute(
                f"SELECT {RUN_COLUMNS} FROM audit_runs r WHERE r.run_id = ?",
                (existing_claim["run_id"],),
            ).fetchone()
            assert row is not None
            if row["status"] == "in_progress":
                action = "claimed"
            elif row["status"] == "completed" and row["window_status"] == "complete":
                action = "reuse"
            else:
                action = "terminal"
            connection.commit()
            return {
                "schema_version": SCHEMA_VERSION,
                "action": action,
                "idempotent_replay": True,
                "run": project_run(
                    row, include_result=row["status"] == "completed"
                ),
            }
        active = connection.execute(
            (
                f"SELECT {RUN_COLUMNS} FROM audit_runs r "
                "WHERE r.target_id = ? AND r.status = 'in_progress'"
            ),
            (target_id,),
        ).fetchone()
        if active is not None:
            connection.commit()
            return {
                "schema_version": SCHEMA_VERSION,
                "action": "busy",
                "idempotent_replay": False,
                "run": project_run(active, include_result=False),
            }
        completed = latest_completed(connection, target_id, reusable_only=True)
        if (
            completed is not None
            and request["window"].status == "complete"
            and request["force_reason"] is None
        ):
            connection.commit()
            return {
                "schema_version": SCHEMA_VERSION,
                "action": "reuse",
                "idempotent_replay": False,
                "run": project_run(completed, include_result=True),
            }
        attempt_no = int(
            connection.execute(
                "SELECT COALESCE(MAX(attempt_no), 0) + 1 FROM audit_runs WHERE target_id = ?",
                (target_id,),
            ).fetchone()[0]
        )
        run_id = "audit-" + sha256_text(request["claim_key"])[:32]
        connection.execute(
            """
            INSERT INTO audit_runs (
              run_id, target_id, claim_key, attempt_no, status, window_status,
              started_at_utc, heartbeat_at_utc, lease_expires_at_utc, force_reason
            ) VALUES (?, ?, ?, ?, 'in_progress', ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                target_id,
                request["claim_key"],
                attempt_no,
                request["window"].status,
                now_text,
                now_text,
                lease_text,
                request["force_reason"],
            ),
        )
        enforce_database_size(connection)
        row = connection.execute(
            f"SELECT {RUN_COLUMNS} FROM audit_runs r WHERE r.run_id = ?", (run_id,)
        ).fetchone()
        assert row is not None
        connection.commit()
        return {
            "schema_version": SCHEMA_VERSION,
            "action": "claimed",
            "idempotent_replay": False,
            "run": project_run(row, include_result=False),
        }
    except BaseException:
        if connection.in_transaction:
            connection.rollback()
        raise
    finally:
        connection.close()


def load_owned_run(
    connection: sqlite3.Connection, request: dict[str, Any]
) -> sqlite3.Row:
    row = connection.execute(
        "SELECT * FROM audit_runs WHERE run_id = ? AND claim_key = ?",
        (request["run_id"], request["claim_key"]),
    ).fetchone()
    if row is None:
        raise HistoryError("run_id and claim_key do not identify an audit run")
    return row


def update_run(database: Path, raw_request: Any, operation: str) -> dict[str, Any]:
    request = validate_run_request(raw_request, operation)
    connection = open_writable_database(database)
    try:
        connection.execute("BEGIN IMMEDIATE")
        validate_schema(connection)
        enforce_database_size(connection)
        now = utc_now()
        now_text = iso_z(now)
        row = load_owned_run(connection, request)
        if operation == "heartbeat":
            if row["status"] != "in_progress":
                raise HistoryError("only an in-progress run can be heartbeated")
            if row["lease_expires_at_utc"] <= now_text:
                connection.execute(
                    """
                    UPDATE audit_runs SET status = 'abandoned', finished_at_utc = ?,
                      failure_code = 'lease-expired',
                      failure_summary = 'claim lease expired'
                    WHERE run_id = ? AND status = 'in_progress'
                    """,
                    (now_text, request["run_id"]),
                )
                enforce_database_size(connection)
                connection.commit()
                raise HistoryError("claim lease expired before heartbeat")
            connection.execute(
                (
                    "UPDATE audit_runs "
                    "SET heartbeat_at_utc = ?, lease_expires_at_utc = ? "
                    "WHERE run_id = ?"
                ),
                (
                    now_text,
                    iso_z(now + timedelta(seconds=LEASE_SECONDS)),
                    request["run_id"],
                ),
            )
        elif operation == "complete":
            result_json = canonical_json(request["result"])
            result_bytes = len(result_json.encode("utf-8"))
            result_sha256 = sha256_text(result_json)
            if row["status"] == "completed":
                if row["result_sha256"] != result_sha256:
                    raise HistoryError(
                        "completed run already contains a different result"
                    )
                projection = project_run(row, include_result=True)
                connection.commit()
                return {
                    "schema_version": SCHEMA_VERSION,
                    "idempotent_replay": True,
                    "run": projection,
                }
            if row["status"] != "in_progress":
                raise HistoryError(
                    f"cannot complete a run in status {row['status']}"
                )
            connection.execute(
                """
                UPDATE audit_runs SET status = 'completed', finished_at_utc = ?,
                  heartbeat_at_utc = ?, result_version = ?, result_json = ?,
                  result_sha256 = ?, result_bytes = ? WHERE run_id = ?
                """,
                (
                    now_text,
                    now_text,
                    RESULT_VERSION,
                    result_json,
                    result_sha256,
                    result_bytes,
                    request["run_id"],
                ),
            )
        elif operation == "fail":
            if row["status"] == "failed":
                if (
                    row["failure_code"] != request["failure_code"]
                    or row["failure_summary"] != request["failure_summary"]
                ):
                    raise HistoryError("failed run already contains a different failure")
                projection = project_run(row, include_result=False)
                connection.commit()
                return {
                    "schema_version": SCHEMA_VERSION,
                    "idempotent_replay": True,
                    "run": projection,
                }
            if row["status"] != "in_progress":
                raise HistoryError(f"cannot fail a run in status {row['status']}")
            connection.execute(
                """
                UPDATE audit_runs SET status = 'failed', finished_at_utc = ?,
                  heartbeat_at_utc = ?, failure_code = ?, failure_summary = ?
                WHERE run_id = ?
                """,
                (
                    now_text,
                    now_text,
                    request["failure_code"],
                    request["failure_summary"],
                    request["run_id"],
                ),
            )
        enforce_database_size(connection)
        updated = connection.execute(
            f"SELECT {RUN_COLUMNS} FROM audit_runs r WHERE r.run_id = ?",
            (request["run_id"],),
        ).fetchone()
        assert updated is not None
        connection.commit()
        return {
            "schema_version": SCHEMA_VERSION,
            "idempotent_replay": False,
            "run": project_run(updated, include_result=operation == "complete"),
        }
    except BaseException:
        if connection.in_transaction:
            connection.rollback()
        raise
    finally:
        connection.close()


def read_request() -> Any:
    try:
        return json.load(sys.stdin)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise HistoryError("stdin must contain one valid JSON value") from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Lookup, claim, and finish bounded Codex work audit history."
    )
    parser.add_argument(
        "command", choices=("lookup", "claim", "heartbeat", "complete", "fail")
    )
    parser.add_argument("--database", type=Path, default=default_history_database())
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    if hasattr(sys.stdin, "reconfigure"):
        sys.stdin.reconfigure(encoding="utf-8")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    try:
        database = args.database.expanduser().resolve()
        request = read_request()
        if args.command == "lookup":
            result = lookup_history(database, request)
        elif args.command == "claim":
            result = claim_history(database, request)
        else:
            result = update_run(database, request, args.command)
    except (HistoryError, OSError, sqlite3.Error) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
