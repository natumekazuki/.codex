---
name: validation-report
description: 実装後に、変更したsourceと実行可能な契約、実行・未実行の検証、ADR / architecture gate、残リスクを短く揃えて報告する。
---

# Validation Report

## 目的

- 実行したcheckだけでなく、変更した現在状態と期待状態の整合を確認する。
- 未実行項目やknowledge placementの未解決を隠さず、完了判断に必要な情報を揃える。

## 出力

- 報告を作る前に `references/template.md` を全文読み、その構造を使う。
- `references/template.md` を出力形式の正本とし、該当事項がない欄も省略しない。

## ルール

- behaviorまたはcontractを変更した場合は、対応する実行可能な契約を示す。追加・更新しない場合は理由を明記する。
- 対象behaviorまたは防ぐfailure modeを先に示し、各checkがどの期待を証明するか対応づける。
- 主要な回帰シナリオと、それを覆うtest / type / schema / static checkを示す。coverage gapは残リスクへ送る。
- 実装を通すために既存のtestやcontractを弱めていないことを確認し、意図したcontract変更は理由を明示する。
- pure refactorや機械変更では、新規testを一律に要求せず、既存の実行可能な契約が維持されることを確認する。
- docs / policy-only変更では、構文、参照、残存語彙、責務整合などの代替checkを示す。
- reviewを実施した場合はscope、complete diffの確認有無、full-diff review回数、`blocking` status、accepted risk、validation gapを示す。実施不要と判断した場合は理由を示す。
- sourceと実行可能な契約が食い違う場合はalignedとせず、意図確認と残作業を報告する。
- ADRとarchitecture文書の判定規則は`AGENTS.md`を正本とし、このSkillへ条件を複製しない。
- 実行していないcheckを成功扱いせず、生log、大きなdiff、repo外pathを出力しない。
