from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).with_name("session_graph.py")
spec = importlib.util.spec_from_file_location("session_graph", SCRIPT)
sg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sg)
FIRST = 'flowchart TB\n    R1["独自実装しない"]\n'
SECOND = FIRST + '    R2["高さを変更できる"]\n'


class SessionGraphTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name).resolve()
        self.graph = self.folder / sg.GRAPH_NAME
        self.draft = self.folder / "draft.mmd"

    def stage(self, text=FIRST):
        self.draft.write_bytes(text.encode("utf-8"))
        return self.draft

    def publish(self, snapshot, text=FIRST):
        return sg.save(self.folder, Path(snapshot["snapshot_path"]), self.stage(text))

    # @test-value v2
    # kind = "invariant"
    # claim = "日本語と改行を保持して保存し、同じ内容の再保存は正本を変更しない"
    # oracle = { type = "contract", ref = "skills/session-graph/SKILL.md#共有ファイルの保存" }
    # fault = "文字列の正規化や無条件置換で要求本文と無変更ファイルを変える"
    # observable = "保存後のbytes、snapshot content、再保存のchangedと更新時刻"
    # observation_boundary = "public-boundary"
    # scope = "session-graph-save"
    # lifecycle = "permanent"
    # impact = "ユーザーの否定条件の破損と不要な更新通知"
    # distinction = "構文検査では保存後の文字保持と無変更時の挙動を確認できない"
    # @end-test-value
    def test_roundtrip_and_unchanged_save(self):
        initial = sg.snapshot(self.folder)
        self.assertFalse(initial["exists"])
        text = SECOND.replace("\n", "\r\n")
        self.assertTrue(self.publish(initial, text)["changed"])
        self.assertEqual(self.graph.read_bytes(), text.encode("utf-8"))
        latest = sg.snapshot(self.folder)
        self.assertEqual(latest["content"], text)
        before = self.graph.stat().st_mtime_ns
        self.assertFalse(self.publish(latest, text)["changed"])
        self.assertEqual(self.graph.stat().st_mtime_ns, before)

    # @test-value v2
    # kind = "invariant"
    # claim = "同じsnapshotからの同時保存は1件だけ成功し、再読後の再適用で両方の指示を保持できる"
    # oracle = { type = "contract", ref = "skills/session-graph/SKILL.md#共有ファイルの保存" }
    # fault = "比較と置換の間を排他せず後勝ちで他セッションの指示を消す"
    # observable = "成功と競合の件数、正本の全文、再適用後の両指示"
    # observation_boundary = "public-boundary"
    # scope = "session-graph-concurrency"
    # lifecycle = "permanent"
    # impact = "MainまたはAuxiliaryが記録した要求が失われる"
    # distinction = "単独保存と静的解析では並行した初回作成と更新を検出できない"
    # @end-test-value
    def test_parallel_create_and_update_reject_stale_snapshot(self):
        for existing in (False, True):
            with self.subTest(existing=existing):
                if existing:
                    self.graph.write_bytes(FIRST.encode())
                a, b = sg.snapshot(self.folder), sg.snapshot(self.folder)
                drafts = [self.folder / "a.mmd", self.folder / "b.mmd"]
                texts = [FIRST + '    A["条件A"]\n', FIRST + '    B["条件B"]\n']
                for draft, text in zip(drafts, texts):
                    draft.write_bytes(text.encode())
                def save_one(args):
                    snap, draft = args
                    try:
                        sg.save(self.folder, Path(snap["snapshot_path"]), draft)
                        return "saved"
                    except sg.ConflictError:
                        return "conflict"
                with ThreadPoolExecutor(max_workers=2) as pool:
                    results = list(pool.map(save_one, zip([a, b], drafts)))
                self.assertCountEqual(results, ["saved", "conflict"])
                self.assertIn(self.graph.read_bytes(), [text.encode() for text in texts])
                latest = sg.snapshot(self.folder)
                combined = FIRST + '    A["条件A"]\n    B["条件B"]\n'
                self.publish(latest, combined)
                self.assertEqual(self.graph.read_bytes(), combined.encode())

    # @test-value v2
    # kind = "invariant"
    # claim = "置換失敗時は旧グラフを保持し、エラーを呼出元へ返す"
    # oracle = { type = "contract", ref = "skills/session-graph/SKILL.md#共有ファイルの保存" }
    # fault = "先に正本をtruncateするかI/O失敗を成功と扱う"
    # observable = "OSErrorと失敗直後および再試行後の正本内容"
    # observation_boundary = "public-boundary"
    # scope = "session-graph-save-failure"
    # lifecycle = "permanent"
    # impact = "保存失敗で記録が消え、未記録の指示のまま作業が進む"
    # distinction = "実filesystemの正常保存だけでは置換失敗境界に到達しない"
    # @end-test-value
    def test_replace_failure_preserves_graph(self):
        self.publish(sg.snapshot(self.folder))
        base = sg.snapshot(self.folder)
        with patch.object(sg.os, "replace", side_effect=OSError("disk failure")):
            with self.assertRaises(OSError):
                self.publish(base, SECOND)
        self.assertEqual(self.graph.read_bytes(), FIRST.encode())
        self.assertTrue(self.publish(base, SECOND)["changed"])
        self.assertEqual(self.graph.read_bytes(), SECOND.encode())

    # @test-value v2
    # kind = "invariant"
    # claim = "ロック待ちは打ち切られ、所有プロセスの強制終了後に次の保存ができる"
    # oracle = { type = "contract", ref = "skills/session-graph/SKILL.md#共有ファイルの保存" }
    # fault = "ロックを永久に待つか中断後にも使用中として残す"
    # observable = "子プロセスのtimeoutと終了コード、所有者終了後の正本内容"
    # observation_boundary = "public-boundary"
    # scope = "session-graph-lock"
    # lifecycle = "permanent"
    # impact = "セッションが記録待ちで操作不能になる"
    # distinction = "同一プロセスのmockではOSによる解放と待機上限を検証できない"
    # @end-test-value
    def test_lock_timeout_and_process_exit(self):
        ready = self.folder / "ready"
        source = (
            "import sys,time; from pathlib import Path; "
            f"sys.path.insert(0, {str(SCRIPT.parent)!r}); import session_graph as s\n"
            f"with s.graph_lock(Path({str(self.folder)!r}), 5):\n"
            f"    Path({str(ready)!r}).write_text('ready')\n"
            "    time.sleep(30)\n"
        )
        owner = subprocess.Popen([sys.executable, "-c", source])
        try:
            deadline = time.monotonic() + 5
            while not ready.exists() and time.monotonic() < deadline:
                if owner.poll() is not None:
                    self.fail("lock owner exited before acquiring lock")
                time.sleep(0.02)
            self.assertTrue(ready.exists())
            blocked = subprocess.run(
                [sys.executable, str(SCRIPT), "snapshot", "--session-folder", str(self.folder),
                 "--lock-timeout", "0.1"], capture_output=True, text=True, timeout=5)
            self.assertEqual(blocked.returncode, 2, blocked.stderr)
            self.assertIn("busy", blocked.stderr)
        finally:
            owner.kill()
            owner.wait(timeout=5)
        self.publish(sg.snapshot(self.folder))
        self.assertEqual(self.graph.read_bytes(), FIRST.encode())

    # @test-value v2
    # kind = "invariant"
    # claim = "破損した記録や別Folderのsnapshotは新規グラフとして保存されない"
    # oracle = { type = "contract", ref = "skills/session-graph/SKILL.md#入口と保存先" }
    # fault = "読込失敗を未作成と扱うか別セッションへ誤保存する"
    # observable = "例外と拒否後の両Folderの正本内容"
    # observation_boundary = "public-boundary"
    # scope = "session-graph-input"
    # lifecycle = "permanent"
    # impact = "以前の要求の消失または別セッションの記録の混入"
    # distinction = "文字列の形式検査だけでは読込と保存対象の対応を確認できない"
    # @end-test-value
    def test_corrupt_and_cross_folder_inputs_are_rejected(self):
        for bad in (b"", b"\xff", b"not a graph"):
            self.graph.write_bytes(bad)
            with self.assertRaises(ValueError):
                sg.snapshot(self.folder)
            self.assertEqual(self.graph.read_bytes(), bad)
        self.graph.unlink()
        other = self.folder / "other"
        other.mkdir()
        foreign = sg.snapshot(other)
        local_copy = self.folder / Path(foreign["snapshot_path"]).name
        local_copy.write_bytes(Path(foreign["snapshot_path"]).read_bytes())
        with self.assertRaises(ValueError):
            sg.save(self.folder, local_copy, self.stage())
        self.assertFalse(self.graph.exists())
        self.assertFalse((other / sg.GRAPH_NAME).exists())
        missing = self.folder / "not-provided"
        with self.assertRaises(FileNotFoundError):
            sg.snapshot(missing)
        self.assertFalse(missing.exists())

    # @test-value v2
    # kind = "invariant"
    # claim = "CLIは競合をexit 3で返し、壊れたdraftをexit 2で拒否して正本を保持する"
    # oracle = { type = "contract", ref = "skills/session-graph/SKILL.md#共有ファイルの保存" }
    # fault = "例外の分類を失って成功や競合以外の通常エラーへ誤変換する"
    # observable = "CLI終了コード、JSON snapshot、正本内容"
    # observation_boundary = "consumer"
    # scope = "session-graph-cli"
    # lifecycle = "permanent"
    # impact = "呼出元が古いdraftで続行するか必要な再読を省く"
    # distinction = "関数呼出しだけではCLIの終了コードと入出力契約を検証しない"
    # @end-test-value
    def test_cli_conflict_and_invalid_draft(self):
        def cli(*args):
            return subprocess.run(
                [sys.executable, "-X", "utf8", str(SCRIPT), *args,
                 "--session-folder", str(self.folder)],
                capture_output=True, text=True, encoding="utf-8", timeout=5)
        read = cli("snapshot")
        self.assertEqual(read.returncode, 0, read.stderr)
        old = json.loads(read.stdout)
        self.publish(sg.snapshot(self.folder))
        draft = self.stage(SECOND)
        conflict = cli("save", "--snapshot", old["snapshot_path"], "--input", str(draft))
        self.assertEqual(conflict.returncode, 3, conflict.stderr)
        self.assertEqual(self.graph.read_bytes(), FIRST.encode())
        current = sg.snapshot(self.folder)
        self.stage("```mermaid\n" + SECOND + "```\n")
        invalid = cli("save", "--snapshot", current["snapshot_path"], "--input", str(draft))
        self.assertEqual(invalid.returncode, 2, invalid.stderr)
        self.assertEqual(self.graph.read_bytes(), FIRST.encode())


if __name__ == "__main__":
    unittest.main()
