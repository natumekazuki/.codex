# Codex 個人設定

本書は`natumekazuki/.codex`の配布資産、保守、配置の案内である。各repositoryでCodexが従う共通ルールの入口は`AGENTS.md`、作業別の本文は`docs/guides/`等の明示された参照先に置く。本書の配布元固有の管理先・リリース境界・検証手順を、他repositoryの作業ルールとして適用しない。

Astraを親に使い、一般の仕事の進め方はモデルへ任せる。追加の共通ルールは過剰実装の抑制、統合優先・修正分離、変更testの価値確認、ユーザー向けUIの設計品質を中心にする。ユーザー変更の保護、操作範囲、承認条件、必要な安全動作は維持する。

このcheckoutの`review-test-value`は、Git差分から変更testを抽出し、通常のread-onlyサブエージェントへreviewを委譲するSkillである。抽出器の成功、全recordのreview、各指摘の扱いを確認する。review完了と全件修正は分け、非ブロッカーは後追いへ引き継ぐ。

## このrepositoryの管理先とリリース境界

このrepositoryはCodexの共通ルールをGit管理する配布元であり、`AGENTS.md`にはrepository固有の規約を置かない。この節は`natumekazuki/.codex`の開発・保守だけに適用し、共通ルールの適用先repositoryには適用しない。

- このrepositoryのバグと後追い残件は、`natumekazuki/.codex` のGitHub Issueで管理する。Issueへの登録・更新・closeは、通常の外部write権限と個別承認の対象として扱う。

### 本repositoryの開発・リリース境界

- Gitタグのないcommitとbranch上の変更は開発途中として扱い、途中状態との互換性を保証しない。
- `vMAJOR.MINOR.PATCH`形式のGitタグが指すcommitをリリース状態とし、そのタグのリリースノートに記載した利用者向け契約を互換維持の対象とする。破壊的変更はmajor versionを上げ、互換修正はminorまたはpatch versionを上げて新しいタグへ記録する。
- 初回の維持対象は`v1.0.0`であり、`review-test-value`のCLI、構造化result、metadata v2、対応adapter、Git差分選択の契約を含む。各契約の詳細は既存のSkill referenceと`docs/releases/v1.0.0.md`で確認する。
- リリースごとに`docs/releases/README.md`の一覧と`docs/releases/vMAJOR.MINOR.PATCH.md`を更新し、変更、互換性、検証結果を記録する。

## 構成

共通ルール本文は`AGENTS.md`、`docs/guides/`、`docs/architecture/subagent-workspace.md`と各Skill・roleの指示に置く。`docs/architecture/instruction-governance.md`は配布構成の案内、`docs/runbooks/`は指定された導入・保守作業の手順である。`docs/system-prompt/`は編集元資産、`docs/adr/`と`docs/releases/`は本repositoryの記録であり、共通ルール本文の置き場ではない。

| 正本 | 内容 |
| --- | --- |
| `AGENTS.md` | 常時必要な原則・操作境界、条件付き参照 |
| `docs/guides/` | 開発・統合、設計判断・文書化、変更test、UI、WithMate操作の作業別詳細 |
| `agents/` | 汎用のカスタムrole |
| `skills/` | 変更testのreview、UI設計、管理・文書向けのSkill |
| `hooks/`、`hooks.json` | 共通ルールの短い再通知、サブエージェント起動時の履歴継承既定値 |
| `config.example.toml`、`config/` | 共有できる設定例。実configと認証は端末local |
| `docs/runbooks/` | 必要時の運用・導入手順 |
| `docs/releases/` | Gitタグごとのリリースノートと互換性・検証結果 |
| `docs/system-prompt/`、`.codex/model-instructions-withmate.md` | Codex system promptの取得版、日本語訳、WithMate用編集元 |
| `docs/adr/` | 判断履歴。適用状態を明記し、置換・撤回後も本文を保持する |

## 共通ルールの保守と検証

