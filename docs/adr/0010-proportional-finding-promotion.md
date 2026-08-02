# ADR-0010: Finding Promotionを到達可能性と責務境界で制限する

- Status: accepted
- Date: 2026-08-02
- Amends: ADR-0004, ADR-0005, ADR-0007
- Related: ADR-0008

## Context

review findingを同じ不変条件familyへ展開するSibling Sweepは、指摘箇所だけを直して兄弟入口に同型failureを残すことを防ぐ。一方、現実的な一件から、新しいsemantic owner、別subsystem、発生証拠のないrepairやfallbackまで同じ論理変更へ取り込むと、要求したfeatureより変更・test・reviewの責務面積が大きくなる。

Candidateを凍結した後は、sourceまたはreview contractの拡大に再検証が必要になる。このコストを避けるために、別の前提変更を同じCandidate、commit、PRへ残すと、独立して判断できる責務が一つの論理変更へ結合される。Sibling Sweepの再発防止効果を維持しながら、到達根拠の弱いhardeningと別責務の抱き合わせを止める境界が必要である。

## Decision

- root sessionの最終分類とSibling Sweepの前に、accepted contract、supported scope、現実的な到達経路、実発生または再現根拠、影響、既存の検知・復旧を確認し、risk acceptanceできずsource repairが必要な場合だけpromotion先のsemantic owner / subsystemを確定する。証拠不足なら`investigation-pending`として分類を保留し、source展開前に追加調査する
- promotion dispositionと最終finding分類を別軸とし、dispositionを先に確定する。source repairのowner判定より先に`accepted risk`を評価し、最終分類を`risk-candidate`として現在のsourceやreview contractを広げない。修正が必要で、同じsupported scopeとsemantic ownerに属する到達可能なfindingは`current-scope repair`とし、`blocking`として現在の論理変更でSibling Sweepへ展開する。同じowner内の別責務境界であることだけではprerequisiteにしない
- accepted contractを満たすために必要でも、新しいsemantic ownerまたは別subsystemの変更を要する場合は、独立したaccepted contract、source、executable contract、reviewを持つ先行論理変更へ分ける
- 各logical changeが自身のsourceとexecutable contractを閉じても、どの適用・deploy順序にも独立して有効な中間境界状態を作れず、現在のaccepted contractが横断変更を明示的に要求する場合だけ、atomicityの根拠を記録して同じ論理変更へ残す。通常のsource / test編集順やCandidate / review / commit / PR運用はatomicityの根拠にしない
- 必要な証拠調査後、現在のaccepted contract違反ではない、またはsupported scopeで現実的に到達しないと確認し、具体的な契約関係、反証可能な仮説、再調査条件の三つをすべて満たすcaseは`hardening follow-up`として分離し、current reviewでは`non-material`とする。単なる証拠不足はhardeningにせず、追加調査で不足要件を確定できる間は`investigation-pending`に残す。調査後も一つ以上を満たさないcaseは`dismissed`として`invalid`とする
- Candidate失効、review再実行、commit、PR、branch運用の手間は、独立責務を抱き合わせる根拠にしない
- auth bypass、secretまたはpersonal dataの露出、現実的なinjection、不可逆なdata lossは到達根拠を確認する。supported scopeで現実的に到達する場合は完了をblockし、不明な場合はsourceを拡張する前に追加調査する

## Alternatives

- 同じ不変条件に見えるcaseをすべて現在の変更へ展開する: 再発防止は強いが、supported scopeと責務境界を越えて変更面積が増えるため採用しない
- 指摘されたcall pathだけを修正する: 同じownerと契約を共有する兄弟入口に現実的なregressionを残すため採用しない
- file数またはdiff行数で上限を設ける: migration、security境界、共有schemaなど必要な非局所変更を誤って拒否し、責務面積を判定できないため採用しない
- Candidate作成後はscopeを変更しない: reviewで判明した現実的なblocking defectを修正できないため採用しない

## Consequences

- Positive: 現実的な兄弟failureを閉じながら、到達証拠のないhardeningを現在のfeatureから分離できる
- Positive: 新しいowner / subsystemの変更が独立して設計、検証、reviewされ、PRの責務を説明しやすくなる
- Positive: Candidate運用コストがscope判断を歪めにくくなる
- Negative: featureが先行変更の完了を待つ場合があり、短期的なdeliveryは遅くなる
- Negative: 到達可能性と分割可能性の判断をtask-localに記録する手間が増える
- Negative: sourceと契約をatomicに変更すべきcaseでは、同じ論理変更へ残す理由の説明が必要になる

## Policy Anchors

- Finding Promotion semantics and Sibling Sweep boundary: `skills/contract-closure/SKILL.md`
- Logical-change lifecycle, prerequisite ordering, and completion gates: `AGENTS.md`
- Reviewer evidence and hardening separation: `agents/reviewer.toml`
- Runtime executable contract: なし。policy scenarioをtask-localに照合し、固定文言を検証するtestは追加しない
