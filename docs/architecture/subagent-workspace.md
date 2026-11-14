# 委譲と作業領域

## WithMateの通常子Sessionとnativeサブエージェント

WithMateのRole・委譲責務・通常子の選定と再利用は[協同guide](../guides/withmate-collaboration.md)に従う。全体統括の実作業は通常子へ委譲し、native子への直接委譲で代替しない。Worker内の細かな分担・独立reviewには製品nativeのサブエージェントを使える。

独立した会話・Character・実行設定・担当状態として継続して追う仕事には通常子、担当内で成果を回収・統合する分業にはnativeを基本とする。同じ仕事を重複委譲しない。native子を独立したWithMate参加者やMemory／Affect所有者とみなさず、nativeの通知・返却・待機契約を使う。

以下のnative制限とWithMateのcatalogは互いの許可を拡張しない。どちらも既存の委譲許可・必須専門審査・操作権限に従う。

## nativeサブエージェント

委譲前に読む。履歴継承はhookで `none` に固定されるため、目的、対象・編集所有、必要なcontext・参照の実path、期待成果・完了条件、権限、現在のSessionFolderを渡す。並行作業では競合を避け、ユーザーと他担当の変更を保護する。調査・reviewはread-onlyと明示する。

共有判断を扱う場合は採用済み判断と適用状況・未合意事項、[設計guide](../guides/design-decisions.md)も渡す。reviewには主要動作・後続の依存と[開発guide](../guides/development.md)の統合基準を含め、全規約を複製しない。子がMemory・Graph・Glossaryを利用できない場合は、親が許可範囲で必要な取得・記録を担う。bindingやtool制限は迂回しない。

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

## Git worktreeの配置

worktreeやcommit固定は具体的な隔離・再現の必要に応じて使い、全reviewへ一律には要求しない。

WithMateでの配置先取得と結果の使い分けは、協同guideの[Worktreeの配置先](../guides/withmate-collaboration.md#worktreeの配置先)を正本とする。ここでは独自のroot・分類・layoutやpath組み立てを定義しない。

親は、登録先の実体とbranch、分岐元のbranch・commit、作成先の占有、未コミット変更を確認して準備を手配する。全体統括は実際のGit操作を担当へ委譲する。配置候補の取得を作成済み・利用可能の証拠とせず、準備した実体の絶対pathを子のWorkspaceへ渡す。既存worktreeの移設・削除や他者の作業領域の上書きは、この準備の許可に含めない。
