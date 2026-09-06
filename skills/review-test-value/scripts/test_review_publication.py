"""Regression for a review interrupted before generation publication."""
from __future__ import annotations

import sys
from pathlib import Path
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import run_test_value_review as coordinator


class ReviewPublicationTests(unittest.TestCase):
    # @test-value v2
    # kind = "regression"
    # claim = "未登録generationがある再開は停止し、保存済み審査記録を変更しない"
    # oracle = { type = "contract", ref = "docs/runbooks/activate-test-value-review.md" }
    # fault = "manifest更新前に中断した記録を無視して次のgenerationへ進む"
    # observable = "再開時のSTATE_UNPUBLISHED_GENERATIONと保存済みファイルの内容"
    # observation_boundary = "component-behavior"
    # scope = "test-value-publication-recovery"
    # lifecycle = "permanent"
    # @end-test-value
    def test_unpublished_generation_blocks_resume_without_erasing_evidence(self):
        for has_result in (False, True):
            with self.subTest(has_result=has_result), tempfile.TemporaryDirectory() as tmp:
                state_dir = Path(tmp)
                kwargs = dict(task_id="review", root=state_dir / "repo", base_oid="a" * 40, mode="working")
                initial = coordinator._load_or_initialize_task(state_dir, **kwargs)
                orphan = state_dir / "generations" / "g000001"
                orphan.mkdir(parents=True)
                if has_result:
                    (orphan / "generation.json").write_text('{"gate":"CHANGES_REQUIRED"}', encoding="utf-8")
                manifest_before = (state_dir / "task-manifest.json").read_bytes()
                with self.assertRaises(coordinator.CoordinatorBlocked) as failure:
                    coordinator._load_or_initialize_task(state_dir, **kwargs)
                self.assertEqual(failure.exception.reason_code, "STATE_UNPUBLISHED_GENERATION")
                self.assertEqual((state_dir / "task-manifest.json").read_bytes(), manifest_before)
                self.assertTrue(orphan.is_dir())
                if has_result:
                    self.assertEqual((orphan / "generation.json").read_text(), '{"gate":"CHANGES_REQUIRED"}')
                # A normally published directory still resumes; the loader below
                # checks the generation contents separately.
                initial["generations"] = [{"generation_id": "g000001", "generation_path": "generations/g000001/generation.json"}]
                coordinator._atomic_write(state_dir / "task-manifest.json", initial)
                self.assertEqual(coordinator._load_or_initialize_task(state_dir, **kwargs), initial)


if __name__ == "__main__":
    unittest.main()
