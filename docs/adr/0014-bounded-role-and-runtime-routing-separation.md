# ADR-0014: bounded roleとruntime routingの責務を分離する

- Status: accepted
- Date: 2026-08-08
- Amends: ADR-0002, ADR-0013
- Related: ADR-0004, ADR-0011, ADR-0012

## Context

実装roleはSparkの小規模変更とSolの非自明な変更に分かれていたが、設計済みで独立検証できるbounded sliceの標準roleがなかった。bounded調査を行うLuna `researcher`も`high` effortで、明確・反復可能なtaskにLunaを使う方針と釣り合っていなかった。

また、静的agent定義がSpark quotaやavailabilityを推測し、Hookが注入するruntime routing方針と重複していた。reviewでは通常slice、specialist review、finding closureを`targeted_reviewer`がSol `xhigh`で兼務し、riskと必要な推論深度が異なる作業を同じroleへ集めていた。

## Decision

- `focused_implementer`をLuna `medium`、`workspace-write`で追加し、要件、観測可能な期待動作、semantic owner、design、targeted checkが確定した独立bounded sliceだけを担当させる。未解決のpublic contract、永続化、migration、認可、security、concurrency、data lossを含む判断は親sessionへ返す。
- 実装roleを、routing modeが許可する小規模・機械的変更の`fast_implementer`、設計済みで関連する複数fileを含めて独立検証できるbounded sliceの`focused_implementer`、独立sliceへ分離できないcross-owner / cross-subsystem整合、複雑なdebug、責務移動、未知経路を横断する実装推論の`implementer`へ分ける。
- bounded調査を担当する`researcher`をLuna `medium`とし、facts、inferences、unknownsを分けて返す。設計、security posture、未解決contractの決定は追加しない。
- 静的agent定義はrole固有のscope、禁止事項、model、effort、sandbox、出力契約だけを所有する。現在のrouting modeに従い、quotaまたはavailabilityを推測しない。Hookはruntime modeとavailabilityに基づくfallbackだけを所有する。
- `slice_reviewer`をLuna `high`、`read-only`で追加し、通常のcompleted sliceだけをbounded reviewする。高リスクtargeted review、contract-closure specialist review、finding-family closureは`targeted_reviewer`、`Full-review gate=run`の一度のholistic complete-diff reviewは`reviewer`が担当する。
- `agents.max_threads`は`agents.max_concurrent_threads_per_session`へ移行する。`max_depth = 1`はCodex CLI 0.146.0のstrict config loadが受理し、子agentによる再委譲を制限する現行意図があるため維持する。
- 効果判定では親子合計token、role別token、親の修正量と追加turn、targeted check初回成功率、blocking finding、validation gap、wall-clockを同じtask classとrouting条件で複数run比較する。Hookへ測定workflowを複製せず、session logを生データ、task-local benchmark recordを比較結果の所有者とする。

## Alternatives

- bounded実装を引き続き`implementer`へ渡す: role数は増えないが、明確な反復作業にもSol `high`を使い続けるため採用しない。
- `focused_implementer`をLuna `high`で開始する: 複雑なtaskには有効だが、今回の利用条件は設計済みbounded sliceなので初期値には採用しない。task class比較で品質低下が確認された場合に再検討する。
- 通常slice reviewも`targeted_reviewer`へ残す: role追加は不要だが、Sol `xhigh`が必要なspecialist/closureと通常sliceのrisk差を表現できないため採用しない。
- routing modeごとにagent registry profileを分ける: 静的catalogからfast roleを除外できるが、profile同期と新session切替の運用が増えるため、まずは常時登録とHook contextを維持する。
- `max_depth`を未掲載という理由だけで削除する: 現行CLIが受理し、再委譲制限の意図も残るため採用しない。

## Consequences

- Positive: bounded実装と通常slice reviewを、riskと推論深度に合うstandard roleへ割り当てられる。
- Positive: quota/availabilityのruntime判断とrole固有contractの静的定義が分離される。
- Positive: `standard-only`ではfast roleを自動選択せず、ユーザーのexact role指定だけを例外にできる。
- Negative: role catalogが増え、親sessionはdesign certainty、risk、validation pathを明示して選択する必要がある。
- Negative: model変更の有効性は設定変更だけでは確定せず、複数のrepresentative runと親の再作業を含む比較が必要になる。

## Policy Anchors

- Role selection and review lifecycle: `AGENTS.md`
- Static role contracts: `agents/*.toml`
- Role registration: `config/agents.example.toml`、端末固有の`config.toml`
- Runtime routing context: `hooks/subagent-routing.ps1`
- Routing and static-contract checks: `hooks/test-subagent-routing.ps1`
- Benchmark procedure: `docs/runbooks/compare-subagent-roles.md`
