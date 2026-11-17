# 委譲と作業領域

## WithMateの通常子Sessionとnativeサブエージェント

WithMateのRole・委譲責務・通常子の選定と再利用は[協同guide](../guides/withmate-collaboration.md)に従う。全体統括の実作業は通常子へ委譲し、native子への直接委譲で代替しない。Worker内の細かな分担・独立reviewには製品nativeのサブエージェントを使える。

独立した会話・Character・実行設定・担当状態として継続して追う仕事には通常子、担当内で成果を回収・統合する分業にはnativeを基本とする。同じ仕事を重複委譲しない。native子を独立したWithMate参加者とみなさず、nativeの通知・返却・待機契約を使う。

通常のMain Sessionは役割を問わず、全体統括・個別統括・Workerを含めて1 Session・1専有Workspaceとし、同じ作業directoryを複数のSessionへ重複割当しない。他SessionのWorkspaceを追加directory等で直接編集して分離を迂回せず、許可されたread-only参照と共同編集は区別する。Auxiliaryとnativeサブエージェントはこの必須ルールの対象外であり、既存の編集所有・衝突回避・権限はそのまま保つ。

以下のnative制限とWithMateのcatalogは互いの許可を拡張しない。どちらも既存の委譲許可・必須専門審査・操作権限に従う。

## nativeサブエージェント

委譲前に読む。履歴継承はhookで `none` に固定されるため、目的、対象・編集所有、必要なcontext・参照の実path、期待成果・完了条件、権限、現在のSessionFolderを渡す。並行作業では競合を避け、ユーザーと他担当の変更を保護する。調査・reviewはread-onlyと明示する。

共有判断を扱う場合は採用済み判断と適用状況・未合意事項、[設計guide](../guides/design-decisions.md)も渡す。reviewには主要動作・後続の依存と[開発guide](../guides/development.md)の統合基準を含め、全規約を複製しない。子がGraph・Glossaryを利用できない場合は、親が許可範囲で必要な取得・記録を担う。bindingやtool制限は迂回しない。

