from __future__ import annotations

import importlib.util
import json
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock


SCRIPT = Path(__file__).with_name("audit_history.py")
SPEC = importlib.util.spec_from_file_location("audit_history", SCRIPT)
assert SPEC and SPEC.loader
HISTORY = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = HISTORY
SPEC.loader.exec_module(HISTORY)


class AuditHistoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.database = self.root / "history.sqlite3"
        self.workspace = self.root / "Workspace"
        self.workspace.mkdir()
        self.now = datetime(2026, 8, 8, 12, tzinfo=timezone.utc)
        self.now_patch = mock.patch.object(HISTORY, "utc_now", return_value=self.now)
        self.now_patch.start()

    def tearDown(self) -> None:
        self.now_patch.stop()
        self.tempdir.cleanup()

    def target_request(
        self,
        *,
        focus_key: str = "review-convergence",
        focus_question: str = "なぜレビューが収束しなかったか",
        claim_key: str | None = None,
        force_reason: str | None = None,
        workspace: str | None = None,
    ) -> dict:
        value: dict = {
            "start": "2026-08-01T20:00",
            "end": "2026-08-02T04:00",
            "timezone": "Asia/Tokyo",
            "workspace": str(self.workspace) if workspace is None else workspace,
            "focus_key": focus_key,
            "focus_question": focus_question,
        }
        if claim_key is not None:
            value["claim_key"] = claim_key
        if force_reason is not None:
            value["force_reason"] = force_reason
        return value

    def result(self, summary: str = "収束遅延の主因を特定した") -> dict:
        return {
            "summary": summary,
            "confidence": "medium",
            "finding_families": ["scope-reconfirmation"],
            "good_decisions": ["最終成果物を確認した"],
            "data_gaps": [],
            "interventions": ["scopeを実装前に固定する"],
            "outcome_context_checked_at_utc": "2026-08-08T12:00:00Z",
        }

    def claim(self, claim_key: str = "claim-1", **kwargs) -> dict:
        return HISTORY.claim_history(
            self.database,
            self.target_request(claim_key=claim_key, **kwargs),
        )

    def complete(self, claim: dict, result: dict | None = None) -> dict:
        return HISTORY.update_run(
            self.database,
            {
                "run_id": claim["run"]["run_id"],
                "claim_key": self.claim_key_for(claim["run"]["run_id"]),
                "result": result or self.result(),
            },
            "complete",
        )

    def claim_key_for(self, run_id: str) -> str:
        connection = sqlite3.connect(self.database)
        try:
            row = connection.execute(
                "SELECT claim_key FROM audit_runs WHERE run_id = ?", (run_id,)
            ).fetchone()
        finally:
            connection.close()
        assert row is not None
        return str(row[0])

    def test_lookup_does_not_create_a_missing_database(self) -> None:
        lookup = HISTORY.lookup_history(self.database, self.target_request())

        self.assertFalse(lookup["history_available"])
        self.assertIsNone(lookup["reusable_exact_match"])
        self.assertFalse(self.database.exists())

    def test_completed_exact_focus_is_reused_without_new_run(self) -> None:
        claimed = self.claim()
        self.assertEqual(claimed["action"], "claimed")
        self.complete(claimed)

        reused = self.claim("claim-2")
        lookup = HISTORY.lookup_history(self.database, self.target_request())

        self.assertEqual(reused["action"], "reuse")
        self.assertEqual(
            lookup["reusable_exact_match"]["result"]["summary"],
            "収束遅延の主因を特定した",
        )
        connection = sqlite3.connect(self.database)
        try:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM audit_runs").fetchone()[0], 1)
        finally:
            connection.close()

    def test_different_focus_on_same_window_is_claimed(self) -> None:
        first = self.claim()
        self.complete(first)

        second = self.claim(
            "claim-2",
            focus_key="validation-directness",
            focus_question="検証はfailureを直接観測したか",
        )

        self.assertEqual(second["action"], "claimed")

    def test_same_focus_with_different_question_is_related_but_not_reused(self) -> None:
        first = self.claim()
        self.complete(first)
        request = self.target_request(
            focus_question="どのfinding familyが繰り返したか"
        )

        lookup = HISTORY.lookup_history(self.database, request)
        second = HISTORY.claim_history(
            self.database, {**request, "claim_key": "claim-2"}
        )

        self.assertIsNone(lookup["reusable_exact_match"])
        self.assertEqual(len(lookup["same_window_related_questions"]), 1)
        self.assertEqual(second["action"], "claimed")

    def test_focus_question_normalization_avoids_format_only_duplicates(self) -> None:
        first = self.claim(focus_question="Review  が\n収束しない理由")
        self.complete(first)

        reused = self.claim(
            "claim-2", focus_question="review が 収束しない理由"
        )

        self.assertEqual(reused["action"], "reuse")

    def test_workspace_normalization_matches_collector_semantics(self) -> None:
        first = self.claim(workspace=str(self.workspace).upper())
        self.complete(first)

        reused = self.claim("claim-2", workspace=str(self.workspace).lower())

        self.assertEqual(reused["action"], "reuse")

    def test_active_claim_blocks_a_concurrent_claim(self) -> None:
        barrier = threading.Barrier(2)
        results: list[dict] = []
        errors: list[BaseException] = []

        def run(claim_key: str) -> None:
            try:
                barrier.wait()
                results.append(self.claim(claim_key))
            except BaseException as exc:  # pragma: no cover - assertion reports it
                errors.append(exc)

        threads = [
            threading.Thread(target=run, args=("claim-a",)),
            threading.Thread(target=run, args=("claim-b",)),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual(errors, [])
        self.assertCountEqual([item["action"] for item in results], ["claimed", "busy"])
        connection = sqlite3.connect(self.database)
        try:
            active = connection.execute(
                "SELECT COUNT(*) FROM audit_runs WHERE status = 'in_progress'"
            ).fetchone()[0]
        finally:
            connection.close()
        self.assertEqual(active, 1)

    def test_claim_retry_is_idempotent_and_cannot_change_target(self) -> None:
        first = self.claim()
        retry = self.claim()

        self.assertEqual(retry["action"], "claimed")
        self.assertTrue(retry["idempotent_replay"])
        self.assertEqual(first["run"]["run_id"], retry["run"]["run_id"])
        with self.assertRaisesRegex(HISTORY.HistoryError, "different audit target"):
            self.claim("claim-1", focus_key="validation-directness")

    def test_expired_claim_key_replay_is_terminal(self) -> None:
        self.claim()
        later = self.now + timedelta(seconds=HISTORY.LEASE_SECONDS + 1)

        with mock.patch.object(HISTORY, "utc_now", return_value=later):
            replay = self.claim()
            replacement = self.claim("claim-2")

        self.assertEqual(replay["action"], "terminal")
        self.assertEqual(replay["run"]["status"], "abandoned")
        self.assertEqual(replacement["action"], "claimed")

    def test_failed_claim_key_replay_is_terminal(self) -> None:
        claimed = self.claim()
        HISTORY.update_run(
            self.database,
            {
                "run_id": claimed["run"]["run_id"],
                "claim_key": "claim-1",
                "failure_code": "evidence-unavailable",
                "failure_summary": "証拠不足",
            },
            "fail",
        )

        replay = self.claim()

        self.assertEqual(replay["action"], "terminal")

    def test_expired_claim_is_abandoned_and_late_complete_is_rejected(self) -> None:
        first = self.claim()
        later = self.now + timedelta(seconds=HISTORY.LEASE_SECONDS + 1)
        with mock.patch.object(HISTORY, "utc_now", return_value=later):
            second = self.claim("claim-2")

        self.assertEqual(second["action"], "claimed")
        with self.assertRaisesRegex(HISTORY.HistoryError, "status abandoned"):
            self.complete(first)

    def test_heartbeat_extends_lease(self) -> None:
        claimed = self.claim()
        later = self.now + timedelta(hours=1)
        with mock.patch.object(HISTORY, "utc_now", return_value=later):
            heartbeat = HISTORY.update_run(
                self.database,
                {
                    "run_id": claimed["run"]["run_id"],
                    "claim_key": "claim-1",
                },
                "heartbeat",
            )

        expected = HISTORY.iso_z(later + timedelta(seconds=HISTORY.LEASE_SECONDS))
        self.assertEqual(heartbeat["run"]["lease_expires_at_utc"], expected)

    def test_expired_heartbeat_is_rejected_and_abandons_claim(self) -> None:
        claimed = self.claim()
        later = self.now + timedelta(seconds=HISTORY.LEASE_SECONDS + 1)

        with mock.patch.object(HISTORY, "utc_now", return_value=later):
            with self.assertRaisesRegex(HISTORY.HistoryError, "lease expired"):
                HISTORY.update_run(
                    self.database,
                    {
                        "run_id": claimed["run"]["run_id"],
                        "claim_key": "claim-1",
                    },
                    "heartbeat",
                )
            replacement = self.claim("claim-2")

        self.assertEqual(replacement["action"], "claimed")

    def test_partial_completion_never_suppresses_a_later_claim(self) -> None:
        original = HISTORY.build_window

        def partial_window(*args, **kwargs):
            window = original(*args, **kwargs)
            return HISTORY.FixedWindow(
                timezone_name=window.timezone_name,
                local_start=window.local_start,
                local_end=window.local_end,
                utc_start=window.utc_start,
                utc_end=window.utc_end,
                status="partial",
            )

        with mock.patch.object(HISTORY, "build_window", side_effect=partial_window):
            first = self.claim()
            self.complete(first)

        second = self.claim("claim-2")

        self.assertEqual(second["action"], "claimed")

    def test_force_reason_allows_an_explicit_rerun(self) -> None:
        first = self.claim()
        self.complete(first)

        rerun = self.claim("claim-2", force_reason="outcome context refresh")

        self.assertEqual(rerun["action"], "claimed")
        self.assertEqual(rerun["run"]["force_reason"], "outcome context refresh")

    def test_complete_is_idempotent_only_for_the_same_result(self) -> None:
        claimed = self.claim()
        first = self.complete(claimed)
        retry = self.complete(claimed)

        self.assertFalse(first["idempotent_replay"])
        self.assertTrue(retry["idempotent_replay"])
        with self.assertRaisesRegex(HISTORY.HistoryError, "different result"):
            self.complete(claimed, self.result("別の結論"))

    def test_failed_run_does_not_suppress_a_new_claim(self) -> None:
        claimed = self.claim()
        failed = HISTORY.update_run(
            self.database,
            {
                "run_id": claimed["run"]["run_id"],
                "claim_key": "claim-1",
                "failure_code": "evidence-unavailable",
                "failure_summary": "必要な証拠を取得できなかった",
            },
            "fail",
        )
        second = self.claim("claim-2")

        self.assertEqual(failed["run"]["status"], "failed")
        self.assertEqual(second["action"], "claimed")

    def test_result_allowlist_rejects_raw_evidence_before_mutation(self) -> None:
        claimed = self.claim()
        raw_result = {**self.result(), "raw_transcript": "RAW_SENTINEL"}

        with self.assertRaisesRegex(HISTORY.HistoryError, "unknown fields"):
            self.complete(claimed, raw_result)

        self.assertNotIn(b"RAW_SENTINEL", self.database.read_bytes())
        connection = sqlite3.connect(self.database)
        try:
            status = connection.execute(
                "SELECT status FROM audit_runs WHERE run_id = ?",
                (claimed["run"]["run_id"],),
            ).fetchone()[0]
        finally:
            connection.close()
        self.assertEqual(status, "in_progress")

    def test_workspace_path_is_hashed_not_persisted(self) -> None:
        claimed = self.claim()
        self.complete(claimed)

        self.assertNotIn(str(self.workspace).encode("utf-8"), self.database.read_bytes())

    def test_corrupted_stored_result_is_not_reused(self) -> None:
        claimed = self.claim()
        self.complete(claimed)
        connection = sqlite3.connect(self.database)
        try:
            connection.execute(
                "UPDATE audit_runs SET result_version = 999 WHERE run_id = ?",
                (claimed["run"]["run_id"],),
            )
            connection.commit()
        finally:
            connection.close()

        with self.assertRaisesRegex(HISTORY.HistoryError, "unsupported version"):
            HISTORY.lookup_history(self.database, self.target_request())

    def test_completed_run_with_null_result_is_not_reused(self) -> None:
        claimed = self.claim()
        self.complete(claimed)
        connection = sqlite3.connect(self.database)
        try:
            connection.execute(
                "UPDATE audit_runs SET result_json = NULL WHERE run_id = ?",
                (claimed["run"]["run_id"],),
            )
            connection.commit()
        finally:
            connection.close()

        with self.assertRaisesRegex(HISTORY.HistoryError, "no stored result"):
            HISTORY.lookup_history(self.database, self.target_request())

    def test_missing_invariant_index_is_rejected(self) -> None:
        self.claim()
        connection = sqlite3.connect(self.database)
        try:
            connection.execute("DROP INDEX audit_one_active_run_per_target")
            connection.commit()
        finally:
            connection.close()

        with self.assertRaisesRegex(HISTORY.HistoryError, "schema objects"):
            HISTORY.lookup_history(self.database, self.target_request())

    def test_oversized_database_is_rejected_before_read_or_replay(self) -> None:
        claimed = self.claim()
        self.complete(claimed)

        with mock.patch.object(HISTORY, "MAX_DATABASE_BYTES", 1):
            with self.assertRaisesRegex(HISTORY.HistoryError, "database exceeds"):
                HISTORY.lookup_history(self.database, self.target_request())
            with self.assertRaisesRegex(HISTORY.HistoryError, "database exceeds"):
                self.claim("claim-2")
            with self.assertRaisesRegex(HISTORY.HistoryError, "database exceeds"):
                self.complete(claimed)

    def test_expiry_transition_rolls_back_if_it_crosses_database_limit(self) -> None:
        claimed = self.claim()
        later = self.now + timedelta(seconds=HISTORY.LEASE_SECONDS + 1)

        with (
            mock.patch.object(HISTORY, "utc_now", return_value=later),
            mock.patch.object(
                HISTORY,
                "database_size",
                side_effect=[0, HISTORY.MAX_DATABASE_BYTES + 1],
            ),
        ):
            with self.assertRaisesRegex(HISTORY.HistoryError, "database exceeds"):
                self.claim()

        connection = sqlite3.connect(self.database)
        try:
            status = connection.execute(
                "SELECT status FROM audit_runs WHERE run_id = ?",
                (claimed["run"]["run_id"],),
            ).fetchone()[0]
        finally:
            connection.close()
        self.assertEqual(status, "in_progress")

    def test_expired_heartbeat_rolls_back_if_it_crosses_database_limit(self) -> None:
        claimed = self.claim()
        later = self.now + timedelta(seconds=HISTORY.LEASE_SECONDS + 1)

        with (
            mock.patch.object(HISTORY, "utc_now", return_value=later),
            mock.patch.object(
                HISTORY,
                "database_size",
                side_effect=[0, HISTORY.MAX_DATABASE_BYTES + 1],
            ),
        ):
            with self.assertRaisesRegex(HISTORY.HistoryError, "database exceeds"):
                HISTORY.update_run(
                    self.database,
                    {
                        "run_id": claimed["run"]["run_id"],
                        "claim_key": "claim-1",
                    },
                    "heartbeat",
                )

        connection = sqlite3.connect(self.database)
        try:
            status = connection.execute(
                "SELECT status FROM audit_runs WHERE run_id = ?",
                (claimed["run"]["run_id"],),
            ).fetchone()[0]
        finally:
            connection.close()
        self.assertEqual(status, "in_progress")

    def test_future_schema_is_rejected_without_downgrade(self) -> None:
        connection = sqlite3.connect(self.database)
        try:
            connection.execute("PRAGMA user_version=99")
            connection.commit()
        finally:
            connection.close()

        with self.assertRaisesRegex(HISTORY.HistoryError, "unsupported"):
            self.claim()

        connection = sqlite3.connect(self.database)
        try:
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 99)
        finally:
            connection.close()

    def test_partial_schema_is_rejected_without_repair(self) -> None:
        connection = sqlite3.connect(self.database)
        try:
            connection.execute("CREATE TABLE unrelated (id INTEGER)")
            connection.commit()
        finally:
            connection.close()

        with self.assertRaisesRegex(HISTORY.HistoryError, "partial"):
            self.claim()
        connection = sqlite3.connect(self.database)
        try:
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM sqlite_master WHERE name = 'audit_runs'"
                ).fetchone()[0],
                0,
            )
        finally:
            connection.close()

    def test_cli_lookup_accepts_utf8_json_and_returns_json(self) -> None:
        request = self.target_request()

        completed = subprocess.run(
            [sys.executable, str(SCRIPT), "lookup", "--database", str(self.database)],
            input=json.dumps(request, ensure_ascii=False).encode("utf-8"),
            capture_output=True,
            check=False,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr.decode("utf-8"))
        output = json.loads(completed.stdout.decode("utf-8"))
        self.assertEqual(output["focus_question"], request["focus_question"])
        self.assertFalse(output["history_available"])

    def test_cli_invalid_utf8_is_a_bounded_error(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(SCRIPT), "lookup", "--database", str(self.database)],
            input=b"\xff",
            capture_output=True,
            check=False,
        )

        self.assertEqual(completed.returncode, 2)
        self.assertIn(b"error:", completed.stderr)
        self.assertNotIn(b"Traceback", completed.stderr)

    def test_cli_invalid_interval_is_a_bounded_error_without_mutation(self) -> None:
        request = {**self.target_request(), "start": "not-a-date"}
        completed = subprocess.run(
            [sys.executable, str(SCRIPT), "lookup", "--database", str(self.database)],
            input=json.dumps(request, ensure_ascii=False).encode("utf-8"),
            capture_output=True,
            check=False,
        )

        self.assertEqual(completed.returncode, 2)
        self.assertIn(b"error:", completed.stderr)
        self.assertNotIn(b"Traceback", completed.stderr)
        self.assertFalse(self.database.exists())


if __name__ == "__main__":
    unittest.main()
