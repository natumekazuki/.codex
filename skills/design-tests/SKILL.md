---
name: design-tests
description: testの新規追加、意味変更、削除、または回帰checkの選定前に、accepted contract、failure mode、consumer、canonical owner、observableを特定し、Unit、component、integration、type、schema、static、build、smoke、browser、visualから最も直接的な検証手段を選ぶ。bug fix、feature実装、refactorに伴うtest設計、価値の薄いtestの見直し、重複testの整理で使う。既存testを変更せず実行するだけの作業には使わない。
---

# Design Tests

変更した振る舞いを壊す欠陥だけを直接検出し、正しい内部変更では失敗しないcheckを設計する。testを作ること自体を完了条件にしない。

## 1. Test Design Gate

sourceまたはtestを編集する前に、変更ごとに次を特定する。会話へ定型文を出す必要はないが、判断と実装へ同じ意味で引き継ぐ。

```text
Failure mode: production codeへ入ると困る具体的な欠陥
Contract: 明示要求、public API、protocol、schema、accepted ADR、外部consumer、または信頼できる既存contract
Consumer impact: 誰にどの観測可能な影響が出るか
Canonical owner: 契約を一度保証する最小の安定境界
Observable: 入出力、状態遷移、外部副作用、error、不変条件
Check layer: failure modeを最も直接観測する手段
Distinctness: 既存checkでは検出できない理由
```

Contractを現在のsourceやtestの存在だけから推定しない。根拠が競合し、選択がconsumerの結果を変える場合は編集を止め、根拠、選択肢、影響、推奨案をユーザーへ示す。

`contract-closure`がtriggerされる変更では、そのClosure Mapを再利用し、同じcontractとfailure modeを別定義しない。

## 2. Check Layerを選ぶ

最小粒度ではなく、failure modeを直接観測できる最小の安定境界を選ぶ。

- 純粋な変換、計算、domain invariantにはUnit testを選ぶ。
- click、callback、focus、表示状態の遷移にはcomponentまたはinteraction testを選ぶ。
- 複数component、DB、filesystem、network、serialization、transactionの協調にはintegrationまたはsmoke testを選ぶ。
- 型、schema、構文、依存方向の制約にはtypecheck、schema validation、static check、buildを選ぶ。
- CSS geometry、viewport、重なり、見切れ、実ブラウザ固有動作にはbrowserまたはvisual checkを選ぶ。

Unit testへ押し込むために、実際のfailure surfaceをmockまたは文字列一致へ置き換えない。

## 3. Candidate Testを反証する

testを実装する前に、次の問いへ具体的に答える。

1. production codeへどの最小欠陥を入れれば、このtestは失敗するか。
2. 対象処理をno-op、空実装、固定値へ変えても誤って通らないか。
3. 振る舞いを保つrename、class順序変更、markup再編、helper抽出、内部call順序変更で失敗しないか。
4. 入力と期待値を同じロジック、同じgenerator、または同じmock設定から作っていないか。
5. 同じfailure modeをcanonical ownerの既存checkがすでに検出していないか。

1へ答えられない、2で通る、3で失敗する、4または5に該当するcandidateは、そのまま追加しない。observable、layer、ownerを再設計するか、追加不要と判断する。

## 4. Test Smellを契約へ照合する

次は自動的な禁止ではなく、Contractで正当化できる場合だけ採用する。

- mockへ設定した値やcallをそのままassertする。
- `not.toThrow()`、存在確認、generic errorだけで結果を確認しない。
- private method、内部call順序、class名、markup、snapshotを固定する。
- framework、言語、libraryの標準動作を再確認する。
- getter、定数、薄い委譲をcoverage目的だけで覆う。
- type、schema、constructorから到達不能な状態を無理に作る。
- 同値な入力を増やし、同じ分岐とfailure modeを重複確認する。
- production codeと同じ式または同じ生成元で期待値を作る。

absence自体が認可、機密性、危険操作、外部protocolなどのaccepted contractならnegative assertionを使ってよい。各leafへ重複させずcanonical ownerで保証する。

## 5. 実装して直接検証する

- assertionをobservableへ置き、一つのtestがどのfailure modeを守るかtest名から分かるようにする。
- bug fixでは費用対効果が合う範囲で修正前の失敗と修正後の成功を確認する。再現が困難なら、同じfailure modeを直接示す代替証拠とgapを明記する。
- error testではerrorの種類、failure timing、失敗前後の副作用を契約に応じて確認する。
- weak testを削除するときは、直接的な代替checkが必要かを先に判断する。根拠となるfailure modeがなければ、代替testを作らず削除してよい。
- 実行後に対象差分を読み、testがproduction behaviorではなくfixture、mock、または現在表現だけを検証していないか再確認する。

## Completion

次を満たしたときtest設計を完了する。

- 各checkが具体的なfailure modeとaccepted contractへ結び付く。
- 選んだlayerがconsumerのfailure surfaceを直接観測する。
- 正しい内部変更では失敗せず、対象欠陥では失敗する。
- 既存checkとの重複または価値のないcoverage追加がない。
- 実行済みcheck、未実行check、validation gapを区別して報告できる。

## 再実行と完了証拠

同じsnapshot・同じ条件で成功済みのcheckは、source、contract、依存、実行環境の変更、失敗やflaky、具体的な未確認interaction、repository必須check、固定commitに紐づく証拠、またはユーザー指定がある場合に限って再実行する。必要なcheckを実行できない場合は成功扱いにせず、未実行コマンド、影響、残るvalidation gapを記録する。

test設計の完了時は、各checkのfailure mode・contract・observable・layerを示し、実行済みcheckと未実行checkを分けて報告する。test価値審査が適用される新規・意味変更のPython、TypeScript、C# testは、`review-test-value`のGit mode、抽出exit `0`、判定`ACCEPT`を完了証拠に含める。既存testを変更せず実行するだけの作業では、このworkflowや審査を追加しない。
