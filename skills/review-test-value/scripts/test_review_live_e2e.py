"""Explicit paid candidate smoke; never enabled by the ordinary CI."""
from __future__ import annotations

import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
import run_test_value_review as pipeline
from review_resolution import Target


def sample(name, expression):
    return (f'# @test-value v2\n# kind = "contract"\n# claim = "{name} detects an incorrect increment"\n'
            '# oracle = { type = "contract", ref = "contract.md" }\n'
            '# fault = "returning the input without incrementing"\n# observable = "returned integer"\n'
            '# observation_boundary = "public-boundary"\n# scope = "increment"\n'
            '# lifecycle = "permanent"\n# @end-test-value\n'
            f'def {name}():\n    assert {expression} == 2\n')


class LiveReviewTests(unittest.TestCase):
    # @test-value v2
    # kind = "contract"
    # claim = "実CLIの単一reviewで供給済み契約のtestを分類し、不足contextのrecordを正常なBLOCKEDとして返す"
    # oracle = { type = "contract", ref = "skills/review-test-value/references/review-contract-v3.md" }
    # fault = "実workerのschemaか入力境界がoffline mockと異なり、review成立または不足検出に失敗する"
    # observable = "明示実行した二batchのcall数とKEEP_PERMANENT、NEEDS_CONTEXT"
    # observation_boundary = "public-boundary"
    # scope = "single-review-live-boundary"
    # lifecycle = "permanent"
    # @end-test-value
    @unittest.skipUnless(os.environ.get("TEST_VALUE_LIVE_E2E") == "1", "explicit paid E2E only")
    def test_real_cli_closed_inputs_and_context_request(self):
        self.assertEqual(platform.system(), "Windows")
        cli = os.environ.get("TEST_VALUE_CODEX_EXE")
        self.assertTrue(cli and Path(cli).is_absolute())
        with tempfile.TemporaryDirectory() as tmp:
            root, state = Path(tmp) / "repo", Path(tmp) / "state"
            root.mkdir(); state.mkdir()
            def git(*args):
                return subprocess.check_output(["git", *args], cwd=root, text=True, stderr=subprocess.PIPE).strip()
            git("init", "-q"); git("config", "user.name", "Candidate E2E")
            git("config", "user.email", "candidate@example.invalid")
            (root / "contract.md").write_text("increment(x) is a public API returning integer x + 1.\n", encoding="utf-8")
            (root / "api.py").write_text("def increment(x):\n    return x + 1\n", encoding="utf-8")
            git("add", "."); git("commit", "-qm", "base")
            base = git("rev-parse", "HEAD")
            (root / "test_increment.py").write_text("from api import increment\n" + sample("test_increment", "increment(1)"), encoding="utf-8")
            (root / "test_unknown.py").write_text("from opaque_fixture import build_subject\n" + sample("test_unknown", "build_subject().opaque_observation()"), encoding="utf-8")
            target = Target(root, base)
            records = pipeline.extract(target)
            host = pipeline.evidence_template(records, "explicit-e2e", target.snapshot())
            host["risk_context"] = {"tags": [], "summary": "Synthetic increment contract, no external side effects", "context": []}
            for record, item in zip(records, host["records"]):
                item["context"] = [{"source": "repository", "kind": "accepted-contract", "ref": "contract.md", "start_line": None, "end_line": None}]
                if record["locator"]["symbol"] == "test_increment":
                    item["context"].append({"source": "repository", "kind": "SUT", "ref": "api.py", "start_line": None, "end_line": None})
                item["retention"] = {"basis": "SUPPORTED", "reason": "Public increment contract", "evidence_refs": ["contract.md"], "temporal": None}
            evidence = Path(tmp) / "host.json"
            evidence.write_text(json.dumps(host), encoding="utf-8")
            args = pipeline.build_parser().parse_args(["--root", str(root), "--changed-from", base,
                "--task-id", "explicit-e2e", "--state-dir", str(state), "--cli", cli,
                "--host-evidence", str(evidence), "--batch-size", "1", "--max-workers", "2"])
            result = pipeline.run(args)
            self.assertEqual(result["llm_batch_calls"], 2)
            self.assertEqual(result["gate"], "BLOCKED")
            outcomes = {item["locator"]["symbol"]: item for item in result["records"]}
            self.assertIsNone(outcomes["test_increment"]["failure"])
            self.assertEqual(outcomes["test_increment"]["verdict"], "KEEP_PERMANENT")
            self.assertIsNone(outcomes["test_unknown"]["failure"])
            self.assertEqual(outcomes["test_unknown"]["verdict"], "NEEDS_CONTEXT")
            repeated = pipeline.run(args)
            self.assertEqual(repeated["llm_batch_calls"], 0)
            self.assertEqual(repeated["gate"], "BLOCKED")


if __name__ == "__main__":
    unittest.main()
