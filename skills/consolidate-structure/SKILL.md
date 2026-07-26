---
name: consolidate-structure
description: change / build / fix の main implementation session が、source、適用可能な executable contract、targeted check の揃った implementation-complete candidate を外部の read-only review cycle へ渡す前に使う。今回変更した scope / dependency topology に semantic owner の分散、独立責務の混在、canonical boundary の迂回、slice 間の decision 重複、または新しい test coupling を示す具体的な evidence がある場合だけ、accepted behavior を変えず一回の bounded consolidation と再検証を行う。review-only session、read-only child、未完成または Red の slice、review 回数、finding 数、clean review、file 数、diff 量、PR 作成依頼だけを契機には使わない。
---

# Consolidate Structure

## 目的

外部 review で correctness finding を探し始める前に、今回の実装で生じた責務、semantic decision、依存方向を main implementation session が一度だけ収束させる。対象は今回変更した internal structure と直接 consumer に限り、accepted behavior と executable contract の意味を維持する。

この Skill は correctness review、repository 全体の cleanup、file size の削減、機械的な DRY 化を行わない。外部 reviewer は引き続き read-only であり、この Skill を実行しない。

## 適用条件

次の条件をすべて満たす場合だけ適用する。

- 現在の session が変更を所有する main change / build / fix session である
- source、適用可能な executable contract または理由付きの代替確認、targeted check が揃い、実装内容が観測可能な **implementation-complete candidate** である
- 次に、Skill 自体とは独立して planned、user-requested、または lifecycle-selected な外部 read-only review cycle へ渡す予定がある
- 今回変更した scope / dependency topology に、次の semantic signal が一つ以上ある
  - 一つの policy、invariant、normalization、validation、error mapping などの semantic decision を複数の可変 owner が持つ
  - 一つの unit に、独立して変更または検証できる workflow、state、side effect、failure boundary が混在する
  - canonical boundary を迂回する依存、ownership の逆転、循環、または曖昧化が生じた
  - slice の統合により、別々の owner が同じ semantic decision を持つ
  - accepted behavior の test が、今回の変更によって private wiring、source layout、内部 call 順へ新たに依存した

file 数、変更行数、diff 量、一つの file への変更集中、関係する layer 数は、semantic signal を調べる範囲の補助にだけ使える。これらの量、review 回数、finding 数、clean review、PR 作成依頼、formatting、rename、または既存負債だけでは発火させない。

ユーザーが PR 作成を依頼した後は、未実施の構造整理を新たに開始しない。

## 手順

### 保持する契約を固定する

次を task-local に列挙する。

- accepted behavior と根拠
- executable contract または理由付きの代替確認
- external consumer から観測できる input、output、state、error、side effect、failure timing
- 実行済み targeted check
- 今回の changed scope と直接 consumer

保持対象を確定できない場合は編集せず、結果を `replan-required` とする。

### topology の before / after を作る

base からの current candidate diff と canonical anchors を読み、次を比較する。

- workflow と変更理由ごとの owner
- state、transaction、authorization、side effect、failure boundary の owner
- sibling entry point が共有する semantic decision
- dependency direction と canonical boundary
- source と executable contract の対応
- test が観測する public behavior と private wiring

同じ構文、似た名前、一時的な file size だけを semantic duplication とみなさない。今回触れていない既存負債と、将来予測だけに基づく抽象化は対象外とする。

### 候補を分類する

各候補を次のいずれかへ分類する。

- `consolidate-now`: 今回の scope 内で accepted behavior を維持したまま stable owner を明確にでき、構造リスクを実際に減らせる
- `leave-as-is`: 現在の owner が妥当、重複が構文上だけ、または新しい抽象化の方が探索コストや依存を増やす
- `replan-required`: accepted behavior の根拠が不足する、または contract、高リスク境界、supported scope を変えなければ解消できない

今回の changed scope 外にある既存負債は分類や編集の対象にせず、必要な場合だけ通常の task backlog として別に扱う。

### bounded edit batch を決める

`consolidate-now` がある場合は、一回で閉じる edit batch を先に固定する。batch には次を含める。

- 移動または統合する semantic decision
- 移動元、canonical owner、直接 consumer
- 保持する accepted behavior と executable contract
- 実行する targeted check、build、typecheck、smoke、必要な Sibling Sweep
- scope が計画外へ広がった場合の停止条件

一回の gate では、この batch だけを実施する。実施後に新しい構造候補を探索しない。

### 許可された整理だけを行う

次の変更だけを許可する。

