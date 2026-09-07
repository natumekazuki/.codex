"""Explicit Windows/ChatGPT Pro E2E; ordinary CI never invokes a paid model."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
import run_test_value_review as coordinator
import review_worker

# Independently specified boundary examples; the expected values are not
# calculated with the implementation under review.
CASES = [("0", 0), ("1", 1), ("9", 9), ("10", 10), ("80", 80),
         ("443", 443), ("8080", 8080), ("65534", 65534), ("65535", 65535),
         ("00080", 80), ("00000", 0), ("", None), ("-1", None), ("+1", None),
         ("65536", None), ("999999", None), (" 80", None), ("80 ", None),
         ("1.0", None), ("1e2", None), ("８０", None), ("abc", None)]
CONTRACT = """# Port input contract
Untrusted port text must contain one or more ASCII decimal digits and represent
an integer from 0 through 65535 inclusive. Leading zeroes are accepted. Return
the integer value; reject all other input with ValueError. The fixture's 22
literal examples cover endpoints, leading zeroes, malformed syntax and overflow.
This input validation boundary is the retained contract for every fixture test.
"""
IMPLEMENTATION = '''def parse_port(text):
    if not text or any(ch < "0" or ch > "9" for ch in text):
        raise ValueError("invalid port syntax")
    value = int(text)
    if value > 65535:
        raise ValueError("port out of range")
    return value
'''


def create_fixture(root: Path) -> str:
    root.mkdir()
    (root / "CONTRACT.md").write_text(CONTRACT, encoding="utf-8")
    (root / "port.py").write_text(IMPLEMENTATION, encoding="utf-8")
    def git(*args):
        return subprocess.check_output(["git", *args], cwd=root, text=True, timeout=15,
            env={**os.environ, "GIT_AUTHOR_DATE": "2026-09-07T00:00:00Z",
                 "GIT_COMMITTER_DATE": "2026-09-07T00:00:00Z"}).strip()
    git("init", "-q")
    git("config", "user.name", "Review fixture")
    git("config", "user.email", "fixture@example.invalid")
    git("add", "CONTRACT.md", "port.py")
    # Fixed dates make a fresh-session fixture reproduce the same base commit.
    git("-c", "commit.gpgsign=false", "commit", "-q", "-m", "fixture base")
    base = git("rev-parse", "HEAD")
    source = "import unittest\nfrom port import parse_port\n\nclass PortTests(unittest.TestCase):\n"
    for index, (text, expected) in enumerate(CASES):
        outcome = "ValueError" if expected is None else f"integer {expected}"
        source += f'''
    # @test-value v2
    # kind = "contract"
    # claim = "port case {index:02d} must produce {outcome} under the ASCII port contract"
    # oracle = {{ type = "contract", ref = "CONTRACT.md" }}
    # fault = "port parsing accepts malformed or out-of-range input or changes an accepted value"
    # observable = "parse_port return value or ValueError for the literal input"
    # observation_boundary = "component-behavior"
    # scope = "port-input-validation"
    # lifecycle = "permanent"
    # risk_tags = ["security"]
    # @end-test-value
    def test_port_{index:02d}(self):
'''
        source += (f"        with self.assertRaises(ValueError):\n            parse_port({text!r})\n" if expected is None
                   else f"        self.assertEqual({expected}, parse_port({text!r}))\n")
    (root / "test_ports.py").write_text(source, encoding="utf-8")
    subprocess.run([sys.executable, "-m", "unittest", "test_ports"], cwd=root,
                   check=True, capture_output=True, timeout=15)
    return base


def run_json(argv: list[str], root: Path, seconds: float):
    # Reuse the owned Job Object and shared deadline, including watchdog cleanup.
    start = time.monotonic()
    outcome = review_worker._invoke_runner(review_worker._run_process, argv, "", root,
                                           deadline_monotonic=start + seconds)
    if outcome.timed_out:
        raise AssertionError("E2E coordinator watchdog expired")
    result = json.loads(outcome.stdout.strip().splitlines()[-1])
    return outcome.returncode, result, time.monotonic() - start


@unittest.skipUnless(sys.platform == "win32" and os.environ.get("TEST_VALUE_E2E_CLI")
                     and os.environ.get("TEST_VALUE_E2E_STATE"),
                     "opt-in Windows native CLI/ChatGPT Pro E2E")
class LiveReviewE2ETests(unittest.TestCase):
    # @test-value v2
    # kind = "regression"
    # claim = "22件の固定selectionを実モデル審査しbatch計画内でterminal gateを返す"
    # oracle = { type = "contract", ref = "docs/runbooks/activate-test-value-review.md" }
    # fault = "少数fixtureのstubだけが成功し実モデル22件では期限超過や部分結果成功になる"
    # observable = "native CLIのterminal JSON/exit、計画時間と全22件のrecord ID"
    # observation_boundary = "public-boundary"
    # scope = "review-live-e2e"
    # lifecycle = "permanent"
    # @end-test-value
    def test_22_record_native_cli_review_returns_terminal_contract(self):
        cli = Path(os.environ["TEST_VALUE_E2E_CLI"])
        output = Path(os.environ["TEST_VALUE_E2E_STATE"])
        self.assertTrue(cli.is_absolute() and cli.is_file() and cli.suffix.lower() == ".exe")
        self.assertTrue(output.is_absolute())
        self.assertFalse(output.resolve().is_relative_to(SCRIPTS.parents[2]))
        output.mkdir(parents=True, exist_ok=True)
        # Keep each run for comparison with a separate new Codex session.
        run_dir = Path(tempfile.mkdtemp(prefix="run-", dir=output))
        state = run_dir / "state"
        state.mkdir()
        evidence = {"fixture": "port-22-v1", "model": "gpt-5.6-luna", "effort": "max", "completed": False}
        try:
            root = run_dir / "repo"
            base = create_fixture(root)
            args = [sys.executable, str(SCRIPTS / "run_test_value_review.py"), "--root", str(root),
                    "--changed-from", base, "--state-dir", str(state), "--cli", str(cli)]
            code, prepared, _ = run_json([*args, "--prepare"], root, 180)
            self.assertEqual((code, prepared["reason_codes"]), (2, ["HOST_EVIDENCE_REQUIRED"]))
            identities = prepared["host_evidence_template"]["retention_by_record"]
            ids = [r["record_id"] for r in identities]
            self.assertEqual(len(ids), 22)
            self.assertEqual([b["record_count"] for b in prepared["metadata_execution_plan"]["batches"]], [10, 10, 2])
            host = copy.deepcopy(prepared["host_evidence_template"])
            contract = {"kind": "accepted-contract", "ref": "CONTRACT.md", "content": CONTRACT,
                        "content_hash": coordinator.content_hash(CONTRACT), "source": "repository", "authority": "repository"}
            supported = {**contract, "meaning": "The literal examples observe the port input contract."}
            refs = [{"ref": contract["ref"], "content_hash": contract["content_hash"]}]
            host["task_id"] = "port-22-live"
            host["parent_risk_assessment"] = {"status": "ASSESSED", "risk_tags": ["security"],
                "rationale": "This fixture exercises rejection of untrusted port syntax and bounds.",
                "evidence": [supported], "evidence_refs": refs}
            for record in host["retention_by_record"]:
                record.update(evidence=[supported], determination={"determination": "SUPPORTED",
                    "rationale": "The assertion directly checks the stated accepted boundary.", "evidence_refs": refs})
            implementation = {"kind": "implementation", "ref": "port.py", "content": IMPLEMENTATION,
                              "content_hash": coordinator.content_hash(IMPLEMENTATION), "source": "repository", "authority": "repository"}
            host["context_by_record"] = [{**{k: r[k] for k in ("record_id", "metadata_hash", "source_hash")},
                                           "items": [contract, implementation]} for r in identities]
            host_path = state / "host.json"
            host_path.write_text(json.dumps(host, ensure_ascii=False), encoding="utf-8")
            # This small fixture expects three batches per phase, with no retry
            # context. The additional 180s covers Git/preflight/final publication.
            batch_count = len(prepared["metadata_execution_plan"]["batches"])
            bound = batch_count * sum(coordinator.BATCH_SECONDS.values()) + 3 * coordinator.PHASE_OVERHEAD_SECONDS + 180
            code, result, elapsed = run_json([*args, "--host-evidence", str(host_path)], root, bound)
            plans = [json.loads(p.read_text(encoding="utf-8")) for p in state.glob("execution-plan-*.json")]
            evidence.update(exit_code=code, elapsed_seconds=elapsed, gate=result.get("gate"),
                            reason_codes=result.get("reason_codes", []), plans=plans)
            self.assertTrue(plans, "preflight-only BLOCKED is not a live model run")
            for plan in plans:
                self.assertLessEqual(len(plan["batches"]), batch_count)
                self.assertEqual([rid for batch in plan["batches"] for rid in batch["record_ids"]], ids)
            self.assertLessEqual(elapsed, sum(p["phase_seconds"] for p in plans) + 180)
            self.assertEqual(code, {"PASS": 0, "CHANGES_REQUIRED": 1, "BLOCKED": 2}[result["gate"]])
            if result["gate"] == "BLOCKED":
                # Only a model-stage timeout/result failure is acceptable as an
                # observed terminal contract. Startup/canary failures are not E2E.
                self.assertTrue(set(result["reason_codes"]) <= {"REVIEW_TIMEOUT", "REVIEW_RESULT_VALIDATION_FAILED", "AGGREGATE_BLOCKED"})
                if "AGGREGATE_BLOCKED" in result["reason_codes"]:
                    self.assertEqual([r["record_id"] for r in result["records"]], ids)
            else:
                self.assertEqual([r["record_id"] for r in result["records"]], ids)
            evidence["completed"] = True
        finally:
            (run_dir / "e2e-summary.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
