# 委譲と作業領域

## WithMateの通常子Sessionとnativeサブエージェント

独立した会話・Character・実行設定・担当状態として継続して追う仕事はWithMateの通常子Session、担当内で成果を回収・統合する分業は製品nativeのサブエージェントを基本とする。調査／実装／review、規模、長さ、Modelだけで固定しない。統括の分担と直接行える範囲は[協同guide](../guides/withmate-collaboration.md#担当の選択と依頼)に従う。同じ仕事を両方へ重複委譲しない。

WithMateの子は別の参加者であり、[Session間の協同](../guides/withmate-collaboration.md)でRole・背景確認・Coordination・明示報告・Turn終了と再開を扱う。同じ担当範囲の追加依頼には継続可能な既存Sessionを使う。native子は別のWithMate参加者や独立したCharacter Memory／Affect所有者とはみなさず、製品nativeの通知・返却・待機契約を使う。

どちらも既存の委譲許可、必須専門審査、操作権限とruntime制限に従う。以下のnative用model・tool制限をWithMate全Providerのallowlistへ広げず、WithMateのカタログをnativeの許可拡大にも使わない。WithMate通常子の[実行条件の選定](../guides/withmate-collaboration.md#実行条件の選定)は協同guideに従う。

## nativeサブエージェント

委譲前に読む。汎用`general_sol`、`general_luna`、`general_terra`、`general_astra`には、対象、必要な結果、権限を依頼ごとに渡す。調査だけの依頼では編集しない。履歴継承に頼らず、review依頼には主要動作、後続の依存、[開発・review・統合](../guides/development.md)の統合基準と、非ブロッカーを全件修正待ちにしないことを含める。必要な参照先は参照元文書から解決した実pathで渡し、全規約を無条件に複製しない。

委譲時は現在のSessionFolderと、作業に必要な共有情報・参照先を渡す。子がtool制限等でMemory・Session Graph・Glossaryを直接利用できない場合は、親が許可範囲内で必要な取得・記録を担い、子へ必要な結果を渡す。子のtool権限とSession bindingの制約を守る。

共有する設計判断に関わる依頼では、必要な要求・前提、採用済みの判断と適用状況、未合意事項、[設計判断・文書化](../guides/design-decisions.md)の参照先も渡す。同じ前提の判断を再利用し、現行実装や草案を採用根拠に置き換えない。不足の調査・推奨案・草案作成までを依頼できるが、親からの委譲を未合意方針の採用や操作権限の拡大と解釈しない。

native子の使用modelは`gpt-6.1-sol`、`gpt-6-luna`、`gpt-6.1-terra`、`gpt-6-astra`のみ。公式情報、設定値と採用理由は[README](../../README.md#modelとrole)に記載する。

- GPT-6.1 Solを通常の親と一般childの既定とし、調査、設計、実装、debug、reviewを担当させる。広い文脈や未解決の判断を含む一般作業を担い、限定した作業でも利用できる。
- Lunaは、進め方・手順・期待結果がほぼ決まっている抽出、定型調査、設計済みの実装、判断済みの基準に沿った照合等へ割り当てる。範囲が小さいことだけで選ばず、未解決の設計・安全性の判断を押し込まない。
- Terraは、明確な入力・要求・完了条件を持つ画像・画面の読解、実描画の確認、提供素材に基づく文章作成、検証方法が明確な局所修正の候補とする。視覚・文章の解釈が必要な場面で選び、Lunaで手順化できる処理を一律に置き換えない。広い設計・契約判断を局所修正という理由で押し込まない。
- Astraは、高度な判断が要求される設計の選択、契約間の矛盾の解消、難しい反例の検討等を、非Astra親から必要な問題に絞って渡す場合に使う。Astra親はその判断を自ら担当し、Astra→Astraは禁止する。

taskの短さやtoken単価だけで決めず、必要な成果・判断と完了条件から直接選ぶ。上位modelの選択に下位modelの失敗を要求せず、Terra等による事前診断を全taskの工程にしない。下位modelの形式的な試行、念のための多重reviewは不要。専門審査の手順と必須条件は該当Skillに従い、役割不足や未解決事項があれば親が必要な追加context・担当を判断する。modelの変更を審査免除やComputer Use等の権限拡大に使わない。

指定modelがruntimeで利用できない場合、許可された構成の親で可能な範囲を続ける。role名だけで実modelを推測せず、起動するsessionのmodel IDとeffortを確認する。履歴継承はhookで`none`に固定されるため、対象・必要な文脈・完了条件を起動時の依頼へ含める。

待機はruntimeの通知・既定値とtoolの許容範囲を使い、短い間隔のpollingを避ける。timeoutした場合は進捗と続行条件を確認し、必要なら再度待つ。

test価値reviewの抽出、read-onlyサブエージェントへの委譲、review観点、完了判断は[review-test-value](../../skills/review-test-value/SKILL.md)を正本とする。専用roleや独自のworker、scheduler、artifact storeは使わない。

同じworking treeで作業する場合は編集範囲と生成物の競合を避け、ユーザーと他の担当の変更を保護する。子は結果、根拠、実行した確認、未解決事項を親へ返し、親が統合と最終確認を行う。通常の成果返却に専用文書は不要である。

親は上記の開発・統合基準で指摘の採否と対応時期を判断し、今回の仕上げと後追いを分ける。非ブロッカーを一律に別タスク化せず、後追いの着手・完了を現在の変更の完了・統合条件にしない。

## Git worktreeの配置

worktreeやcommit固定は具体的な隔離・再現の必要に応じて使い、全reviewへ一律には要求しない。

WithMateでの配置先取得と結果の使い分けは、協同guideの[Worktreeの配置先](../guides/withmate-collaboration.md#worktreeの配置先)を正本とする。ここでは独自のroot・分類・layoutやpath組み立てを定義しない。

親が、登録先の実体とbranch、分岐元のbranch・commit、作成先の占有、未コミット変更を確認し、必要なGit操作を行う。配置候補の取得を作成済み・利用可能の証拠とせず、準備した実体の絶対pathを子のWorkspaceへ渡す。既存worktreeの移設・削除や他者の作業領域の上書きは、この準備の許可に含めない。