native子の使用modelは以下の4つのみ。設定値と採用理由は[README](../../README.md#modelとrole)に記載する。

| model／汎用role | 選ぶ仕事 |
| --- | --- |
| `gpt-6.1-sol`／`general_sol` | 通常の親・一般childの既定。広い文脈や未解決の判断を含む調査・設計・実装・debug・review |
| `gpt-6-luna`／`general_luna` | 進め方・期待結果がほぼ決まった抽出・定型調査・設計済み実装・基準照合 |
| `gpt-6.1-terra`／`general_terra` | 明確な入力・要求・検証方法を持つ画像・画面読解、実描画確認、素材に基づく文章、局所修正 |
| `gpt-6-astra`／`general_astra` | 非Astra親から、高度な設計選択・契約矛盾・難しい反例を必要な問題に絞って渡す。Astra→Astraは禁止 |

必要な成果・判断・完了条件から選び、短さや単価だけで決めない。上位modelの前に下位modelの試行や事前診断を義務化せず、定型処理へ未解決の設計・安全判断を押し込まない。専門審査は該当Skillに従う。

role名から実modelを推測せず、起動時のmodel ID・effortを確認する。利用不可なら許可された親で可能な範囲を続ける。model変更で審査や操作権限を変えない。

待機はruntimeの通知・既定値とtoolの許容範囲を使い、短いpollingを避ける。timeout時は進捗と続行条件を確認して必要なら待ち直す。

test価値reviewはruntimeの `review-test-value` Skillに従い、専用role・scheduler・artifact storeを作らない。子は結果・根拠・実施確認・未解決を返し、親が統合・最終確認と指摘の採否・対応時期を判断する。通常の返却に専用文書は要らず、非ブロッカー全件修正待ちにはしない。

## 子の作業領域と親の準備

子を起動する直接の親が、起動前にその子の専用作業領域を作成・確認して絶対pathを渡す。全体統括は自身が起動する個別統括とWorkerの分を、個別統括は自身のWorkerの分を準備する。準備に失敗したら子の起動を保留し、親のWorkspaceを代用しない。子を親のWorkspaceで起動して自己準備させず、領域の準備・回収だけを目的にWorkerを起動しない。Worktree準備だけを直接依頼された場合も、受けた統括が自身で実施する。作業領域の管理は統括の直接操作に含めるが、短い実作業全般を統括へ戻す例外にはしない。

Git管理下の通常子には専用Worktreeを割り当てる。同じrepositoryでの並行作業は別のbranchで行う。Git管理外の作業は[非Gitの作業領域](#非gitの作業領域)に従う。配置先の取得と結果の使い分けは、協同guideの[Worktreeの配置先](../guides/withmate-collaboration.md#worktreeの配置先)を正本とする。

## Git worktreeの配置

commit固定は具体的な隔離・再現の必要に応じて使い、全reviewへ一律には要求しない。Git管理下の通常子Sessionには、reviewを含めて専用Worktreeを割り当てる。Auxiliaryとnativeサブエージェントでは、具体的な隔離・再現の必要に応じてWorktreeを使う。非Gitの場合は[非Gitの作業領域](#非gitの作業領域)に従う。ここでは独自のroot・分類・layoutやpath組み立てを定義しない。

親が、登録先の実体とbranch、分岐元のbranch・commit、作成先の占有、未コミット変更を確認し、必要なGit操作を行う。返された既存Worktreeは他Sessionの占有を確認してから割り当て、無条件に共有しない。forceで同じbranchを複数checkoutしない。配置候補の取得を作成済み・利用可能の証拠とせず、準備した実体の絶対pathを子のWorkspaceへ渡す。既存worktreeの移設・削除や他者の作業領域の上書きは、この準備の許可に含めない。

## 作業領域の再利用と回収

子の作業領域は同じSession・同じ担当作業で再利用し、Turn単位で作り直さない。待機・中断・修正待ちの間は保持し、idleや経過日数だけで削除しない。親は子の成果を受入し、必要な統合の後に回収する。回収前に、実行中や予約済みの作業と他Sessionの利用がないこと、成果と資料の保全、未コミット・未追跡・ignoredファイルに残すべきデータがないことを確認する。Worktreeとbranchは別々に回収できる。未統合のcommitや採否未決の成果を無断で破棄せず、中止・不採用の場合は保存か破棄かを決めてから扱う。通常の削除が拒否されたら、forceへの自動的な切り替えはしない。

親が回収できるのは、この運用で新規に作った子用のWorktree、ローカルtask branch、非Git専用領域に限る。無関係な既存領域とremote・default・protected branchは対象外とする。回収の管理台帳は新設せず、再開時は保存されたbranch・commitと保全した成果から親が作業領域を再準備する。

子Sessionへの送信が割当Workspaceの不在を理由に拒否された場合、送信元Sessionが復旧を担う。Git管理下では保存したbranch・commitから元の割当pathへWorktreeを再準備し、非Gitでは保全した入力から専用領域を再作成する。いずれも利用可能な実体を確認してから改めて送信する。拒否時に未配送（`effect: none`）が確認できた場合に限って再送し、受付結果が不明なら同じrequestIdと宛先で状態を確認して重複送信を避ける。送信元が安全に復旧できない場合は再送を保留して報告し、子Sessionに復旧を委ねない。

## 非Gitの作業領域

Git管理外の作業では、親が専用directoryへ今回必要な入力だけをコピーし、子は原本を直接編集しない。親は原本の現在状態と対象を確認して、必要な成果だけを反映する。directory全体の上書き戻しはしない。継続した開発や並行統合が見込まれる場合はGitでの管理を提案し、合意がない限りgit initや全ファイルのcommitをしない。DBや外部サービス等、directoryの分離だけでは隔離できない対象は、準備の前に方式を相談する。非Git専用領域の回収も、この運用で新規に作った専用領域だけを対象に、[作業領域の再利用と回収](#作業領域の再利用と回収)と同じ条件で行う。
