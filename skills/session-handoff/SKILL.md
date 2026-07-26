---
name: session-handoff
description: セッション終了前に、現在のgit・検証・未完了状態とsource、実行可能な契約、ADRへのpointerをhandoffへ整理する。ユーザーが`$session-handoff`を指定するか、handoff文書の作成を明示的に依頼した場合だけ使う。単なる終了、commit、作業中断、次回再開の表明では使わない。
---

# Session Handoff

## 目的

- 次回の再開候補とローカル状態を `docs/handoff/` に記録する。
- handoff は一時的な運用snapshotとし、現在の実装、期待動作、決定理由の正本にはしない。

## 手順

1. 現在状態を収集する。
- branch、`git status --short`、直近commit、未commit変更、直近のbuild / test結果を確認する。
- 関連するsource、test / type / schema / static check、accepted ADR、必要なarchitecture文書のrepo相対pathを特定する。
- 実行中process、認証、端末固有状態など、gitから復元できない再開条件を確認する。secretや資格情報そのものは記録しない。

2. 情報の正本を確認する。
- 現在の実装説明はsource、期待動作と不変条件は実行可能な契約へのpointerで示し、handoffへ複製しない。
- 採用済みの重要判断がADR条件を満たす場合は、handoffだけに理由を残さずADRを作成または更新する。
- 未決定の選択肢は決定済みとして書かず、blockerまたはopen questionとして残す。

3. 残作業を再開可能な単位にする。
- `完了` / `進行中` / `未着手` / `blocker` を分ける。
- reviewable sliceを使っている場合は、現在のslice、依存先、観測可能な成果、targeted check、targeted reviewの要否と`blocking` statusを記録する。未完成sliceを完了扱いしない。
- 各項目に、次に読む正本、実行するcommand、または編集対象を付ける。
- sourceと実行可能な契約の不一致、未完了のcompletion gate、未検証の主要リスクを明記する。
- handoffやplanを次回の正本とは呼ばず、再開候補を探す索引として扱う。

4. handoffを作成する。
- 保存先を `docs/handoff/handoff-YYYYMMDD-HHmm.md` とする。
- 絶対日時とtimezoneを記載する。
- 出力前に `references/template.md` を全文読み、その構造を使う。
- 末尾に、次回は`$session-resume`で正本とgit状態を再確認してから続行する手順を置く。

## 出力

- `references/template.md` を出力形式の正本とする。
- 該当事項がない欄も省略せず、`none` または理由を記載する。

## 品質チェック

- handoffを現在実装、期待動作、決定理由の正本として扱っていないか確認する。
- source、実行可能な契約、ADRへのpointerがrepo相対pathになっているか確認する。
- ADR条件を満たす採用済み判断がhandoffだけに残っていないか確認する。
- 残作業に具体的な次のactionがあるか確認する。
- 未実行検証、blocker、非file文脈、絶対日時を記録したか確認する。
- sourceと実行可能な契約の差異、未完了gate、残リスクを隠していないか確認する。
- 現在のsliceと、依存sliceを開始できる状態かを区別したか確認する。
- secret、token、資格情報、不要なraw logを含めていないか確認する。
