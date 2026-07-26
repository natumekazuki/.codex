---
name: session-resume
description: 前回セッションのハンドオフ文書を読み込み、現在のリポジトリ状態との差分を確認して再開計画を作るスキル。ユーザーが`$session-resume`を指定するか、handoffを使った再開処理を明示的に依頼した場合だけ使う。単なる「再開」「続き」「昨日の続き」では使わない。
---

# Session Resume

## 概要

- 前回の終了時点と現在のコード状態を突き合わせ、再開順序を確定する。
- 再開直後に迷わないよう、最初の実行ステップと検証項目を明示する。

## 実行手順

1. 再開候補を特定する。
- まず `docs/handoff/` 配下の最新 `handoff-*.md` を探す。
- 見つからない場合は、明示的にactive statusを持つ`docs/plans/*/plan.md`を優先し、statusがなければ未完了項目を持つ最新候補を探す。複数候補が同等なら決め打ちせず候補を示す。どちらもなければ現在のcode、test、git状態から再開点を組み立てる。
- handoff と plan は再開候補を探すための索引として扱い、現在の実装や期待動作の正本にはしない。

2. 現在状態を検証する。
- `git status --short`、現在ブランチ、直近コミットを確認する。
- ハンドオフ時点の想定との差分（追加変更、未反映コミット、環境差）を抽出する。
- handoff または plan が指す関連 source と、test / type / schema / static check の実行可能な契約を読む。
- 関連する accepted ADR があれば読み、現在の source と実行可能な契約が決定に反していないか確認する。
- source は現在の実装、実行可能な契約は期待状態として分けて記録する。
- handoff、plan、source、実行可能な契約が食い違う場合は、一方へ機械的に合わせない。ユーザー要求、外部契約、accepted ADR、既存の実行可能な契約、履歴上の根拠から意図した動作を確認し、差異と必要な判断を再開計画に明記する。

3. 再開計画を作成する。
- handoffに未完成のreviewable sliceがある場合は、そのsliceのsource、applicable executable contractまたは代替確認、targeted checkを揃えて閉じることを最初の候補とする。前提sliceが閉じる前に依存sliceを開始しない。
- `今すぐ着手` / `次に着手` / `後回し` の3段で並べる。
- 各タスクに対象ファイルまたは実行コマンドを付ける。
- 30分以内で成果が出る「最初の1ステップ」を必ず定義する。
- source、実行可能な契約、ADR / architecture contextをcanonical anchorとして示す。
- 観測した差異と、続行前に必要な判断またはblockerを分けて記録する。

4. 再開または確認を行う。
- 再開計画を短く提示し、依頼済みの change / build / fix は追加承認を待たずに依頼範囲内で続行する。
- 未解決事項の選択によって結果が実質的に変わる場合、外部 write、破壊的操作、履歴改変、または依頼範囲の拡張が必要な場合だけ、実行前にユーザーへ確認する。
- 複数session、高リスク、判断の保存価値など`AGENTS.md`の条件を満たす場合だけ`docs/plans/YYYYMMDD-topic/plan.md`を作成する。会話内の短いchecklistで足りる場合はplan fileを作成しない。

## 出力テンプレート

```markdown
## 再開サマリ

- 参照handoff: <path | none>
- 現在ブランチ:
- 差分の有無:

## Canonical Anchors

- Current implementation source:
- Executable expectations:
- ADR / architecture context:

## Observed Discrepancies

- <difference or none>

## Decisions / Blockers

- <required decision, blocker, or none>

## Current Slice

- Observable outcome:
- Dependencies / next slice:
- Targeted check / review status:

## 今すぐ着手
1.
2.

## 次に着手
1.
2.

## 後回し
1.

## 直近コマンド

- `git status --short`
- `<targeted validation command>`
```

## 再ハンドオフ方針

- 再開後に終了する場合も、ユーザーが`$session-handoff`またはhandoff文書の作成を明示したときだけ次回用文書を更新する。

## 品質チェック

- 参照元handoffをpathまたは`none`で明示したか確認する。
- 差分確認（ブランチ/未コミット変更）を含めたか確認する。
- 関連 source、実行可能な契約、accepted ADR と照合したか確認する。
- source の現在状態と実行可能な契約の期待状態を区別したか確認する。
- handoff または plan を現在実装や期待動作の正本として扱っていないか確認する。
- 「次の1手」が曖昧でないか確認する。
- canonical anchor、観測差異、必要な判断またはblockerを明示したか確認する。
- 未完成sliceがある場合、成果、依存関係、targeted check、review statusを明示したか確認する。
- 追加承認を要求する場合は、結果を変える未解決事項または追加 authority が必要な理由を明示したか確認する。
- 再終了時にhandoffの明示依頼がある場合だけ、`$session-handoff`を呼ぶ導線を入れたか確認する。
