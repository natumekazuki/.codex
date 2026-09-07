"""Contracts for the single semantic pipeline; fake transport is not live review."""
from __future__ import annotations

import copy
from datetime import date
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import run_test_value_review as pipeline
import review_worker as worker
from build_review_packets import digest, make_batches, model_input, selected_records
from extract_test_values import ADAPTER_PROFILES, sha256_text
from review_resolution import Target, record_gate, load_state, save_state, state_lock
from validate_review_result import (CONTRACT_VERSION, ReviewError, VERDICTS, bind_response,
                                    response_schema, validate_response)


def answer(count, verdict="KEEP_PERMANENT"):
    return {"reviews": [{"ordinal": i, "verdict": verdict, "summary": "", "findings": [],
                         "context_request": None} for i in range(count)]}


def metadata(name, *, version=2):
    fields = [f"# @test-value v{version}", '# kind = "contract"', f'# claim = "{name} observes the increment"',
              '# oracle = { type = "contract", ref = "contract.md" }',
              '# scope = "increment"', '# lifecycle = "permanent"']
    if version == 2:
        fields += ['# fault = "returning the unchanged input"', '# observable = "returned integer"',
                   '# observation_boundary = "public-boundary"']
    else:
        fields += ['# failure_mode = "returning the unchanged input"']
    return "\n".join([*fields, '# @end-test-value', f'def {name}():', '    assert 1 + 1 == 2', ''])


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "repo"
        self.root.mkdir()
        self.state = Path(self.tmp.name) / "state"
        self.state.mkdir()
        self.hostfile = Path(self.tmp.name) / "host.json"
        self.git("init", "-q")
        self.git("config", "user.name", "Test")
        self.git("config", "user.email", "test@example.invalid")
        (self.root / "contract.md").write_text("The public increment operation returns input + 1.\n")
        self.git("add", ".")
        self.git("commit", "-qm", "base")
        self.base = self.git("rev-parse", "HEAD").strip()
        self.args = pipeline.build_parser().parse_args([
            "--root", str(self.root), "--changed-from", self.base,
            "--task-id", "test-task", "--state-dir", str(self.state),
            "--cli", "unused.exe", "--host-evidence", str(self.hostfile),
            "--batch-size", "2", "--max-workers", "2",
        ])

    def git(self, *args):
        return subprocess.check_output(["git", *args], cwd=self.root, text=True, stderr=subprocess.PIPE)

    def write_tests(self, count):
        (self.root / "test_feature.py").write_text("\n".join(metadata(f"test_{i}") for i in range(count)), encoding="utf-8")

    def host(self):
        target = Target(self.root, self.base, "staged" if self.args.staged else "head" if self.args.head else "working", self.args.head)
        records = pipeline.extract(target)
        value = pipeline.evidence_template(records, "test-task", target.snapshot())
        value["risk_context"] = {"tags": ["authorization"], "summary": "Explicit task risk", "context": []}
        for entry in value["records"]:
            entry["context"] = [{"source": "repository", "ref": "contract.md", "kind": "accepted-contract",
                                 "start_line": None, "end_line": None}]
            entry["retention"] = {"basis": "SUPPORTED", "reason": "Protect the accepted increment contract",
                                  "evidence_refs": ["contract.md"], "temporal": None}
        self.store(value)
        return value

    def store(self, value):
        self.hostfile.write_text(json.dumps(value), encoding="utf-8")

    def run_pipeline(self, function):
        return pipeline.run(self.args, worker=function, preparer=lambda **_: {"identity": "fixed-worker"})

    # @test-value v2
    # kind = "contract"
    # claim = "全verdictの診断fieldは空値を含めてschemaとvalidatorが同じ形を受理し、ordinalからhost identityを付与する"
    # oracle = { type = "contract", ref = "skills/review-test-value/references/review-contract-v3.md" }
    # fault = "phase固有の空値条件やモデル出力順序で有効な意味判定を拒否する"
    # observable = "schema検証の成功とhostが付与したrecord_idの順序"
    # observation_boundary = "component-behavior"
    # scope = "single-review-flat_schema_accepts_all_diagnostic_combinations_and_binds_ordinals"
    # lifecycle = "permanent"
    # @end-test-value
    def test_flat_schema_accepts_all_diagnostic_combinations_and_binds_ordinals(self):
        import jsonschema
        schema = response_schema()
        for verdict in VERDICTS:
            for summary in ("", "reason"):
                for findings in ([], ["specific finding"]):
                    for context in (None, "", "missing fixture"):
                        result = answer(2, verdict)
                        for item in result["reviews"]:
                            item.update(summary=summary, findings=findings, context_request=context)
                        result["reviews"].reverse()
                        jsonschema.validate(result, schema)
                        self.assertEqual([x["ordinal"] for x in validate_response(result, 2)], [0, 1])
        integral = answer(1)
        integral["reviews"][0]["ordinal"] = 0.0
        jsonschema.validate(integral, schema)
        self.assertEqual(validate_response(integral, 1)[0]["ordinal"], 0)
        records = [{"record_id": f"host-{i}", "metadata_hash": "m", "source_hash": "s", "input_hash": "input"} for i in range(2)]
        bound = bind_response({"reviews": list(reversed(answer(2)["reviews"]))}, records)
        self.assertEqual([x["record_id"] for x in bound], ["host-0", "host-1"])
        self.assertNotIn("ordinal", bound[0])

    # @test-value v2
    # kind = "contract"
    # claim = "型・未知verdict・余分なfieldと欠落重複範囲外ordinalを異なる失敗分類で拒否する"
    # oracle = { type = "contract", ref = "skills/review-test-value/references/review-contract-v3.md" }
    # fault = "不正なmodel出力を正常verdictとして集約する"
    # observable = "ReviewErrorのcategory"
    # observation_boundary = "component-behavior"
    # scope = "single-review-malformed_response_and_ordinal_failures_are_not_semantic_verdicts"
    # lifecycle = "permanent"
    # @end-test-value
    def test_malformed_response_and_ordinal_failures_are_not_semantic_verdicts(self):
        for mutate, category in (
            (lambda r: r["reviews"].pop(), "ordinal"),
            (lambda r: r["reviews"][1].update(ordinal=0), "ordinal"),
            (lambda r: r["reviews"][1].update(ordinal=2), "ordinal"),
            (lambda r: r["reviews"][0].update(ordinal=True), "response_schema"),
            (lambda r: r["reviews"][0].update(verdict="APPROVE"), "response_schema"),
            (lambda r: r["reviews"][0].update(input_hash="echo"), "response_schema"),
        ):
            value = answer(2)
            mutate(value)
            with self.assertRaises(ReviewError) as caught:
                validate_response(value, 2)
            self.assertEqual(caught.exception.category, category)

    # @test-value v2
    # kind = "contract"
    # claim = "5recordをsize2の独立batchで並列reviewし、3callだけで全recordを集約する"
    # oracle = { type = "contract", ref = "skills/review-test-value/references/review-contract-v3.md" }
    # fault = "phaseやauditが追加されるかbatch結果を取りこぼす"
    # observable = "call数・同時実行数・closed inputの内容とaggregate gate"
    # observation_boundary = "component-behavior"
    # scope = "single-review-parallel_batches_have_one_call_each_and_one_closed_input"
    # lifecycle = "permanent"
    # @end-test-value
    def test_parallel_batches_have_one_call_each_and_one_closed_input(self):
        self.write_tests(5)
        self.host()
        seen, active, peak = [], 0, 0
        lock = threading.Lock()
        def fake(packet, **kwargs):
            nonlocal active, peak
            with lock:
                seen.append(packet)
                active += 1
                peak = max(peak, active)
            time.sleep(.04)
            with lock:
                active -= 1
            return {"reviews": list(reversed(answer(len(packet["records"]))["reviews"]))}
        result = self.run_pipeline(fake)
        self.assertEqual(result["gate"], "PASS")
        self.assertEqual((len(seen), result["llm_batch_calls"], peak), (3, 3, 2))
        self.assertEqual(sorted(len(x["records"]) for x in seen), [1, 2, 2])
        for packet in seen:
            for item in packet["records"]:
                self.assertEqual(set(item), {"ordinal", "metadata", "metadata_format", "test_source", "locator", "change_kind", "context", "risk_context", "artifact"})
                self.assertIn("authorization", item["risk_context"]["tags"])
                self.assertIn("assert", item["test_source"])
                self.assertIn("input + 1", item["context"][0]["content"])
        stored = (self.state / "review-state.json").read_text()
        self.assertNotIn("assert 1 + 1", stored)
        self.assertNotIn(str(self.root), stored)

    # @test-value v2
    # kind = "contract"
    # claim = "不足contextを追加したrecordだけ再reviewし、同じinputのNEEDS_CONTEXTは自動retryしない"
    # oracle = { type = "contract", ref = "skills/review-test-value/references/review-contract-v3.md" }
    # fault = "同一recordのvariance retryや解決済みrecordの再実行が起こる"
    # observable = "workerに渡したsymbol一覧とgate・call数"
    # observation_boundary = "component-behavior"
    # scope = "single-review-context_addition_rereviews_only_the_affected_record"
    # lifecycle = "permanent"
    # @end-test-value
    def test_context_addition_rereviews_only_the_affected_record(self):
        self.write_tests(3)
        host = self.host()
        seen = []
        def fake(packet, **kwargs):
            seen.extend(x["locator"]["symbol"] for x in packet["records"])
            value = answer(len(packet["records"]))
            for item, review in zip(packet["records"], value["reviews"]):
                if item["locator"]["symbol"] == "test_1" and len(item["context"]) == 1:
                    review["verdict"] = "NEEDS_CONTEXT"
            return value
        first = self.run_pipeline(fake)
        self.assertEqual(first["gate"], "BLOCKED")
        self.assertEqual(len(seen), 3)
        unchanged = self.run_pipeline(fake)
        self.assertEqual((unchanged["gate"], unchanged["llm_batch_calls"], len(seen)), ("BLOCKED", 0, 3))
        host["records"][1]["context"].append({"source": "host-observed", "kind": "accepted-contract",
            "ref": "task:extra", "authority": "explicit-user-requirement", "content": "The assertion must observe the returned value."})
        self.store(host)
        after = self.run_pipeline(fake)
        self.assertEqual((after["gate"], after["llm_batch_calls"]), ("PASS", 1))
        self.assertEqual(seen, ["test_0", "test_1", "test_2", "test_1"])

    # @test-value v2
    # kind = "contract"
    # claim = "timeoutを非意味的失敗として保存し、同じinputは明示したtransport retryだけで再実行する"
    # oracle = { type = "contract", ref = "skills/review-test-value/references/review-contract-v3.md" }
    # fault = "timeoutをverdictへ変換するか通常再開でmodelを再実行する"
    # observable = "failure categoryとbatch indexおよびcall数"
    # observation_boundary = "component-behavior"
    # scope = "single-review-failure_is_saved_without_automatic_variance_retry"
    # lifecycle = "permanent"
    # @end-test-value
    def test_failure_is_saved_without_automatic_variance_retry(self):
        self.write_tests(2)
        self.host()
        calls = []
        def failing(packet, **kwargs):
            calls.append(1)
            raise ReviewError("timeout", "REVIEW_TIMEOUT")
        first = self.run_pipeline(failing)
        self.assertEqual(first["gate"], "BLOCKED")
        self.assertEqual(first["records"][0]["failure"], {"category": "timeout", "code": "REVIEW_TIMEOUT", "batch_index": 0})
        second = self.run_pipeline(failing)
        self.assertEqual((second["llm_batch_calls"], len(calls)), (0, 1))
        self.args.retry_transport = True
        self.run_pipeline(failing)
        self.assertEqual(len(calls), 2)

    # @test-value v2
    # kind = "contract"
    # claim = "一つのbatchのordinal失敗で全体はBLOCKEDになり他の完了recordを再実行しない"
    # oracle = { type = "contract", ref = "skills/review-test-value/references/review-contract-v3.md" }
    # fault = "部分成功を全体PASSにするか成功済みbatchを再実行する"
    # observable = "record別gate・failure category・次runのcall数"
    # observation_boundary = "component-behavior"
    # scope = "single-review-schema_failure_in_one_batch_preserves_other_results"
    # lifecycle = "permanent"
    # @end-test-value
    def test_schema_failure_in_one_batch_preserves_other_results(self):
        self.write_tests(3)
        self.host()
        def fake(packet, **kwargs):
            return answer(0 if len(packet["records"]) == 1 else 2)
        first = self.run_pipeline(fake)
        self.assertEqual(first["gate"], "BLOCKED")
        self.assertEqual([x["gate"] for x in first["records"]], ["PASS", "PASS", "BLOCKED"])
        self.assertEqual(first["records"][2]["failure"]["category"], "ordinal")
        second = self.run_pipeline(lambda *a, **k: self.fail("unchanged input must not call a model"))
        self.assertEqual(second["llm_batch_calls"], 0)

    # @test-value v2
    # kind = "contract"
    # claim = "空selectionと旧candidate stateをreview成功として扱わない"
    # oracle = { type = "contract", ref = "skills/review-test-value/references/review-contract-v3.md" }
    # fault = "対象がないことや旧stateを新形式の合格として利用する"
    # observable = "emptyのBLOCKEDとOLD_CANDIDATE_STATE"
    # observation_boundary = "component-behavior"
    # scope = "single-review-empty_selection_and_legacy_state_never_pass"
    # lifecycle = "permanent"
    # @end-test-value
    def test_empty_selection_and_legacy_state_never_pass(self):
        self.host()
        value = self.run_pipeline(lambda *a, **k: self.fail("empty selection"))
        self.assertEqual((value["gate"], value["reason_codes"]), ("BLOCKED", ["EMPTY_SELECTION"]))
        (self.state / "task-manifest.json").write_text("{}")
        with self.assertRaises(ReviewError) as caught:
            self.run_pipeline(lambda *a, **k: self.fail("old state"))
        self.assertEqual(caught.exception.code, "OLD_CANDIDATE_STATE")

    # @test-value v2
    # kind = "contract"
    # claim = "中断したbatchと失われたcanonical stateを忘れず非成功として再開する"
    # oracle = { type = "contract", ref = "skills/review-test-value/references/review-contract-v3.md" }
    # fault = "記録紛失後に空の成功状態を初期化する"
    # observable = "再開gate・call数とSTATE_MISSING"
    # observation_boundary = "component-behavior"
    # scope = "single-review-lost_state_and_interrupted_batch_are_not_forgotten"
    # lifecycle = "permanent"
    # @end-test-value
    def test_lost_state_and_interrupted_batch_are_not_forgotten(self):
        self.write_tests(1)
        self.host()
        self.run_pipeline(lambda packet, **kw: answer(1))
        path = self.state / "review-state.json"
        state = json.loads(path.read_text())
        entry = next(iter(state["records"].values()))
        entry.update(review=None, gate="BLOCKED", failure={"category": "transport", "code": "INTERRUPTED_BATCH"})
        save_state(self.state, state)
        result = self.run_pipeline(lambda *a, **k: self.fail("interrupted is not an automatic retry"))
        self.assertEqual((result["gate"], result["llm_batch_calls"]), ("BLOCKED", 0))
        path.unlink()
        with self.assertRaises(ReviewError) as caught:
            self.run_pipeline(lambda *a, **k: self.fail("lost state"))
        self.assertEqual(caught.exception.code, "STATE_MISSING")

    # @test-value v2
    # kind = "contract"
    # claim = "KEEPは保持根拠と現行lifecycleをhostで検証し期限切れや未確認条件をPASSにしない"
    # oracle = { type = "contract", ref = "skills/review-test-value/references/review-contract-v3.md" }
    # fault = "modelのKEEPだけで保持条件不足を救済する"
    # observable = "host record gateと期限診断"
    # observation_boundary = "component-behavior"
    # scope = "single-review-keep_requires_host_retention_and_nonexpired_lifecycle"
    # lifecycle = "permanent"
    # @end-test-value
    def test_keep_requires_host_retention_and_nonexpired_lifecycle(self):
        self.write_tests(1)
        host = self.host()
        target = Target(self.root, self.base)
        record = pipeline.extract(target)[0]
        records, hosts = pipeline.build_inputs(target, [record], host, "test-task", target.snapshot())
        evidence = hosts[record["record_id"]]
        today = date(2026, 9, 7)
        self.assertEqual(record_gate(record, "KEEP_PERMANENT", evidence, target, target.snapshot(), today)[0], "PASS")
        evidence["retention"]["basis"] = "UNRESOLVED"
        self.assertEqual(record_gate(record, "KEEP_PERMANENT", evidence, target, target.snapshot(), today)[0], "BLOCKED")
        evidence["retention"]["basis"] = "SUPPORTED"
        record["metadata"].update(lifecycle="characterization", expires_on="2026-09-07")
        self.assertEqual(record_gate(record, "KEEP_TEMPORARY", evidence, target, target.snapshot(), today), ("CHANGES_REQUIRED", "TEMPORARY_EXPIRED"))
        record["metadata"]["expires_on"] = "2026-09-08"
        self.assertEqual(record_gate(record, "KEEP_TEMPORARY", evidence, target, target.snapshot(), today)[0], "PASS")
        record["metadata"]["review_when"] = "public contract changes"
        self.assertEqual(record_gate(record, "KEEP_TEMPORARY", evidence, target, target.snapshot(), today)[0], "BLOCKED")

    # @test-value v2
    # kind = "contract"
    # claim = "削除した有効なv1は元metadataで審査し、削除根拠の検証後だけ完了する"
    # oracle = { type = "contract", ref = "skills/review-test-value/references/review-contract-v3.md" }
    # fault = "過去v1へv2を要求するか削除のみで合格にする"
    # observable = "model-visible旧metadataとresolution前後のgate"
    # observation_boundary = "component-behavior"
    # scope = "single-review-deleted_v1_is_reviewed_without_inventing_v2_fields"
    # lifecycle = "permanent"
    # @end-test-value
    def test_deleted_v1_is_reviewed_without_inventing_v2_fields(self):
        self.write_tests(0)
        (self.root / "test_old.py").write_text(metadata("test_old", version=1))
        self.git("add", ".")
        self.git("commit", "-qm", "historical v1")
        self.base = self.git("rev-parse", "HEAD").strip()
        self.args.changed_from = self.base
        (self.root / "test_old.py").unlink()
        host = self.host()
        host["records"][0]["retention"].update(basis="UNSUPPORTED", reason="Task contract does not require this obsolete assertion")
        self.store(host)
        seen = []
        def fake(packet, **kwargs):
            seen.append(packet)
            return answer(1, "DROP")
        first = self.run_pipeline(fake)
        self.assertEqual(first["gate"], "CHANGES_REQUIRED")
        item = seen[0]["records"][0]
        self.assertEqual((item["metadata_format"], item["change_kind"]), (1, "DELETED"))
        self.assertIn("failure_mode", item["metadata"])
        self.assertNotIn("observable", item["metadata"])
        host["records"][0]["resolution"] = {"action": "DROP", "snapshot_hash": host["snapshot_hash"],
            "reason_kind": "NO_ALTERNATIVE_REQUIRED", "reason": "Approved task contract has no need for this check",
            "evidence_refs": ["contract.md"], "target": None, "check": None}
        self.store(host)
        self.assertEqual(self.run_pipeline(fake)["gate"], "PASS")

    # @test-value v2
    # kind = "contract"
    # claim = "policy checkへの移設は現存する移設先と現snapshotの成功receiptが必要"
    # oracle = { type = "contract", ref = "skills/review-test-value/references/review-contract-v3.md" }
    # fault = "架空の移設先や古いreceiptを合格にする"
    # observable = "移設gateのCHANGES_REQUIREDとPASS"
    # observation_boundary = "component-behavior"
    # scope = "single-review-move_requires_actual_target_and_snapshot_bound_success"
    # lifecycle = "permanent"
    # @end-test-value
    def test_move_requires_actual_target_and_snapshot_bound_success(self):
        self.write_tests(1)
        host = self.host()
        target = Target(self.root, self.base)
        record = pipeline.extract(target)[0]
        _, hosts = pipeline.build_inputs(target, [record], host, "test-task", target.snapshot())
        evidence = hosts[record["record_id"]]
        verdict = "MOVE_TO_POLICY_CHECK"
        self.assertEqual(record_gate(record, verdict, evidence, target, target.snapshot(), date.today())[0], "CHANGES_REQUIRED")
        record["change_kind"] = "DELETED"
        snapshot = target.snapshot()
        evidence["resolution"] = {"action": verdict, "snapshot_hash": snapshot, "reason_kind": "POLICY_CHECK",
            "reason": "Policy artifact checks the declaration", "evidence_refs": ["contract.md"],
            "target": {"ref": "missing.policy", "content_hash": sha256_text("policy")},
            "check": {"snapshot_hash": snapshot, "target_hash": sha256_text("policy"), "exit_code": 0, "output_hash": sha256_text("ok")}}
        self.assertEqual(record_gate(record, verdict, evidence, target, snapshot, date.today())[0], "CHANGES_REQUIRED")
        (self.root / "check.policy").write_text("policy")
        evidence["resolution"]["target"]["ref"] = "check.policy"
        snapshot = target.snapshot()
        evidence["resolution"]["snapshot_hash"] = snapshot
        evidence["resolution"]["check"]["snapshot_hash"] = snapshot
        self.assertEqual(record_gate(record, verdict, evidence, target, snapshot, date.today())[0], "PASS")
        evidence["resolution"]["check"]["snapshot_hash"] = "old"
        self.assertEqual(record_gate(record, verdict, evidence, target, snapshot, date.today())[0], "CHANGES_REQUIRED")

    # @test-value v2
    # kind = "contract"
    # claim = "stagedとheadの審査は対応Git snapshotを使い未stageの壊れた本文を読まない"
    # oracle = { type = "contract", ref = "skills/review-test-value/references/review-contract-v3.md" }
    # fault = "working treeを混ぜて審査対象を変える"
    # observable = "固定Git modeでの正常gate"
    # observation_boundary = "component-behavior"
    # scope = "single-review-fixed_commit_and_index_ignore_unstaged_test_mutations"
    # lifecycle = "permanent"
    # @end-test-value
    def test_fixed_commit_and_index_ignore_unstaged_test_mutations(self):
        self.write_tests(1)
        self.git("add", ".")
        self.args.staged = True
        self.host()
        (self.root / "test_feature.py").write_text("invalid Python ???")
        result = self.run_pipeline(lambda packet, **kw: answer(len(packet["records"])))
        self.assertEqual(result["gate"], "PASS")
        self.git("commit", "-qm", "target")
        self.args.staged = False
        self.args.head = self.git("rev-parse", "HEAD").strip()
        self.args.state_dir = Path(self.tmp.name) / "head-state"
        self.args.state_dir.mkdir()
        self.host()
        self.assertEqual(self.run_pipeline(lambda packet, **kw: answer(len(packet["records"])))['gate'], "PASS")

    # @test-value v2
    # kind = "contract"
    # claim = "通常batchはtoolを無効にした単一transport callで結果を返しtool eventを拒否する"
    # oracle = { type = "contract", ref = "skills/review-test-value/references/review-contract-v3.md" }
    # fault = "canary callやtool実行が通常経路へ入り込む"
    # observable = "argvのtool制約・call数・unexpected tool失敗"
    # observation_boundary = "component-behavior"
    # scope = "single-review-worker_has_one_transport_call_and_no_normal_tool_activity"
    # lifecycle = "permanent"
    # @end-test-value
    def test_worker_has_one_transport_call_and_no_normal_tool_activity(self):
        preparation = {"cli": "codex.exe", "role": {"model": "gpt-5.6-luna", "model_reasoning_effort": "max"},
                       "instructions": "Review data", "files": {}, "environment": {}}
        calls = []
        value = answer(1, "NEEDS_CONTEXT")
        events = [{"type": "item.completed", "item": {"type": "agent_message", "text": json.dumps(value)}}, {"type": "turn.completed"}]
        def transport(argv, text, cwd, deadline, cancel, env):
            calls.append((argv, text))
            self.assertGreater(deadline, time.monotonic())
            self.assertTrue((cwd / "result-schema.json").exists())
            return worker.ProcessOutcome(0, "\n".join(json.dumps(x) for x in events), "")
        with mock.patch.object(worker, "_check_managed_inputs"), mock.patch.object(worker, "_scratch_inputs"):
            result = worker.execute_review({"records": [{"ordinal": 0}]}, preparation=preparation, runner=transport)
        self.assertEqual(result, value)
        self.assertEqual(len(calls), 1)
        argv = calls[0][0]
        for feature in ("shell_tool", "unified_exec", "multi_agent", "apps", "plugins"):
            position = argv.index(feature)
            self.assertEqual(argv[position - 1], "--disable")
        self.assertIn("--strict-config", argv)
        with self.assertRaises(ReviewError) as caught:
            worker.parse_transport(worker.ProcessOutcome(0, json.dumps({"type": "item.completed", "item": {"type": "command_execution"}}), ""))
        self.assertEqual(caught.exception.category, "transport")

    # @test-value v2
    # kind = "security"
    # claim = "root外contextと古いhost snapshotをLLMへ渡す前に拒否する"
    # oracle = { type = "contract", ref = "skills/review-test-value/references/review-contract-v3.md" }
    # fault = "外部fileや別snapshotの根拠を閉じたreview inputへ混入する"
    # observable = "input失敗分類とworker未呼出し"
    # observation_boundary = "component-behavior"
    # scope = "single-review-context-boundary"
    # lifecycle = "permanent"
    # @end-test-value
    def test_bad_context_and_stale_snapshot_stop_before_model(self):
        self.write_tests(1)
        initial = self.host()
        outside = Path(self.tmp.name) / "outside.txt"
        outside.write_text("private outside content")
        calls = []
        for entry in ({"source": "repository", "ref": "../outside.txt", "kind": "helper",
                       "start_line": None, "end_line": None}, None):
            value = copy.deepcopy(initial)
            if entry is not None:
                value["records"][0]["context"].append(entry)
            else:
                value["snapshot_hash"] = "stale"
            self.store(value)
            with self.assertRaises(ReviewError) as caught:
                self.run_pipeline(lambda *a, **kw: calls.append(a))
            self.assertEqual(caught.exception.category, "input")
            self.assertNotIn("private outside", json.dumps(caught.exception.diagnostic()))
        self.assertEqual(calls, [])

    # @test-value v2
    # kind = "regression"
    # claim = "追加testを消しても過去REDESIGNを空selectionとして合格にしない"
    # oracle = { type = "contract", ref = "skills/review-test-value/references/review-contract-v3.md" }
    # fault = "現在の対象だけで集約し未解消の過去判定を失う"
    # observable = "削除後のCHANGES_REQUIREDと追加LLM callゼロ"
    # observation_boundary = "component-behavior"
    # scope = "single-review-historical-obligation"
    # lifecycle = "permanent"
    # @end-test-value
    def test_historical_redesign_survives_empty_selection(self):
        self.write_tests(1)
        self.host()
        first = self.run_pipeline(lambda packet, **kw: answer(len(packet["records"]), "REDESIGN"))
        self.assertEqual(first["gate"], "CHANGES_REQUIRED")
        (self.root / "test_feature.py").unlink()
        self.host()
        worker_call = mock.Mock(side_effect=AssertionError("no new review input"))
        result = self.run_pipeline(worker_call)
        self.assertEqual(result["gate"], "CHANGES_REQUIRED")
        self.assertEqual(result["records"][0]["reason_code"], "HISTORICAL_REDESIGN")
        self.assertEqual(result["llm_batch_calls"], 0)
        worker_call.assert_not_called()

    # @test-value v2
    # kind = "contract"
    # claim = "batch入力予算を超えたとき対象を切り捨てずモデル呼出し前に停止する"
    # oracle = { type = "contract", ref = "skills/review-test-value/references/review-contract-v3.md" }
    # fault = "文字数制限に合わせてrecordを欠落させるか未検証の一部を送信する"
    # observable = "BATCH_INPUT_TOO_LARGEと失敗batch index"
    # observation_boundary = "component-behavior"
    # scope = "single-review-batch-budget"
    # lifecycle = "permanent"
    # @end-test-value
    def test_batch_budget_rejects_without_partial_partition(self):
        records = [{"material": {"test_source": "small"}}, {"material": {"test_source": "x" * 1000}}]
        with self.assertRaises(ReviewError) as caught:
            make_batches(records, 1, max_chars=100)
        self.assertEqual(caught.exception.code, "BATCH_INPUT_TOO_LARGE")
        self.assertEqual(caught.exception.location, {"batch_index": 1})
        self.assertEqual(len(records), 2)


if __name__ == "__main__":
    unittest.main()
