from __future__ import annotations

from contextlib import redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).with_name("session_graph.py")
spec = importlib.util.spec_from_file_location("session_graph_cleanup", SCRIPT)
sg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sg)
FIRST = 'flowchart TB\n    R["説明の更新"]\n'
SECOND = FIRST + '    C["操作権限を維持"]\n'
INDEX = "index.mmd"


class SessionGraphCleanupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name).resolve()
        self.graph = self.folder / sg.GRAPH_DIR / INDEX
        self.draft = self.folder / (sg.DRAFT_PREFIX + "local.mmd")

    def stage(self, text=FIRST):
        self.draft.write_bytes(text.encode("utf-8"))
        return self.draft

    # @test-value v2
    # kind = "invariant"
    # claim = "保存後と読取のみの後片付けは指定入力だけを削除し、再実行では既にない対象を返す"
    # oracle = { type = "contract", ref = "skills/session-graph/SKILL.md#共有ファイルの保存" }
    # fault = "対象走査で別の入力も削除するか、読取のみ・再実行の入力を扱えない"
    # observable = "CLI終了コードとdeleted、missing、errors、各入力・正本・lockの存在とbytes"
    # observation_boundary = "consumer"
    # scope = "session-graph-cleanup-lifecycle"
    # lifecycle = "permanent"
    # impact = "必要な共有記録や別担当の入力が失われる、または読取のたびに一時ファイルが残る"
    # distinction = "既存の保存testは明示cleanupのCLIと削除範囲を観測しない"
    # @end-test-value
    def test_cleanup_save_readonly_and_repeat_preserve_unselected_files(self):
        initial = sg.snapshot(self.folder, INDEX)
        base = Path(initial["snapshot_path"])
        other = Path(sg.snapshot(self.folder, INDEX)["snapshot_path"])
        other_bytes = other.read_bytes()
        saved = sg.save(self.folder, INDEX, base, self.stage())
        self.assertTrue(saved["changed"])
        self.assertTrue(base.exists())
        self.assertTrue(self.draft.exists())
        outcome = subprocess.run(
            [sys.executable, "-X", "utf8", str(SCRIPT), "cleanup",
             "--session-folder", str(self.folder), "--graph", INDEX,
             "--snapshot", str(base), "--input", str(self.draft)],
            capture_output=True, text=True, encoding="utf-8", timeout=5)
        self.assertEqual(outcome.returncode, 0, outcome.stderr)
        result = json.loads(outcome.stdout)
        self.assertCountEqual(result["deleted"], [str(base), str(self.draft)])
        self.assertEqual(result["errors"], [])
        self.assertFalse(base.exists())
        self.assertFalse(self.draft.exists())
        self.assertEqual(other.read_bytes(), other_bytes)
        self.assertEqual(self.graph.read_bytes(), FIRST.encode())
        self.assertTrue((self.folder / sg.LOCK_NAME).exists())
        read_only = sg.cleanup(self.folder, INDEX, other)
        self.assertEqual(read_only["deleted"], [str(other)])
        self.assertEqual(read_only["errors"], [])
        repeated = sg.cleanup(self.folder, INDEX, base, self.draft)
        self.assertCountEqual(repeated["missing"], [str(base), str(self.draft)])
        self.assertEqual(repeated["errors"], [])
        self.assertEqual(self.graph.read_bytes(), FIRST.encode())

    # @test-value v2
    # kind = "invariant"
    # claim = "cleanupは範囲外・生成名でない入力・対象不一致・不正形式を、他の入力の削除前に拒否する"
    # oracle = { type = "contract", ref = "skills/session-graph/SKILL.md#共有ファイルの保存" }
    # fault = "未検証のpathを削除するか、片方の入力を削除してから他方の不正を検出する"
    # observable = "ValueErrorと拒否後のsnapshot、draft、指定外ファイルのbytes"
    # observation_boundary = "public-boundary"
    # scope = "session-graph-cleanup-target-safety"
    # lifecycle = "permanent"
    # impact = "正本・ユーザー資料・別話題の再適用資料が誤削除される"
    # distinction = "保存pathの検査は新しい削除操作や全入力の事前検証を保証しない"
    # @end-test-value
    def test_cleanup_rejects_invalid_targets_before_any_deletion(self):
        initial = sg.snapshot(self.folder, INDEX)
        base = Path(initial["snapshot_path"])
        self.stage()
        sg.save(self.folder, INDEX, base, self.draft)
        user_file = self.folder / "session-graph.mmd"
        user_file.write_bytes(FIRST.encode())
        nested = self.folder / "nested"
        nested.mkdir()
        nested_draft = nested / self.draft.name
        nested_draft.write_bytes(FIRST.encode())
        outside = tempfile.TemporaryDirectory()
        self.addCleanup(outside.cleanup)
        outside_draft = Path(outside.name).resolve() / self.draft.name
        outside_draft.write_bytes(FIRST.encode())
        for invalid in (self.graph, user_file, self.folder / sg.LOCK_NAME,
                        nested_draft, outside_draft, Path(self.draft.name), self.folder):
            with self.subTest(path=str(invalid)), self.assertRaises(ValueError):
                sg.cleanup(self.folder, INDEX, base, invalid)
            self.assertTrue(base.exists())
            self.assertEqual(self.draft.read_bytes(), FIRST.encode())
        self.assertEqual(user_file.read_bytes(), FIRST.encode())
        self.assertEqual(nested_draft.read_bytes(), FIRST.encode())
        self.assertEqual(outside_draft.read_bytes(), FIRST.encode())
        other_base = Path(sg.snapshot(self.folder, "other.mmd")["snapshot_path"])
        foreign_base = Path(sg.snapshot(Path(outside.name).resolve(), INDEX)["snapshot_path"])
        local_foreign = self.folder / foreign_base.name
        local_foreign.write_bytes(foreign_base.read_bytes())
        for invalid in (other_base, local_foreign):
            with self.subTest(snapshot=str(invalid)), self.assertRaises(ValueError):
                sg.cleanup(self.folder, INDEX, invalid, self.draft)
            self.assertTrue(invalid.exists())
            self.assertEqual(self.draft.read_bytes(), FIRST.encode())
        self.stage("not a graph")
        with self.assertRaises(ValueError):
            sg.cleanup(self.folder, INDEX, base, self.draft)
        self.assertTrue(base.exists())
        self.assertEqual(self.draft.read_bytes(), b"not a graph")
        self.assertEqual(self.graph.read_bytes(), FIRST.encode())

    # @test-value v2
    # kind = "invariant"
    # claim = "生成名でもリンクされたsnapshotとdraftは削除せず、リンク先と他の指定入力を保持する"
    # oracle = { type = "contract", ref = "skills/session-graph/SKILL.md#共有ファイルの保存" }
    # fault = "生成名だけを信用してリンク入力を削除対象にする"
    # observable = "ValueError、リンクの存在、リンク先と指定snapshot・draftのbytes"
    # observation_boundary = "public-boundary"
    # scope = "session-graph-cleanup-link-safety"
    # lifecycle = "permanent"
    # impact = "入力の所在を誤認し、別担当の資料やリンクを失う"
    # distinction = "通常pathの拒否と保存側のlink testはcleanupの実リンク拒否を観測しない"
    # @end-test-value
    def test_cleanup_rejects_linked_inputs(self):
        base = Path(sg.snapshot(self.folder, INDEX)["snapshot_path"])
        self.stage()
        linked_draft = self.folder / (sg.DRAFT_PREFIX + "linked.mmd")
        linked_snapshot = self.folder / (sg.SNAPSHOT_PREFIX + "linked.json")
        try:
            linked_draft.symlink_to(self.draft)
            linked_snapshot.symlink_to(base)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"symlink creation unavailable: {exc}")
        for snapshot, draft in ((base, linked_draft), (linked_snapshot, self.draft)):
            with self.subTest(snapshot=str(snapshot)), self.assertRaises(ValueError):
                sg.cleanup(self.folder, INDEX, snapshot, draft)
            self.assertTrue(linked_draft.is_symlink())
            self.assertTrue(linked_snapshot.is_symlink())
            self.assertTrue(base.exists())
            self.assertEqual(self.draft.read_bytes(), FIRST.encode())

    # @test-value v2
    # kind = "invariant"
    # claim = "削除失敗はexit 2と未削除pathで報告され、成功済み保存を保ち、部分削除後も再実行できる"
    # oracle = { type = "contract", ref = "skills/session-graph/SKILL.md#共有ファイルの保存" }
    # fault = "削除失敗を成功と報告するか、保存を巻き戻すか、部分削除で再実行できなくなる"
    # observable = "mainの終了コードとerrors、deleted、missing、正本・入力のbytesと存在"
    # observation_boundary = "consumer"
    # scope = "session-graph-cleanup-failure"
    # lifecycle = "permanent"
    # impact = "残存ファイルが隠される、または後片付けの失敗で保存済み記録を失う"
    # distinction = "正常な削除や保存失敗testではunlinkの拒否と部分削除を再現しない"
    # @end-test-value
    def test_cleanup_reports_delete_failure_without_invalidating_save(self):
        base = Path(sg.snapshot(self.folder, INDEX)["snapshot_path"])
        saved = sg.save(self.folder, INDEX, base, self.stage())
        unlink = Path.unlink
        def deny_draft(path, *args, **kwargs):
            if path == self.draft:
                raise PermissionError("deletion denied")
            return unlink(path, *args, **kwargs)
        output = io.StringIO()
        with patch.object(sg.Path, "unlink", autospec=True, side_effect=deny_draft), redirect_stdout(output):
            code = sg.main(["cleanup", "--session-folder", str(self.folder),
                            "--graph", INDEX, "--snapshot", str(base),
                            "--input", str(self.draft)])
        result = json.loads(output.getvalue())
        self.assertEqual(code, 2)
        self.assertEqual(result["errors"], [{"path": str(self.draft), "error": "deletion denied"}])
        self.assertEqual(result["deleted"], [str(base)])
        self.assertTrue(saved["changed"])
        self.assertEqual(self.graph.read_bytes(), FIRST.encode())
        self.assertEqual(self.draft.read_bytes(), FIRST.encode())
        retry = sg.cleanup(self.folder, INDEX, base, self.draft)
        self.assertEqual(retry["deleted"], [str(self.draft)])
        self.assertEqual(retry["missing"], [str(base)])
        self.assertEqual(retry["errors"], [])
        self.assertEqual(self.graph.read_bytes(), FIRST.encode())

    # @test-value v2
    # kind = "invariant"
    # claim = "競合したsaveは入力を自動削除せず保持し、再適用後に明示cleanupできる"
    # oracle = { type = "contract", ref = "skills/session-graph/SKILL.md#共有ファイルの保存" }
    # fault = "save失敗時に入力を自動削除して再適用資料を失う"
    # observable = "ConflictError、失敗直後の入力bytes、再適用後の正本と明示cleanup結果"
    # observation_boundary = "public-boundary"
    # scope = "session-graph-cleanup-reapply"
    # lifecycle = "permanent"
    # impact = "共有編集の競合解消に必要な自分の変更や読込元が失われる"
    # distinction = "既存の競合testは失敗後の入力保持と明示cleanupの境界をassertしない"
    # @end-test-value
    def test_conflicting_save_retains_inputs_for_reapplication(self):
        stale = Path(sg.snapshot(self.folder, INDEX)["snapshot_path"])
        current = Path(sg.snapshot(self.folder, INDEX)["snapshot_path"])
        sg.save(self.folder, INDEX, current, self.stage())
        self.stage(SECOND)
        stale_bytes = stale.read_bytes()
        with self.assertRaises(sg.ConflictError):
            sg.save(self.folder, INDEX, stale, self.draft)
        self.assertEqual(stale.read_bytes(), stale_bytes)
        self.assertEqual(self.draft.read_bytes(), SECOND.encode())
        self.assertEqual(self.graph.read_bytes(), FIRST.encode())
        reread = Path(sg.snapshot(self.folder, INDEX)["snapshot_path"])
        sg.save(self.folder, INDEX, reread, self.draft)
        self.assertEqual(self.graph.read_bytes(), SECOND.encode())
        self.assertEqual(sg.cleanup(self.folder, INDEX, reread, self.draft)["errors"], [])
        self.assertEqual(sg.cleanup(self.folder, INDEX, stale)["errors"], [])


if __name__ == "__main__":
    unittest.main()
