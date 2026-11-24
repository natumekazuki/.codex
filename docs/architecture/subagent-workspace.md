# 委譲と作業領域

委譲先は責任の持たせ方で選ぶ。独立した会話・Character・担当状態として成果を追うならWithMateの通常子、Workerが担当内で回収する分業・独立reviewなら許可されたnative子を使う。同じ仕事を二重に渡さない。統括の責任・通常子の選定と配送は[Session間の協同](../guides/withmate-collaboration.md)に従う。nativeは別のWithMate参加者ではなく、製品の通知・返却経路を使う。

## 子の作業領域と親の準備

WithMateの通常Mainは統括・Workerともに1 Sessionにつき1専有Workspaceを使う。起動する直接親が起動前に実体を準備し、その絶対pathを渡す。準備だけのWorkerを立てず、失敗時は子の起動を保留する。他SessionのWorkspaceを共用したり、追加directory経由で直接編集したりしない。許可されたread-only参照は共同編集と区別する。

Git管理下の通常子にはreviewでも専用Worktreeを用い、並行作業は別branchとする。特定commitへの固定は再現・隔離が必要な時に選ぶ。Auxiliaryとnative子には一律の専用Workspaceを課さず、編集所有・衝突・権限と必要な隔離から決める。

## Git worktreeの配置

1. WithMateでは対象repository・branchを `session.resolve_worktree` で解決する。利用可能な既存登録を優先し、返された配置先を使う。未設定なら配置に必要な不足だけ確認する。今回限りの指定は新規候補にだけ適用し、保存方針・既存登録を変更しない。SessionFolder・Crew Folderからpathを組み立てない。
2. 配置候補は実体ではない。直接親が分岐元のbranch・commit、実体とbranch、他Sessionの占有、未コミット変更を確認して必要なGit操作を行う。同じbranchをforceで複数checkoutしない。既存領域の移設・削除・上書きは準備の範囲外。追加writeが要るなら専用の狭い範囲で通常の承認を求め、拒否を権限拡大で迂回しない。
3. 子へ渡すのは利用可能と確かめたWorkspace。WithMateはGitの作成・統合を代行しない。実体・branch・占有が変わった事情がなければ確認結果を再利用できる。

## 非Gitの作業領域

親が専用directoryに必要な入力だけをコピーし、子は原本を直接編集しない。親は受入時の原本と照合し、必要な成果だけを戻す。継続的な並行統合にGitが必要なら提案し、合意なしの `git init` や一括commitはしない。DBや外部サービスなどdirectory分離では保護できない対象は準備前に方式を相談する。

## 作業領域の再利用と回収

同じSession・同じ担当の続きには元の領域を使う。idle・経過日数を理由に待機中・中断中・修正待ちの領域を回収しない。親が回収できるのは、この運用で**新規に作った**子用Worktree、ローカルtask branch、非Git専用領域だけ。既存領域、remote・default・protected branchを含めない。

回収は受入・必要な統合の後に行う。実行中・予約済みの作業や他Sessionの利用がなく、成果・参照資料が保全されていることを確認する。未コミット・未追跡・ignoredのデータも対象とし、未統合commitや採否未決の成果を捨てない。中止・不採用なら保存か破棄かを先に決める。Worktreeとbranchは別々に扱い、通常削除の拒否からforceへ切り替えない。

割当Workspaceの不在で送信が拒否されたら、送信元が元の割当pathに復旧する。Gitなら保存したbranch・commit、非Gitなら保全した入力から再準備する。実体を確認できなければ再送を保留し、自分で復旧できない子へ任せない。再送可否は[受付の証拠](../guides/withmate-collaboration.md#通常送信と実行中の補足)で判断する。専用の回収台帳は作らない。

## nativeサブエージェント

nativeの使用モデルは次の4つに限る。WithMateのcatalogや外部role名でこの制限は広がらない。

| model | 向いている担当 |
| --- | --- |
| `gpt-6.2-sol` | 通常の親・一般子の既定。広い文脈を要する調査・設計・実装・debug・review |
| `gpt-6-luna` | 手順と期待結果が定まった抽出・変換・照合・設計済み実装 |
| `gpt-6.1-terra` | 入力・完了条件が明確な画像や画面の読解、素材に基づく文章、局所修正 |
| `gpt-6.2-astra` | 難しい判断、契約間の矛盾、反例。非Astra親から問題を絞って渡す。Astra→Astraは禁止 |

必要な成果・判断・検証から直接選び、短さ・単価や下位modelの事前試行を条件にしない。起動時の実model・effortを確認する。未提供なら許可された親でできる範囲を進め、必須専門審査を親の自己評価で代用しない。

汎用roleの権限は親から継承するが、履歴は継承させない（`fork_turns=none`）。親は目的・編集所有・必要な実path、SessionFolder、契約・完了条件・許可範囲を依頼に含める。調査・reviewはread-onlyを明示し、利用できるruntime制限を適用して他担当・ユーザーの変更を保護する。共有判断に関わる時は採否・適用範囲と設計guide、reviewでは主要動作・後続契約と開発guideの該当基準を渡す。Graph・Glossaryのbindingを持たない子には、親が権限内で必要な情報を取得・記録する。

SessionStart／SubagentStartは共通入口を通知する。制限を実行するのは別のPreToolUse hookで、一覧外の明示model、Astra親からAstraの明示指定または `general_astra` を拒否し、許可する呼出しの履歴だけを `none` に置換する。省略modelや任意roleの実modelを解決するのはhookではなく設定・runtimeである。

native子は結果と受入に必要な根拠を親に返す。待機はruntimeの通知・許容timeoutを使い、必要な場合にだけ待ち直す。親が統合・最終確認・指摘の採否と時期を担う。test価値審査はruntimeの `review-test-value` Skillに従い、汎用の返却書式や別の審査経路を作らない。
