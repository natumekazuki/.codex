# Extracted Test Value Output v2

stdoutへUTF-8 JSON objectを一つ返す。

```json
{
  "schema_version": 2,
  "adapter": "python-source-v1",
  "coverage": "python-source-declarations-v1",
  "repository_root": ".",
  "tests": [],
  "transitions": null,
  "diagnostics": [],
  "warnings": []
}
```

宣言抽出能力を変更していないため、言語ごとのadapterとcoverage名は[source adapter契約](source-adapters-v1.md)を維持する。Git modeの選択条件は[Git selection契約](git-selection-v1.md)に従う。

各recordは`source`、`metadata_format_version`、`metadata`、`source_text`、`source_hash`、`metadata_hash`を持つ。metadata formatは結合したmarkerから確定する。metadataとhashが取得できても、diagnosticsがある結果は審査へ渡せない。v1 recordは移行入力であり、v2への自動変換結果ではない。

`transitions`は明示path modeでは`null`、Git modeでは配列である。Git modeの各要素は`kind`、`before`、`after`を持ち、shapeは次のいずれかとする。

- `ADDED`: `before`は`null`、`after`は現snapshotのrecord
- `SURVIVED`: `before`はbase snapshotのrecord、`after`は現snapshotのrecord
- `DELETED`: `before`はbase snapshotのrecord、`after`は`null`

Git modeの`tests`は`ADDED`と`SURVIVED`の`after`を同じ決定論的順序で並べたものと一致する。`DELETED.before`は削除前のmetadata、source locator、本文、hashを保持し、削除によって元の審査義務を失わせない。対応が一意に確定しない場合は`RECORD_TRANSITION_UNRESOLVED`を返し、exit `1`とする。

source locator、LF正規化、canonical JSONとSHA-256、決定論的な順序はv1の規則を維持する。locatorは編集をまたぐ永続IDではない。`warnings`と`diagnostics`はそれぞれ`code`、`path`、`line`、`message`を持つ配列とし、errorをwarningへ弱めない。

exit `0`は抽出errorなし、`1`は修正可能なsource/metadata diagnostic、`2`は信頼できる結果を構築できないCLI、環境、I/O等の失敗である。`TEST_VALUE_V2_REQUIRED`は両modeでerrorとする。空の抽出結果とexit `0`は、coordinatorの未解決義務やresolutionの完了を意味しない。

metadata/alignment/deep/finalの審査契約はv2である。旧resultのshape推測や自動読替えは行わない。標準有効化の条件は[有効化runbook](../../../docs/runbooks/activate-test-value-review.md)を参照する。