- 既存 semantic decision を一つの canonical owner へ移し、今回の直接 consumer を同じ論理変更で移行する
- 混在した internal responsibility を、既存 contract に沿った凝集単位へ分ける
- internal dependency direction を既存の stable boundary に揃える
- import、path、fixture、test helper を機械的に追随させる
- assertion を別 file または helper へ移す場合、同じ observable、failure mode、assertion semantics をそのまま保つ

次の変更は行わない。

- public API、protocol、schema、永続化、migration、authorization、external side effect、error semantics、ordering、failure timing、concurrency、resource limit、resource ownership / authorization scope、第三者 dependency の変更
- accepted executable contract の削除、弱体化、skip、意味変更
- snapshot、golden、mock expectation を新しい internal implementation に合わせるだけの更新
- 今回触れていない既存負債の cleanup、一般的 hardening、将来予測に基づく共通化

禁止境界へ触れる、behavior preservation を証明できない、または settled design を越える場合は編集を止め、`replan-required` として通常 workflow の調査と設計へ戻す。該当する場合は `contract-closure` も適用する。

### 編集後に slice を再検証する

整理で source、wiring、test helper のいずれかを変更した時点で、整理前の green 結果を最終検証として扱わない。slice を implementation 中へ戻し、少なくとも次を行う。

- 整理前に実行した targeted check を再実行する
- 移動した owner、dependency、test seam の回帰リスクに応じて build、typecheck、lint、smoke を再実行する
- `contract-closure` 対象なら、整理で影響した invariant family の Sibling Sweep を再実行する
- source と executable contract が、保持対象とした behavior について矛盾していないことを再確認する

失敗が残る間は外部 review へ渡さない。計画した batch 内で修正できなければ `replan-required` とする。

### gate を閉じる

候補分類と gate の最終結果を混同しない。`consolidate-now` は編集前の候補であり、edit batch と post-edit validation が終わるまで `ready-after-consolidation` を返さない。

計画した delta と post-edit validation だけを確認し、次のいずれかを返す。

- `not-applicable`: 前提を満たさない。`reason` を `no-topology-evidence`、`candidate-not-ready`、`wrong-session`、`pr-requested`、`no-review-handoff` のいずれかで返す
- `ready-unchanged`: qualifying と考えた evidence を inventory した結果、全候補が `leave-as-is`
- `ready-after-consolidation`: 一回の bounded edit batch と post-edit validation が完了した
- `replan-required`: behavior preservation、scope、または contract の再判断が必要

qualifying evidence を inventory した gate instance では、外部 review へ進める結果を `ready-unchanged` と `ready-after-consolidation` に限る。no-op は正常な結果であり、改善候補がゼロになるまで探索しない。

`not-applicable` は review readiness の判定ではない。Skill は後続処理を決めず、reason だけを main lifecycle へ返す。reason 別の遷移は `AGENTS.md` に従い、Skill 自体を review trigger にしない。

## 停止規則

- 一回の topology inventory、一回の planned edit batch、一回の closure 確認で終了する
- Skill 自身の edit、review finding、clean review を再発火条件にしない
- 後続の finding 対応が新しい semantic owner、dependency direction、responsibility boundary、または test coupling を実際に生じた場合だけ、新しい implementation-complete candidate として再判定する
- 二つの構造案を往復する、または計画外の consumer や subsystem へ scope が広がる場合は `replan-required` で停止する
- Skill は外部 review を開始せず、review 回数、scope、fresh-context 条件を変更しない

## subagent と reviewer の境界

topology の事実収集が大きい場合だけ、main session は read-only researcher に raw diff、canonical anchors、調査範囲を渡せる。researcher は dependency map、semantic duplication 候補、test seam を返すだけで、gate の実行、分類、編集、完了判断を行わない。

reviewer への入力は `AGENTS.md` と、該当する場合は `contract-closure` の既存 review 契約に従う。この Skill は review 種別、入力、fresh-context 条件を上書きしない。

- initial review には post-consolidation の raw diff、accepted contract、canonical anchors、実行済み check を渡し、「構造整理済み」という結論や却下した候補は渡さない
- targeted re-review には、対象 finding、修復した slice、resulting delta、再実行した check を既存契約どおり渡す
- fresh-context full-diff closure review に限り、過去 finding、claimed resolution、実装者の結論、既存 Closure Map を渡さない

## task-local 出力

恒久的な topology 文書は作らず、main session の作業記録として次だけを短く残す。

```text
Result: not-applicable | ready-unchanged | ready-after-consolidation | replan-required
Reason:
Trigger evidence:
Preserved contracts:
Responsibility delta:
Applied edit batch:
Post-edit checks:
Escalation or residual risk:
```
