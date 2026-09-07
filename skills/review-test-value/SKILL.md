---
name: review-test-value
description: Python、TypeScript、C#のtest新規追加・意味変更をGit差分から抽出し、専用Luna/maxで検証価値と本文整合を必須審査する。削除・移設の解消も扱う。既存checkの実行だけには起動しない。
---

# Review Test Value

構造化metadataとtest sourceの対応付け、入力固定、結果の集合・順序・hash検証はscriptが所有する。親は実際のsourceとaccepted contractを確認して保持根拠とriskを渡す。参照先を読まず、oracle.refの存在やmodelの自由出力だけで保持を承認しない。

このcheckoutは候補であり、実モデルE2E・候補自身の審査・新規session確認が完了するまでliveへ配布しない。[有効化runbook](../../docs/runbooks/activate-test-value-review.md)で状態を確認する。以下は候補を明示実行する経路であり、旧単一審査へ戻すfallbackではない。

## testを増やす前の判断

現在の要求・契約・具体的な不具合を根拠に、どの欠陥を検出し、assertionが何を直接観測するかを決める。正しい内部変更で壊れる実装詳細依存、既存checkと同じ欠陥の重複検出、同じ生成元による入力と期待値の循環を避ける。type、schema、static、build、smoke、browser、visual checkの方が直接的ならそちらを選ぶ。別のDesign Gateや提出物は要求しない。

不要なtestは追加しない・減らす・適切なcheckへ移す結論を扱う。必要なnegative testや安全境界をabsenceという理由だけで捨てない。既存checkを実行するだけなら設計・価値審査を追加しない。

## 候補の実行

Python 3.11以降を使う。対象の選択はtask開始時のbaseからのGit modeとし、pathやrecordを都合よく選び直さない。対象外の未変更testを一括審査・移行しない。metadataを書く場合は[comment-format-v2](references/comment-format-v2.md)、対応宣言とGit選択は[source-adapters-v1](references/source-adapters-v1.md)と[git-selection-v1](references/git-selection-v1.md)を必要に応じて読む。

TypeScript／C#の対象があり依存が未準備の場合だけ、対応するadapterを準備する。

```powershell
npm ci --prefix <skill-dir>/scripts/adapters/typescript
dotnet restore <skill-dir>/scripts/adapters/csharp/TestValue.CSharpExtractor.csproj
```

入口は`run_test_value_review.py`。root、task base、対象snapshot、SessionFolder内のtask専用state、native CLI、host evidenceを指定する。working treeが既定で、stagedは`--staged`、commit固定は`--head <commit>`を使う。審査のためだけにcommit・stage・base変更をしない。

最初は同じ入口に`--prepare`を付け、`--host-evidence`を省いて現在のidentityとhost evidenceの雛形を取得する。この準備はmodelを呼ばない。雛形へ実際に確認した根拠を記入してから、同じ対象とstateで以下を実行する。hashやrecord集合を親が手計算し直さない。

```powershell
python -X utf8 <skill-dir>/scripts/run_test_value_review.py `
  --root <repository-root> --changed-from <task-base> `
  --state-dir <task-state-directory> --cli <native-codex-executable> `
  --host-evidence <host-evidence-json>
