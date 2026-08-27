# ADR-0020: テスト価値を隣接コメントから決定論的に抽出する

- Status: accepted
- Date: 2026-08-27
- Supersedes: none

## Context

- AIが生成するテストの価値を審査するには、テストが守るclaim、oracle、failure mode、scopeを本文と対応付けて渡す必要がある。
- sidecarと安定IDを全テストへ導入すると、sourceとの同期、rename、孤児metadata、migrationが新しい運用負担になる。
- AIへテスト探索やコメント対応付けを任せると、同じsourceから異なる入力が生成され、欠落情報を推測で補う可能性がある。
- runtime runnerとの照合は動的生成やparameterized caseを扱える一方、frameworkごとの実行環境とcollection side effectをMVPへ持ち込む。

## Decision

- テスト価値の正本を、test declarationへ直接隣接するversion付きの`@test-value`コメントblockとする。
- v1のpayloadは行コメントprefixを除去したTOMLとし、claim、oracle、failure mode、scopeなどのfieldをschema validationする。
- コメント結合、言語native parserによるtest declaration抽出、source slice、path、line locator、hash、diagnostic、JSON projectionを決定論的なCLIが所有する。
- Pythonは`ast`と`tokenize`、TypeScriptはTypeScript Compiler API、C#はRoslynをsource parserとして使う。metadataのTOML parse、schema validation、binding、projectionは共通のPython CLIが所有する。
- 一つのJSON resultは一つのsource adapterだけを表す。複数言語のpathは言語ごとにCLI呼び出しを分け、既存のoutput schema v1を維持する。
- AIは抽出済みrecordを入力として価値コメントとtest本文を審査し、結合、補完、source range決定を行わない。
- v1は安定ID、sidecar、runtime collection照合、動的生成testの発見を持たない。recordはrepository相対pathとqualified symbolで識別するが、renameをまたぐ恒久identityとはみなさない。
- JSONはsourceから再生成できる派生物とし、repositoryの正本として永続化しない。

## Alternatives

- テスト単位のsidecarと安定IDを導入する: frameworkをまたぐidentityを持てるが、MVPの価値検証前に同期、migration、孤児管理を恒久コストとして導入するため採用しない。
- test runnerのcollection結果を主キーにする: 実行対象を正確に取得できる場合があるが、framework固有処理、collection side effect、動的IDの正規化が抽出責務を広げるためv1では採用しない。
- AIがsourceから価値項目を推論する: authoring負荷は減るが、作者が主張した契約とAIが復元した仮説を区別できず、決定論的なレビュー入力にならないため採用しない。
- 自由記述コメントだけを抽出する: 軽量だが必須field、型、lifecycle条件を機械検証できないため採用しない。

## Consequences

- Positive: 価値コメントはtest sourceと同じ変更単位で移動し、sidecarとの同期が不要になる。
- Positive: 同じsourceとpath入力から、AIへ渡すJSONを再現できる。
- Positive: 欠落、重複、未結合、不正TOML、不正schemaをAI審査前に拒否できる。
- Negative: test sourceへ構造化コメントを書く必要がある。
- Negative: 各source adapter v1の抽出集合はtest runnerのruntime collection集合を証明しない。
- Negative: TypeScript adapterはNode.jsと固定済みnpm依存、C# adapterは.NET 8 SDKと固定済みNuGet依存を必要とする。
- Negative: renameをまたぐ履歴追跡、oracle解決、repository全体の重複判定は別の仕組みを必要とする。
- Follow-up: 実利用で必要性を確認してから、runner照合、追加言語adapter、oracle resolver、authoring helperを独立した契約として追加する。

## Executable Anchors

- Source: `skills/review-test-value/scripts/extract_test_values.py`
- Tests / types / schemas / static checks: `skills/review-test-value/scripts/test_extract_test_values.py`、`skills/review-test-value/scripts/test_extract_test_values_multilang.py`
- User-facing format: `skills/review-test-value/references/comment-format-v1.md`
- Projection and diagnostics: `skills/review-test-value/references/output-v1.md`