統合・後追い修正の共通基準は[開発・review・統合](docs/guides/development.md)、読む条件は[`AGENTS.md`](AGENTS.md)が正本である。以下は本repositoryでそれらの指示を変更・配置する際の保守手順と検証ケースである。

### 設計判断と文書の更新

共通の判断方法、文書の更新・保存、リリースノートのリンク規則は[設計判断・文書化](docs/guides/design-decisions.md)に置く。配布元の案内やリリースノートへ共通ルール本文を重複させず、正本を更新する。

入口とhookは検出条件と詳細への参照にとどめる。検証では、単純な変更、共有境界の不足、事実と方針、一部採用・保留、read-only、未定義境界、要求変更、branch統合・置換・廃止等を必要な範囲で確認する。確認結果は既存の作業報告・PR等へ残し、文書上の判断確認、実際の草案・応答、live配置・新規session等の実効確認を区別する。新しい恒久test・承認台帳・文書同期基盤は設けない。

### 方針変更の検証

変更した指示間の整合性、Skillの構文、既存hookの出力を確認する。行動は、許可された安全な対象で次のようなケースを使って確認する。各開発タスクで全ケースを実行する義務や、新しい恒久test・管理基盤は設けない。

| 条件 | 確認する行動 |
| --- | --- |
| 管理先が未定義／定義済み | 前者は実装開始前に確認し、後者は既存定義を利用する |
| 変更Aの主要動作・必須確認は成立し、補助表示の不具合が残る。後続タスクBがAの統合待ち | Aを引継ぎ・統合・必要確認後、Bを着手可能にする。Aの非ブロッカー修正を待たない |
| Aの主要動作・依存契約が不成立、または具体的な重大な安全問題がある | 対象の統合を止め、根拠と必要な対応を示す |
| test reviewで改善候補が残る／必須checkが失敗する／描画未確認 | 非ブロッカーは分離するが、必須確認の失敗・未実施は免除しない |
| ブロッカー修正の確認や別の修正タスクで、新しい非ブロッカーを発見する | 別件を引き継ぎ、必要な範囲だけ確認する。指定された修正自体を再延期しない |
| Issue登録に失敗する、または操作権限がない | 未登録・未実施を明示し、プロジェクトの運用と権限に従う。成功や引継ぎ済みを捏造しない |
| 後追い修正が現行バージョンに間に合わない | 非ブロッカーだけで公開を延期せず、修正リリース等へ引き継ぐ |

配布元の変更、実環境への配置、親・履歴を継承しない子・再開やcompact後の有効な指示、実際の行動を区別する。ルールの復唱や判断例だけでmerge・後続の開始が実証されたとは扱わず、実施した検証と未実施の範囲を既存の作業報告へ残す。

## modelとrole

本repositoryの設定例・role定義は`gpt-6-astra`、`gpt-6-sol`、`gpt-6-luna`で構成する。この節は配布設定と採用理由の説明であり、作業時の委譲基準は[Subagent Review Boundary](docs/architecture/subagent-workspace.md)が正本である。

### 公式情報と運用判断

