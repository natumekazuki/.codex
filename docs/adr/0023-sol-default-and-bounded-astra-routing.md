# ADR-0023: Sol常用と限定Astra routingを分離する

- Status: accepted
- Date: 2026-09-06
- Amends: ADR-0014
- Related: ADR-0013, ADR-0016, ADR-0019

## Context

Astraをroot profileと通常のdesigner / reviewerへ広く適用する案は、高い推論能力を利用できる一方で、通常作業の消費量と運用負担が大きい。model未指定roleを`agents.default_subagent_model`で切り替える方式は、意図しないdefault childや通常roleにもAstraを継承させる。

難しい設計判断や反例探索ではAstraを使う余地を残しつつ、通常の調査、実装、検証、reviewは既存のSol / Luna roleで完結させる必要がある。投入条件を静的role説明だけへ置くと、同一turnの再投入、follow-up、compaction後の枠復活を制御できない。

## Decision

- 通常rootの共有例はSol / mediumを維持し、通常roleはSolまたはLunaを明示する。Astra root profileは手動の例外として残すが、default childはSolとする。
- Astra専用のread-only roleとして`astra_consultant`と`astra_reviewer`だけを追加する。両roleはAstra / medium / Standardとし、実装、commit、外部write、再委譲を禁止する。
- `astra_consultant`は具体的な調査後も残る重要な設計判断または矛盾、`astra_reviewer`は既に必要と判定されたreview内の難しい反例だけを扱う。既存のdesigner、reviewer、targeted_reviewerのreview kindとcommit-bound契約は維持する。
- runtime modeを`conditional`、`manual`、`off`に分け、既定は`manual`とする。自動投入は親user turnにつき2 role合計1回、同一root sessionで同時1件までとする。spawn、follow-up、retryは枠を消費し、wait、status、結果取得、terminationは消費しない。
- `hooks/astra-routing.ps1`がmode、turn、予約、実行中agent、manual grantをGit管理外のstateで所有する。`PreToolUse`で投入前に予約し、`SubagentStart` / `SubagentStop`で実行状態を更新し、`UserPromptSubmit` / `SessionStart`で短い条件を再注入する。
- state破損時はAstra自動投入と、対象modelを判定できない既存agentへのfollow-upを継続して拒否する。新しいSol / Luna作業は止めない。Astraが動作中でないことを確認して対象stateを削除した後に再生成する。hook未実行、特殊tool経路、専用role以外のaliasでmodel指定が省略された呼出しまで完全に封鎖したとは扱わず、実runtimeの確認を導入条件に残す。

## Consequences

- 通常作業のmodel選択とAstra利用目的が静的roleで明確になり、profile継承による意図しないAstra起動を避けられる。
- 一つの難問へAstraを一度だけ投入し、その後の実装と検証をSol / Lunaへ戻せる。
- runtime stateとhook trustが増える。portable sourceとPowerShell状態遷移の検証だけでは、実hostのhook到達、model read-back、compaction / resume経路を証明できない。
- follow-up先を既知のAstra agentとして識別するには、正常なspawn予約と`SubagentStart`のstateが必要になる。特殊経路やstate消失は完全遮断の対象外として明示する。

## Policy Anchors

- Common selection policy: `AGENTS.md`
- Static role contracts: `agents/astra_consultant.toml`, `agents/astra_reviewer.toml`, and the existing `agents/*.toml`
- Runtime guard and executable contract: `hooks/astra-routing.ps1`, `hooks/test-astra-routing.ps1`
- Operator procedure: `hooks/astra-routing-modes.md`
- Benchmark and rollout: `docs/runbooks/compare-subagent-roles.md`
