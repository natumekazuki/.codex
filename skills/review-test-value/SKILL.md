---
name: review-test-value
description: Python、TypeScript、C#の追加・意味変更・削除・移設testを、固定したGit差分、旧側を含む本文、docコメント、契約の根拠から独立したread-onlyサブエージェントへ渡して価値を審査する。runtime test collectionや動的生成caseの展開には使わない。
---

# Review Test Value

何を残すかはユーザーhomeの `~/.codex/docs/guides/test-changes.md`、説明は同じhomeの `~/.codex/docs/guides/code-comments.md`、独立担当の選定は `~/.codex/docs/architecture/subagent-workspace.md` に従う。手順はruntimeが示すこのSkillを使う。reviewとテスト実行は別である。

## 差分と本文を固定する

1. タスク開始時のbaseを完全なcommit IDで示し、審査する対象snapshotを固定する。対象commit、確認中に変えないindex、または未追跡分を含めて保存した変更集合を使う。別のbaseや動くworking treeの名前だけで固定したことにしない。保存した範囲と実際に出す差分が変われば、影響箇所を更新する。
2. パスで事前に絞らず、ファイルの追加・削除・改名とpatchの両側を確認する。commitなら `git diff --name-status -M <base> <target>` と `git diff --no-ext-diff --no-textconv -M <base> <target>`、indexなら `git diff --cached --name-status -M <base>` と `git diff --cached --no-ext-diff --no-textconv -M <base>` を使う。Git属性などでテキストソースにpatchが出ない場合は、対象パスの旧・新の元の内容を次の手順で取得して比較する。未追跡ファイルが対象なら、名前だけでなく本文も固定した対象に含める。test file名だけで選ばず、既存・変更両側でframeworkの宣言・呼び出しや生成元、fixture・mock・設定の変更も確認し、testの意味が変わる影響先を辿る。
3. 追加・意味変更（docコメントの意味変更を含む）・削除・移設されたtestを、両側のパスと宣言位置で特定する。変更hunkだけでなく関連するtest本文と付随するdocコメント、比較に必要な前後を読む。旧本文は `git show <base>:<old-path>`、対象側は `git show <target>:<new-path>` またはindexの `git show :<new-path>` で取得できる。純粋な移設でも、runnerが検出するか、依存・実行条件・保証が維持されるか確認する。改名が削除と追加に分かれても片側を落とさず、名前だけで同じtestとみなさない。

旧testのdocコメントがない、または旧書式しかないときは、旧本文・当時の記述と確認できる契約をそのまま使う。削除のために過去の説明を追加せず、不明な対応・根拠は不足として示す。専用CLI・JSONによる全件機械選択やruntime case一覧の網羅性は保証しない。必要対象を確認できなかった範囲は明記する。

## 独立した担当へ渡す

通常のread-onlyサブエージェントへ、repository root、固定base・対象snapshot、差分範囲、対象fileとlocator、旧側を含む本文・docコメント、維持契約の確認先、以下の観点を渡す。契約・SUT・fixtureを共有する範囲はまとめ、分ける場合も旧側を含めて担当範囲の漏れを確認する。削除・置換の提案理由と既知の契約は区別する。担当自身が対象snapshotのproduction code、fixture、mock、根拠を読めるようにし、アクセスできない原文は出典付きで渡す。親の要約だけで置き換えない。

## 一回のreviewで確認する観点

- **守る契約。** 失敗が利用者・データ・機能に及ぼす具体的な影響と、既存checkでは足りない保証を確認する。実装やtestの存在自体は保持理由にならない。削除・移設では、現役の保証の持ち先と旧機構専用の保証を分ける。同等品を自動では要求しない。
- **説明と根拠。** 条件、期待結果、検出したい故障が読めるか。期待値に根拠が要るなら正本の箇所を辿る。一時固定・一時検証の見直しや除去の条件を確認し、未確認の判断理由や契約を補作しない。
- **本文と検出力。** setupとactionが対象のproduction pathを通り、故障がassertionの観測に届くか。期待値と実装の循環、mockが隠す故障、内部配線を縛るだけのassertionに注意する。移設で検出・設定・依存が変わるなら影響まで確認する。

## 審査を閉じる条件

親は実際の所見を読み、確認した範囲と未確認を区別し、指摘を扱う。起動失敗・空の応答・必要対象の確認漏れを審査済みにせず、不足を補って影響範囲だけ再確認する。差分確認、独立審査、必要なtest実行、統合可否は別に扱う。指摘の分類・記録・引継ぎは `~/.codex/docs/guides/development.md` に従う。固定verdictや返答schemaは要求しない。
