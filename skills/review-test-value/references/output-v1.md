# Extracted Test Value Output v1

## Result

stdoutへUTF-8 JSON objectを一つ出力する。

```json
{
  "schema_version": 1,
  "adapter": "python-source-v1",
  "coverage": "python-source-declarations-v1",
  "repository_root": ".",
  "tests": [],
  "diagnostics": []
}
```

各`tests` recordは次を持つ。

- `source`: repository相対path、qualified symbol、metadataとdeclarationのline locator
- `metadata`: parseとschema validationに成功したtest value object。不正または欠落時は`null`
- `source_text`: 最初のdecoratorからdeclaration末尾までのLF正規化済みsource
- `source_hash`: `source_text`のSHA-256
- `metadata_hash`: canonical JSONへ変換した`metadata`のSHA-256。metadataがない場合は`null`

path、record、diagnostic、JSON keyの順序は固定する。pathはPOSIX区切り、改行はLFへ正規化する。Unicode normalizationは行わない。

## Diagnostic Codes

- `SOURCE_OUTSIDE_ROOT`
- `SOURCE_DECODE_ERROR`
- `SOURCE_SYNTAX_ERROR`
- `TEST_VALUE_MISSING`
- `TEST_VALUE_DUPLICATE`
- `TEST_VALUE_UNBOUND`
- `TEST_VALUE_PARSE_ERROR`
- `TEST_VALUE_SCHEMA_ERROR`
- `TEST_DECLARATION_UNSUPPORTED`

各diagnosticは`code`、`path`、`line`、`message`を持つ。自動処理は`code`を使い、`message`を固定文面として解析しない。

## Exit Status

- `0`: error diagnosticなしで抽出した。
- `1`: sourceまたはmetadataのerror diagnosticを返した。取得可能なrecordはstdoutへ残す。
- `2`: CLI引数、I/O、内部処理の失敗により信頼できる結果を構築できなかった。

exit `1`と`2`を同じ失敗として扱わない。`2`のとき部分結果を推測しない。
