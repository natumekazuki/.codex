# ADR-0004: reviewをblocking findingと明示的なrisk acceptanceで収束させる

- Status: accepted, amended by ADR-0012 and ADR-0013
- Date: 2026-07-18
- Supersedes: ADR-0003
- Amended by: ADR-0012 (2026-08-03), ADR-0013 (2026-08-03)

## Amendment

ADR-0012は、blocking修正後のfresh-context full-diff closure reviewと一つの論理変更につき3回の上限を、単一のholistic complete-diff reviewとfinding family / resulting deltaのtargeted closureへ置き換える。ADR-0013は、holistic reviewを`reviewer`、targeted review、specialist review、targeted closureを`targeted_reviewer`へ分離する。本ADRのfinding分類、risk acceptance、reviewable slice、重大な安全問題を回数だけで受容しない決定は維持する。

## Context

- fresh-context reviewは実装者や前回reviewerのanchoringを減らせる一方、更新後diff全体から毎回新しいfindingを探索すると、低頻度の異常系や一般的なhardening案を追加し続けられる
- 複数の責務をまとめて実装後に初めてreviewすると、契約違反の発見が後続責務へ波及し、修正範囲と再検証範囲が広がる。一方、未完成なfileやcommitごとにreviewすると、観測可能な期待動作がないまま指摘だけが増える
- ADR-0003は3回後に設計を再確認する条件を定めたが、再設計後を新しい収束cycleとしていたため、full-diff review自体の上限とaccepted riskによる終了条件を持っていなかった
- findingのseverity、完了を止める分類、運用上受容できる残存リスクを分け、重大な安全問題を見逃さずにreviewを有限回で閉じる必要がある

## Decision

- `reviewer`と`targeted_reviewer`はfindingごとにseverityと`blocking`、`risk-candidate`、`non-material`、`invalid`の分類を提案し、root sessionがsource、accepted contract、executable contract、supported scopeと照合して分類を確定する。`risk-candidate`を提案する場合は、発生条件と可能性、影響、検知可能性、復旧可能性、follow-upの要否を示す
- `blocking`には、accepted contractまたは明示された安全境界への違反、現実的な到達条件、具体的な影響、sourceまたはexecutable contractに基づくevidenceを要求する
- 低頻度の異常系は、影響が限定され、自動検知でき、復旧手段があり、機密性侵害または不可逆なデータ損失を伴わない場合に限りaccepted riskとして完了できる
- auth bypass、secretまたはpersonal dataの露出、現実的なinjection、不可逆なデータ破損は自動的にrisk acceptanceせず、未修正で残す場合はユーザー判断を求める
- 複数の別々に検証可能な責務を含むnon-trivial taskは、観測可能な契約とtargeted checkが完結するreviewable sliceへ分ける
- targeted reviewは、後続sliceの前提になる、高リスク境界を持つ、または独立reviewの便益が明確なsliceに限定する。`blocking` findingは後続sliceを開始する前に、同じsliceのtargeted checkとtargeted re-reviewで閉じる
- 未完成、未実行、または期待動作を観測できない途中状態には機械的にreviewを挟まない
- final reviewはcomplete diffを対象とし、slice間のinteractionとcross-cutting contractを優先する。閉じたsliceを`blocking` findingとして再度開く場合は、integrationで生じた新しい到達条件または具体的なevidenceを要求する
- 統合後のcomplete-diff reviewで`blocking`を修正した場合は、更新後diff全体についてfresh-context closure reviewを一度行い、その後はfinding familyと修正deltaのtargeted reviewへ移る。slice途中の修正にはfull-diff reviewを適用しない
- 修正が高リスク境界を拡張した場合または具体的な新証拠が確認済み範囲を再度開く場合だけfull-diff reviewを追加し、一つの論理変更につき3回を上限とする
- 3回目の後も`blocking`が残る場合は完了扱いにせず、要求、設計、責務境界、contractまたはユーザー判断へ戻る。同一論理変更の4回目のfull-diff reviewは行わず、高リスクなscope拡張を続ける場合はユーザー確認後に新しいaccepted contractを持つ別の論理変更として切り出す
- 完了条件はfinding総数が0であることではなく、未解決の`blocking`がなく、その他のfinding、accepted risk、validation gap、残リスクが根拠付きで分類されていることである
- review運用は`AGENTS.md`、holistic reviewerの責務と出力は`agents/reviewer.toml`、targeted review、specialist review、targeted closureの責務と出力は`agents/targeted_reviewer.toml`、contract-closure時の展開は`skills/contract-closure/SKILL.md`を正本とする。自然言語ポリシーの完全一致はstatic checkで固定しない
- `hooks/test-subagent-routing.ps1`は`subagent-routing.ps1`と`set-spark-routing.ps1`を実行し、runtime mode、fallback、state precedence、出力だけを検証する。review cycleを機械制御するruntimeを導入した場合は、その状態遷移を別のexecutable contractとして検証する

## Alternatives

- findingが0になるまでfull-diff reviewを反復する: 未知の欠陥を追加探索できるが、終了条件をreviewerの探索分散へ委ね、低確率リスクを明示的に受容できないため採用しない
- full-diff reviewを1回に固定する: 実行コストは低いが、`blocking`修正による回帰を独立した文脈で確認できないため採用しない
- すべての実装後に初めてreviewする: review回数は減るが、一つの責務の契約違反が後続責務へ波及してから発見されるため採用しない
- fileまたはcommitごとにreviewする: 差分は小さくなるが、契約が完結していない途中状態への指摘が増え、責務境界とも一致しないため採用しない
- 回数だけを上限にして残ったfindingを無視する: 重大な契約違反や安全問題を未分類のまま残すため採用しない
- severityだけで完了可否を決める: 発生可能性、supported scope、検知、復旧を表現できず、同じseverityでも運用判断が異なるため採用しない

## Consequences

- Positive: reviewの独立性を保ちながら、広範な再探索を有限回で閉じられる
- Positive: 責務単位で契約違反を閉じるため、後続実装への波及と修正時のblast radiusを抑えられる
- Positive: 低頻度で復旧可能な異常系をaccepted riskとして追跡し、高影響のsecurityまたはdata lossと分けられる
- Positive: reviewerは反例探索、root sessionは契約照合と最終分類という責務境界が明確になる
- Negative: root sessionはfindingの到達可能性、検知、復旧を評価し、accepted riskの根拠を報告する必要がある
- Negative: root sessionはreviewable sliceの境界と依存関係を定め、targeted reviewが必要なsliceのcontextと結果を管理する必要がある
- Negative: model varianceや未知の欠陥を完全には排除できず、full-diff reviewの上限後に高リスクscopeを拡張する場合はユーザー確認と別の論理変更への切り出しが必要になる
- Negative: 現在のreview分類と収束は自然言語の運用契約であり、runtimeによる機械的な強制はない
- Follow-up: review結果から分類誤りまたは上限不足が繰り返し確認された場合は、本ADRをsupersedeして条件を見直す

## Policy Anchors

- Source: `AGENTS.md`、`agents/reviewer.toml`、`agents/targeted_reviewer.toml`、`agents/fast_reviewer.toml`、`skills/contract-closure/SKILL.md`
- Executable contract: なし。現在のreview分類と収束は自然言語の運用契約であり、`hooks/test-subagent-routing.ps1`の責務には含めない
