---
name: contract-closure
description: 境界、public API、永続化、migration、外部副作用、認可、並行処理、resource limit、owner / scope変更を実装・修正・reviewするとき、変更した不変条件と複合値の組を兄弟入口、状態遷移、failure timing、aggregate scope、public projection、executable contractまで展開し、独立した反証reviewで閉じる。review findingやbug fixを局所修正で終わらせず、同じ不変条件familyの再発を防ぐときに使う。
---

# Contract Closure

変更行ではなく、変更した不変条件の到達範囲を確認する。green testや指摘箇所の修正だけで完了扱いにしない。

## Workflow

1. 変更またはfindingを、観測されたcaseと、その背後の不変条件へ分ける。
2. 関連するsource、test、type、schema、static check、accepted ADRを読む。
3. capability、operation、owner、状態、resource scopeが同じ兄弟経路を検索する。
4. 単独では妥当でも組合せで不正になるfield、version、generation、owner / scopeを一つの複合不変条件として列挙する。
5. 該当triggerの展開軸を `references/trigger-matrices.md` から選ぶ。複数該当する場合は必要な節を組み合わせる。
6. task-localなClosure Mapを作り、反例を先に列挙する。
7. 各不変条件を最も強い実行可能な場所へ置く。type / schema / shared validation / static checkで強制できる契約をtestだけへ退避しない。
8. 実装または修正後、targeted checkに加えてSibling Sweepを行う。
9. 非局所的または高リスクな変更にはIndependent Closure Reviewを行う。
10. 未確認cell、意図的な例外、実行不能なcheckを残リスクとして報告する。

## Closure Map

会話またはtask-local noteへ、必要な項目だけ短く作る。恒久文書を既定にしない。

```text
Invariant:
Coupled invariants / valid combinations:
Trigger:
Canonical anchors:
Sibling channels:
State / operation sequences:
Failure points:
Owner / scope / projections:
Resource scopes:
Counterexamples:
Executable contracts:
Independent review evidence:
Uncovered risks:
```

空欄を埋めることを目的にしない。今回の変更で意味が変わる軸だけを選び、選ばなかった高リスク軸には理由を付ける。

## Finding Promotion

review findingやbugを受けたら、指摘されたcall pathだけを直さない。

1. 観測されたfailureを一文で固定する。
2. failureを許した不変条件の欠落を一文で表す。
3. 同じ入力源、operation family、owner、state transition、resource scopeを横断検索する。
4. 同型failureを起こす反例を追加し、まとめて修正する。
5. targeted regression testと、可能なら共有境界のtype / schema / validation / static checkを更新する。
6. 過去findingと同じfamilyなら、局所再発ではなくworkflow gapとして報告する。

Findingへのreply、thread resolve、対象testの追加だけをSibling Sweepの代わりにしない。

## Finding Classification and Review Convergence

finding分類、risk acceptance、review回数、完了条件は`AGENTS.md`の「Validation and Review Completion Gates」を正本とする。このSkillは、changed invariant、到達可能な反例、兄弟経路、executable contract、未確認cellをevidenceとして返し、分類を提案するところまでを担当する。

- sliceのtargeted reviewで見つかった`blocking`は、同じsliceのSibling Sweep、targeted check、targeted re-reviewで閉じる。
- fresh-context full-diff closure reviewは、統合後のcomplete-diff reviewで`blocking`へ対応した場合だけ適用する。未完成または未統合のtaskへ広げない。

## Independent Closure Review

契約が複数入口・複数subsystemへ波及する、複合不変条件を変更する、または失敗がpublic contract、永続化、migration、外部副作用、認可、owner / scope、並行処理、resource limitへ重大な影響を与える場合は、実装とtargeted checkの後、完了前に実装者から独立したreviewを行う。

- researcherは根拠収集、validatorは機械的確認、reviewerは反例探索を担当する。researchやgreen testをreviewの代用にしない。
- initialまたはtargetedなIndependent Closure Reviewでは、reviewerにgoal、ユーザー要求または既存のaccepted contract、raw diff、canonical anchors、task-local Closure Map、実行済みcheckを渡す。実装者の結論を確定事実として渡さない。
- blocking修正後のfresh-context full-diff closure reviewでは、過去finding、claimed resolution、実装者の結論、既存Closure Mapを渡さない。reviewerがaccepted contract、更新後raw diff、canonical anchors、実行済みcheckから不変条件と反例を再構築する。
- reviewerはfinding-firstで、反例、同じ契約を持つ兄弟経路、failure timing、owner / scope、欠けたexecutable contractを根拠付きで返し、各findingの分類を提案する。
- rootはfindingをsourceとexecutable contractへ照合して分類を確定し、採用した`blocking` findingを同じ不変条件familyへ展開してから修正・再検証する。
- reviewerを利用できない場合は、実装時の推論を引き継がないfresh-context second passを行い、独立review未実施を残リスクとして報告する。

pure refactorや局所的な機械変更へ独立reviewを義務化しない。変更規模ではなく、契約の非局所性と失敗時の影響で判定する。

## Knowledge Placement

- 現在の挙動と構造はsourceへ置く。
- 期待動作、不変条件、validation、regression expectationはtest / type / schema / static checkへ置く。
- 一箇所の近くで必要な理由はcode commentへ置く。
- 後戻り困難な選択理由はADRへ置く。
- プロジェクト固有の契約や生のreview commentをMemoryだけへ置かない。
- Memoryには、将来も有用な非ファイル文脈、確定した判断、正本へのpointerだけを置く。raw finding、log、diff、未確認の一般化は保存しない。
- 複数projectで繰り返す一般的な観点は、このSkillの改善候補として報告する。repository作業中に無断でglobal Skillを変更しない。

## Completion Gate

- 同じ不変条件を持つ兄弟入口と兄弟operationを確認した。
- 複合不変条件をfieldごとの妥当性だけで済ませず、許可・不許可の組合せとatomic update単位を確認した。
- 正常系だけでなく、主要なsequenceとfailure timingを確認した。
- per-item制約をaggregate / concurrent / process scopeと混同していない。
- owner変更がread、write、auth、projection、audit、cleanupへ必要な範囲で伝播した。
- public responseとerrorは内部型の流用ではなく、許可した情報だけを投影した。
- 既存データや旧schemaを扱う場合、populated stateと途中失敗を確認した。
- findingから得た一般則を、対象箇所以外へ適用した結果を報告できる。
- 非局所的または高リスクな変更ではIndependent Closure Reviewを実施した。未実施なら理由と代替確認を報告した。
- 未解決の`blocking` findingがなく、その他のfindingを根拠付きで分類した。
- accepted riskがある場合は、発生条件、影響、検知、復旧、follow-upの要否を報告した。
- full-diff reviewの回数と、追加reviewを行った場合のtriggerとscopeを報告した。

pure refactorや局所的な機械変更では、無関係なclosure軸を儀式的に展開しない。
