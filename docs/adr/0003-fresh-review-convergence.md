# ADR-0003: fresh-context reviewをmaterial findingの収束gateにする

- Status: superseded
- Date: 2026-07-17
- Supersedes: none
- Superseded by: ADR-0004

## Context

- 実装とreviewの履歴を共有したreviewerは、実装者の結論や前回findingへanchoringし、更新後diffに残る別系統の欠陥を見落とすことがある
- 一度のreviewだけでは探索の分散を吸収できず、別sessionのreviewで追加のmaterial findingが出る場合がある
- 一方、material findingとnitを区別せず無制限にreviewを反復すると、収束しない局所修正と過剰な実行コストを招く
- review反復の終了条件と、局所修正から要求・設計・責務境界の再確認へ戻る条件を選ぶ必要がある

## Decision

- non-trivialまたはhigh-riskな変更でmaterial findingへ対応した後は再検証し、実装・前回review履歴を引き継がないfresh reviewerへ更新後diff全体と未追跡変更、accepted contract、canonical anchors、実行済みcheckを渡す
- fresh reviewerは前回findingの修正確認に限定せず、更新後差分を新規reviewとして反例探索する。実装者の結論、前回finding、claimed resolutionは信頼済みの前提として渡さない
- material findingが残る場合はfinding familyへ展開して修正・再検証し、新しいfresh reviewerで再reviewする。material findingがなくなり、必要なcheckが通ることを完了gateとする
- 3回の独立review後もmaterial findingが続く場合は、局所修正を続けず、要求、設計、責務境界、executable contractを再確認する。再設計後のreviewは新しい収束cycleとして扱う
- nitだけが残る場合は、非materialである根拠と残リスクを報告して完了できる
- root sessionがreview cycle、入力scope、findingの採否、再設計への移行を所有し、reviewerはfinding-firstの反例探索を担当する
- review運用は`AGENTS.md`、reviewerの責務と出力は`agents/reviewer.toml`を正本とする。自然言語の完全一致をstatic checkで固定せず、実行時のreview cycleを機械制御できる仕組みを導入する場合に、その状態遷移と入力scopeを実行可能な契約として検証する

## Alternatives

- 同じreviewerへ修正確認だけを依頼する: 前回findingと自身の結論へ注意が固定され、新しいfindingの探索が弱くなるため採用しない
- reviewを一度だけ実施する: 実行コストは低いが、探索の分散とanchoringを十分に抑えられないため採用しない
- material findingが出なくなるまで上限なく反復する: 高い収束率を期待できるが、設計上の問題を局所修正で追い続け、nitでも停止できないため採用しない
- 2回で再設計へ戻る: 早く設計を見直せるが、独立reviewの分散を吸収する前に正常な修正cycleを打ち切る可能性が高いため採用しない
- 4回以上を許容する: 追加の探索機会は増えるが、3回続けてmaterial findingが残る状態では局所問題より要求・設計・契約の不整合を疑う方が費用対効果に優れるため採用しない

## Consequences

- Positive: 別sessionで得られる独立性を開発session内へ持ち込み、修正確認だけでは見つからないfindingを完了前に探索できる
- Positive: material finding、nit、設計resetの境界が明確になり、早期終了と無限反復の両方を抑えられる
- Negative: non-trivialまたはhigh-riskな変更ではreviewと検証の実行コストが増える
- Negative: 3回という閾値は経験的な運用判断であり、model varianceや全findingの検出を保証しない
- Follow-up: review結果から閾値が過剰または不足と確認された場合は、本ADRをsupersedeして根拠とともに変更する

## Policy Anchors

- Source: `AGENTS.md`、`agents/reviewer.toml`
- Executable contract: なし。現在はroot sessionとreviewerの運用契約であり、routing testの責務には含めない
