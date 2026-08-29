# ADR-0021: テスト価値審査の対象をGit差分から選択する

- Status: accepted
- Date: 2026-08-29
- Supersedes: none
- Extends: ADR-0020

## Context

- ADR-0020の明示path抽出は決定的だが、新規・変更testの価値審査を呼び出し側が省略できる。
- test file単位でコメントを必須化すると、変更していない既存testまで一括移行の対象になる。
- AIが変更rangeを手入力すると、選択漏れを機械的に区別できない。
- 現段階ではrepository全体のCI gateを導入せず、Codexの標準作業経路を強制したい。

## Decision

- `review-test-value`の公開CLIへ、base revisionと比較対象から対象testを選ぶGit modeを追加する。
- Git modeは対象言語を一つ指定し、その言語の変更fileをGit差分から自動発見する。呼び出し側は個別pathやline rangeを指定しない。
- baseと比較対象は直接比較し、merge-base、upstream、task開始commitをCLIが推測しない。task開始時に固定したbaseを呼び出し側が渡す。
- 比較対象はworking tree、index、明示commitを区別する。抽出sourceも比較対象と同じsnapshotから読む。
- working tree比較はbase以降のcommit、staged、unstaged、non-ignored untracked fileを含む。
- test declarationのsource rangeまたは直接隣接する`@test-value` blockへ差分が交差したrecordだけを抽出する。
- 変更していない既存testとそのmetadata欠落diagnosticはGit modeの結果へ含めない。
- syntax error、decode error、adapter failureなど、変更sourceの信頼できる抽出を妨げるfailureは選択範囲外として隠さない。
- pure renameと削除は価値内容の審査対象にしない。renameと同時に内容が変わった場合は変更recordを対象にする。test削除の妥当性は`design-tests`が所有する。
- 一つのresultは一つのsource adapterだけを表すADR-0020の契約と、output schema v1を維持する。
- CI gateはこの判断に含めない。運用実績から機械的なmerge gateが必要になった場合は別契約として判断する。

## Alternatives

- AIがpathやline rangeを指定する: 既存testの一括移行は避けられるが、対象漏れを呼び出し側が作れるため採用しない。
- 変更file内の全testを審査する: 実装は単純だが、無関係な既存testのmetadata移行を強制するため採用しない。
- 最初からCI gateを導入する: 強制力は高いが、repository運用とmerge policyまで同時に拡張するため現段階では採用しない。

## Consequences

- Positive: 新規・意味変更されたtestをCodexの裁量で選択対象から外せない。
- Positive: 変更していない既存testへ一括でmetadataを導入せず段階移行できる。
- Positive: working tree、index、commit snapshotのどれを審査したかを区別できる。
- Negative: Git管理repositoryと明示base revisionが必要になる。
- Negative: 複数言語の変更では言語ごとにCLIを実行する必要がある。
- Negative: pure renameと削除の価値判断はGit modeの対象外となる。

## Executable Anchors

- Git selection: `skills/review-test-value/scripts/git_diff_selection.py`
- Extraction integration: `skills/review-test-value/scripts/extract_test_values.py`
- Tests: `skills/review-test-value/scripts/test_extract_test_values.py`、`skills/review-test-value/scripts/test_extract_test_values_multilang.py`
- Usage contract: `skills/review-test-value/references/git-selection-v1.md`