```

host evidenceは現在のsnapshot・recordに結び付いたrisk評価、必要な限定context、実際に確認した保持根拠を渡す。sourceの内容・hash・意味判断を区別する。不足や競合を推測で埋めず、具体的な不足が返ったら確認する。各phaseのpacketを手組みしない。

入口が全言語の抽出、独立したLuna metadata審査、固定済み結果を使うalignment、決定論的なrequired deep review、保持と既存resolution、全体gateを接続する。metadataがREDESIGNでもalignmentを省略しない。審査結果の正確な型は[output-v2](references/output-v2.md)、意味は[metadata](references/metadata-review-contract.md)／[alignment](references/alignment-review-contract.md)／[deep](references/deep-review-contract.md)／[routing](references/routing-policy.md)が所有する。

## 完了条件と不足の扱い

- `0 = PASS`: 全言語・必要な全phase/deep review・surviving record・DROP/MOVE義務が現在のsnapshotで揃った。
- `1 = CHANGES_REQUIRED`: metadata／test／保持先に具体的な修正が必要。
- `2 = BLOCKED`: 入力・依存・隔離・model・根拠等の不足により、信頼できる審査を完了できない。

PASSとtest自体の実行成功は別の証拠である。抽出やvalidator単体のexit 0、空selection、削除だけ、消えたledgerを全体PASSにしない。元のREDESIGNをACCEPTへ書き換えず、根拠ある削除・移設の解消を別の結果として扱う。

専門workerはphaseごとに履歴を持たない独立CLIで実行し、metadata phaseへ本文・locator・親履歴・一般hookを渡さない。read-onlyという文言だけを入力隔離の証拠にしない。設定・起動記録と合成canaryの拒否を確認できない場合、packet送信前に停止する。親や汎用子の自己評価、別model、旧結果へのfallbackで補わない。

全phaseでLuna/maxを使い、metadata／alignmentは`test_value_luna`、deepは`test_value_deep`を別runで呼ぶ。追加contextでも判断できなければNEEDS_CONTEXTを親へ返し、Solや他modelへ自動昇格しない。

初期予算はworker同時1、通常audit10%、追加contextによるdeep再実行最大1回。各実行の上限はmetadata／alignment 5分、deep 15分とする。deep入力が800,000文字を超える場合だけ、固定済みの対象順で事前にbatch分割する。全batchの検証済み結果が揃わなければ全体PASSにしない。単独recordの予算超過や期限・cancel・途中失敗を黙って切り捨てず非成功とする。stateには既存resolutionの未解決義務を保持し、別taskや別snapshotの証拠を流用しない。

## Validation

変更した影響に直接対応するcheckを実行する。説明・metadataだけの変更でも、発火条件や相対参照の意味が変わる場合は、対象Skillのquick validationと参照確認を行う。同じsnapshotで成功済みのcheckは、source・contract・依存・実行環境の変更、失敗やflaky、具体的な未確認リスク、必須checkまたはユーザー指定がある場合に限って再実行する。CIの全環境検証と、localで無関係なadapterをrestoreすることは同じ要件ではない。

### 説明・metadata

```powershell
python -X utf8 <skill-creator>/scripts/quick_validate.py skills/review-test-value
```

相対参照、対象範囲、起動条件の意味を読み合わせ、必要なreferencesへ到達できることを確認する。descriptionだけでなくWorkflowや参照先を変更した場合は、影響する下記のcheckも実行する。

### Git差分選択

```powershell
python -X utf8 -m unittest skills/review-test-value/scripts/test_extract_test_values.py
python -X utf8 -m py_compile skills/review-test-value/scripts/git_diff_selection.py
```

Git modeのbase commit、対象path、line rangeの選択を変更した場合に実行する。`test_extract_test_values.py`がGit差分選択を直接検証し、Git modeでは手作業で対象pathを差し替えない。

### 言語adapter・抽出

```powershell
python -X utf8 -m unittest skills/review-test-value/scripts/test_extract_test_values_multilang.py
python -X utf8 -m py_compile skills/review-test-value/scripts/extract_test_values.py
```

変更した言語のadapter、コメント形式、抽出CLIに対応するcheckだけを実行する。Python adapterとGit modeは上記の`test_extract_test_values.py`、TypeScriptまたはC# adapterは`test_extract_test_values_multilang.py`で検証する。初めて使う言語の依存準備はWorkflowの既存手順に従い、変更していないadapterのlocal restoreは必須にしない。CIのWindows/Linux多言語検証は維持する。

### review packet・schema・routing

出力JSON Schemaの意味検証には、検証用のPython環境へ固定した依存を導入する。抽出器と通常審査のruntime依存ではない。

```powershell
python -m pip install -r skills/review-test-value/scripts/requirements-test.txt
python -X utf8 -m unittest skills/review-test-value/scripts/test_review_packets.py
python -X utf8 -m unittest skills/review-test-value/scripts/test_review_result_schema.py
python -X utf8 -m unittest skills/review-test-value/scripts/test_review_output_schema.py
python -X utf8 -m unittest skills/review-test-value/scripts/test_review_routing.py
python -X utf8 -m unittest skills/review-test-value/scripts/test_review_resolution.py
python -X utf8 -m py_compile skills/review-test-value/scripts/build_review_packets.py
python -X utf8 -m py_compile skills/review-test-value/scripts/review_routing.py
python -X utf8 -m py_compile skills/review-test-value/scripts/validate_review_result.py
```

packet、result schema、routing、判定検証の実装や公開CLI契約を変更した場合に実行する。exit `0`の`tests`だけを審査し、exit `1`/`2`や`NEEDS_CONTEXT`を完了扱いにしない。専門roleの入力境界と全体gateの確認は、候補実行の検証とは別に必要である。

### workerとcoordinator

```powershell
python -X utf8 -m unittest skills/review-test-value/scripts/test_preflight_review_worker.py
python -X utf8 -m unittest skills/review-test-value/scripts/test_review_worker.py skills/review-test-value/scripts/test_run_test_value_review.py
python -X utf8 -m py_compile skills/review-test-value/scripts/preflight_review_worker.py
python -X utf8 -m py_compile skills/review-test-value/scripts/review_worker.py skills/review-test-value/scripts/run_test_value_review.py
```

preflight_review_worker.pyはversion照会とreadiness報告だけを行う。review_worker.pyはWindows native CLI 0.153.4と既存ChatGPT Pro認証を対象に、管理入力の検査と合成canaryを通してからphaseを実行する。未確認のOS・CLI版・認証種別はpacket送信前に停止する。offline testや`BLOCKED`を実モデル成功と扱わない。候補版の実行と継続条件は[有効化runbook](../../docs/runbooks/activate-test-value-review.md)を参照する。
