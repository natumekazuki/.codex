# Write workflow

一般・業務文書の新規作成、リライト、自然さ・読みやすさの改善に使う。ユーザーが指定した文体やCharacterを優先し、事実、引用、数値、固有名詞、JSONやschema、CLI token、test metadata、API名など機械が読む文字列を文体調整で変えない。

## 設計する

1. 読者、目的、読み終えた後に起きてほしいことを特定する。不明点が結果を変える場合だけ確認する。
2. 文書タイプが定まったら、対応する型を一つ読む。
   - 議事録: [doctypes/minutes.md](doctypes/minutes.md)
   - 調査・分析レポート: [doctypes/report.md](doctypes/report.md)
   - 社内ガイド・マニュアル: [doctypes/guide.md](doctypes/guide.md)
   - リサーチメモ・企画書・ディスカッションペーパー: [doctypes/memo.md](doctypes/memo.md)
   - スライド構成: [doctypes/slide.md](doctypes/slide.md)
3. 主メッセージを一文にし、見出しだけで論旨が追えるスケルトンを作る。主メッセージを決められない場合は、[revision-guide.md](revision-guide.md) の「素材集め」に戻る。
4. 重要な節を厚く、軽い節を短くする。全節を同じ構成や分量に揃えない。

既存の `style-profile.md` があれば読む。ユーザーが文体の学習を求めた場合だけ、[../assets/style-profile-template.md](../assets/style-profile-template.md) を使って過去文章から傾向を抽出する。個別の指摘を一般的な禁止語へ拡張しない。

## 執筆する

[writing-constitution.md](writing-constitution.md) を読み、結論と主メッセージを先に置く。説明は地の文を基本とし、並列項目、手順、比較にだけリストや表を使う。固有名詞、数値、実例で主張を接地し、事実、推定、意見、限界を区別する。

リライトでは、元の事実と意図を保つ。同じ修正を全項目へ一律に当てず、読者に価値を足す箇所だけを直す。

## quickで検査する

quickでもlintを省略しない。Skill rootを基準に次を実行する。

```text
uv run <skill-root>/scripts/lint.py --json <file>
```

文書のジャンルが明確なら `--genre essay|tech|business` を指定する。lintを実行できない環境では [manual-checklist.md](manual-checklist.md) を使い、未実行理由を明示する。

lintのfindingを文脈に照らして「直す」「残す」に仕分ける。見出しと各段落の先頭文を自分で読み、論旨、見出し、反復、濃淡、結びを確認する。findingがなければ一周で終えてよい。

## fullで検査する

fullではquickの工程に加え、次の機械的確認と独立reviewを行う。

```text
uv run <skill-root>/scripts/outline.py <file>
uv run <skill-root>/scripts/terms.py <file>
uv run <skill-root>/scripts/lint.py --reading-load <file>
```

`terms.py` は専門用語の確認が必要な文書で使う。review観点は成果物に生じ得る欠陥から選ぶ。

- 構造: 論旨、見出し、反復、濃淡、結びを確認する。
- 読みやすさ: 語順、係り受け、主述の距離、否定、列挙、専門語の負荷を確認する。
- doctype適合: 選んだ型の必須要素と用途への適合を確認する。

すべての文書に三つのreviewerを固定しない。複数の独立した観点が必要なら、その独立性を保てる担当へ分ける。一人の独立reviewerが関連する複数観点をまとめてもよい。執筆者は所見を判断台帳へ統合し、直すか残すかを決める。明示されたreview観点は省略しない。

読みやすさの判断が必要なら [readability-principles.md](readability-principles.md) と [readability-antipatterns.md](readability-antipatterns.md) を読む。lint findingの判断に迷ったカテゴリだけ [revision-guide.md](revision-guide.md)、[forbidden-patterns.md](forbidden-patterns.md)、[translationese.md](translationese.md)、[genre-notes.md](genre-notes.md) を読む。全referenceを一括で読み込まない。

`scripts/semantic.py` は重量級の実験的なopt-in検出器であり、fullの必須工程ではない。ユーザーが深層検出を求め、初回の大きなdownloadを許可し、環境が対応するときだけ使う。

## 収束して片付ける

修正後はlintを再実行し、直前のJSONを `--baseline` に渡してresolved / new / persistingを確認する。すべてのfindingを仕分け、修正による新しいfindingがなくなるまで繰り返す。同じfindingが再発する場合は [revision-guide.md](revision-guide.md) の「発散ガード」を使う。

最後に初見の読者として通読し、主メッセージ、事実保持、読みやすさ、リズムを確認する。作業中の判断台帳、lint JSON、下書きのbackupは削除し、ユーザーが求めた完成物だけを残す。
