from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from unittest import mock


SCRIPT = Path(__file__).with_name("collect_session_evidence.py")
SPEC = importlib.util.spec_from_file_location("collect_session_evidence", SCRIPT)
assert SPEC and SPEC.loader
COLLECTOR = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = COLLECTOR
SPEC.loader.exec_module(COLLECTOR)


def sql_text(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


class CollectSessionEvidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        sqlite = shutil.which("sqlite3")
        if sqlite is None:
            self.fail("sqlite3 CLI is required for the collector contract tests")
        self.sqlite = sqlite
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.codex_home = self.root / "codex"
        self.workspace = self.root / "workspace"
        self.workspace.mkdir()
        self.database = self.root / "withmate-v6.db"
        self.local_timezone = COLLECTOR.resolve_timezone("Asia/Tokyo")
        self.start_date = datetime.now(self.local_timezone).date() - timedelta(days=2)
        self.local_start = datetime.combine(
            self.start_date, time(hour=18), tzinfo=self.local_timezone
        )
        self.local_end = self.local_start + timedelta(days=1)
        self.utc_start = self.local_start.astimezone(timezone.utc)
        self.utc_end = self.local_end.astimezone(timezone.utc)
        self.create_database()
        self.create_rollout()

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def create_database(self) -> None:
        workspace = sql_text(str(self.workspace))
        local_start = self.local_start
        utc_start = self.utc_start
        utc_end = self.utc_end
        slash_start = local_start.strftime("%Y/%m/%d %H:%M")
        slash_inside = (local_start + timedelta(hours=9)).strftime("%Y/%m/%d %H:%M")
        slash_turn_start = (local_start + timedelta(hours=10)).strftime("%Y/%m/%d %H:%M")
        slash_turn_end = (local_start + timedelta(hours=10, minutes=5)).strftime(
            "%Y/%m/%d %H:%M"
        )
        offset_inside = (local_start + timedelta(hours=9, minutes=15)).isoformat()
        positive_offset_without_seconds = (
            (utc_start + timedelta(hours=2))
            .astimezone(timezone(timedelta(hours=5, minutes=30)))
            .isoformat(timespec="minutes")
        )
        negative_offset_without_seconds = (
            (utc_start + timedelta(hours=3))
            .astimezone(timezone(timedelta(hours=-5)))
            .isoformat(timespec="minutes")
        )
        naive_space_inside = (local_start + timedelta(hours=9, minutes=20)).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        utc_overlap_start = (utc_start - timedelta(hours=1)).isoformat().replace("+00:00", "Z")
        utc_overlap_end = (utc_start + timedelta(hours=1)).isoformat().replace("+00:00", "Z")
        utc_interim = (utc_start + timedelta(minutes=10)).isoformat().replace("+00:00", "Z")
        utc_output = (utc_start + timedelta(minutes=30)).isoformat().replace("+00:00", "Z")
        utc_usage = (utc_start + timedelta(minutes=31)).isoformat().replace("+00:00", "Z")
        utc_audit = (utc_start + timedelta(minutes=40)).isoformat().replace("+00:00", "Z")
        end_excluded = self.local_end
        schema = f"""
        CREATE TABLE sessions_v6 (
          id TEXT PRIMARY KEY, title TEXT NOT NULL, state TEXT NOT NULL,
          thread_id TEXT NOT NULL, workspace_path TEXT NOT NULL
        );
        CREATE TABLE session_messages_v6 (
          session_id TEXT NOT NULL, seq INTEGER NOT NULL, role TEXT NOT NULL,
          body TEXT NOT NULL, created_at TEXT NOT NULL
        );
        CREATE TABLE session_turns_v6 (
          id INTEGER PRIMARY KEY, session_id TEXT, phase TEXT NOT NULL,
          summary TEXT NOT NULL, error_summary TEXT NOT NULL,
          started_at TEXT NOT NULL, completed_at TEXT, updated_at TEXT NOT NULL
        );
        CREATE TABLE session_turn_interims_v6 (
          turn_id INTEGER NOT NULL, seq INTEGER NOT NULL, body TEXT NOT NULL,
          created_at TEXT NOT NULL
        );
        CREATE TABLE session_turn_provider_outputs_v6 (
          turn_id INTEGER NOT NULL, seq INTEGER NOT NULL, kind TEXT NOT NULL,
          summary TEXT NOT NULL, payload_json TEXT NOT NULL, created_at TEXT NOT NULL
        );
        CREATE TABLE audit_events_v6 (
          session_id TEXT, event_type TEXT NOT NULL, summary TEXT NOT NULL,
          created_at TEXT NOT NULL
        );
        INSERT INTO sessions_v6 VALUES
          ('launch-1','fixture','completed','native-1',{workspace});
        INSERT INTO session_messages_v6 VALUES
          ('launch-1',1,'user','{{"role":"user","text":"# Character Definition Snapshot\\nCharacter: Fixture\\nDescription: Fixture\\n# User Input\\nDB included"}}','{slash_start}'),
          ('launch-1',2,'assistant','DB end excluded','{end_excluded.strftime("%Y/%m/%d %H:%M")}'),
          ('launch-1',3,'user','Offset ISO included','{offset_inside}'),
          ('launch-1',4,'user','Legitimate body with # User Input marker','{slash_inside}'),
          ('launch-1',5,'assistant','Same-source repeat','{slash_inside}:01'),
          ('launch-1',6,'assistant','Same-source repeat','{slash_inside}:02'),
          ('launch-1',7,'user','Naive space ISO included','{naive_space_inside}'),
          ('launch-1',8,'user','Positive offset without seconds included','{positive_offset_without_seconds}'),
          ('launch-1',9,'user','Negative offset without seconds included','{negative_offset_without_seconds}');
        INSERT INTO session_turns_v6 VALUES
          (1,'launch-1','completed','overlap','','{utc_overlap_start}','{utc_overlap_end}','{utc_overlap_end}'),
          (2,'launch-1','completed','slash turn','','{slash_turn_start}','{slash_turn_end}','{slash_turn_end}');
        INSERT INTO session_turn_interims_v6 VALUES
          (1,0,'progress','{utc_interim}');
        INSERT INTO session_turn_provider_outputs_v6 VALUES
          (1,0,'operation','', '{{"value":{{"type":"command_execution","summary":"tests passed"}}}}','{utc_output}'),
          (1,1,'usage','usage', '{{"value":{{"tokens":999}}}}','{utc_usage}');
        INSERT INTO audit_events_v6 VALUES
          ('launch-1','diagnostic','diagnostic event','{utc_audit}');
        """
        result = subprocess.run(
            [self.sqlite, str(self.database)],
            input=schema,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def create_rollout(self) -> None:
        path_date = self.utc_start.date()
        directory = (
            self.codex_home
            / "sessions"
            / f"{path_date:%Y}"
            / f"{path_date:%m}"
            / f"{path_date:%d}"
        )
        directory.mkdir(parents=True)
        self.rollout = directory / "rollout-fixture.jsonl"
        records = [
            {
                "timestamp": (self.utc_start - timedelta(hours=1)).isoformat(),
                "type": "session_meta",
                "payload": {"id": "native-1", "cwd": str(self.workspace)},
            },
            {
                "timestamp": self.utc_start.isoformat(),
                "type": "event_msg",
                "payload": {
                    "type": "user_message",
                    "message": "# Character Definition Snapshot\nCharacter: Fixture\nDescription: Fixture\n# User Input\nRollout boundary included",
                },
            },
            {
                "timestamp": (self.utc_start + timedelta(minutes=20)).isoformat(),
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "call_id": "call-1",
                    "name": "exec_command",
                    "arguments": json.dumps({"cmd": "python -m unittest"}),
                },
            },
            {
                "timestamp": (self.utc_start + timedelta(minutes=21)).isoformat(),
                "type": "event_msg",
                "payload": {"type": "token_count", "tokens": 999},
            },
            {
                "timestamp": (self.utc_start + timedelta(minutes=22)).isoformat(),
                "type": "response_item",
                "payload": {
                    "type": "function_call_output",
                    "call_id": "call-1",
                    "output": json.dumps({"exit_code": 0, "status": "completed"}),
                },
            },
            {
                "timestamp": (self.utc_start + timedelta(hours=9, seconds=1)).isoformat(),
                "type": "event_msg",
                "payload": {"type": "agent_message", "message": "Same-source repeat"},
            },
            {
                "timestamp": self.utc_end.isoformat(),
                "type": "event_msg",
                "payload": {"type": "agent_message", "message": "End excluded"},
            },
        ]
        self.rollout.write_text(
            "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records),
            encoding="utf-8",
        )
        os.utime(
            self.rollout,
            (
                (self.utc_start - timedelta(days=2)).timestamp(),
                (self.utc_start - timedelta(days=2)).timestamp(),
            ),
        )

    def run_collector_process(
        self,
        *extra: str,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> subprocess.CompletedProcess[str]:
        selected_start = start or self.local_start
        selected_end = end or self.local_end
        return subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--start",
                selected_start.replace(tzinfo=None).isoformat(timespec="microseconds"),
                "--end",
                selected_end.replace(tzinfo=None).isoformat(timespec="microseconds"),
                "--timezone",
                "Asia/Tokyo",
                "--withmate-db",
                str(self.database),
                "--codex-home",
                str(self.codex_home),
                *extra,
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )

    def run_collector(
        self,
        *extra: str,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> dict:
        result = self.run_collector_process(*extra, start=start, end=end)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_fixed_half_open_interval_crosses_midnight_and_excludes_usage(self) -> None:
        before = (self.database.stat().st_mtime_ns, self.database.stat().st_size)
        result = self.run_collector("--workspace", str(self.workspace), "--detail")
        after = (self.database.stat().st_mtime_ns, self.database.stat().st_size)

        self.assertEqual(before, after)
        self.assertEqual(result["schema_version"], 3)
        self.assertEqual(result["fixed_window"]["local_start"], self.local_start.isoformat())
        self.assertEqual(result["fixed_window"]["local_end"], self.local_end.isoformat())
        self.assertEqual(result["fixed_window"]["utc_start"], COLLECTOR.iso_z(self.utc_start))
        self.assertEqual(result["fixed_window"]["utc_end"], COLLECTOR.iso_z(self.utc_end))
        self.assertEqual(result["fixed_window"]["status"], "complete")
        self.assertEqual(result["session_count"], 1)
        session = result["sessions"][0]
        self.assertEqual(session["session_id"], "native-1")
        self.assertEqual(session["sources"], ["codex-rollout", "withmate-v6"])
        texts = [
            event["content"]["text"]
            for event in session["events"]
            if "content" in event
        ]
        self.assertIn("DB included", texts)
        self.assertIn("Offset ISO included", texts)
        self.assertIn("Positive offset without seconds included", texts)
        self.assertIn("Negative offset without seconds included", texts)
        self.assertIn("Naive space ISO included", texts)
        self.assertIn("Legitimate body with # User Input marker", texts)
        self.assertEqual(texts.count("Same-source repeat"), 2)
        self.assertIn("Rollout boundary included", texts)
        self.assertNotIn("DB end excluded", texts)
        self.assertNotIn("End excluded", texts)
        self.assertFalse(any("Character Definition Snapshot" in text for text in texts))
        self.assertFalse(any("token" in event["kind"] for event in session["events"]))
        self.assertEqual(result["source_counts"]["withmate"]["provider_outputs"], 1)
        self.assertEqual(
            result["source_counts"]["codex_rollouts"]["excluded_event_counts"][
                "event_msg:token_count"
            ],
            1,
        )
        self.assertEqual(result["source_counts"]["codex_rollouts"]["candidate_files"], 1)
        self.assertTrue(any(event["kind"] == "turn_overlap" for event in session["events"]))
        self.assertEqual(
            sum(event["kind"] == "turn_started" for event in session["events"]), 1
        )
        self.assertTrue(any(event["kind"] == "tool_call" for event in session["events"]))
        self.assertTrue(any(event["kind"] == "tool_result" for event in session["events"]))
        command_execution = next(
            event for event in session["events"] if event["kind"] == "command_execution"
        )
        self.assertEqual(
            command_execution["metadata"]["failure_status"], "unknown"
        )
        self.assertEqual(session["unknown_failure_status_events"], 1)
        self.assertEqual(session["unknown_failure_status_omitted"], 0)
        merged_repeat = next(
            event
            for event in session["events"]
            if event.get("content", {}).get("text") == "Same-source repeat"
            and len(event.get("sources", [])) == 2
        )
        self.assertEqual(merged_repeat["sources"], ["codex-rollout", "withmate-v6"])
        self.assertEqual(result["truncation"]["deduplicated_messages"], 1)

    def test_session_filter_reports_missing_id_as_gap(self) -> None:
        result = self.run_collector("--session-id", "missing")
        self.assertEqual(result["session_count"], 0)
        self.assertIn("requested session IDs not found", result["data_gaps"][0])

    def test_interval_status_ordering_and_historical_scope(self) -> None:
        now = datetime.fromisoformat("2026-08-02T02:00:00+09:00")
        partial = COLLECTOR.build_window(
            "2026-08-01T20:00", "2026-08-02T04:00", "Asia/Tokyo", now=now
        )
        self.assertEqual(partial.status, "partial")
        complete = COLLECTOR.build_window(
            "2026-07-30T20:00", "2026-07-31T04:00", "Asia/Tokyo", now=now
        )
        self.assertEqual(complete.status, "complete")
        with self.assertRaises(COLLECTOR.CollectorError):
            COLLECTOR.build_window(
                "2026-08-02T03:00", "2026-08-02T04:00", "Asia/Tokyo", now=now
            )
        with self.assertRaises(COLLECTOR.CollectorError):
            COLLECTOR.build_window(
                "2026-08-01T20:00", "2026-08-01T20:00", "Asia/Tokyo", now=now
            )

    def test_interval_boundaries_require_offsetless_local_datetimes(self) -> None:
        now = datetime.fromisoformat("2026-08-02T02:00:00+09:00")
        for invalid in (
            "2026-08-01",
            "2026-08-01 20:00",
            "2026-08-01T20:00+09:00",
            "2026-08-01T20:00:00.1234567",
        ):
            with self.subTest(invalid=invalid):
                with self.assertRaises(COLLECTOR.CollectorError):
                    COLLECTOR.build_window(
                        invalid, "2026-08-02T01:00", "Asia/Tokyo", now=now
                    )
        with self.assertRaises(COLLECTOR.CollectorError):
            COLLECTOR.resolve_timezone("../UTC")

    def test_dst_ambiguous_and_nonexistent_local_datetimes_are_rejected(self) -> None:
        try:
            eastern = COLLECTOR.resolve_timezone("America/New_York")
        except COLLECTOR.CollectorError:
            self.skipTest("host timezone data does not include America/New_York")

        for value in ("2026-03-08T02:30", "2026-11-01T01:30"):
            with self.subTest(value=value):
                with self.assertRaises(COLLECTOR.CollectorError):
                    COLLECTOR.parse_local_boundary(value, "--start", eastern)
                with self.assertRaises(ValueError):
                    COLLECTOR.parse_timestamp(value, slash_timezone=eastern)

    def test_subsecond_interval_boundaries_are_filtered_exactly(self) -> None:
        start = self.local_start + timedelta(seconds=30, microseconds=500_000)
        end = start + timedelta(seconds=1)
        values = [
            (20, "before", start - timedelta(microseconds=1)),
            (21, "start included", start),
            (22, "inside included", start + timedelta(microseconds=1)),
            (23, "end excluded", end),
        ]
        rows = ",\n".join(
            "('launch-1',"
            f"{seq},'user','{body}','{occurred.strftime('%Y/%m/%d %H:%M:%S.%f')}')"
            for seq, body, occurred in values
        )
        inserted = subprocess.run(
            [self.sqlite, str(self.database)],
            input=f"INSERT INTO session_messages_v6 VALUES {rows};",
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        self.assertEqual(inserted.returncode, 0, inserted.stderr)

        result = self.run_collector(
            "--workspace", str(self.workspace), "--detail", start=start, end=end
        )
        texts = [
            event["content"]["text"]
            for event in result["sessions"][0]["events"]
            if "content" in event
        ]
        self.assertIn("start included", texts)
        self.assertIn("inside included", texts)
        self.assertNotIn("before", texts)
        self.assertNotIn("end excluded", texts)

    def test_character_headings_without_snapshot_envelope_are_preserved(self) -> None:
        text = (
            "# Character Definition Snapshot\n"
            "This is a document example, not an injected envelope.\n"
            "# User Input\n"
            "Keep the complete text."
        )
        self.assertEqual(COLLECTOR.normalize_user_text(text), text)

    def test_user_text_preserves_leading_and_trailing_whitespace(self) -> None:
        literal = "  keep leading\nkeep trailing  \n"
        self.assertEqual(COLLECTOR.normalize_user_text(literal), literal)

        wrapped = (
            "# Character Definition Snapshot\n"
            "Character: Fixture\n"
            "Description: Fixture\n"
            "# User Input\n"
            "  keep leading\nkeep trailing  \n"
        )
        self.assertEqual(
            COLLECTOR.normalize_user_text(wrapped),
            "  keep leading\nkeep trailing  \n",
        )

    def test_literal_json_is_not_unwrapped_as_a_message_envelope(self) -> None:
        literal = json.dumps(
            {"text": "literal user data", "other": 1},
            ensure_ascii=False,
            separators=(",", ":"),
        )
        wrapped = json.dumps(
            {"role": "user", "text": literal},
            ensure_ascii=False,
            separators=(",", ":"),
        )

        self.assertEqual(COLLECTOR.normalize_user_text(literal), literal)
        self.assertEqual(
            COLLECTOR.normalize_user_text(
                COLLECTOR.unwrap_withmate_message(wrapped, "user")
            ),
            literal,
        )
        self.assertEqual(
            COLLECTOR.unwrap_withmate_message(literal, "user"),
            literal,
        )
        assistant_wrapped = json.dumps(
            {"role": "assistant", "text": "answer", "artifact": {"kind": "none"}}
        )
        self.assertEqual(
            COLLECTOR.unwrap_withmate_message(assistant_wrapped, "assistant"),
            "answer",
        )
        assistant_literal = json.dumps(
            {"role": "assistant", "text": "keep whole object", "other": 1}
        )
        self.assertEqual(
            COLLECTOR.unwrap_withmate_message(assistant_literal, "assistant"),
            assistant_literal,
        )

    def test_explicit_zero_limit_is_rejected(self) -> None:
        result = self.run_collector_process("--detail", "--max-events", "0")
        self.assertEqual(result.returncode, 2)
        self.assertIn("--max-events must be greater than zero", result.stderr)

    def test_index_mode_rejects_detail_event_limits(self) -> None:
        result = self.run_collector_process("--max-events", "1")
        self.assertEqual(result.returncode, 2)
        self.assertIn("require --detail", result.stderr)

    def test_aggregate_output_limit_is_exact_across_sessions(self) -> None:
        malformed = self.rollout.with_name("rollout-uncertain-tail.jsonl")
        records = [
            {
                "timestamp": self.utc_start.isoformat(),
                "type": "session_meta",
                "payload": {"id": "native-2", "cwd": str(self.workspace)},
            },
            {
                "timestamp": (self.utc_start + timedelta(minutes=1)).isoformat(),
                "type": "event_msg",
                "payload": {"type": "user_message", "message": "uncertain tail included"},
            },
        ]
        malformed.write_text(
            "".join(json.dumps(record) + "\n" for record in records) + "{broken\n",
            encoding="utf-8",
        )

        result = self.run_collector("--detail", "--max-events", "1")

        self.assertEqual(sum(len(session["events"]) for session in result["sessions"]), 1)
        self.assertEqual(result["source_counts"]["codex_rollouts"]["candidate_files"], 2)
        self.assertEqual(
            result["source_counts"]["codex_rollouts"]["uncertain_tail_files_included"],
            1,
        )
        self.assertGreater(result["truncation"]["omitted_events"], 0)

    def test_discovery_and_byte_limits_fail_closed(self) -> None:
        byte_result = self.run_collector_process("--max-rollout-bytes", "1")
        self.assertEqual(byte_result.returncode, 2)
        self.assertIn("rollout candidate bytes exceed", byte_result.stderr)

        self.rollout.with_name("rollout-second.jsonl").write_text(
            self.rollout.read_text(encoding="utf-8"), encoding="utf-8"
        )
        file_result = self.run_collector_process("--max-rollout-files", "1")
        self.assertEqual(file_result.returncode, 2)
        self.assertIn("rollout discovery exceeded", file_result.stderr)

    def test_database_and_collection_budgets_fail_closed(self) -> None:
        row_result = self.run_collector_process("--max-database-rows", "1")
        self.assertEqual(row_result.returncode, 2)
        self.assertIn(
            "naive timestamp domain preflight exceeded --max-database-rows",
            row_result.stderr,
        )

        event_result = self.run_collector_process("--max-collected-events", "1")
        self.assertEqual(event_result.returncode, 2)
        self.assertIn("--max-collected-events exceeded", event_result.stderr)

        tail_result = self.run_collector_process("--max-tail-probe-bytes", "1")
        self.assertEqual(tail_result.returncode, 0, tail_result.stderr)
        tail_payload = json.loads(tail_result.stdout)
        self.assertLessEqual(
            tail_payload["source_counts"]["codex_rollouts"]["tail_probe_bytes"], 1
        )
        self.assertEqual(
            tail_payload["source_counts"]["codex_rollouts"][
                "uncertain_tail_files_included"
            ],
            1,
        )

        huge_body_result = subprocess.run(
            [self.sqlite, str(self.database)],
            input=(
                "UPDATE session_messages_v6 SET body=hex(zeroblob(10000)) "
                "WHERE seq=1;"
            ),
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        self.assertEqual(huge_body_result.returncode, 0, huge_body_result.stderr)
        byte_result = self.run_collector_process("--max-database-bytes", "4096")
        self.assertEqual(byte_result.returncode, 2)
        self.assertIn(
            "SQLite output exceeded --max-database-bytes", byte_result.stderr
        )

    def test_sqlite_worker_io_faults_fail_closed(self) -> None:
        class FakeStream:
            def __init__(self, failure: str | None = None) -> None:
                self.failure = failure
                self.closed = False

            def write(self, value: bytes) -> int:
                if self.failure == "write":
                    raise OSError(22, "write failed")
                return len(value)

            def flush(self) -> None:
                return None

            def read(self, size: int = -1) -> bytes:
                if self.failure == "read":
                    raise OSError(5, "read failed")
                return b""

            def close(self) -> None:
                self.closed = True

        class FakeProcess:
            def __init__(self, channel: str) -> None:
                self.stdin = FakeStream("write" if channel == "stdin" else None)
                self.stdout = FakeStream("read" if channel == "stdout" else None)
                self.stderr = FakeStream("read" if channel == "stderr" else None)
                self.killed = False

            def wait(self, timeout: float | None = None) -> int:
                return 0

            def kill(self) -> None:
                self.killed = True

        for channel in ("stdin", "stdout", "stderr"):
            with self.subTest(channel=channel):
                process = FakeProcess(channel)
                with mock.patch.object(
                    COLLECTOR.subprocess, "Popen", return_value=process
                ):
                    with self.assertRaisesRegex(
                        COLLECTOR.CollectorError, f"SQLite {channel} I/O failed"
                    ):
                        COLLECTOR.run_sqlite_json(
                            self.sqlite,
                            self.database,
                            "SELECT 1;",
                            COLLECTOR.CountBudget("test bytes", 1024),
                        )
                self.assertTrue(process.killed)

    def test_sqlite_nonterminating_workers_fail_closed(self) -> None:
        class FakeStream:
            closed = False

            def close(self) -> None:
                self.closed = True

        class FakeProcess:
            def __init__(self) -> None:
                self.stdin = FakeStream()
                self.stdout = FakeStream()
                self.stderr = FakeStream()

            def wait(self, timeout: float | None = None) -> int:
                return 0

            def kill(self) -> None:
                return None

        class StuckThread:
            def __init__(self, *args: object, **kwargs: object) -> None:
                return None

            def start(self) -> None:
                return None

            def join(self, timeout: float | None = None) -> None:
                return None

            def is_alive(self) -> bool:
                return True

        with mock.patch.object(COLLECTOR.subprocess, "Popen", return_value=FakeProcess()):
            with mock.patch.object(COLLECTOR.threading, "Thread", StuckThread):
                with self.assertRaisesRegex(
                    COLLECTOR.CollectorError,
                    "SQLite I/O worker did not terminate",
                ):
                    COLLECTOR.run_sqlite_json(
                        self.sqlite,
                        self.database,
                        "SELECT 1;",
                        COLLECTOR.CountBudget("test bytes", 1024),
                    )

    def test_sqlite_timeout_terminates_before_failing(self) -> None:
        class EmptyStream:
            closed = False

            def write(self, value: bytes) -> int:
                return len(value)

            def flush(self) -> None:
                return None

            def read(self, size: int = -1) -> bytes:
                return b""

            def close(self) -> None:
                self.closed = True

        class TimeoutProcess:
            def __init__(self) -> None:
                self.stdin = EmptyStream()
                self.stdout = EmptyStream()
                self.stderr = EmptyStream()
                self.killed = False

            def wait(self, timeout: float | None = None) -> int:
                if timeout is not None and not self.killed:
                    raise subprocess.TimeoutExpired("sqlite3", timeout)
                return -9

            def kill(self) -> None:
                self.killed = True

        process = TimeoutProcess()
        with mock.patch.object(COLLECTOR.subprocess, "Popen", return_value=process):
            with self.assertRaisesRegex(
                COLLECTOR.CollectorError, "read-only SQLite query timed out"
            ):
                COLLECTOR.run_sqlite_json(
                    self.sqlite,
                    self.database,
                    "SELECT 1;",
                    COLLECTOR.CountBudget("test bytes", 1024),
                )
        self.assertTrue(process.killed)

    def test_sqlite_timeout_has_bounded_post_kill_wait(self) -> None:
        class EmptyStream:
            def write(self, value: bytes) -> int:
                return len(value)

            def flush(self) -> None:
                return None

            def read(self, size: int = -1) -> bytes:
                return b""

            def close(self) -> None:
                return None

        class NonterminatingProcess:
            def __init__(self) -> None:
                self.stdin = EmptyStream()
                self.stdout = EmptyStream()
                self.stderr = EmptyStream()
                self.killed = False
                self.wait_timeouts: list[float | None] = []

            def wait(self, timeout: float | None = None) -> int:
                self.wait_timeouts.append(timeout)
                raise subprocess.TimeoutExpired("sqlite3", timeout)

            def kill(self) -> None:
                self.killed = True

        process = NonterminatingProcess()
        with mock.patch.object(COLLECTOR.subprocess, "Popen", return_value=process):
            with self.assertRaisesRegex(
                COLLECTOR.CollectorError,
                "SQLite process did not terminate after query timeout",
            ):
                COLLECTOR.run_sqlite_json(
                    self.sqlite,
                    self.database,
                    "SELECT 1;",
                    COLLECTOR.CountBudget("test bytes", 1024),
                )

        self.assertTrue(process.killed)
        self.assertEqual(
            process.wait_timeouts,
            [
                COLLECTOR.SQLITE_QUERY_TIMEOUT_SECONDS,
                COLLECTOR.SQLITE_POST_KILL_WAIT_SECONDS,
            ],
        )

    def test_sqlite_timeout_discloses_kill_failure(self) -> None:
        class EmptyStream:
            def write(self, value: bytes) -> int:
                return len(value)

            def flush(self) -> None:
                return None

            def read(self, size: int = -1) -> bytes:
                return b""

            def close(self) -> None:
                return None

        class UnkillableProcess:
            def __init__(self) -> None:
                self.stdin = EmptyStream()
                self.stdout = EmptyStream()
                self.stderr = EmptyStream()

            def wait(self, timeout: float | None = None) -> int:
                raise subprocess.TimeoutExpired("sqlite3", timeout)

            def kill(self) -> None:
                raise OSError(5, "kill denied")

        with mock.patch.object(
            COLLECTOR.subprocess, "Popen", return_value=UnkillableProcess()
        ):
            with self.assertRaisesRegex(
                COLLECTOR.CollectorError,
                "process kill failed:.*kill denied",
            ):
                COLLECTOR.run_sqlite_json(
                    self.sqlite,
                    self.database,
                    "SELECT 1;",
                    COLLECTOR.CountBudget("test bytes", 1024),
                )

    def test_sqlite_timeout_discloses_kill_failure_when_process_then_exits(self) -> None:
        class EmptyStream:
            def write(self, value: bytes) -> int:
                return len(value)

            def flush(self) -> None:
                return None

            def read(self, size: int = -1) -> bytes:
                return b""

            def close(self) -> None:
                return None

        class ExitRaceProcess:
            def __init__(self) -> None:
                self.stdin = EmptyStream()
                self.stdout = EmptyStream()
                self.stderr = EmptyStream()
                self.wait_count = 0

            def wait(self, timeout: float | None = None) -> int:
                self.wait_count += 1
                if self.wait_count == 1:
                    raise subprocess.TimeoutExpired("sqlite3", timeout)
                return 0

            def kill(self) -> None:
                raise OSError(5, "kill denied during exit race")

        process = ExitRaceProcess()
        with mock.patch.object(COLLECTOR.subprocess, "Popen", return_value=process):
            with self.assertRaisesRegex(
                COLLECTOR.CollectorError,
                "read-only SQLite query timed out; process kill failed:.*exit race",
            ):
                COLLECTOR.run_sqlite_json(
                    self.sqlite,
                    self.database,
                    "SELECT 1;",
                    COLLECTOR.CountBudget("test bytes", 1024),
                )

        self.assertEqual(process.wait_count, 2)

    def test_known_failures_remain_classified_from_both_sources(self) -> None:
        provider_timestamp = (
            self.utc_start + timedelta(minutes=45)
        ).isoformat().replace("+00:00", "Z")
        provider_payload = sql_text(
            json.dumps(
                {
                    "value": {
                        "type": "rate_limit",
                        "message": "provider failed PROVIDER_SECRET_SENTINEL",
                        "private": "DO_NOT_EXPOSE",
                    }
                },
                ensure_ascii=False,
                separators=(",", ":"),
            )
        )
        inserted = subprocess.run(
            [self.sqlite, str(self.database)],
            input=(
                "INSERT INTO session_turn_provider_outputs_v6 VALUES "
                f"(1,2,'provider_error','provider failed',{provider_payload},"
                f"'{provider_timestamp}');"
            ),
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        self.assertEqual(inserted.returncode, 0, inserted.stderr)

        with self.rollout.open("a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(
                    {
                        "timestamp": (
                            self.utc_start + timedelta(minutes=46)
                        ).isoformat(),
                        "type": "event_msg",
                        "payload": {
                            "type": "error",
                            "message": "rollout failed ROLLOUT_SECRET_SENTINEL",
                            "turn_id": {"private": "TURN_ID_SECRET_SENTINEL"},
                            "duration_ms": "DURATION_SECRET_SENTINEL",
                            "status": "STATUS_SECRET_SENTINEL",
                        },
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )

        collected = self.run_collector("--workspace", str(self.workspace))
        detail = self.run_collector(
            "--workspace", str(self.workspace), "--detail"
        )
        events = detail["sessions"][0]["events"]
        provider_error = next(
            event for event in events if event["kind"] == "provider_error"
        )
        rollout_error = next(event for event in events if event["kind"] == "error")

        self.assertEqual(
            provider_error["metadata"]["operation_type"], "rate_limit"
        )
        self.assertNotIn("content", provider_error)
        self.assertEqual(
            set(provider_error["metadata"]["error_evidence"]),
            {"original_chars", "sha256"},
        )
        self.assertTrue(COLLECTOR.known_failure_event(provider_error))
        self.assertNotIn("content", rollout_error)
        self.assertEqual(
            set(rollout_error["metadata"]["error_evidence"]),
            {"original_chars", "sha256"},
        )
        self.assertTrue(COLLECTOR.known_failure_event(rollout_error))
        failure_counts = collected["sessions"][0]["session_index"][
            "known_failure_kind_counts"
        ]
        self.assertEqual(failure_counts["provider_error"], 1)
        self.assertEqual(failure_counts["error"], 1)
        for projection in (collected, detail):
            serialized = json.dumps(projection, ensure_ascii=False)
            self.assertNotIn("DO_NOT_EXPOSE", serialized)
            self.assertNotIn("PROVIDER_SECRET_SENTINEL", serialized)
            self.assertNotIn("ROLLOUT_SECRET_SENTINEL", serialized)
            self.assertNotIn("TURN_ID_SECRET_SENTINEL", serialized)
            self.assertNotIn("DURATION_SECRET_SENTINEL", serialized)
            self.assertNotIn("STATUS_SECRET_SENTINEL", serialized)

    def test_non_error_rollout_event_metadata_uses_safe_projection(self) -> None:
        with self.rollout.open("a", encoding="utf-8") as handle:
            for offset, payload in enumerate(
                (
                    {
                        "type": "patch_apply_end",
                        "turn_id": "turn-safe-123",
                        "duration_ms": 42,
                        "status": "SUCCESS",
                    },
                    {
                        "type": "web_search_end",
                        "turn_id": {"private": "TURN_ID_SECRET_SENTINEL"},
                        "duration_ms": "DURATION_SECRET_SENTINEL",
                        "status": {"private": "STATUS_SECRET_SENTINEL"},
                    },
                    {
                        "type": "task_complete",
                        "turn_id": "failed-turn",
                        "duration_ms": 84,
                        "status": "failed",
                    },
                )
            ):
                handle.write(
                    json.dumps(
                        {
                            "timestamp": (
                                self.utc_start
                                + timedelta(minutes=48, seconds=offset)
                            ).isoformat(),
                            "type": "event_msg",
                            "payload": payload,
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )

        detail = self.run_collector(
            "--workspace", str(self.workspace), "--detail"
        )
        events = detail["sessions"][0]["events"]
        valid = next(event for event in events if event["kind"] == "patch_apply_end")
        malformed = next(
            event for event in events if event["kind"] == "web_search_end"
        )
        failed = next(event for event in events if event["kind"] == "task_complete")

        self.assertEqual(valid["metadata"]["duration_ms"], 42)
        self.assertEqual(valid["metadata"]["status"], "success")
        self.assertEqual(
            set(valid["metadata"]["turn_id_evidence"]),
            {"original_chars", "sha256"},
        )
        self.assertNotIn("turn_id", valid["metadata"])
        self.assertNotIn("metadata", malformed)
        self.assertEqual(failed["metadata"]["status"], "failed")
        self.assertEqual(
            failed["metadata"]["failure_status"], "known-failure"
        )
        self.assertTrue(COLLECTOR.known_failure_event(failed))
        serialized = json.dumps(detail, ensure_ascii=False)
        self.assertNotIn("turn-safe-123", serialized)
        self.assertNotIn("TURN_ID_SECRET_SENTINEL", serialized)
        self.assertNotIn("DURATION_SECRET_SENTINEL", serialized)
        self.assertNotIn("STATUS_SECRET_SENTINEL", serialized)

        index = self.run_collector("--workspace", str(self.workspace))
        self.assertEqual(
            index["sessions"][0]["session_index"]["known_failure_kind_counts"][
                "task_complete"
            ],
            1,
        )

        per_session_cap = self.run_collector(
            "--workspace",
            str(self.workspace),
            "--detail",
            "--max-events-per-session",
            "1",
            "--max-events",
            "10",
        )
        self.assertEqual(
            [event["kind"] for event in per_session_cap["sessions"][0]["events"]],
            ["task_complete"],
        )

        global_cap = self.run_collector(
            "--workspace",
            str(self.workspace),
            "--detail",
            "--max-events-per-session",
            "1200",
            "--max-events",
            "1",
        )
        self.assertEqual(
            [event["kind"] for event in global_cap["sessions"][0]["events"]],
            ["task_complete"],
        )

    def test_turn_error_summary_is_known_failure_from_source(self) -> None:
        secret = "turn failed TURN_ERROR_SECRET_SENTINEL"
        updated = subprocess.run(
            [self.sqlite, str(self.database)],
            input=(
                f"UPDATE session_turns_v6 SET error_summary='{secret}' "
                "WHERE id=1;"
            ),
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        self.assertEqual(updated.returncode, 0, updated.stderr)

        index = self.run_collector("--workspace", str(self.workspace))
        detail = self.run_collector(
            "--workspace", str(self.workspace), "--detail"
        )
        turn_failure = next(
            event
            for event in detail["sessions"][0]["events"]
            if event.get("metadata", {}).get("failure_status") == "known-failure"
            and event["kind"] in {"turn_started", "turn_overlap"}
        )

        self.assertNotIn("content", turn_failure)
        self.assertEqual(
            turn_failure["metadata"]["failure_status"], "known-failure"
        )
        self.assertEqual(
            set(turn_failure["metadata"]["error_evidence"]),
            {"original_chars", "sha256"},
        )
        self.assertTrue(COLLECTOR.known_failure_event(turn_failure))
        self.assertEqual(
            index["sessions"][0]["session_index"]["known_failure_kind_counts"][
                turn_failure["kind"]
            ],
            1,
        )
        for projection in (index, detail):
            self.assertNotIn(secret, json.dumps(projection, ensure_ascii=False))

    def test_provider_object_type_and_summary_are_not_projected(self) -> None:
        provider_timestamp = (
            self.utc_start + timedelta(minutes=47)
        ).isoformat().replace("+00:00", "Z")
        provider_payload = sql_text(
            json.dumps(
                {
                    "value": {
                        "type": {"private": "TYPE_SECRET"},
                        "summary": {"private": "SUMMARY_SECRET"},
                    }
                },
                ensure_ascii=False,
                separators=(",", ":"),
            )
        )
        inserted = subprocess.run(
            [self.sqlite, str(self.database)],
            input=(
                "INSERT INTO session_turn_provider_outputs_v6 VALUES "
                f"(1,2,'provider_error','safe summary',{provider_payload},"
                f"'{provider_timestamp}');"
            ),
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        self.assertEqual(inserted.returncode, 0, inserted.stderr)

        collected = self.run_collector(
            "--workspace", str(self.workspace), "--detail"
        )
        provider_error = next(
            event
            for event in collected["sessions"][0]["events"]
            if event["kind"] == "provider_error"
        )

        self.assertNotIn("content", provider_error)
        self.assertEqual(
            provider_error["metadata"]["error_evidence"]["original_chars"],
            len("safe summary"),
        )
        self.assertIsNone(provider_error["metadata"]["operation_type"])
        serialized = json.dumps(collected, ensure_ascii=False)
        self.assertNotIn("TYPE_SECRET", serialized)
        self.assertNotIn("SUMMARY_SECRET", serialized)
        self.assertEqual(
            COLLECTOR.safe_provider_operation_type("command_execution"),
            "command_execution",
        )
        self.assertEqual(
            COLLECTOR.safe_provider_operation_type(
                "x" * (COLLECTOR.MAX_PROVIDER_OPERATION_TYPE_CHARS + 1)
            ),
            "",
        )

    def test_workspace_filter_is_applied_before_canonical_session_merge(self) -> None:
        workspace_b = self.root / "workspace-b"
        workspace_b.mkdir()
        workspace_b_sql = sql_text(str(workspace_b))
        timestamp = (
            self.utc_start + timedelta(hours=2)
        ).isoformat().replace("+00:00", "Z")
        inserted = subprocess.run(
            [self.sqlite, str(self.database)],
            input=(
                "INSERT INTO sessions_v6 VALUES "
                f"('launch-2','fixture-b','completed','native-1',{workspace_b_sql});"
                "INSERT INTO session_messages_v6 VALUES "
                f"('launch-2',1,'user','workspace B only','{timestamp}');"
                "INSERT INTO session_messages_v6 VALUES "
                "('launch-1',99,'user','invalid in workspace A','not-a-time');"
            ),
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        self.assertEqual(inserted.returncode, 0, inserted.stderr)

        collected_b = self.run_collector(
            "--workspace", str(workspace_b), "--detail"
        )
        self.assertEqual(collected_b["session_count"], 1)
        texts_b = [
            event["content"]["text"]
            for event in collected_b["sessions"][0]["events"]
            if "content" in event
        ]
        self.assertEqual(texts_b, ["workspace B only"])
        self.assertEqual(
            collected_b["sessions"][0]["workspaces"], [str(workspace_b)]
        )
        self.assertEqual(
            collected_b["source_counts"]["withmate"]["invalid_timestamps"], 0
        )

        collected_a = self.run_collector(
            "--workspace", str(self.workspace), "--detail"
        )
        texts_a = [
            event["content"]["text"]
            for event in collected_a["sessions"][0]["events"]
            if "content" in event
        ]
        self.assertNotIn("workspace B only", texts_a)

    def test_workspace_comparison_casefolds_independent_of_host_normcase(self) -> None:
        mixed_case = self.root / "Workspace" / "Project"
        lower_case = self.root / "workspace" / "project"

        with mock.patch.object(
            COLLECTOR.os.path, "normcase", side_effect=lambda value: value
        ):
            self.assertEqual(
                COLLECTOR.normalize_path(str(mixed_case)),
                COLLECTOR.normalize_path(str(lower_case)),
            )

    def test_invalid_database_timestamps_are_disclosed_before_filtering(self) -> None:
        result = subprocess.run(
            [self.sqlite, str(self.database)],
            input=(
                "INSERT INTO session_messages_v6 VALUES "
                "('launch-1',20,'user','bad offset','2026-13-01T00:00+09:00'),"
                "('launch-1',21,'user','bad slash','2026/13/01 00:00'),"
                "('launch-1',22,'user','bad naive','2026-13-01 00:00:00'),"
                "('launch-1',23,'user','bad hour','2026-01-01T24:00:00Z'),"
                "('launch-1',24,'user','mixed slash','2026-01/01 00:00'),"
                "('launch-1',25,'user','too precise','2026-01-01T00:00:00.1234567Z');"
            ),
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

        collected = self.run_collector("--detail")

        self.assertEqual(
            collected["source_counts"]["withmate"]["invalid_timestamps"], 6
        )
        self.assertTrue(
            any(
                "session_messages_v6.created_at count=6" in gap
                for gap in collected["data_gaps"]
            )
        )

    def test_naive_timestamp_timezone_failures_are_disclosed_before_filtering(
        self,
    ) -> None:
        outside_interval = (self.local_start - timedelta(hours=3)).strftime(
            "%Y-%m-%dT%H:%M:%S"
        )
        inserted = subprocess.run(
            [self.sqlite, str(self.database)],
            input=(
                "INSERT INTO session_messages_v6 VALUES "
                f"('launch-1',40,'user','outside interval','{outside_interval}');"
            ),
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        self.assertEqual(inserted.returncode, 0, inserted.stderr)

        original_parse_timestamp = COLLECTOR.parse_timestamp

        def reject_outside_interval(value: str, *, slash_timezone: object) -> datetime:
            if value.strip() == outside_interval:
                raise ValueError("ambiguous local datetime in the timezone")
            return original_parse_timestamp(value, slash_timezone=slash_timezone)

        gaps: list[str] = []
        with mock.patch.object(
            COLLECTOR, "parse_timestamp", side_effect=reject_outside_interval
        ):
            invalid_count = COLLECTOR.collect_timestamp_domain_gaps(
                self.sqlite,
                self.database,
                self.local_timezone,
                COLLECTOR.CountBudget("test rows", 10_000),
                COLLECTOR.CountBudget("test bytes", 10 * 1024 * 1024),
                gaps,
                str(self.workspace),
            )

        self.assertEqual(invalid_count, 1)
        self.assertTrue(
            any(
                "session_messages_v6.created_at "
                "reason=ambiguous local datetime count=1" in gap
                for gap in gaps
            )
        )

    def test_database_timestamp_whitespace_uses_one_canonical_domain(self) -> None:
        slash = (self.local_start + timedelta(hours=11)).strftime("%Y/%m/%d %H:%M")
        naive = (self.local_start + timedelta(hours=12)).strftime("%Y-%m-%d %H:%M:%S")
        offset = (self.utc_start + timedelta(hours=13)).isoformat()
        turn_start = (self.utc_start + timedelta(hours=14)).isoformat()
        turn_end = (self.utc_start + timedelta(hours=14, minutes=5)).isoformat()
        result = subprocess.run(
            [self.sqlite, str(self.database)],
            input=(
                "INSERT INTO session_messages_v6 VALUES "
                f"('launch-1',30,'user','spaced slash','  {slash}  '),"
                f"('launch-1',31,'user','spaced naive','  {naive}  '),"
                f"('launch-1',32,'user','spaced offset','  {offset}  ');"
                "INSERT INTO session_turns_v6 VALUES "
                f"(30,'launch-1','completed','spaced turn','','  {turn_start}  ',"
                f"'  {turn_end}  ','  {turn_end}  ');"
            ),
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

        collected = self.run_collector("--detail")
        texts = [
            event["content"]["text"]
            for event in collected["sessions"][0]["events"]
            if "content" in event
        ]

        self.assertIn("spaced slash", texts)
        self.assertIn("spaced naive", texts)
        self.assertIn("spaced offset", texts)
        self.assertIn("spaced turn", texts)
        self.assertEqual(
            collected["source_counts"]["withmate"]["invalid_timestamps"], 0
        )

    def test_sql_timestamp_domain_matches_parser_contract(self) -> None:
        samples = [
            "  2026/01/31 23:59  ",
            "2026/01/31 23:59:59.123456",
            "2026-01-31T23:59",
            "2026-01-31 23:59:59.123456",
            "2026-01-31T23:59+05:30",
            "2026-01-31T23:59:59.1Z",
            "2026-02-30T00:00:00Z",
            "2026-01-31T24:00:00Z",
            "2026/01/31T23:59",
            "2026/01/31 23:59+09:00",
            "2026-01-31T23:59:59.1234567Z",
            "2026-01-31T23:59+0900",
            "2026-01-31X23:59",
            "2026-01-31T23:59+15:00",
            "0000-01-31T23:59Z",
            "2026-01-31T23:59+05:60",
            "2026-01-31T23:59+14:01",
            "2026-01-31T23:59-14:01",
            "2026-01-31T23:59+14:00",
            "2026-01-31T23:59-14:00",
        ]
        values = ",".join(
            f"({index},{sql_text(value)})" for index, value in enumerate(samples)
        )
        rows = COLLECTOR.run_sqlite_json(
            self.sqlite,
            self.database,
            "WITH samples(ord,value) AS (VALUES "
            f"{values}) SELECT ord,value,"
            f"{COLLECTOR.timestamp_domain_predicate('value')} AS domain_ok "
            "FROM samples ORDER BY ord;",
            COLLECTOR.CountBudget("test bytes", 1024 * 1024),
        )

        for row in rows:
            try:
                COLLECTOR.parse_timestamp(
                    str(row["value"]), slash_timezone=self.local_timezone
                )
                parser_ok = True
            except ValueError:
                parser_ok = False
            self.assertEqual(
                bool(row["domain_ok"]),
                parser_ok,
                msg=f"domain mismatch for {row['value']!r}",
            )

    def test_ambiguous_cross_source_message_candidates_are_not_deduplicated(self) -> None:
        session = COLLECTOR.ensure_session({}, "ambiguous")
        content = COLLECTOR.bounded_text("same", 100)
        occurred = COLLECTOR.iso_z(self.utc_start)
        session["events"] = [
            {
                "occurred_at_utc": occurred,
                "kind": "assistant_message",
                "source": source,
                "content": dict(content),
            }
            for source in ("withmate-v6", "withmate-v6", "codex-rollout")
        ]

        finalized, truncation = COLLECTOR.finalize_sessions(
            {"ambiguous": session},
            workspace_filter=None,
            selected_ids=set(),
            max_events_per_session=10,
            max_events=10,
            detail=True,
        )

        self.assertEqual(len(finalized[0]["events"]), 3)
        self.assertEqual(truncation["deduplicated_messages"], 0)

    def test_sub_millisecond_messages_are_not_deduplicated(self) -> None:
        session = COLLECTOR.ensure_session({}, "sub-millisecond")
        content = COLLECTOR.bounded_text("same", 100)
        session["events"] = [
            {
                "occurred_at_utc": COLLECTOR.iso_z(
                    self.utc_start + timedelta(microseconds=microseconds)
                ),
                "kind": "assistant_message",
                "source": source,
                "content": dict(content),
            }
            for microseconds, source in (
                (100, "withmate-v6"),
                (900, "codex-rollout"),
            )
        ]

        finalized, truncation = COLLECTOR.finalize_sessions(
            {"sub-millisecond": session},
            workspace_filter=None,
            selected_ids=set(),
            max_events_per_session=10,
            max_events=10,
            detail=True,
        )

        self.assertEqual(len(finalized[0]["events"]), 2)
        self.assertEqual(truncation["deduplicated_messages"], 0)

    def test_historical_turns_do_not_consume_target_day_row_budget(self) -> None:
        historical_start = (self.local_start - timedelta(days=30)).strftime(
            "%Y/%m/%d %H:%M"
        )
        historical_end = (self.local_start - timedelta(days=30) + timedelta(minutes=1)).strftime(
            "%Y/%m/%d %H:%M"
        )
        values = ",\n".join(
            f"({100 + index},'launch-1','completed','old','','{historical_start}',"
            f"'{historical_end}','{historical_end}')"
            for index in range(50)
        )
        result = subprocess.run(
            [self.sqlite, str(self.database)],
            input=f"INSERT INTO session_turns_v6 VALUES {values};",
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

        collected = self.run_collector("--detail")

        self.assertEqual(collected["source_counts"]["withmate"]["turns"], 2)

    def test_tail_probe_uses_actual_opened_bytes(self) -> None:
        window = COLLECTOR.build_window(
            self.local_start.replace(tzinfo=None).isoformat(timespec="seconds"),
            self.local_end.replace(tzinfo=None).isoformat(timespec="seconds"),
            "Asia/Tokyo",
            now=datetime.now(self.local_timezone),
        )
        declared_limit = self.rollout.stat().st_size
        with mock.patch.object(
            COLLECTOR,
            "last_rollout_timestamp",
            return_value=("uncertain", None, declared_limit + 1),
        ):
            with self.assertRaisesRegex(
                COLLECTOR.CollectorError, "tail probing exceeded"
            ):
                COLLECTOR.candidate_rollouts(
                    self.codex_home / "sessions",
                    window,
                    max_bytes=declared_limit * 2,
                    max_files=10,
                    max_tail_probe_bytes=declared_limit,
                )

    def test_rollout_path_date_never_excludes_western_timezone_event(self) -> None:
        western = timezone(timedelta(hours=-8))
        target = self.start_date
        local_start = datetime.combine(target, time.min, tzinfo=western)
        local_end = local_start + timedelta(days=1)
        window = COLLECTOR.FixedWindow(
            timezone_name="Etc/GMT+8",
            local_start=local_start,
            local_end=local_end,
            utc_start=local_start.astimezone(timezone.utc),
            utc_end=local_end.astimezone(timezone.utc),
            status="complete",
        )
        next_path_date = window.utc_end.date()
        directory = (
            self.codex_home
            / "sessions"
            / f"{next_path_date:%Y}"
            / f"{next_path_date:%m}"
            / f"{next_path_date:%d}"
        )
        directory.mkdir(parents=True, exist_ok=True)
        next_day_path = directory / "rollout-western.jsonl"
        next_day_path.write_text(
            json.dumps(
                {
                    "timestamp": (window.utc_end - timedelta(minutes=1)).isoformat(),
                    "type": "event_msg",
                    "payload": {"type": "agent_message", "message": "included"},
                }
            )
            + "\n",
            encoding="utf-8",
        )

        candidates, _, _, _ = COLLECTOR.candidate_rollouts(
            self.codex_home / "sessions",
            window,
            max_bytes=10 * 1024 * 1024,
            max_files=10,
            max_tail_probe_bytes=10 * 1024 * 1024,
        )

        self.assertIn(next_day_path, candidates)

    def test_rollout_line_is_bounded_before_full_materialization(self) -> None:
        result = self.run_collector_process("--max-rollout-line-bytes", "64")
        self.assertEqual(result.returncode, 2)
        self.assertIn("record exceeded --max-rollout-line-bytes", result.stderr)

    def test_rollout_timestamp_gaps_are_aggregated(self) -> None:
        sessions_root = self.root / "gap-sessions"
        sessions_root.mkdir()
        rollout = sessions_root / "rollout-gaps.jsonl"
        records = [
            {
                "timestamp": self.utc_start.isoformat(),
                "type": "session_meta",
                "payload": {"id": "gaps", "cwd": str(self.workspace)},
            },
            *[
                {
                    "type": "event_msg",
                    "payload": {"type": "user_message", "message": f"missing-{index}"},
                }
                for index in range(4)
            ],
        ]
        rollout.write_text(
            "".join(json.dumps(record) + "\n" for record in records),
            encoding="utf-8",
        )
        gaps: list[str] = []
        event_budget = COLLECTOR.CountBudget("test events", 1)

        counts = COLLECTOR.collect_rollouts(
            sessions_root,
            COLLECTOR.FixedWindow(
                timezone_name="Asia/Tokyo",
                local_start=self.local_start,
                local_end=self.local_end,
                utc_start=self.utc_start,
                utc_end=self.utc_end,
                status="complete",
            ),
            {},
            text_limit=100,
            max_bytes=1024 * 1024,
            max_line_bytes=1024 * 1024,
            max_files=10,
            max_tail_probe_bytes=1024 * 1024,
            workspace_filter=None,
            gaps=gaps,
            event_budget=event_budget,
        )

        self.assertEqual(counts["timestamp_missing_records"], 4)
        self.assertEqual(counts["timestamp_invalid_records"], 0)
        self.assertEqual(event_budget.used, 0)
        self.assertEqual(
            gaps,
            [
                "rollout relevant records missing timestamp count=4; "
                "window membership is unknown"
            ],
        )

    def test_default_returns_session_index_without_event_stream(self) -> None:
        result = self.run_collector("--workspace", str(self.workspace))
        detail = self.run_collector(
            "--workspace", str(self.workspace), "--detail"
        )
        session = result["sessions"][0]
        index = session["session_index"]

        self.assertEqual(
            result["collection_contract"]["content_mode"], "session-index"
        )
        self.assertEqual(
            set(session),
            {
                "session_id",
                "withmate_session_ids",
                "first_event_at_utc",
                "last_event_at_utc",
                "workspaces",
                "sources",
                "session_index",
            },
        )
        self.assertNotIn("events", session)
        self.assertNotIn("event_count_before_limits", session)
        self.assertNotIn("event_kind_counts_before_limits", session)
        self.assertNotIn("omitted_events", session)
        self.assertNotIn("unknown_failure_status_events", session)
        self.assertNotIn("unknown_failure_status_omitted", session)
        self.assertGreater(index["event_count"], 0)
        self.assertGreater(index["event_kind_counts"]["tool_result"], 0)
        self.assertTrue(index["goal_cues"])
        self.assertTrue(index["outcome_cues"])
        self.assertTrue(
            all(
                cue["content"]["original_chars"] >= len(cue["content"]["text"])
                for cue in [*index["goal_cues"], *index["outcome_cues"]]
                if "content" in cue
            )
        )
        self.assertEqual(
            result["truncation"]["detail_events_not_projected"],
            index["event_count"],
        )
        self.assertLess(
            len(json.dumps(result, ensure_ascii=False, separators=(",", ":"))),
            len(json.dumps(detail, ensure_ascii=False, separators=(",", ":"))),
        )

    def test_session_index_counts_known_failures_without_event_projection(self) -> None:
        successes = [
            {
                "kind": "tool_result",
                "metadata": {"exit_code": 0, "sequence": sequence},
            }
            for sequence in range(30)
        ]
        failure = {"kind": "tool_result", "metadata": {"exit_code": 1}}

        index = COLLECTOR.build_session_index([*successes, failure])

        self.assertEqual(index["event_count"], 31)
        self.assertEqual(index["event_kind_counts"], {"tool_result": 31})
        self.assertEqual(index["known_failure_event_count"], 1)
        self.assertEqual(index["known_failure_kind_counts"], {"tool_result": 1})

    def test_success_with_stderr_warning_is_not_failure(self) -> None:
        metadata = COLLECTOR.tool_output_metadata(
            {
                "call_id": "warning",
                "output": json.dumps(
                    {
                        "exit_code": 0,
                        "status": "completed",
                        "stderr": "warning only",
                    }
                ),
            }
        )
        event = {"kind": "tool_result", "metadata": metadata}

        self.assertEqual(metadata["failure_status"], "known-success")
        self.assertIn("stderr_evidence", metadata)
        self.assertNotIn("error_evidence", metadata)
        self.assertFalse(COLLECTOR.tool_result_failed(event))

    def test_tool_metadata_does_not_project_raw_command_or_error_text(self) -> None:
        secret = "Authorization: Bearer secret-sentinel"
        call_metadata = COLLECTOR.tool_call_metadata(
            {
                "call_id": "secret-call",
                "name": "exec_command",
                "arguments": json.dumps({"cmd": f"curl -H '{secret}' example.test"}),
            }
        )
        result_metadata = COLLECTOR.tool_output_metadata(
            {
                "call_id": "secret-call",
                "output": json.dumps(
                    {
                        "exit_code": 1,
                        "error": secret,
                        "stderr": f"request failed: {secret}",
                    }
                ),
            }
        )
        projection = json.dumps(
            {"call": call_metadata, "result": result_metadata}, sort_keys=True
        )

        self.assertNotIn(secret, projection)
        self.assertEqual(
            set(call_metadata["command_evidence"]), {"original_chars", "sha256"}
        )
        self.assertEqual(
            set(result_metadata["error_evidence"]), {"original_chars", "sha256"}
        )
        self.assertEqual(
            set(result_metadata["stderr_evidence"]), {"original_chars", "sha256"}
        )
        self.assertEqual(result_metadata["failure_status"], "known-failure")

        invalid_metadata = COLLECTOR.tool_output_metadata(
            {
                "call_id": "invalid-fields",
                "output": json.dumps(
                    {
                        "exit_code": secret,
                        "isError": secret,
                        "status": secret,
                        "wall_time_seconds": secret,
                    }
                ),
            }
        )
        invalid_projection = json.dumps(invalid_metadata, sort_keys=True)
        self.assertNotIn(secret, invalid_projection)
        for key in ("exit_code", "isError", "status", "wall_time_seconds"):
            self.assertNotIn(key, invalid_metadata)
        self.assertEqual(invalid_metadata["failure_status"], "unknown")

    def test_unknown_executable_status_omission_is_disclosed(self) -> None:
        session = COLLECTOR.ensure_session({}, "unknown-status")
        COLLECTOR.add_source(session, "withmate-v6")
        session["events"] = [
            {
                "occurred_at_utc": COLLECTOR.iso_z(
                    self.utc_start + timedelta(seconds=index)
                ),
                "kind": "command_execution",
                "source": "withmate-v6",
                "metadata": {"failure_status": "unknown", "sequence": index},
            }
            for index in range(30)
        ]

        finalized, truncation = COLLECTOR.finalize_sessions(
            {"unknown-status": session},
            workspace_filter=None,
            selected_ids=set(),
            max_events_per_session=160,
            max_events=1000,
            detail=False,
        )

        self.assertNotIn("unknown_failure_status_events", finalized[0])
        self.assertNotIn("events", finalized[0])
        self.assertEqual(
            finalized[0]["session_index"]["unknown_failure_status_events"], 30
        )
        self.assertNotIn("unknown_failure_status_omitted", finalized[0])
        self.assertEqual(truncation["unknown_failure_status_events"], 30)
        self.assertEqual(truncation["unknown_failure_status_omitted"], 30)

    def test_unmatched_tool_call_omission_is_disclosed(self) -> None:
        session = COLLECTOR.ensure_session({}, "unmatched-tool-calls")
        COLLECTOR.add_source(session, "codex-rollout")
        session["events"] = [
            {
                "occurred_at_utc": COLLECTOR.iso_z(
                    self.utc_start + timedelta(seconds=index)
                ),
                "kind": "tool_call",
                "source": "codex-rollout",
                "metadata": {
                    "call_id": f"call-{index}",
                    "tool": "exec_command",
                },
            }
            for index in range(30)
        ]

        finalized, truncation = COLLECTOR.finalize_sessions(
            {"unmatched-tool-calls": session},
            workspace_filter=None,
            selected_ids=set(),
            max_events_per_session=160,
            max_events=1000,
            detail=False,
        )

        self.assertNotIn("unknown_failure_status_events", finalized[0])
        self.assertNotIn("events", finalized[0])
        self.assertEqual(
            finalized[0]["session_index"]["unknown_failure_status_events"], 30
        )
        self.assertNotIn("unknown_failure_status_omitted", finalized[0])
        self.assertEqual(truncation["unknown_failure_status_events"], 30)
        self.assertEqual(truncation["unknown_failure_status_omitted"], 30)

    def test_matched_tool_call_is_not_unknown(self) -> None:
        session = COLLECTOR.ensure_session({}, "matched-tool-call")
        COLLECTOR.add_source(session, "codex-rollout")
        session["events"] = [
            {
                "occurred_at_utc": COLLECTOR.iso_z(self.utc_start),
                "kind": "tool_call",
                "source": "codex-rollout",
                "metadata": {"call_id": "matched", "tool": "exec_command"},
            },
            {
                "occurred_at_utc": COLLECTOR.iso_z(
                    self.utc_start + timedelta(seconds=1)
                ),
                "kind": "tool_result",
                "source": "codex-rollout",
                "metadata": {
                    "call_id": "matched",
                    "failure_status": "known-success",
                },
            },
        ]

        finalized, truncation = COLLECTOR.finalize_sessions(
            {"matched-tool-call": session},
            workspace_filter=None,
            selected_ids=set(),
            max_events_per_session=10,
            max_events=10,
            detail=True,
        )

        tool_call = next(
            event
            for event in finalized[0]["events"]
            if event["kind"] == "tool_call"
        )
        self.assertNotIn("failure_status", tool_call["metadata"])
        self.assertEqual(truncation["unknown_failure_status_events"], 0)

    def test_reused_tool_call_id_is_ambiguous(self) -> None:
        session = COLLECTOR.ensure_session({}, "reused-tool-call")
        COLLECTOR.add_source(session, "codex-rollout")
        session["events"] = [
            {
                "occurred_at_utc": COLLECTOR.iso_z(
                    self.utc_start + timedelta(seconds=index)
                ),
                "kind": "tool_call",
                "source": "codex-rollout",
                "metadata": {"call_id": "reused", "tool": "exec_command"},
            }
            for index in range(2)
        ]
        session["events"].append(
            {
                "occurred_at_utc": COLLECTOR.iso_z(
                    self.utc_start + timedelta(seconds=2)
                ),
                "kind": "tool_result",
                "source": "codex-rollout",
                "metadata": {
                    "call_id": "reused",
                    "failure_status": "known-success",
                },
            }
        )

        finalized, truncation = COLLECTOR.finalize_sessions(
            {"reused-tool-call": session},
            workspace_filter=None,
            selected_ids=set(),
            max_events_per_session=10,
            max_events=10,
            detail=True,
        )

        calls = [
            event
            for event in finalized[0]["events"]
            if event["kind"] == "tool_call"
        ]
        self.assertEqual(truncation["unknown_failure_status_events"], 2)
        self.assertTrue(
            all(
                call["metadata"]["result_status"]
                == "ambiguous-call-result-cardinality"
                for call in calls
            )
        )

    def test_empty_tool_call_id_is_unknown_even_with_empty_result_id(self) -> None:
        session = COLLECTOR.ensure_session({}, "empty-tool-call")
        COLLECTOR.add_source(session, "codex-rollout")
        session["events"] = [
            {
                "occurred_at_utc": COLLECTOR.iso_z(self.utc_start),
                "kind": "tool_call",
                "source": "codex-rollout",
                "metadata": {"call_id": "", "tool": "exec_command"},
            },
            {
                "occurred_at_utc": COLLECTOR.iso_z(
                    self.utc_start + timedelta(seconds=1)
                ),
                "kind": "tool_result",
                "source": "codex-rollout",
                "metadata": {"call_id": "", "failure_status": "known-success"},
            },
        ]

        finalized, truncation = COLLECTOR.finalize_sessions(
            {"empty-tool-call": session},
            workspace_filter=None,
            selected_ids=set(),
            max_events_per_session=10,
            max_events=10,
            detail=True,
        )

        tool_call = next(
            event
            for event in finalized[0]["events"]
            if event["kind"] == "tool_call"
        )
        self.assertEqual(tool_call["metadata"]["result_status"], "invalid-call-id")
        self.assertEqual(truncation["unknown_failure_status_events"], 1)

    def test_turn_failure_is_preserved_by_per_session_and_global_caps(self) -> None:
        sessions: dict[str, dict] = {}
        failures: list[dict] = []
        for session_index in range(2):
            session_id = f"turn-failure-{session_index}"
            session = COLLECTOR.ensure_session(sessions, session_id)
            COLLECTOR.add_source(session, "withmate-v6")
            start = self.utc_start + timedelta(minutes=session_index)
            failure = {
                "occurred_at_utc": COLLECTOR.iso_z(start),
                "kind": "turn_started",
                "source": "withmate-v6",
                "metadata": {"failure_status": "known-failure"},
            }
            failures.append(failure)
            session["events"] = [
                failure,
                {
                    "occurred_at_utc": COLLECTOR.iso_z(
                        start + timedelta(seconds=1)
                    ),
                    "kind": "assistant_message",
                    "source": "withmate-v6",
                },
            ]

        finalized, truncation = COLLECTOR.finalize_sessions(
            sessions,
            workspace_filter=None,
            selected_ids=set(),
            max_events_per_session=1,
            max_events=2,
            detail=True,
        )

        retained = [event for session in finalized for event in session["events"]]
        self.assertEqual(retained, failures)
        self.assertEqual(truncation["omitted_events"], 2)

    def test_per_session_output_cap_preserves_failed_tool_result(self) -> None:
        session = COLLECTOR.ensure_session({}, "cap-session")
        COLLECTOR.add_source(session, "codex-rollout")
        start = self.utc_start
        session["events"] = [
            {
                "occurred_at_utc": COLLECTOR.iso_z(start + timedelta(seconds=index)),
                "kind": "user_message" if index < 80 else "assistant_message",
                "source": "codex-rollout",
            }
            for index in range(160)
        ]
        failure = {
            "occurred_at_utc": COLLECTOR.iso_z(start + timedelta(seconds=80, microseconds=1)),
            "kind": "tool_result",
            "source": "codex-rollout",
            "metadata": {"exit_code": 1},
        }
        session["events"].insert(80, failure)

        finalized, truncation = COLLECTOR.finalize_sessions(
            {"cap-session": session},
            workspace_filter=None,
            selected_ids=set(),
            max_events_per_session=160,
            max_events=1000,
            detail=True,
        )

        self.assertEqual(len(finalized[0]["events"]), 160)
        self.assertIn(failure, finalized[0]["events"])
        self.assertEqual(truncation["omitted_events"], 1)

    def test_per_session_output_cap_preserves_provider_error(self) -> None:
        session = COLLECTOR.ensure_session({}, "provider-cap-session")
        COLLECTOR.add_source(session, "withmate-v6")
        start = self.utc_start
        provider_error = {
            "occurred_at_utc": COLLECTOR.iso_z(
                start + timedelta(seconds=80, microseconds=1)
            ),
            "kind": "provider_error",
            "source": "withmate-v6",
        }
        session["events"] = [
            {
                "occurred_at_utc": COLLECTOR.iso_z(start + timedelta(seconds=index)),
                "kind": "user_message" if index < 80 else "assistant_message",
                "source": "withmate-v6",
            }
            for index in range(160)
        ]
        session["events"].insert(80, provider_error)

        finalized, truncation = COLLECTOR.finalize_sessions(
            {"provider-cap-session": session},
            workspace_filter=None,
            selected_ids=set(),
            max_events_per_session=160,
            max_events=1000,
            detail=True,
        )

        self.assertEqual(len(finalized[0]["events"]), 160)
        self.assertIn(provider_error, finalized[0]["events"])
        self.assertEqual(truncation["omitted_events"], 1)

    def test_global_output_cap_preserves_failures_across_sessions(self) -> None:
        sessions: dict[str, dict] = {}
        failures: list[dict] = []
        for session_index in range(2):
            session_id = f"global-{session_index}"
            session = COLLECTOR.ensure_session(sessions, session_id)
            COLLECTOR.add_source(session, "codex-rollout")
            start = self.utc_start + timedelta(minutes=session_index)
            failure = {
                "occurred_at_utc": COLLECTOR.iso_z(start + timedelta(seconds=1)),
                "kind": "tool_result",
                "source": "codex-rollout",
                "metadata": {"exit_code": 1},
            }
            failures.append(failure)
            session["events"] = [
                {
                    "occurred_at_utc": COLLECTOR.iso_z(start),
                    "kind": "user_message",
                    "source": "codex-rollout",
                },
                failure,
                {
                    "occurred_at_utc": COLLECTOR.iso_z(start + timedelta(seconds=2)),
                    "kind": "assistant_message",
                    "source": "codex-rollout",
                },
            ]

        finalized, truncation = COLLECTOR.finalize_sessions(
            sessions,
            workspace_filter=None,
            selected_ids=set(),
            max_events_per_session=10,
            max_events=4,
            detail=True,
        )

        retained = [event for session in finalized for event in session["events"]]
        self.assertEqual(len(retained), 4)
        self.assertTrue(all(failure in retained for failure in failures))
        self.assertEqual(truncation["omitted_events"], 2)

    def test_global_output_cap_preserves_provider_errors_across_sessions(self) -> None:
        sessions: dict[str, dict] = {}
        provider_errors: list[dict] = []
        for session_index in range(2):
            session_id = f"provider-global-{session_index}"
            session = COLLECTOR.ensure_session(sessions, session_id)
            COLLECTOR.add_source(session, "withmate-v6")
            start = self.utc_start + timedelta(minutes=session_index)
            provider_error = {
                "occurred_at_utc": COLLECTOR.iso_z(start + timedelta(seconds=1)),
                "kind": "provider_error",
                "source": "withmate-v6",
            }
            provider_errors.append(provider_error)
            session["events"] = [
                {
                    "occurred_at_utc": COLLECTOR.iso_z(start),
                    "kind": "user_message",
                    "source": "withmate-v6",
                },
                provider_error,
                {
                    "occurred_at_utc": COLLECTOR.iso_z(start + timedelta(seconds=2)),
                    "kind": "assistant_message",
                    "source": "withmate-v6",
                },
            ]

        finalized, truncation = COLLECTOR.finalize_sessions(
            sessions,
            workspace_filter=None,
            selected_ids=set(),
            max_events_per_session=10,
            max_events=4,
            detail=True,
        )

        retained = [event for session in finalized for event in session["events"]]
        self.assertEqual(len(retained), 4)
        self.assertTrue(
            all(provider_error in retained for provider_error in provider_errors)
        )
        self.assertEqual(truncation["omitted_events"], 2)

    def test_global_optional_allocation_has_canonical_session_tiebreak(self) -> None:
        def retained_session(order: list[str]) -> str:
            sessions: dict[str, dict] = {}
            for session_id in order:
                session = COLLECTOR.ensure_session(sessions, session_id)
                COLLECTOR.add_source(session, "codex-rollout")
                session["events"] = [
                    {
                        "occurred_at_utc": COLLECTOR.iso_z(self.utc_start),
                        "kind": "user_message",
                        "source": "codex-rollout",
                    }
                ]
            finalized, _ = COLLECTOR.finalize_sessions(
                sessions,
                workspace_filter=None,
                selected_ids=set(),
                max_events_per_session=10,
                max_events=1,
                detail=True,
            )
            return next(
                session["session_id"] for session in finalized if session["events"]
            )

        self.assertEqual(retained_session(["a", "b"]), "a")
        self.assertEqual(retained_session(["b", "a"]), "a")

    def test_output_cap_fails_closed_when_failures_alone_exceed_limit(self) -> None:
        failures = [
            {"kind": "tool_result", "metadata": {"exit_code": 1}}
            for _ in range(3)
        ]

        with self.assertRaisesRegex(
            COLLECTOR.CollectorError,
            "known failure events exceed --max-events-per-session",
        ):
            COLLECTOR.trim_preserving_known_failures(
                failures, 2, "--max-events-per-session"
            )

        sessions: dict[str, dict] = {}
        for index, failure in enumerate(failures):
            session = COLLECTOR.ensure_session(sessions, f"failure-{index}")
            COLLECTOR.add_source(session, "codex-rollout")
            failure.update(
                {
                    "occurred_at_utc": COLLECTOR.iso_z(
                        self.utc_start + timedelta(seconds=index)
                    ),
                    "source": "codex-rollout",
                }
            )
            session["events"] = [failure]

        with self.assertRaisesRegex(
            COLLECTOR.CollectorError,
            "known failure events exceed --max-events",
        ):
            COLLECTOR.finalize_sessions(
                sessions,
                workspace_filter=None,
                selected_ids=set(),
                max_events_per_session=2,
                max_events=2,
                detail=True,
            )

    def test_output_cap_fails_closed_when_provider_errors_exceed_limit(self) -> None:
        provider_errors = [{"kind": "provider_error"} for _ in range(3)]

        with self.assertRaisesRegex(
            COLLECTOR.CollectorError,
            "known failure events exceed --max-events-per-session",
        ):
            COLLECTOR.trim_preserving_known_failures(
                provider_errors, 2, "--max-events-per-session"
            )

    def test_missing_sqlite_has_no_fallback(self) -> None:
        with mock.patch.object(COLLECTOR.shutil, "which", return_value=None):
            with self.assertRaisesRegex(COLLECTOR.CollectorError, "sqlite3 CLI is required"):
                COLLECTOR.require_sqlite()


if __name__ == "__main__":
    unittest.main()
