---
name: review-test-value
description: Python、TypeScript、C#の変更testをGit差分から決定論的に抽出し、構造化された@test-value metadataとtest本文を通常のread-onlyサブエージェント審査へ渡す。runtime test collectionや動的生成caseの展開には使わない。
---

# Review Test Value

差分から選定するのは抽出器、testと維持契約の対応を確かめるのは独立したread-onlyの審査担当、指摘の採否・対応時期を決めるのは親である。恒久testを残す判断はユーザーhomeの `~/.codex/docs/guides/test-changes.md`、担当選択は `~/.codex/docs/architecture/subagent-workspace.md` に従う。

## 対象を固定して抽出する

タスク開始時のbase commitと審査対象のsnapshotを特定する。追加・意味変更・削除・移設を含む差分から、言語ごとに抽出する。宣言の認識範囲は[対応adapter](references/source-adapters-v1.md)、metadataの追加・修正は[v2コメント書式](references/comment-format-v2.md)に従う。script・referenceは作業対象repositoryではなく、runtimeが示すこのSkillのdirectoryから解決する。次の例の `$reviewSkillRoot` はその絶対pathである。

```powershell
python -X utf8 "$reviewSkillRoot/scripts/extract_test_values.py" --root <repository-root> --changed-from <task-base-commit> --language python
```

`--language` は `python`、`typescript`、`csharp` のいずれか。既定のworking tree、`--staged` のindex、`--head <commit>` のcommitは別の対象である。[Git差分・遷移契約](references/git-selection-v1.md)に従い、都合のよいbase・path・行を手で選ばない。

| 終了値 | 審査へ渡せるもの |
| --- | --- |
| `0` | JSONの `tests` と `transitions` の全record。対象なしと審査済みを区別する。 |
| `1` | 抽出未完了。source・metadataの診断を確認し、部分結果で進めない。直比較の失敗が `RECORD_TRANSITION_UNRESOLVED` だけなら、[既存のfirst-parent統合履歴経路](references/git-selection-v1.md#統合履歴による審査)を使える。元のbaseと最終snapshotを保ち、終端を含む全区間の抽出成功と全recordの審査が必要。 |
| `2` | CLI・adapter・I/O等の失敗。抽出成功や問題なしとは扱わない。 |

遷移の旧・新の本文とmetadataを保つ。`DELETED.before` は、旧testにmetadataがなければ `null` のまま、正常なv1なら元のまま審査に使う。現行側の欠落・不正を補完しない。固定baseのTypeScriptの動的titleは式を含む宣言であり、実行時case一覧ではない。移設が削除と追加に分かれても、名前だけで存続と決めない。抽出を通すためにtestの意味や配置、履歴を変えない。

## 独立した担当へ渡す

契約・SUT・fixtureを共有するrecordは全件を読める単位にまとめ、通常のread-onlyサブエージェントへ依頼する。分割した場合も全record・全遷移を網羅する。担当の枠が限られれば順次扱い、同じ対象を観点ごとに再委譲しない。

依頼にはrepository root、base・対象snapshot、対象fileとlocator、抽出したmetadataとtest source、審査範囲と維持契約の根拠、下記の観点と統合基準を渡す。削除・置換の理由は確認済みの契約と分ける。担当は該当snapshotのproduction code、fixture、mock、oracleへ自分で辿る。担当から取得できないsourceは親が出典とともに渡し、要約や親の自己評価で独立確認を置き換えない。

## 一回のreviewで確認する観点

- **守る契約。** そのtestが落ちるとどの利用者・データ・機能に何が起きるか。実装や既存testの存在、`permanent` の指定は維持契約の根拠ではない。削除・移設も同じ基準で見て、旧機構専用のtestに同等品を自動で要求しない。有効な保証には、既存checkや小さいtestの方が直接検出できないかを考える。
- **metadataと根拠。** claim・fault・observable・観測境界・scope・lifecycleが自己完結し、欠陥を具体的に反証できるか。[oracleの根拠](references/comment-format-v2.md#oracleの根拠参照)を実際に辿って期待値を確認する。本文から欠けた意味を補わず、参照不能なら判断に必要な不足を返す。
- **本文と検出力。** setupとactionが意図するproduction pathを通り、欠陥がassertionの直接観測まで伝わるか。期待値が実装と循環する、mockが欠陥を隠す、内部の配線を縛るだけ、といった場合は、どの故障を検出できないか、またはどの正しい変更を拒むかを示す。

## 審査を閉じる条件

親は、対象ごとの自然言語の所見を読み、根拠・影響を確かめる。抽出成功、全recordの独立審査、必要なtest実行、修正済み、統合可能を分ける。起動失敗・空の応答・未確認recordがあれば審査は完了していない。必要なcontextまたは担当を補い、影響するrecordだけ再確認する。

指摘の採否・時期・引継ぎは `~/.codex/docs/guides/development.md` に従う。必須確認を後追いにはできないが、任意改善の全件修正は完了条件ではない。固定verdict・返答schema・追加の同一性証明は求めない。抽出器を変更した場合は、`scripts/test_extract_test_values*.py` のPython・多言語回帰testを実行し、抽出器とGit選択scriptの構文も確認する。
