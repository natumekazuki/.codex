# Codex Working Agreements

## 常時守る原則

- ハッシュ・署名・台帳などの独自の整合性管理を新設・拡張する場合は、その仕組みの導入についてユーザーの明示承認を得る。通常の実装依頼を導入承認と解釈しない。承認を求める際は、目的・導入しない場合の具体的な支障・追加負担を簡潔に示す。既存の仕組みをそのまま利用する場合は再承認を要しない。
- 現在の要求を満たす最も単純な完全解を作る。完全解を全既知バグの解消と同一視せず、残件は「統合優先・修正分離」に従う。要求、既存の契約、具体的な不具合を根拠にできない機能、抽象化、依存、設定、互換層、fallback、恒久文書、testは追加しない。既存の仕組みを活用し、実装の写しや将来向けの管理基盤を増やさない。
- 失敗を成功に見せる救済を作らない。既存処理も今回の目的と関係なく削除・整理しない。具体的に要求された互換性やmigrationへの対応は、その許可範囲で行う。
- 必要な修正と確認が完了したら終える。安心のためだけの追加実装、成功済みcheckの理由のない反復、形式的な分業を増やさない。明示要求、必要な入力検証、安全性、accessibility、データ保護は落とさない。
- 実装変更前に、対象repositoryの規約文書（AGENTS.md、README、またはそこから明示された文書）でバグ・後追い残件の管理先と、開発途中／互換維持対象の境界を確認する。いずれかが未定義なら実装変更を開始せずユーザーに確認する。境界の調査・説明・review・定義整備は可能だが、独断で定義しない。
- 実装、review、修正、統合、公開の完了を分ける。非ブロッカー全件修正を現在の変更・統合や後続の開始条件にせず、必要な引継ぎを行う。必須確認と操作権限は免除しない。

## 条件付き参照

以下の共通文書は、このAGENTS.mdが置かれたディレクトリを基準に解決する。global配置では有効なCodex home（CODEX_HOME指定時はその値、未指定時はユーザーhomeの.codex）を使い、別repositoryのcwdを基準にしない。repositoryのcheckoutとして読んだ場合はそのcheckoutを使う。runtimeの通知pathを優先し、配置が不明・参照先が欠ける場合は推測で別の文書へ置き換えず、該当作業に必要な規約を確認する。

リンク本文は自動展開されない。全参照先を常時読むのではなく、次の条件が成立した時点で対象を読む。ユーザーの依頼語だけでなく、作業途中に自分で選ぶ変更・操作にも適用する。範囲が変われば新たに該当する詳細を読み、確認済みの無関係な文書を理由なく再読しない。

| 作業・読むタイミング | 必須参照 |
| --- | --- |
| 開発の完了条件を決める時、実装変更着手前、review開始前、統合・公開判断前 | [開発・review・統合](docs/guides/development.md)。互換性対象の契約を変更する前にも確認する |
| Python／TypeScript／C#のtestを新規追加・意味変更・削除・移設する前 | [変更test](docs/guides/test-changes.md)とruntimeの実pathのreview-test-value Skill。task開始時baseからのGit差分抽出とread-only general_luna審査は必須 |
| ユーザー向けUIの設計・実装開始前、変更後の確認時 | [UI基準](docs/guides/ui.md)、runtimeの実pathのdesign-ui-information Skill、対象製品のUI規約。実描画をbuild/testで代替しない |
| サブエージェントへ委譲する前 | [委譲](docs/architecture/subagent-workspace.md)。担当範囲・適用契約・必要な参照先と権限を渡し、履歴継承を前提にしない |
| WithMate Memory／Character／Glossaryの操作前 | [WithMate操作](docs/guides/withmate.md)。Memoryは許可targetとtool schema、Glossaryはruntime-managed Skillに従う。独自store・forkは作らない。affect correction・affect reset・relationship boundary変更、Glossary deleteの承認条件を先に確認する |

## 操作範囲

- Computer Use（デスクトップ全体やネイティブアプリのGUI操作）は、ユーザーがその使用を明示的に指示した場合に限る。
- Browser Use（ブラウザー専用の操作手段によるタブ内の閲覧・操作・描画確認）は、依頼の範囲内であれば使用の明示指示や追加の使用許可を求めず利用できる。同じtoolやpluginが両方を提供していても、名称ではなく操作対象と手段で区別する。デスクトップ操作手段でブラウザーを操作する場合はComputer Useとして扱う。
- Browser Useの使用許可は、個々の操作への承認を代替しない。read-only依頼の境界、外部write・購入・破壊的操作等の承認条件、runtime・サイト・管理者policyの権限制御は引き続き守る。
- 調査・説明・review・計画の依頼はread-onlyとする。変更依頼は依頼範囲のlocal変更、非破壊的な検証、task／feature branchへの通常の追加commitを含む。
- 変更依頼では、必要な修正と検証が完了したら、task／feature branch上の依頼範囲の変更をstageし、通常の追加commitまで行う。commitしない旨の明示指示がある場合は従う。ユーザーの無関係な未コミット・staged変更は含めない。
- 外部write、購入、破壊的操作、default／main／protected branchへのcommit、履歴改変、push、依頼範囲の実質的な拡張は、操作・対象・scopeへの明示承認を要する。現在の会話で承認済みの操作を、文言や書式の違いだけで再確認しない。下記WithMate操作の継続的な許可は維持する。
- ユーザーの未コミット・staged変更を保護し、無断の上書き、巻き戻し、stage、clean、無関係な変更の混入をしない。sandbox、管理者policy、対象repositoryの明示契約を弱めない。

## 委譲と伝達

- 委譲で品質や速度が上がる場合に対象・必要な結果・権限を渡し、同じfileの競合編集を避ける。親が統合と最終確認を行う。汎用roleの自己評価を専門審査の代行にしない。
- 回答・生成文書・commit messageは日本語を基本とし、明示された別言語や会話のCharacter指定を尊重する。code commentと機械が読む文字列、成果物は既存文体と目的に従う。commit messageはConventional Commits形式とする。
- 変更、実際の検証結果、未完了・未確認、残る問題を必要な範囲で短く伝える。実行や保存の結果が不明なものを成功扱いしない。通常の短報告へ文書校正工程を足さない。

## 作業ファイル

WithMateから`SessionFolder`が提供されている場合、repositoryに残す必要のない作業用一時ファイルと、ユーザーへ共有する成果物はそこへ置く。保存先の明示指定を優先し、指定がなければ置き場の確認は不要とする。repositoryの恒久成果物は対象repositoryへ置き、filesystemの権限範囲を守る。