2026-09-23にOpenAI公式のモデルページ、[GPT-6 guide](https://developers.openai.com/api/docs/guides/latest-model/gpt-6-astra.md)、[Codexのモデル選択](https://learn.chatgpt.com/docs/models)を確認した。公式の位置づけと、このrepositoryで採用する担当範囲を区別する。

| model | 公式の位置づけ | このrepositoryでの担当 |
| --- | --- | --- |
| [GPT-6 Astra](https://developers.openai.com/api/docs/models/gpt-6-astra) | 最も高い能力を持ち、code・apps・researchをまたぐ最難関の一貫作業向け | 親として要件・統合・最終判断を担う。非Astra親からは、最難関の横断的推論・設計判断に限定して委譲する |
| [GPT-6 Sol](https://developers.openai.com/api/docs/models/gpt-6-sol) | 複雑なcodingとagentic workflow向け | 複雑な実装、debug、調査、複数の契約を照合するreview。必要な判断の難しさから直接選べる |
| [GPT-6 Luna](https://developers.openai.com/api/docs/models/gpt-6-luna) | 明確で反復可能な大量処理を効率よく行うmodel | 限定調査、抽出・要約、設計済みの小実装、明確な基準を持つreview。未解決の設計判断は親へ返す |

公式はSol・Lunaのcoding、事実の信頼性、伝達の改善を説明し、Astraについて複数の評価で出力token削減と高い成果を報告している。ただし、今回取得した公式docから3モデルの同条件での定量比較は確定できない。独立評価およびこのrepositoryでの実測比較も未確認であり、上表の担当分けは公式の位置づけに基づく運用判断である。

[API価格](https://developers.openai.com/api/docs/pricing)はStandard・272K以下の入力・100万tokenあたり、Astraが入力$10／出力$50、Solが$2／$10、Lunaが$0.10／$0.50。これはtoken単価であり、Codexの実消費枠や1タスクの費用比ではない。再作業、推論token、cache、長文料金、実行時間を含む効果は[比較手順](docs/runbooks/compare-subagent-roles.md)で別途確認する。

### 設定と委譲

| 用途 | model | effort |
| --- | --- | --- |
| 通常の親／`astra` profile | `gpt-6-astra` | low、Standard速度 |
| 手動切替の`sol` profile | `gpt-6-sol` | medium、Standard速度 |
| 一般childの既定／`general_luna` | `gpt-6-luna` | high |
| `general_sol` | `gpt-6-sol` | medium |
| `general_astra` | `gpt-6-astra` | medium |

Codex公式の開始推奨はAstra Light（設定値`low`）、Sol Medium、Luna High。Astra子は難しい判断を限定して渡すため`medium`を維持する。これらは最適値を実証したものではなく、具体的な品質不足がある時だけ対応modelで利用可能なeffortを調整する。

委譲基準の正本は[Subagent Review Boundary](docs/architecture/subagent-workspace.md)。hookはその要点を再通知する。標準`default`／`worker`／`explorer`はカスタムroleとは別であり、model省略時は設定例の一般child既定値を使う。汎用roleの権限は親から継承し、read-only依頼は起動時に明示し、利用可能なruntimeの制限も適用する。`review-test-value`は引き続き`general_luna`へ委譲し、抽出契約・全recordの審査・統合基準は変えない。

`PreToolUse` hookは3モデル以外の明示的な`model`指定を拒否する。Astra親からの`general_astra`とAstraの直接指定も拒否する。許可された`spawn_agent`／`Agent`の`fork_turns`は常に`none`へ置き換え、他の引数は保持する。roleの実modelやmodel未指定時の既定値はconfigと新規sessionで確認し、hookが任意の外部role定義まで検証すると扱わない。設定例の待機timeoutの最小値と既定値は120000 msを維持する。

親をSolへ切り替える場合は、有効な`CODEX_HOME`直下へ配置した`sol.config.toml`を使う。

```powershell
codex --profile sol
codex --profile astra
```

どちらも同じ3つの汎用role・共通ルールを使う。指定modelがruntimeで利用できない場合は、許可された構成の親で可能な作業を続ける。必須の専門審査等が実行できなければ未実施として報告する。配布元の設定とlive設定・実行結果を区別する。

### model選択の定義箇所

| 対象 | model選択を持つ箇所・扱い |
| --- | --- |
| 共有config・profile・registry | `config.example.toml`、`config/*.toml`。親、一般child、3 roleの登録を揃える |
| カスタムrole | `agents/general_{astra,sol,luna}.toml`。model ID、effort、担当範囲を定義する |
| 委譲とhook | `docs/architecture/subagent-workspace.md`、`hooks/implementation-restraint.ps1`、`hooks/subagent-fork-default.ps1`、`hooks.json` |
| test価値審査 | `AGENTS.md`、`docs/guides/test-changes.md`、`skills/review-test-value/`、比較runbookはmodel IDではなく`general_luna`を参照するため、role更新を利用する |
| 指示ファイル・Skill・CI・script | `.codex/model-instructions-withmate*.md`を含め確認。上記以外に運用modelの固定指定はない |

## Skill

| Skill | 起動用途 |
| --- | --- |
| `review-test-value` | Python／TypeScript／C#のtest新規追加・意味変更・削除・移設をGit差分から抽出し、通常のread-only reviewへ渡す |
| `design-ui-information` | 通常のユーザー向けUIの新設・変更・設計見直し。内容と体験に合う情報の採否、画面構成、視覚表現、一貫性、実描画の確認 |
| `japanese-tech-writing-review` | 明示的な技術文書の推敲・論証・表記確認 |
| `natural-japanese` | 明示的な自然さの推敲・採点・文体調整 |
| `audit-codex-work-quality` | 日次・固定期間の作業監査 |
| `relaygraph` | 採用済みrepositoryの関係調査・変更・検証。新規導入は明示依頼時 |

UIの新設・変更では`AGENTS.md`から`design-ui-information`の参照を求め、同Skillの`agents/openai.yaml`は暗黙呼出しを許可する。二つの文書Skillは各Skillの明示呼出し設定を維持する。`review-test-value`は通常のSkillとして利用する。通常のREADME編集、commit、短報告へ自動の校正工程を付けない。明示された文書modeの必要工程は保つ。

Skillはruntimeが通知する実pathから読む。本repositoryの`skills/`は配布元であり、全hostの探索先が同じとは仮定しない。新規sessionの一覧で発見と重複を確認する。`withmate-glossary`はWithMateが配布する別枠のmanaged Skillであり、コピー・forkしない。

`natural-japanese`のupstreamは[coji/natural-japanese](https://github.com/coji/natural-japanese)。同期commitとlicenseは同Skillの`NOTICE`／`LICENSE`に記録する。

```powershell
pwsh ./scripts/sync-natural-japanese.ps1 -Check
pwsh ./scripts/sync-natural-japanese.ps1
```

同期scriptはlocal adaptationと明示起動policyを再現し、同Skillに未コミット変更があれば拒否する。通常の作業中に無関係な同期を行う必要はない。

### UI Skillの適用と検証

`design-ui-information`は業務・操作中心のUIに限定しない。記事、作品集、商品紹介、検索・閲覧サービス、モバイルアプリ、娯楽・制作ツール等も、内容と中心となる体験から構成する。本文や作品を補足へ追いやらず、不要な情報の羅列、無計画な縦積み、画面ごとの別設計を完成扱いしない。短さや特定の見た目を全UIへ強制しない。

表示内容・文言・見た目・操作の変更はSkill名の明示がなくても対象とし、誤字修正などの確認は影響範囲に限定する。UIへ影響しない内部処理の変更へUI設計工程を追加しない。適用条件は[`AGENTS.md`](AGENTS.md)、必須基準は[UI基準](docs/guides/ui.md)、詳細の正本は[`SKILL.md`](skills/design-ui-information/SKILL.md)、製品固有の方針・共通部品・基準画面は対象アプリやサイト側で扱う。

Metadataの`allow_implicit_invocation: true`は暗黙呼出しの許可であり、個々の依頼で適用された証拠ではない。公式の[Skill呼び出しとmetadataの説明](https://learn.chatgpt.com/docs/build-skills)も参照し、配布元の編集、実行環境への反映、実際の出力を分けて検証する。

ルール更新・配置時は、許可された環境で次を確認する。

1. `AGENTS.md`、Skill本文、metadata、READMEの適用条件と完了条件を照合する。明示呼出し限定、文字や単一surfaceの一律優先、本文の補足扱い、描画未確認を代替検査で確認済みにする旧方針が残っていないかを見る。YAMLの構文、Skill名と`$design-ui-information`の対応も確認する。
2. 新規sessionで有効な指示と、runtimeが通知するSkillの実path・内容・発見・重複を確認する。別のpathを読んでいる、旧版や重複がある、参照記録が取れない場合は区別して記録する。配布元を編集しただけで反映済みとしない。
3. Skill名や「デザインも考えて」を付けない通常のUI依頼と、UI非関連の依頼を実行する。下表の異なる体験・条件を使い、利用可能な参照記録と実際の採否・構成・表現・描画確認を照合する。適用の自己申告や参照記録だけでは合格にしない。
4. PR説明など既存の記録先へ、依頼と条件、確認できた参照、描画上の結果、修正・再確認、後追い先、未実施・未確認を簡潔に残す。発見した問題は共通の統合基準で分類し、ブロッカーの修正・再確認と非ブロッカーの引継ぎを分ける。範囲外へ無断で修正を広げない。

以下はこのルール変更の検証ケースであり、日々の小さなUI変更ごとに全件を課すものではない。提供する文章・画像・データと、変更を許可する範囲を用意して実行する。

| 依頼・条件 | 期待する結果 |
| --- | --- |
| 提供した長文と写真で記事ページを作る | 本文・写真を主内容とし、章立て・行長・文字・余白を設計する。長さだけで折りたたまず、不必要な操作誘導を足さない。 |
| 内部IDや未使用の技術情報を含むデータで、音楽・書籍・作品等のコレクションを作る | 鑑賞・探索に合う画像、まとまり、密度、移動方法を選び、全metadataを列挙しない。 |
| 指定した作品・商品と表現方針でポートフォリオや紹介ページを作る | 画像・文字・余白を目的に合わせる。管理画面の密度や単一面を強制せず、架空の実績や定型sectionで埋めない。 |
| 短い補足が大きなカードで縦積みされ、主内容が下方へ押し出されたページを整理する | 採否、まとまり、面積、順序、反復を直す。文字縮小・全折りたたみ・内部スクロールへの移し替えで済ませない。 |
| 画像と長文を含むページを幅広・狭幅で表示する | 読む順序と主従を保ち、画像比率・折り返し・余白を実描画で確認する。横幅を埋めるだけ、全部縦積みにするだけで済ませない。 |
| 共通規約と妥当な既存画面がある製品へ閲覧画面・設定画面を追加する | 構成が異なってもnavigation、文字・余白・色、用語、操作を揃え、同等部品を作り直さない。 |
| 比較・入力を中心とし、利用者が照合に使う番号もある画面を作る | 必要な比較材料・番号と情報密度を保つ。情報削減や鑑賞向けの大きな余白を一律に強制しない。 |
| 検索結果0件、未取得、取得失敗、共有機能だけの利用制限を実装する | 状態を区別し、空領域や制約の説明を過大に展開しない。主内容全体への影響と補助機能だけの制約を分ける。 |
| 誤字修正とUI非関連の内部処理変更をそれぞれ依頼する | 前者は変更箇所と影響に確認を限定し、後者にUI設計・描画工程を追加しない。 |
| 描画環境または必要な操作許可がない条件でUIを変更する | 実装、代替確認、視覚上の未確認を分ける。UI品質確認済みとせず、権限を緩和しない。 |

描画確認ではページ全体と代表的な閲覧・操作の流れを見て、参照方針や関係画面と比較する。取得したスクリーンショットを見ずに完了とせず、操作・motionの変更は静止画だけで済ませない。Test/build、DOM、accessibility検査の成功は視覚品質の代替ではない。ブラウザー専用の操作手段によるBrowser Useは、依頼の範囲内であれば追加の使用許可なしで利用できる。デスクトップ全体やネイティブアプリのGUIを操作するComputer Useには明示指示を要する。外部write等の個別承認とruntime側の権限制御は維持し、詳細は`AGENTS.md`の操作範囲に従う。

上記は検証手順であって実施記録ではない。ルールを変更したこと、sessionで適用されたこと、出力品質を確認したことを区別し、未実施は未実施として残す。利用者調査をしていない場合、使いやすさや好みが実証されたとは扱わない。専用の採点・台帳・CI基盤は追加しない。

## 配置と検証

共通ルールの利用時の配置先は、ユーザーhome直下の`~/.codex/`に固定する。このrepositoryを同ディレクトリへcheckoutする配置と、別checkoutから必要なファイルをコピー・linkする配置を区別する。共通指示を導入・更新する際は、`AGENTS.md`だけでなく`docs/guides/`と`docs/architecture/subagent-workspace.md`を`~/.codex/`配下に同じ相対配置で揃える。WithMateの接続手順も利用する配置では`docs/runbooks/withmate-character-context.md`と`docs/runbooks/withmate-repository-glossary.md`を揃える。AGENTS.mdとhookの共通文書参照は`~/.codex/...`というコード・path表記とし、`~`を実行環境のユーザーhomeへ解決する。作業対象repositoryのcwd、配布元checkout、`CODEX_HOME`による別配置へ参照先を切り替えない。symlink配置でも`~/.codex/`から各参照先へ到達できることを確認する。本README等の通常の相対リンクは配布元の文書閲覧用として残す。実環境の更新は配布元の編集と別の操作であり、無関係な設定を上書きしない。

[公式のAGENTS.md探索](https://developers.openai.com/codex/guides/agents-md/)はglobalとrepository rootからcwdまでの指示を組み合わせる。通常のMarkdownリンクはその本文の自動注入ではなく、配下すべてのAGENTS.mdを読む仕組みでもない。[Skill](https://developers.openai.com/codex/skills/)は名前・説明から選択した後に本文を読む別の仕組みである。履歴を継承しない子へは必要な条件・実path・権限を依頼に含める。

配置後は別repositoryのrootと下位ディレクトリから、読み込まれたAGENTS.mdの実path、`~/.codex/`配下の該当する詳細への到達、対象repositoryの管理先・互換性定義を確認する。`.codex`専用のIssue管理先・リリース契約を他repositoryへ適用しない。参照先が欠けた場合は配置を修復してから該当作業へ進み、同名のrepository内文書や本文のhook全注入で代用しない。

端末への適用時は既存`config.toml`へ設定例の必要sectionだけを反映する。MCP binding、認証、private path、無関係な設定を共有例へ持ち込まず、live全体を上書きしない。`agents/`とregistry例、選択profileを同じCodex homeへ配置する。

hookは有効な`CODEX_HOME`（未指定ならユーザーhomeの`.codex`）から解決する。`/hooks`でtrustと到達を確認し、inline hooks等との重複を避ける。新規session、一般child、再開・compactionで短い抑制を届ける。read-only reviewの境界は起動時の依頼で明示する。
WithMate由来のSessionFolder・Character context・MCPツールのいずれかが提供されている場合は、最初の応答前に[WithMate利用方針](docs/guides/withmate.md)を読む。Context・Recall、event-time appraisal、回答前の保存候補確認の利用契機は同文書、Memory／Characterの呼出契約はMCP toolの説明とschemaに従う。[runbook](docs/runbooks/withmate-character-context.md)はセットアップ・障害調査時に参照する。Glossaryは[導入説明](docs/runbooks/withmate-repository-glossary.md)とruntime-managed Skillを必要時に参照する。通常の許可と対象・revision・個別承認条件を維持する。生成済みruntimeやplugin状態、実config、認証はGit管理しない。

CIは決定論的な抽出器、parser、Git差分選択、adapterの回帰checkを確認する。LLM reviewは親が通常のread-onlyサブエージェントへ委譲し、モデル実行やsecretを公開CIへ追加しない。
