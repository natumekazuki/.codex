---
name: review-test-value
description: Python、TypeScript、C#の新規・変更testに隣接する`@test-value`を抽出し、コメントとtest本文が同じfailure modeを検出するか審査する。pytest・unittest、Jest・Vitest・Playwright、xUnit・NUnit・MSTestの価値レビューとreview packet生成に使う。runtime test collection、動的case展開、CI gate構築には使わない。
---

# Review Test Value

構造化コメントとtest sourceの対応付けをscriptへ任せ、AIは抽出済みrecordだけを審査する。欠落した値や曖昧な結合を会話内で補完しない。

二段階審査のartifactはbootstrap中であり、runtime activationと新session smokeが完了するまでこのSkillの実行経路には使用しない。`test_value_luna`と`test_value_sol`を必須roleとして起動せず、以下の現行workflowを使う。

抽出CLIには`tomllib`を含むPython 3.11以降を使う。TypeScriptにはNode.jsと固定済みnpm依存、C#には.NET 8 SDKと固定済みNuGet依存を追加で使う。

## Workflow

1. repository instructionと対象pathを確認する。
2. 対象言語とsource adapterの対応範囲を[references/source-adapters-v1.md](references/source-adapters-v1.md)で確認する。動的生成、runtime collectionとの一致が必要なtestはv1対象外として報告する。
3. 価値コメントを書くか直す場合は、先に[references/comment-format-v1.md](references/comment-format-v1.md)を読む。
4. TypeScriptまたはC#を初めて抽出する環境では、対応する依存を準備する。

```powershell
npm ci --prefix <skill-dir>/scripts/adapters/typescript
dotnet restore <skill-dir>/scripts/adapters/csharp/TestValue.CSharpExtractor.csproj
```

5. 新規・意味変更testの審査では[references/git-selection-v1.md](references/git-selection-v1.md)を読み、task開始時に固定したbase commitから対象snapshotまでのGit差分で抽出する。対象pathやline rangeを手で選ばない。複数言語は言語ごとに実行を分ける。

```powershell
python -X utf8 <skill-dir>/scripts/extract_test_values.py `
  --root <repository-root> `
  --changed-from <task-base-commit> `
  --language python
```

明示的なfile全体の審査またはmetadata migrationでは、repository rootと同一言語のsource pathを指定する従来modeを使う。

```powershell
python -X utf8 <skill-dir>/scripts/extract_test_values.py `
  --root <repository-root> `
  <test-source-path> [<test-source-path> ...]
```

6. exit `1`ではstdoutの`diagnostics`を読み、sourceまたはコメントを修正してから再実行する。抽出器を迂回してAI審査へ進まない。
7. exit `2`ではstderrを読み、root、path、依存、I/Oを直す。信頼できる部分結果があるとみなさない。
8. exit `0`の`tests`だけを[references/review-contract.md](references/review-contract.md)に従って審査する。
9. JSON field、diagnostic、exit statusの確認が必要なら[references/output-v1.md](references/output-v1.md)を読む。

## Extraction Rules

- 従来modeでは明示されたpathだけをscriptへ渡す。抽出器へ対象testの選択を推測させない。
- Git modeでは対象pathとline rangeをGit差分選択器へ任せ、個別指定へ置き換えない。
- 一回の呼び出しへ`.py`、`.ts` / `.tsx`、`.cs`を混在させない。
- `metadata`、`source_text`、line locator、hashを抽出結果のまま扱う。
- 通常コメントやdocstringを構造化metadataへ昇格しない。
- `metadata: null`をAIが推定値で埋めない。
- `coverage`をruntime runnerの収集結果として扱わない。
- JSONを恒久artifactやsource of truthとして保存しない。必要なら同じsourceから再生成する。

## Review Result

test recordごとに次を返す。

- `ACCEPT`: 抽出record内では価値コメントが反証可能で、本文のobservableが同じfailure modeを検出する。
- `REDESIGN`: claim、oracle、failure mode、scope、distinctness、または本文との対応に具体的な欠陥がある。
- `NEEDS_CONTEXT`: record外の根拠がなければrecord内の設計判定も確定できず、明示的な追加sourceが必要である。

phase判定には`evidence`、`unverified`、必要なら`next_action`を添える。oracle本文が入力されていない場合は`oracle.ref`を必ず`unverified`へ残し、参照先の存在、claimの裏付け、非循環性を確認済みと表現しない。文章の巧拙だけを`REDESIGN`理由にしない。

## Validation

変更した影響に直接対応するcheckを実行する。説明・metadataだけの変更でも、発火条件や相対参照の意味が変わる場合は、対象Skillのquick validationと参照確認を行う。同じsnapshotで成功済みのcheckは、source・contract・依存・実行環境の変更、失敗やflaky、具体的な未確認リスク、必須checkまたはユーザー指定がある場合に限って再実行する。CIの全環境検証と、localで無関係なadapterをrestoreすることは同じ要件ではない。

### 説明・metadata

```powershell
python -X utf8 <skill-creator>/scripts/quick_validate.py skills/review-test-value
```

相対参照、対象範囲、起動条件の意味を読み合わせ、必要なreferencesへ到達できることを確認する。descriptionだけでなくWorkflowや参照先を変更した場合は、影響する下記のcheckも実行する。

### Git差分選択

```powershell
python -X utf8 -m unittest skills/review-test-value/scripts/test_review_routing.py
python -X utf8 -m py_compile skills/review-test-value/scripts/git_diff_selection.py
```

Git modeのbase commit、対象path、line rangeの選択やroutingを変更した場合に実行する。Git modeでは手作業で対象pathを差し替えない。

### 言語adapter・抽出

```powershell
python -X utf8 -m unittest skills/review-test-value/scripts/test_extract_test_values.py
python -X utf8 -m unittest skills/review-test-value/scripts/test_extract_test_values_multilang.py
python -X utf8 -m py_compile skills/review-test-value/scripts/extract_test_values.py
```

Python、TypeScript、C#のadapter、コメント形式、抽出CLIを変更した場合に実行する。初めて使う言語の依存準備はWorkflowの既存手順に従い、変更していないadapterのlocal restoreは必須にしない。CIのWindows/Linux多言語検証は維持する。

### review packet・schema・routing

```powershell
python -X utf8 -m unittest skills/review-test-value/scripts/test_review_packets.py
python -X utf8 -m unittest skills/review-test-value/scripts/test_review_result_schema.py
python -X utf8 -m unittest skills/review-test-value/scripts/test_review_routing.py
python -X utf8 -m py_compile skills/review-test-value/scripts/build_review_packets.py
python -X utf8 -m py_compile skills/review-test-value/scripts/review_routing.py
python -X utf8 -m py_compile skills/review-test-value/scripts/validate_review_result.py
```

packet、result schema、routing、判定検証の実装や公開CLI契約を変更した場合に実行する。exit `0`の`tests`だけを審査し、exit `1`/`2`や`NEEDS_CONTEXT`を完了扱いにしない。現在のtest価値審査gateと`test_value_luna`/`test_value_sol`の役割は、このSkill変更で有効化・変更しない。
