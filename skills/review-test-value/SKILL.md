---
name: review-test-value
description: Pythonのtest sourceへ隣接する構造化された`@test-value`コメントとtest declarationを決定論的に抽出し、コメントの検証価値とtest本文の整合を審査する。新規・変更テストの価値レビュー、価値コメントの追加・修正、曖昧・重複・実装詳細へ結合したテストの見直し、AIレビュー入力の生成で使う。runtime test collection、全言語対応、CI gateの構築には使わない。
---

# Review Test Value

構造化コメントとtest sourceの対応付けをscriptへ任せ、AIは抽出済みrecordだけを審査する。欠落した値や曖昧な結合を会話内で補完しない。

抽出CLIには`tomllib`を含むPython 3.11以降を使う。

## Workflow

1. repository instructionと対象pathを確認する。
2. Python以外、動的生成、runtime collectionとの一致が必要なtestはv1対象外として報告する。
3. 価値コメントを書くか直す場合は、先に[references/comment-format-v1.md](references/comment-format-v1.md)を読む。
4. repository rootと明示的なsource pathを指定して抽出する。

```powershell
python -X utf8 <skill-dir>/scripts/extract_test_values.py `
  --root <repository-root> `
  <test-source-path> [<test-source-path> ...]
```

5. exit `1`ではstdoutの`diagnostics`を読み、sourceまたはコメントを修正してから再実行する。抽出器を迂回してAI審査へ進まない。
6. exit `2`ではstderrを読み、root、path、I/Oを直す。信頼できる部分結果があるとみなさない。
7. exit `0`の`tests`だけを[references/review-contract.md](references/review-contract.md)に従って審査する。
8. JSON field、diagnostic、exit statusの確認が必要なら[references/output-v1.md](references/output-v1.md)を読む。

## Extraction Rules

- 明示されたpathだけをscriptへ渡す。抽出器へ対象testの選択を推測させない。
- `metadata`、`source_text`、line locator、hashを抽出結果のまま扱う。
- 通常コメントやdocstringを構造化metadataへ昇格しない。
- `metadata: null`をAIが推定値で埋めない。
- `coverage=python-source-declarations-v1`をruntime runnerの収集結果として扱わない。
- JSONを恒久artifactやsource of truthとして保存しない。必要なら同じsourceから再生成する。

## Review Result

test recordごとに次を返す。

- `ACCEPT`: 抽出record内では価値コメントが反証可能で、本文のobservableが同じfailure modeを検出する。
- `REDESIGN`: claim、oracle、failure mode、scope、distinctness、または本文との対応に具体的な欠陥がある。
- `NEEDS_CONTEXT`: record外の根拠がなければrecord内の設計判定も確定できず、明示的な追加sourceが必要である。

判定には`evidence`、`unverified`、必要なら`next_action`を添える。oracle本文が入力されていない場合は`oracle.ref`を必ず`unverified`へ残し、参照先の存在、claimの裏付け、非循環性を確認済みと表現しない。文章の巧拙だけを`REDESIGN`理由にしない。

## Validation

Skillまたはscriptを変更したら次を実行する。

```powershell
python -X utf8 -m unittest skills/review-test-value/scripts/test_extract_test_values.py
python -X utf8 -m py_compile skills/review-test-value/scripts/extract_test_values.py
python -X utf8 <skill-creator>/scripts/quick_validate.py skills/review-test-value
```
